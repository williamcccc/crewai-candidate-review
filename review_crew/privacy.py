"""強制關閉 CrewAI 的遙測與執行軌跡上傳。

CrewAI 預設會：
- 傳送匿名使用遙測（OpenTelemetry → telemetry.crewai.com）
- 首次執行時「自動收集執行軌跡」並上傳到 CrewAI 雲端，內容包含 LLM 的輸入與輸出（也就是履歷內容）

本模組在匯入 crewai 之前強制設定環境變數，**不以 .env 的值為準**，避免使用者誤設而外流。
另外 crew.py 建立 Crew 時也會明確傳入 tracing=False，雙重保險。
"""

import os

_FORCED_ENV = {
    "CREWAI_TRACING_ENABLED": "false",  # 關閉執行軌跡（含首次自動收集）
    "CREWAI_DISABLE_TELEMETRY": "true",  # 關閉匿名遙測
    "CREWAI_DISABLE_TRACKING": "true",
    "OTEL_SDK_DISABLED": "true",
    "CREWAI_DISABLE_VERSION_CHECK": "true",  # 不對外查詢版本
}


def enforce_privacy_env() -> None:
    """覆寫（非 setdefault）隱私相關環境變數。"""
    os.environ.update(_FORCED_ENV)


enforce_privacy_env()
