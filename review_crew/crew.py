"""CrewAI 組裝：四角色評估與單一 prompt 對照組。

隱私設計：
- 對外函式只接受 `RedactionResult`（遮蔽後的結果），不接受原始字串，從型別上避免未遮蔽的文字被送出。
- 匯入 crewai 之前先強制關閉遙測與軌跡上傳（見 privacy.py）。
"""

from __future__ import annotations

# 必須在 crewai 之前匯入
from review_crew import privacy  # noqa: F401  # isort: skip

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import yaml
from crewai import LLM, Agent, Crew, Process, Task

from review_crew.redaction import RedactionResult

CONFIG_DIR = Path(__file__).resolve().parent / "config"

# 依執行順序；最後一個為綜合建議書
REVIEW_TASKS = ("tech_review", "hr_review", "manager_review", "final_report")
TASK_TITLES = {
    "tech_review": "技術面試官",
    "hr_review": "HR 招募專員",
    "manager_review": "用人主管",
    "final_report": "綜合建議書",
}


class ConfigError(RuntimeError):
    """環境設定不足（例如缺少金鑰）。訊息不含任何履歷內容。"""


@dataclass(frozen=True)
class ReviewOutput:
    sections: dict[str, str]  # task 名稱 → Markdown

    @property
    def final(self) -> str:
        return self.sections.get("final_report", "")


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"缺少環境變數 {name}，請在 .env 中設定（可參考 .env.example）。")
    return value


def build_llm() -> LLM:
    """建立 Gemini LLM。模型名稱與金鑰一律由環境變數提供。"""
    return LLM(
        model=_require_env("GEMINI_MODEL"),
        api_key=_require_env("GEMINI_API_KEY"),
        temperature=0.3,
    )


def _load_yaml(name: str) -> dict:
    with (CONFIG_DIR / name).open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_crew(llm: LLM) -> Crew:
    agents_cfg = _load_yaml("agents.yaml")
    tasks_cfg = _load_yaml("tasks.yaml")

    agents = {
        key: Agent(
            role=cfg["role"],
            goal=cfg["goal"],
            backstory=cfg["backstory"],
            llm=llm,
            allow_delegation=False,
            verbose=False,
        )
        for key, cfg in agents_cfg.items()
    }

    common_rules = tasks_cfg["common_rules"]

    tasks: dict[str, Task] = {}
    for key in REVIEW_TASKS:
        cfg = tasks_cfg[key]
        tasks[key] = Task(
            name=key,
            # 共同規則（含今天日期與公平性規則）附加在每個任務後面；{today} 等佔位符由 kickoff 代入
            description=cfg["description"].rstrip() + "\n\n" + common_rules,
            expected_output=cfg["expected_output"],
            agent=agents[cfg["agent"]],
            # 明確給 None 表示「不帶前面任務的輸出」：三份評估互相獨立，避免後面的角色被前面的意見帶偏。
            # （不指定時 CrewAI 預設會把前面所有任務的輸出當成上下文）
            context=[tasks[c] for c in cfg.get("context", [])] or None,
        )

    return Crew(
        agents=list(agents.values()),
        tasks=[tasks[k] for k in REVIEW_TASKS],
        process=Process.sequential,
        memory=False,  # 不把履歷存進長期記憶
        tracing=False,  # 雙重保險：不上傳執行軌跡
        verbose=False,
    )


def _inputs(
    resume: RedactionResult, jd: RedactionResult, today: date | None = None
) -> dict[str, str]:
    if not isinstance(resume, RedactionResult) or not isinstance(jd, RedactionResult):
        raise TypeError("只接受遮蔽後的 RedactionResult，請先呼叫 redact()。")
    # 模型不知道今天日期，不帶入的話各角色對「至今」的年資算法會不一致
    today = today or date.today()
    return {"resume": resume.text, "jd": jd.text, "today": today.isoformat()}


def run_crew_review(resume: RedactionResult, jd: RedactionResult) -> ReviewOutput:
    """四角色評估。"""
    inputs = _inputs(resume, jd)
    crew = build_crew(build_llm())
    result = crew.kickoff(inputs=inputs)
    sections = {key: out.raw for key, out in zip(REVIEW_TASKS, result.tasks_output)}
    return ReviewOutput(sections=sections)


SINGLE_PROMPT = """你是招募委員會，請一次扮演技術面試官、HR 招募專員、用人主管三個角色評估以下候選人，
最後整合成一份面試建議書。

{common_rules}
請用繁體中文 Markdown，結構如下：
## 結論
（建議：進入下一關／有條件進入下一關／保留／不建議；技術符合度分數；2–3 句理由；有條件時寫明條件）
## 必要條件對照
（JD 必要條件逐項：符合／證據不足／履歷未提及）
## 三方共識
## 三方分歧
## 面試重點（5 個問題，標明由誰提出；三個角色至少各 1 題）
## 風險與待確認事項

【JD】
{jd}

【履歷】
{resume}
"""


def build_single_prompt(inputs: dict[str, str]) -> str:
    """組出對照組的 prompt。共同規則與四角色版共用 tasks.yaml 的 common_rules。"""
    common_rules = _load_yaml("tasks.yaml")["common_rules"].format(today=inputs["today"])
    return SINGLE_PROMPT.format(common_rules=common_rules, **inputs)


def run_single_prompt(resume: RedactionResult, jd: RedactionResult) -> str:
    """對照組：同樣的輸入與輸出格式，只呼叫一次 LLM。"""
    inputs = _inputs(resume, jd)
    llm = build_llm()
    return str(llm.call(build_single_prompt(inputs)))
