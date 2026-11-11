"""送出 LLM 前的個資遮蔽。

設計原則：
- 規則比對只能「盡量」抓到個資，不保證 100%，因此介面必須讓使用者預覽遮蔽結果並確認後才送出。
- 回傳結果只記錄「各類別遮蔽了幾處」，不保留原始個資值，避免原文經由日誌或畫面外流。
- 保留評估所需資訊：工作年月（例如 2019/03）、居住城市、技能、公司與學校（公司與學校可選擇遮蔽）。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

# 台灣縣市：完整地址遮蔽時保留縣市，方便評估通勤或地點條件
_CITIES = (
    "台北市|臺北市|新北市|桃園市|台中市|臺中市|台南市|臺南市|高雄市|基隆市|"
    "新竹市|新竹縣|苗栗縣|彰化縣|南投縣|雲林縣|嘉義市|嘉義縣|屏東縣|宜蘭縣|"
    "花蓮縣|台東縣|臺東縣|澎湖縣|金門縣|連江縣"
)

# 依序套用：先處理含標籤的欄位與較長的樣式，避免被較短的樣式切碎
_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("Email", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "[Email]"),
    (
        "個人連結",
        re.compile(
            r"(?:https?://)?(?:www\.)?(?:linkedin\.com|github\.com|facebook\.com|instagram\.com)/[^\s，,。)）]+",
            re.IGNORECASE,
        ),
        "[個人連結]",
    ),
    # 中文字在 Python 中屬於 \w，「身分證A123…」之間沒有 \b，所以改用前後環視判斷邊界
    ("身分證/居留證", re.compile(r"(?<![A-Za-z0-9])[A-Z][1289]\d{8}(?![0-9])"), "[身分證]"),
    (
        "手機",
        re.compile(r"(?<!\d)(?:\+?886[\s\-]?|0)9\d{2}[\s\-]?\d{3}[\s\-]?\d{3}(?!\d)"),
        "[電話]",
    ),
    (
        "市話",
        re.compile(
            r"(?<!\d)(?:\(0\d{1,2}\)|0\d{1,2})[\s\-]?\d{3,4}[\s\-]?\d{4}(?!\d)(?:\s*(?:#|分機)\s*\d{1,5})?"
        ),
        "[電話]",
    ),
    (
        "生日",
        re.compile(
            r"(?:生日|出生(?:日期)?|Birth(?:day|\s*date)?|DOB)\s*[:：]?\s*"
            r"(?:民國\s*\d{2,3}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日|\d{4}\s*[./\-年]\s*\d{1,2}\s*[./\-月]\s*\d{1,2}\s*日?)",
            re.IGNORECASE,
        ),
        "生日：[生日]",
    ),
    (
        "完整日期",
        # 僅遮蔽「年月日」完整日期；「年月」(如 2019/03) 為工作年資所需，保留
        re.compile(r"(?<!\d)(?:19|20)\d{2}[./\-]\d{1,2}[./\-]\d{1,2}(?!\d)"),
        "[日期]",
    ),
]

_ADDRESS = re.compile(
    rf"(?P<city>{_CITIES})[^\s，,。\n]{{0,20}}?(?:路|街|大道)[^\s，,。\n]{{0,20}}?號(?:之\d+)?(?:\s*\d+\s*樓)?(?:之\d+)?"
)

# 「姓名：王大明」「Name: Daming Wang」之類的標籤欄位
# 中文名取到空白為止；英文名允許中間有空白（如 Daming Wang）
_NAME_LABEL = re.compile(
    r"(?:姓\s*名|Name)\s*[:：]\s*([一-鿿·．]{2,10}|[A-Za-z][A-Za-z .'\-]{0,40}[A-Za-z])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RedactionResult:
    """遮蔽結果。`counts` 只記錄類別與次數，不含原始值。"""

    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def _split_terms(raw: str) -> list[str]:
    """把使用者輸入的「逗號或換行分隔」清單切開，去空白、去重，長的優先（避免短字串先吃掉長字串的一部分）。"""
    parts = re.split(r"[,，、\n]+", raw or "")
    terms = {p.strip() for p in parts if len(p.strip()) >= 2}
    return sorted(terms, key=len, reverse=True)


def _replace_terms(text: str, terms: list[str], placeholder: str) -> tuple[str, int]:
    count = 0
    for term in terms:
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        text, n = pattern.subn(placeholder, text)
        count += n
    return text, count


def redact(
    text: str,
    *,
    names: str = "",
    extra_terms: str = "",
    candidate_label: str = "[候選人]",
) -> RedactionResult:
    """遮蔽文字中的個資。

    Args:
        text: 原始文字（履歷或 JD）。
        names: 使用者額外指定要遮蔽的姓名（逗號或換行分隔）。標籤欄位中的姓名會自動加入。
        extra_terms: 其他要遮蔽的詞（如前公司、學校），逗號或換行分隔。
        candidate_label: 姓名替換後的代號。
    """
    counts: Counter[str] = Counter()

    # 1. 先抓「姓名：」欄位的值，併入使用者指定的姓名，再全文替換
    label_names = [m.group(1).strip() for m in _NAME_LABEL.finditer(text)]
    all_names = _split_terms("\n".join([names, *label_names]))
    text, n = _replace_terms(text, all_names, candidate_label)
    if n:
        counts["姓名"] += n

    # 2. 其他自訂詞
    text, n = _replace_terms(text, _split_terms(extra_terms), "[已遮蔽]")
    if n:
        counts["自訂詞"] += n

    # 3. 完整地址（保留縣市）
    text, n = _ADDRESS.subn(lambda m: f"{m.group('city')}[地址]", text)
    if n:
        counts["地址"] += n

    # 4. 規則樣式
    for category, pattern, placeholder in _PATTERNS:
        text, n = pattern.subn(placeholder, text)
        if n:
            counts[category] += n

    return RedactionResult(text=text, counts=dict(counts))
