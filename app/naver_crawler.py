import html
import json
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 "
    "Mobile/15E148 Safari/604.1"
)


class CrawlError(RuntimeError):
    pass


@dataclass
class PlaceMatch:
    place_id: str
    place_type: str
    source_url: str


@dataclass
class ReviewItem:
    review_id: str
    text: str
    created_at: str | None = None
    rating: float | None = None


class NaverPlaceCrawler:
    """Public-page crawler with explicit failure states.

    It never treats arbitrary page text as a review. Review bodies are accepted
    only when found inside structured JSON state and in a review-like object/path.
    """

    def __init__(self, timeout: int = 15, pause: float = 0.6):
        self.timeout = timeout
        self.pause = pause
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": MOBILE_UA,
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
        })

    def resolve_place(self, store_name: str, address: str = "") -> PlaceMatch:
        query = " ".join(x for x in [store_name, address] if x).strip()
        if not query:
            raise CrawlError("매장명/주소가 비어 있습니다")

        url = f"https://search.naver.com/search.naver?query={quote(query)}"
        r = self.session.get(url, timeout=self.timeout)
        if r.status_code != 200:
            raise CrawlError(f"네이버 검색 HTTP {r.status_code}")

        body = html.unescape(r.text)
        patterns = [
            r"m\.place\.naver\.com/(restaurant|place|cafe)/([0-9]{5,})",
            r"map\.naver\.com/(?:p/)?entry/place/([0-9]{5,})",
            r"(?:placeId|entryId)[=\"':]+([0-9]{5,})",
        ]
        for i, pattern in enumerate(patterns):
            m = re.search(pattern, body, flags=re.I)
            if not m:
                continue
            if i == 0:
                ptype, pid = m.group(1).lower(), m.group(2)
            else:
                ptype, pid = "place", m.group(1)
            return PlaceMatch(pid, ptype, url)

        raise CrawlError("네이버 검색결과에서 플레이스를 찾지 못했습니다")

    @staticmethod
    def _balanced_json(text: str, marker: str) -> dict[str, Any] | None:
        idx = text.find(marker)
        if idx < 0:
            return None
        eq = text.find("=", idx)
        start = text.find("{", eq if eq >= 0 else idx)
        if start < 0:
            return None
        depth = 0
        in_str = False
        esc = False
        quote_ch = ""
        for pos in range(start, len(text)):
            ch = text[pos]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == quote_ch:
                    in_str = False
                continue
            if ch in ('"', "'"):
                in_str = True
                quote_ch = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : pos + 1])
                    except json.JSONDecodeError:
                        return None
        return None

    def _fetch_structured_state(self, place_id: str, place_type: str) -> tuple[dict[str, Any], str]:
        candidates = []
        for ptype in [place_type, "restaurant", "place"]:
            if ptype not in candidates:
                candidates.append(ptype)

        last_error = ""
        for ptype in candidates:
            url = f"https://m.place.naver.com/{ptype}/{place_id}/review/visitor?reviewSort=recent"
            r = self.session.get(
                url,
                timeout=self.timeout,
                headers={"Referer": f"https://m.place.naver.com/{ptype}/{place_id}/home"},
            )
            if r.status_code in (403, 429):
                raise CrawlError(f"네이버 접근 제한 HTTP {r.status_code}")
            if r.status_code != 200:
                last_error = f"HTTP {r.status_code}"
                continue
            for marker in ("window.__APOLLO_STATE__", "__APOLLO_STATE__"):
                state = self._balanced_json(r.text, marker)
                if state:
                    return state, url
            last_error = "구조화 리뷰 데이터(APOLLO_STATE)를 찾지 못함"
            time.sleep(self.pause)
        raise CrawlError(last_error or "리뷰 페이지를 읽지 못했습니다")

    @staticmethod
    def _pick_text(node: dict[str, Any]) -> str | None:
        for key in ("body", "reviewBody", "content", "comment", "reviewText", "text"):
            value = node.get(key)
            if isinstance(value, str):
                value = re.sub(r"\s+", " ", html.unescape(value)).strip()
                if 2 <= len(value) <= 4000:
                    return value
        return None

    @staticmethod
    def _looks_like_review(path: str, node: dict[str, Any]) -> bool:
        hint = (path + " " + " ".join(map(str, node.keys()))).lower()
        return "review" in hint and any(
            k in node for k in ("id", "reviewId", "created", "createdAt", "author", "rating", "starRating")
        )

    def _walk_reviews(self, obj: Any, path: str = "root") -> list[ReviewItem]:
        found: list[ReviewItem] = []
        if isinstance(obj, dict):
            text = self._pick_text(obj)
            if text and self._looks_like_review(path, obj):
                rid = str(obj.get("reviewId") or obj.get("id") or "")
                if not rid:
                    rid = str(abs(hash(text)))
                created = obj.get("createdAt") or obj.get("created") or obj.get("visitDate")
                rating_raw = obj.get("rating") or obj.get("starRating")
                try:
                    rating = float(rating_raw) if rating_raw is not None else None
                except (TypeError, ValueError):
                    rating = None
                found.append(ReviewItem(rid, text, str(created) if created else None, rating))
            for key, value in obj.items():
                found.extend(self._walk_reviews(value, f"{path}.{key}"))
        elif isinstance(obj, list):
            for idx, value in enumerate(obj):
                found.extend(self._walk_reviews(value, f"{path}[{idx}]"))
        return found

    def fetch_latest_reviews(self, store_name: str, address: str = "", limit: int = 30) -> tuple[PlaceMatch, list[ReviewItem], str]:
        match = self.resolve_place(store_name, address)
        time.sleep(self.pause)
        state, review_url = self._fetch_structured_state(match.place_id, match.place_type)
        reviews = self._walk_reviews(state)
        deduped: dict[str, ReviewItem] = {}
        for item in reviews:
            deduped.setdefault(item.review_id, item)
        result = list(deduped.values())[:limit]
        if not result:
            raise CrawlError("구조화 데이터는 읽었지만 리뷰 본문 객체를 찾지 못했습니다")
        return match, result, review_url
