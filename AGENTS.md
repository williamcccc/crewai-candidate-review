# 專案規範（AI 程式碼代理共用）

本檔為 Claude Code、Codex 等程式碼代理於本專案工作時的共用規範。各工具專屬檔（如 `CLAUDE.md`）只以 `@AGENTS.md` 匯入，不複製內容。

## 專案定位

**CrewAI 練習專案**：在 Streamlit 介面貼上履歷與 JD，由四個 CrewAI 角色（技術面試官、HR、用人主管、彙整者）產出面試建議書，並與「單一 prompt」對照組比較。

- 這是**練習與評估用**專案，不採用正式專案的多步驟閉環流程；改動以小步、可運行為原則。
- 注意區分：`review_crew/config/agents.yaml` 是 CrewAI 的 AI 角色設定（產品的一部分）；本檔是給程式碼代理看的規範。

## 個資紅線（不可違反）

本專案會處理**真實履歷**，以下規則優先於任何功能需求：

1. **送出 LLM 前必須先遮蔽**：任何呼叫 LLM 的路徑都必須先經過 `review_crew/redaction.py` 的 `redact()`，並由使用者在介面上預覽確認後才送出。不得新增繞過遮蔽或預覽確認的路徑。
2. **不落地**：履歷原文與評估結果只存在記憶體（Streamlit session），不寫入檔案、日誌或快取。若新增「儲存」功能，只能存遮蔽後的版本，且存放於已列入 `.gitignore` 的資料夾。
3. **不外流**：不得開啟 LLM 追蹤（LangSmith 等）；CrewAI 遙測維持關閉（見 `.env.example`）；不得把履歷內容放進 log、例外訊息或 print。
4. **測試與範例只用虛構資料**：`tests/` 與 `samples/` 一律使用虛構內容（如 `王小明`、`範例科技`），測試資料於程式碼內建構，**嚴禁讀取 `private/`**。
5. **真實履歷只放 `private/`**：該資料夾已列入 `.gitignore`；代理不得讀取、列出或引用其中檔案，除非使用者明確要求。

## 設定與機密

- LLM 僅使用 Gemini；金鑰與模型名稱一律由 `.env` 讀取，不得寫死於程式碼；新增環境變數須同步更新 `.env.example`。
- `.env` 不進版控。

## 專案結構

```
app.py                      # Streamlit 介面（貼上 → 遮蔽預覽 → 確認送出 → 結果）
review_crew/
├── privacy.py              # 匯入 crewai 前強制關閉遙測與執行軌跡上傳（不可移除或改為 setdefault）
├── redaction.py            # 個資遮蔽（規則比對 + 使用者指定詞）
├── crew.py                 # CrewAI 組裝、單一 prompt 對照組、模型選擇
└── config/
    ├── agents.yaml         # 四個 AI 角色
    └── tasks.yaml          # 三份評估 → 綜合建議書
.streamlit/config.toml      # 關閉 Streamlit 使用統計、只綁 localhost
tests/                      # unittest，離線、不呼叫 LLM
samples/                    # 虛構履歷與 JD
```

## 常用指令（於專案根目錄）

```bash
.venv/Scripts/python -m unittest discover -s tests -t .
.venv/Scripts/streamlit run app.py
```

修改 `review_crew/` 底下的模組後須**重啟** Streamlit：頁面重新整理只會重跑 `app.py`，不會重新載入已匯入的模組。

## CrewAI 1.15 實作注意事項（已踩過的坑）

- **模型名稱必須在 CrewAI 的 Gemini 白名單內**：`GEMINI_MODEL` 需為 `gemini/<名稱>`，且名稱列於 `crewai/llms/constants.py` 的 `GEMINI_MODELS`，才會走原生 Gemini SDK；不在清單內會改走 LiteLLM，而本專案**未安裝 LiteLLM**，會直接報錯。換模型前先查該清單。
- **Task 的 `context` 語意**：不指定（預設 `NOT_SPECIFIED`）時會自動帶入「前面所有任務的輸出」；明確給 `None` 才是不帶。三份評估刻意設為 `None` 以保持獨立，不可移除。
- **首次執行會自動上傳執行軌跡**（含 LLM 輸入輸出）：由 `privacy.py` 的 `CREWAI_TRACING_ENABLED=false` 與 Crew 的 `tracing=False` 雙重關閉。
- Ollama 等本機模型**不在範圍內**（使用者已決定只用 Gemini），不要再加回。

## 開發原則

- 環境：Python 3.13、Windows；路徑用 `pathlib.Path`，檔案一律 UTF-8。
- 修改 `redaction.py` 時必須同步補測試，並確認 `tests/test_redaction.py` 全數通過；遮蔽規則只能變嚴，不得為了方便放寬。
- 單元測試不得呼叫真實 LLM。
- 回覆使用繁體中文。
