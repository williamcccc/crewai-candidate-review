"""Streamlit 介面：貼上履歷與 JD → 遮蔽預覽 → 確認送出 → 四角色評估／單一 prompt 對照。

隱私流程：
1. 原文只存在 Streamlit session（記憶體），不寫檔、不寫日誌。
2. 送出前必須先產生遮蔽預覽；使用者可在預覽中手動再刪改，並勾選確認後才能送出。
3. 原文一旦修改，舊的預覽自動作廢，必須重新產生。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# privacy 會在 crewai 之前強制關閉遙測；crew 模組內也會再匯入一次
from review_crew import privacy  # noqa: E402,F401  # isort: skip
from review_crew.crew import (  # noqa: E402
    REVIEW_TASKS,
    TASK_TITLES,
    ConfigError,
    run_crew_review,
    run_single_prompt,
)
from review_crew.redaction import RedactionResult, redact  # noqa: E402

SAMPLES = ROOT / "samples"

st.set_page_config(page_title="CrewAI 候選人評估", page_icon="🧑‍💼", layout="wide")


# ---------- 狀態 ----------
def _init_state() -> None:
    defaults = {
        "resume_raw": "",
        "jd_raw": "",
        "preview": None,  # dict: resume / jd (RedactionResult), fingerprint
        "crew_result": None,
        "single_result": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _fingerprint(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def _clear_all() -> None:
    for key in ("resume_raw", "jd_raw", "resume_edit", "jd_edit", "confirm"):
        st.session_state.pop(key, None)
    st.session_state.preview = None
    st.session_state.crew_result = None
    st.session_state.single_result = None


def _load_samples() -> None:
    st.session_state.resume_raw = (SAMPLES / "resume_sample.md").read_text(encoding="utf-8")
    st.session_state.jd_raw = (SAMPLES / "jd_sample.md").read_text(encoding="utf-8")


def _friendly_error(err: Exception) -> str:
    """錯誤訊息只顯示類型與簡短說明，避免把輸入內容帶到畫面上。"""
    if isinstance(err, ConfigError):
        return str(err)
    return f"{type(err).__name__}：{str(err)[:200]}"


_init_state()

# ---------- 側邊欄 ----------
with st.sidebar:
    st.header("設定")
    st.warning("遮蔽後的文字會送到 Google Gemini。若使用真實履歷，請確認金鑰屬於**付費方案**（免費方案資料可能被用於改進產品）。")

    st.subheader("額外遮蔽")
    extra_names = st.text_area(
        "姓名（逗號或換行分隔）",
        help="「姓名：」欄位會自動偵測；自傳或推薦人等其他地方出現的姓名請填在這裡。",
        height=70,
    )
    extra_terms = st.text_area(
        "其他詞（前公司、學校等）",
        help="預設保留公司與學校以利評估；若要一併遮蔽請填在這裡。",
        height=70,
    )

    st.divider()
    st.button("載入虛構範例", on_click=_load_samples, use_container_width=True)
    st.button("清除所有內容", on_click=_clear_all, use_container_width=True, type="secondary")
    st.caption("所有內容只存在這個瀏覽器分頁的記憶體中，關閉或重新整理即消失。")

st.title("🧑‍💼 CrewAI 候選人評估（練習專案）")

# ---------- 步驟 1：貼上原文 ----------
st.subheader("① 貼上履歷與 JD")
col_r, col_j = st.columns(2)
with col_r:
    st.text_area("履歷", key="resume_raw", height=300)
with col_j:
    st.text_area("JD", key="jd_raw", height=300)

current_fp = _fingerprint(
    st.session_state.resume_raw, st.session_state.jd_raw, extra_names, extra_terms
)
preview = st.session_state.preview
if preview and preview["fingerprint"] != current_fp:
    # 原文或遮蔽設定改了，舊預覽作廢
    st.session_state.preview = preview = None
    st.session_state.pop("confirm", None)

if st.button("產生遮蔽預覽", type="primary"):
    if not st.session_state.resume_raw.strip() or not st.session_state.jd_raw.strip():
        st.error("請先貼上履歷與 JD。")
    else:
        resume_red = redact(
            st.session_state.resume_raw, names=extra_names, extra_terms=extra_terms
        )
        jd_red = redact(st.session_state.jd_raw, names=extra_names, extra_terms=extra_terms)
        st.session_state.preview = preview = {
            "resume": resume_red,
            "jd": jd_red,
            "fingerprint": current_fp,
        }
        st.session_state.resume_edit = resume_red.text
        st.session_state.jd_edit = jd_red.text
        st.session_state.pop("confirm", None)
        st.session_state.crew_result = None
        st.session_state.single_result = None

# ---------- 步驟 2：預覽與確認 ----------
if preview:
    st.subheader("② 確認遮蔽結果")
    counts = dict(preview["resume"].counts)
    for k, v in preview["jd"].counts.items():
        counts[k] = counts.get(k, 0) + v
    if counts:
        st.write("已遮蔽：" + "、".join(f"{k} {v} 處" for k, v in counts.items()))
    else:
        st.warning("沒有偵測到任何個資。若這是真實履歷，請仔細檢查下方內容。")
    st.caption("規則比對無法保證抓到全部個資。下方內容就是**實際會送出的文字**，可以直接手動刪改。")

    col_r, col_j = st.columns(2)
    with col_r:
        st.text_area("履歷（將送出）", key="resume_edit", height=300)
    with col_j:
        st.text_area("JD（將送出）", key="jd_edit", height=300)

    confirmed = st.checkbox("我已檢查上方內容，沒有殘留可辨識個人的資訊", key="confirm")

    # ---------- 步驟 3：執行 ----------
    st.subheader("③ 執行評估")
    c1, c2, c3 = st.columns(3)
    run_crew = c1.button("四角色評估（CrewAI）", disabled=not confirmed, use_container_width=True)
    run_single = c2.button("單一 prompt 對照組", disabled=not confirmed, use_container_width=True)
    run_both = c3.button("兩者都跑", disabled=not confirmed, type="primary", use_container_width=True)

    if confirmed and (run_crew or run_single or run_both):
        # 以使用者確認過（可能手動修改過）的文字為準
        resume_final = RedactionResult(text=st.session_state.resume_edit, counts=preview["resume"].counts)
        jd_final = RedactionResult(text=st.session_state.jd_edit, counts=preview["jd"].counts)

        if run_crew or run_both:
            with st.spinner("四個角色評估中，約需 1–3 分鐘…"):
                try:
                    st.session_state.crew_result = run_crew_review(resume_final, jd_final)
                except Exception as err:  # noqa: BLE001 - 顯示友善訊息即可
                    st.error(f"四角色評估失敗：{_friendly_error(err)}")
        if run_single or run_both:
            with st.spinner("單一 prompt 產生中…"):
                try:
                    st.session_state.single_result = run_single_prompt(resume_final, jd_final)
                except Exception as err:  # noqa: BLE001
                    st.error(f"單一 prompt 失敗：{_friendly_error(err)}")

# ---------- 步驟 4：結果 ----------
crew_result = st.session_state.crew_result
single_result = st.session_state.single_result
if crew_result or single_result:
    st.subheader("④ 結果")
    tab_names = ["並排比較"]
    if crew_result:
        tab_names += [TASK_TITLES[k] for k in REVIEW_TASKS if k != "final_report"]
    tabs = st.tabs(tab_names)

    with tabs[0]:
        left, right = st.columns(2)
        with left:
            st.markdown("#### CrewAI 綜合建議書")
            st.markdown(crew_result.final if crew_result else "_尚未執行_")
        with right:
            st.markdown("#### 單一 prompt")
            st.markdown(single_result or "_尚未執行_")

    if crew_result:
        for tab, key in zip(tabs[1:], [k for k in REVIEW_TASKS if k != "final_report"]):
            with tab:
                st.markdown(crew_result.sections.get(key, ""))
