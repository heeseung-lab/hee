import re
from dataclasses import dataclass

DEFAULT_BAD = [
    "불친절", "맛없", "별로", "최악", "위생", "더럽", "머리카락",
    "늦", "오래 걸", "짜증", "불쾌", "실망", "비싸", "재방문 안"
]
DEFAULT_GOOD = [
    "친절", "맛있", "추천", "깨끗", "만족", "좋아요", "재방문", "최고"
]

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

    bad_hits = sorted({w for w in bad_words if _contains(normalized, w)})
    good_hits = []
    for word in good_words:
        if not _contains(normalized, word):
            continue
        # '불친절'을 '친절' 긍정으로 중복 판정하지 않는다.
        if word == "친절" and ("불친절" in normalized or "친절하지" in normalized):
            continue
        good_hits.append(word)
    good_hits = sorted(set(good_hits))

    score = max(0, len(bad_hits) * 10 - len(good_hits) * 2)
    level = "집중관리" if score >= 20 else "주의" if score >= 10 else "정상"
    return Analysis(bad_hits, good_hits, score, level)
