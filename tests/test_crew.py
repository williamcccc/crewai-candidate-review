"""CrewAI 組裝的離線測試：不呼叫任何 LLM。"""

import os
import unittest
from datetime import date

from review_crew.crew import (
    REVIEW_TASKS,
    ConfigError,
    _inputs,
    build_crew,
    build_llm,
    build_single_prompt,
    run_crew_review,
    run_single_prompt,
)
from review_crew.redaction import RedactionResult, redact

from crewai import LLM


class PrivacyEnvTests(unittest.TestCase):
    def test_tracing_and_telemetry_forced_off(self):
        self.assertEqual(os.environ["CREWAI_TRACING_ENABLED"], "false")
        self.assertEqual(os.environ["CREWAI_DISABLE_TELEMETRY"], "true")
        self.assertEqual(os.environ["OTEL_SDK_DISABLED"], "true")

    def test_privacy_overrides_user_value(self):
        from review_crew import privacy

        os.environ["CREWAI_TRACING_ENABLED"] = "true"
        privacy.enforce_privacy_env()
        self.assertEqual(os.environ["CREWAI_TRACING_ENABLED"], "false")


class InputGuardTests(unittest.TestCase):
    """未遮蔽的字串不可送出。"""

    def test_raw_string_is_rejected(self):
        with self.assertRaises(TypeError):
            _inputs("姓名：王小明", redact("JD"))  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            run_crew_review("原文", "原文")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            run_single_prompt("原文", "原文")  # type: ignore[arg-type]

    def test_redacted_result_is_accepted(self):
        inputs = _inputs(redact("姓名：王小明"), RedactionResult(text="JD"), today=date(2026, 1, 2))
        self.assertEqual(inputs, {"resume": "姓名：[候選人]", "jd": "JD", "today": "2026-01-02"})

    def test_today_defaults_to_current_date(self):
        inputs = _inputs(RedactionResult(text="R"), RedactionResult(text="JD"))
        self.assertEqual(inputs["today"], date.today().isoformat())


class BuildLlmTests(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.pop(k, None) for k in ("GEMINI_MODEL", "GEMINI_API_KEY")}

    def tearDown(self):
        for k in ("GEMINI_MODEL", "GEMINI_API_KEY"):
            os.environ.pop(k, None)
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v

    def test_missing_key_raises_config_error(self):
        os.environ["GEMINI_MODEL"] = "gemini/gemini-3.8-flash"
        with self.assertRaises(ConfigError) as ctx:
            build_llm()
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))

    def test_missing_model_raises_config_error(self):
        os.environ["GEMINI_API_KEY"] = "offline-test"
        with self.assertRaises(ConfigError) as ctx:
            build_llm()
        self.assertIn("GEMINI_MODEL", str(ctx.exception))

    def test_builds_gemini_llm(self):
        os.environ["GEMINI_MODEL"] = "gemini/gemini-3.8-flash"
        os.environ["GEMINI_API_KEY"] = "offline-test"
        self.assertEqual(type(build_llm()).__name__, "GeminiCompletion")


class BuildCrewTests(unittest.TestCase):
    def setUp(self):
        # 只建立物件，不會發出任何請求
        self.crew = build_crew(LLM(model="gemini/gemini-3.8-flash", api_key="offline-test"))

    def test_structure(self):
        self.assertEqual([t.name for t in self.crew.tasks], list(REVIEW_TASKS))
        self.assertEqual(len(self.crew.agents), 4)

    def test_tracing_and_memory_disabled(self):
        self.assertIs(self.crew.tracing, False)
        self.assertFalse(self.crew.memory)

    def test_reviews_are_independent_and_final_reads_all(self):
        by_name = {t.name: t for t in self.crew.tasks}
        for key in ("tech_review", "hr_review", "manager_review"):
            self.assertIsNone(by_name[key].context, key)
        final_ctx = [t.name for t in by_name["final_report"].context]
        self.assertEqual(final_ctx, ["tech_review", "hr_review", "manager_review"])

    def test_no_delegation(self):
        self.assertTrue(all(a.allow_delegation is False for a in self.crew.agents))

    def test_every_task_gets_common_rules(self):
        """今天日期與公平性規則要附加到每一個任務，包括綜合建議書。"""
        for task in self.crew.tasks:
            self.assertIn("{today}", task.description, task.name)
            self.assertIn("兵役", task.description, task.name)
            self.assertIn("不要列舉可能原因", task.description, task.name)
            self.assertIn("不可假設 JD 沒寫的條件", task.description, task.name)
            self.assertIn("最多只能是「有條件進入下一關」", task.description, task.name)
            self.assertIn("不可因證據不足而把建議降為「有條件」", task.description, task.name)
            self.assertIn("技術符合度評分標準", task.description, task.name)

    def test_final_report_offers_conditional_and_must_have_table(self):
        final = {t.name: t for t in self.crew.tasks}["final_report"]
        self.assertIn("有條件進入下一關", final.expected_output)
        self.assertIn("## 必要條件對照", final.expected_output)
        self.assertIn("不可加入三份評估與 JD 都沒有的說法", final.description)

    def test_manager_asks_questions_and_final_covers_all_roles(self):
        by_name = {t.name: t for t in self.crew.tasks}
        self.assertIn("追問", by_name["manager_review"].expected_output)
        final = by_name["final_report"]
        self.assertIn("至少各 1 題", final.expected_output)
        self.assertIn("不要整段照抄", final.description)


class SinglePromptTests(unittest.TestCase):
    def test_prompt_shares_rules_and_fills_placeholders(self):
        inputs = _inputs(
            RedactionResult(text="履歷內容"), RedactionResult(text="JD內容"), today=date(2026, 1, 2)
        )
        prompt = build_single_prompt(inputs)
        self.assertIn("今天日期是 2026-01-02", prompt)
        self.assertIn("兵役", prompt)
        self.assertIn("履歷內容", prompt)
        self.assertIn("JD內容", prompt)
        self.assertIn("至少各 1 題", prompt)
        self.assertIn("不可假設 JD 沒寫的條件", prompt)
        self.assertIn("技術符合度評分標準", prompt)
        self.assertIn("有條件進入下一關", prompt)
        self.assertIn("不可因證據不足而把建議降為「有條件」", prompt)
        self.assertIn("## 必要條件對照", prompt)
        self.assertNotIn("{", prompt)


if __name__ == "__main__":
    unittest.main()
