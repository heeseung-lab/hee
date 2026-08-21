import base64
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

GRAPHQL_QUERY = """
query getVisitorReviews($input: VisitorReviewsInput) {
  visitorReviews(input: $input) {
    items { id rating body visited created businessName }
    total
    showRecommendationSort
  }
}
"""


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
    """네이버 공개 플레이스에서 구조화된 방문자리뷰만 수집한다."""

    def __init__(self, timeout: int = 15, pause: float = 0.8):
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
            r"(?:pcmap\.)?place\.naver\.com/(restaurant|place|cafe)/([0-9]{5,})",
            r"map\.naver\.com/(?:p/)?entry/place/([0-9]{5,})",
            r"(?:placeId|entryId)[=\"':]+([0-9]{5,})",
        ]
        for i, pattern in enumerate(patterns):
            m = re.search(pattern, body, flags=re.I)
            if not m:
                continue
            if i <= 1:
                ptype, pid = m.group(1).lower(), m.group(2)
            else:
                ptype, pid = "restaurant", m.group(1)
            return PlaceMatch(pid, ptype, url)
        raise CrawlError("네이버 검색결과에서 플레이스를 찾지 못했습니다")

    @staticmethod
    def _wtm_token(place_id: str, place_type: str) -> str:
        raw = json.dumps({"arg": place_id, "type": place_type, "source": "place"}, ensure_ascii=False, separators=(",", ":"))
        return base64.b64encode(raw.encode("utf-8")).decode("ascii")

    def _graphql_reviews(self, place_id: str, place_type: str, limit: int) -> tuple[list[ReviewItem], str]:
        types = []
        for candidate in (place_type, "restaurant", "place"):
            if candidate not in types:
                types.append(candidate)
        endpoints = ["https://api.place.naver.com/graphql", "https://pcmap-api.place.naver.com/place/graphql"]
        errors = []
        for business_type in types:
            referer = f"https://m.place.naver.com/{business_type}/{place_id}/review/visitor"
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://m.place.naver.com",
                "Referer": referer,
                "x-wtm-graphql": self._wtm_token(place_id, business_type),
            }
            page = 1
            items: list[ReviewItem] = []
            while len(items) < limit and page <= 3:
                page_size = min(50, max(1, limit - len(items)))
                payload = [{
                    "operationName": "getVisitorReviews",
                    "variables": {"input": {
                        "businessId": place_id,
                        "businessType": business_type,
                        "page": page,
                        "size": page_size,
                        "isPhotoUsed": False,
                        "includeContent": True,
                        "getAuthorInfo": True,
                        "item": "0",
                    }},
                    "query": GRAPHQL_QUERY,
                }]
                page_items = None
                visitor_total = None
                for endpoint in endpoints:
                    for attempt in range(3):
                        try:
                            r = self.session.post(endpoint, headers=headers, json=payload, timeout=self.timeout)
                        except requests.RequestException as exc:
                            errors.append(f"{endpoint} {type(exc).__name__}")
                            break
                        if r.status_code in (403, 429) or r.status_code >= 500:
                            errors.append(f"{endpoint} HTTP {r.status_code}")
                            if attempt < 2:
                                time.sleep((attempt + 1) * 1.5)
                                continue
                            break
                        if r.status_code != 200:
                            errors.append(f"{endpoint} HTTP {r.status_code}")
                            break
                        try:
                            data = r.json()
                            root = data[0] if isinstance(data, list) else data
                            visitor = (root.get("data") or {}).get("visitorReviews") or {}
                            visitor_total = visitor.get("total")
                            raw_items = visitor.get("items") or []
                            page_items = []
                            for raw in raw_items:
                                body = re.sub(r"\s+", " ", html.unescape(str(raw.get("body") or ""))).strip()
                                if not body:
                                    continue
                                rating = raw.get("rating")
                                try:
                                    rating = float(rating) if rating is not None else None
                                except (TypeError, ValueError):
                                    rating = None
                                page_items.append(ReviewItem(
                                    str(raw.get("id") or abs(hash((body, raw.get("created"))))),
                                    body,
                                    str(raw.get("created") or raw.get("visited") or "") or None,
                                    rating,
                                ))
                            if page_items or visitor_total == 0:
                                break
                            gql_errors = root.get("errors") or []
                            if gql_errors:
                                errors.append("GraphQL: " + str(gql_errors[0].get("message", "unknown")))
                        except (ValueError, KeyError, TypeError) as exc:
                            errors.append(f"GraphQL 응답 파싱 {type(exc).__name__}")
                            break
                    if page_items is not None:
                        break
                if page_items is None:
                    break
                if not page_items:
                    if page == 1 and visitor_total == 0:
                        return [], referer
                    break
                items.extend(page_items)
                if len(items) >= limit or len(page_items) < page_size:
                    break
                page += 1
                time.sleep(self.pause)
            if items:
                deduped = {x.review_id: x for x in items}
                return list(deduped.values())[:limit], referer
        raise CrawlError("방문자리뷰 GraphQL 수집 실패: " + (" | ".join(errors[-4:]) if errors else "응답 없음"))

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
                        return json.loads(text[start:pos + 1])
                    except json.JSONDecodeError:
                        return None
        return None

    def _apollo_reviews(self, place_id: str, place_type: str, limit: int) -> tuple[list[ReviewItem], str]:
        last_error = ""
        for ptype in dict.fromkeys([place_type, "restaurant", "place"]):
            url = f"https://m.place.naver.com/{ptype}/{place_id}/review/visitor?reviewSort=recent"
            r = self.session.get(url, timeout=self.timeout, headers={"Referer": f"https://m.place.naver.com/{ptype}/{place_id}/home"})
            if r.status_code in (403, 429):
                last_error = f"APOLLO 접근 제한 HTTP {r.status_code}"
                continue
            if r.status_code != 200:
                last_error = f"APOLLO HTTP {r.status_code}"
                continue
            state = self._balanced_json(r.text, "window.__APOLLO_STATE__") or self._balanced_json(r.text, "__APOLLO_STATE__")
            if not state:
                last_error = "APOLLO_STATE 없음"
                continue
            reviews = self._walk_reviews(state)
            deduped = {x.review_id: x for x in reviews}
            if deduped:
                return list(deduped.values())[:limit], url
            last_error = "APOLLO_STATE에 리뷰 본문 객체 없음"
        raise CrawlError(last_error or "APOLLO 리뷰 폴백 실패")

    @staticmethod
    def _pick_text(node: dict[str, Any]) -> str | None:
        for key in ("body", "reviewBody", "content", "comment", "reviewText"):
            value = node.get(key)
            if isinstance(value, str):
                value = re.sub(r"\s+", " ", html.unescape(value)).strip()
                if 2 <= len(value) <= 4000:
                    return value
        return None

    @staticmethod
    def _looks_like_review(path: str, node: dict[str, Any]) -> bool:
        hint = (path + " " + " ".join(map(str, node.keys()))).lower()
        return "review" in hint and any(k in node for k in ("id", "reviewId", "created", "createdAt", "author", "rating"))

    def _walk_reviews(self, obj: Any, path: str = "root") -> list[ReviewItem]:
        found: list[ReviewItem] = []
        if isinstance(obj, dict):
            text = self._pick_text(obj)
            if text and self._looks_like_review(path, obj):
                rid = str(obj.get("reviewId") or obj.get("id") or abs(hash(text)))
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
        gql_error = None
        try:
            reviews, url = self._graphql_reviews(match.place_id, match.place_type, limit)
            if reviews:
                return match, reviews, url
            raise CrawlError("방문자리뷰가 0건이거나 본문 공개 리뷰가 없습니다")
        except CrawlError as exc:
            gql_error = str(exc)
        try:
            reviews, url = self._apollo_reviews(match.place_id, match.place_type, limit)
            if reviews:
                return match, reviews, url
        except CrawlError as fallback:
            raise CrawlError(f"GraphQL 실패: {gql_error}; 구조화 폴백 실패: {fallback}") from fallback
        raise CrawlError(gql_error or "리뷰를 수집하지 못했습니다")
