# CrewAI 候選人評估（練習專案）

貼上履歷與 JD，由四個 CrewAI 角色產出面試建議書，並與「單一 prompt」對照組並排比較，用來評估多代理協作是否真的帶來更多元、更有用的觀點。

```
履歷 + JD ──► 個資遮蔽 ──► 預覽確認 ──┬─► 技術面試官 ─┐
                                    ├─► HR 招募專員 ─┼─► 招募委員會主席 ─► 綜合建議書
                                    ├─► 用人主管 ───┘
                                    └─► 單一 prompt（對照組）
```

三位評估者**互相獨立**（看不到彼此意見），最後由主席整合並列出共識與分歧。

## 快速開始

```bash
# 1. 建立虛擬環境並安裝（Windows）
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt

# 2. 設定金鑰
cp .env.example .env        # 然後編輯 .env，填入 GEMINI_API_KEY

# 3. 啟動
.venv/Scripts/streamlit run app.py
```

瀏覽器開啟 http://localhost:8501，按側邊欄「載入虛構範例」即可試跑。

> **模型名稱**：`GEMINI_MODEL` 預設為 `gemini/gemini-3.8-flash`。換模型前請確認兩件事：
> 1. 名稱列在 CrewAI 的 Gemini 白名單（`crewai/llms/constants.py` 的 `GEMINI_MODELS`）內，否則會改走未安裝的 LiteLLM 而報錯。
> 2. 該模型仍開放給你的帳號使用。舊模型下架後，API 會回傳 404（例如 `gemini-2.5-flash` 已不開放給新帳號）。
>
> 修改 `review_crew/` 底下的程式或設定後，需要**重啟** Streamlit 才會生效。

## 使用流程

1. **貼上**履歷與 JD。
2. **產生遮蔽預覽**：自動遮蔽姓名、電話、Email、身分證、生日、完整地址、個人連結；可在側邊欄額外指定要遮蔽的姓名、公司、學校。
3. **確認**：預覽區就是實際會送出的文字，可以直接手動刪改；勾選確認後才能執行。
4. **執行**：四角色評估、單一 prompt，或兩者都跑，結果並排比較。

## 使用真實履歷前請先讀

| 防護 | 說明 |
| :--- | :--- |
| 送出前遮蔽 | 規則比對**無法保證 100%**，一定要看過預覽再確認；自傳、推薦人段落的姓名請在側邊欄補上 |
| Gemini 資料政策 | 遮蔽後的文字會送到 Google；Gemini API **免費方案**的資料可能被用於改進 Google 產品，真實履歷請用付費方案金鑰 |
| 關閉 CrewAI 遙測與軌跡 | CrewAI 預設首次執行會上傳執行軌跡（含 LLM 輸入輸出）；本專案在程式中強制關閉（`review_crew/privacy.py`），並對 Crew 設定 `tracing=False` |
| 關閉 Streamlit 統計 | `.streamlit/config.toml` 關閉使用統計，且只綁定 localhost |
| 不落地 | 原文與結果只存在瀏覽器分頁的記憶體，不寫檔、不寫日誌；重新整理即消失 |
| 不進版控 | 真實履歷檔案請放 `private/`（已列入 `.gitignore`） |

另外，依個資法，履歷是為「招募」目的蒐集；拿來測試第三方 AI 工具可能超出原蒐集目的。建議只用少量、已遮蔽的履歷測試，公司履歷請先確認公司規範。

## 調整角色與規則

直接改 YAML 即可，不需動程式碼：

| 檔案 | 內容 |
| :--- | :--- |
| [agents.yaml](review_crew/config/agents.yaml) | 四個角色的 `role`、`goal`、`backstory` |
| [tasks.yaml](review_crew/config/tasks.yaml) | 各任務的說明與輸出格式，以及 `common_rules`（共同規則） |

- `common_rules` 會自動附加到每個任務後面，**單一 prompt 對照組也使用同一份**，兩種模式的規則保持一致，比較才公平。
- 可用的佔位符：`{resume}`、`{jd}`、`{today}`（執行當天日期，讓模型能正確計算「至今」的年資）。

### 目前的評估規則（摘要）

