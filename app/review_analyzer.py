import re
from dataclasses import dataclass

DEFAULT_BAD = [
    "불친절", "친절하지", "싸가지", "무례", "기분 나쁨", "불쾌", "짜증",
    "맛없", "별로", "최악", "위생", "더러", "머리카락", "이물질",
    "오래 걸", "늦게", "대기", "비싸", "양이 적", "실망", "다신",
]
DEFAULT_GOOD = [
    "친절", "상냥", "맛있", "추천", "깨끗", "만족", "좋았", "좋아요",
    "최고", "재방문", "빠르", "푸짐", "깔끔", "감사", "신선",
]
NEGATIVE_FRIENDLY = ["친절하지", "불친절", "안 친절", "친절은 아님", "친절하지는"]


@dataclass
class Analysis:
    bad_hits: list[str]
    good_hits: list[str]
    score: int
    level: str


def _contains(text: str, keyword: str) -> bool:
    return keyword.lower() in text.lower()


def analyze_review(text: str, bad_words=None, good_words=None) -> Analysis:
    bad_words = bad_words or DEFAULT_BAD
    good_words = good_words or DEFAULT_GOOD
    normalized = re.sub(r"\s+", " ", text or "").strip()
    bad_hits = sorted({word for word in bad_words if _contains(normalized, word)})
    good_hits = []
    for word in good_words:
        if not _contains(normalized, word):
            continue
        if word == "친절" and any(neg in normalized for neg in NEGATIVE_FRIENDLY):
            continue
        good_hits.append(word)
    good_hits = sorted(set(good_hits))
    score = max(0, len(bad_hits) * 10 - len(good_hits) * 2)
    if score >= 20:
        level = "집중관리"
    elif score >= 10:
        level = "주의"
    else:
        level = "정상"
    return Analysis(bad_hits, good_hits, score, level)