- 每個判斷都要引用履歷原文；沒提到就寫「履歷未提及」。
- 不得推論年齡、性別、婚姻等與工作無關的條件，也不得透過兵役、育兒等間接線索推測；空窗期只能以開放式問題確認。
- 團隊現況只能依 JD 描述，不可假設 JD 沒寫的資源；候選人的期待與團隊現況不符時要指出。
- **技術符合度（1–5 分）**依「必要條件有沒有工作經歷佐證」給分。
- **結論**分為：進入下一關／有條件進入下一關／保留／不建議。
  - 必要條件「履歷未提及」→ 最多只能給「有條件」，並寫明條件。
  - 必要條件「證據不足」（例如只列在技能清單）→ 不影響結論，只列為面試追問項目。

## 測試

```bash
.venv/Scripts/python -m unittest discover -s tests -t .
```

測試完全離線，不呼叫 LLM；只使用虛構資料。

## 評估建議

同一份履歷與 JD 各跑「四角色」與「單一 prompt」，比較：

- 三方分歧是否真的有意義（還是只是換句話說）
- 面試問題是否更具體、更貼近履歷內容
- 花費時間與 Token（四角色呼叫 LLM 4 次，單一 prompt 1 次）

`samples/` 有兩份虛構履歷可以搭配 `jd_sample.md` 使用：

| 檔案 | 候選人 | 用途 |
| :--- | :--- | :--- |
| `resume_sample.md` | 7 年資深後端，LLM 只有個人專案 | 條件明顯符合；側邊欄「載入虛構範例」載入的就是這份 |
| `resume_borderline.md` | 轉職約 3 年，有 RAG 評測實績但缺 Redis、CI/CD | 條件邊緣；需手動貼上 |

## 評估結果紀錄（2026-11，gemini-3.8-flash）

| | 資深後端（sample） | 條件邊緣（borderline） |
| :--- | :--- | :--- |
| 結論（兩種模式相同） | 進入下一關 | 有條件進入下一關 |
| 技術符合度 | 3 分（Docker 證據不足） | 2 分（缺 Redis、CI/CD） |
| 耗時：單一 prompt／四角色 | 約 45 秒／150 秒 | 約 45 秒／130 秒 |

觀察：

- **兩種模式的結論在兩份範例中都相同**，多角色沒有改變判斷。
- **多角色的價值在細節**：三位評估者各自獨立判斷，分歧有實際依據；HR 會看任期趨勢、技術官會逐項核對證據，建議書比較容易核對。單一 prompt 的「三方分歧」比較像是替三個角色分配不同的關注點。
- **品質改善主要來自規則，而不是角色數量**。調整前，兩種模式都犯過相同的錯誤：年資算錯、假設團隊有資深成員、強弱候選人分數相同，加上上述規則後兩邊一起改善。
- 代價：四角色耗時約 3 倍。

結論可以是「CrewAI 版明顯較好」，也可以是「單一 prompt 就夠了」——兩者都是有價值的評估結果。

## 專案結構

```
app.py                      # Streamlit 介面（貼上 → 遮蔽預覽 → 確認送出 → 結果）
review_crew/
├── privacy.py              # 匯入 crewai 前強制關閉遙測與軌跡上傳
├── redaction.py            # 個資遮蔽
├── crew.py                 # ★ CrewAI 組裝、執行、單一 prompt 對照組
└── config/
    ├── agents.yaml         # ★ 四個角色
    └── tasks.yaml          # ★ 四個任務與共同規則
.streamlit/config.toml      # 關閉 Streamlit 使用統計、只綁 localhost
.env.example                # 環境變數範本（複製為 .env）
tests/                      # 離線單元測試
samples/                    # 虛構履歷與 JD
AGENTS.md                   # 給程式碼代理（Claude Code 等）的專案規範
```

標 ★ 的是 CrewAI 的核心：YAML 定義角色與任務，`crew.py` 把它們組成 `Agent`、`Task`、`Crew` 後呼叫 `kickoff()`。其餘檔案屬於本專案的介面、隱私防護與測試。

### CrewAI 實作重點

- `kickoff(inputs=...)` 會把值代入 YAML 中的 `{resume}`、`{jd}`、`{today}`。
- `Task.context` 不指定時，會自動帶入「前面所有任務的輸出」；明確給 `None` 才是不帶。三份評估刻意設為 `None` 以保持獨立，綜合建議書再用 `context` 讀取三份結果。
- 使用 `Process.sequential`，任務依清單順序執行。
