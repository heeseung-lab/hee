import argparse
import html
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from app.naver_crawler import NaverPlaceCrawler

KST = ZoneInfo("Asia/Seoul")
OUT_DIR = Path("site/data/brands")
INDEX = OUT_DIR / "index.json"
REGIONS = {
    "서울": (126.9780, 37.5665), "부산": (129.0756, 35.1796), "대구": (128.6014, 35.8714),
    "인천": (126.7052, 37.4563), "광주": (126.8526, 35.1595), "대전": (127.3845, 36.3504),
    "울산": (129.3114, 35.5384), "세종": (127.2890, 36.4800), "경기": (127.0095, 37.2749),
    "강원": (127.7298, 37.8854), "충북": (127.4917, 36.6357), "충남": (126.6728, 36.6588),
    "전북": (127.1088, 35.8203), "전남": (126.4629, 34.8161), "경북": (128.5056, 36.5760),
    "경남": (128.6919, 35.2383), "제주": (126.5312, 33.4996),
}
# 네이버 지도는 검색 좌표/지역어에 따라 결과가 달라지므로 시군구 단위 질의를 병행한다.
SEARCH_AREAS = [
    "서울 강남", "서울 서초", "서울 송파", "서울 강동", "서울 광진", "서울 성동", "서울 동대문", "서울 중랑",
    "서울 성북", "서울 강북", "서울 도봉", "서울 노원", "서울 은평", "서울 서대문", "서울 마포", "서울 양천",
    "서울 강서", "서울 구로", "서울 금천", "서울 영등포", "서울 동작", "서울 관악", "서울 용산", "서울 중구", "서울 종로",
    "경기 수원", "경기 성남", "경기 용인", "경기 고양", "경기 화성", "경기 안산", "경기 안양", "경기 부천",
    "경기 남양주", "경기 평택", "경기 시흥", "경기 김포", "경기 파주", "경기 의정부", "경기 광주", "경기 하남",
    "경기 광명", "경기 군포", "경기 오산", "경기 이천", "경기 양주", "경기 구리", "경기 포천", "경기 의왕",
    "인천 중구", "인천 남동", "인천 부평", "인천 서구", "인천 연수", "부산 해운대", "부산 부산진", "부산 동래", "부산 사하", "부산 북구",
    "대구 수성", "대구 달서", "대구 북구", "대전 서구", "대전 유성", "광주 북구", "광주 서구", "울산 남구", "울산 북구", "세종",
    "강원 춘천", "강원 원주", "강원 강릉", "강원 속초", "충북 청주", "충북 충주", "충북 제천", "충남 천안", "충남 아산", "충남 서산",
    "전북 전주", "전북 군산", "전북 익산", "전북 정읍", "전남 목포", "전남 순천", "전남 여수", "전남 광양",
    "경북 포항", "경북 구미", "경북 경주", "경북 안동", "경북 경산", "경남 창원", "경남 김해", "경남 양산", "경남 진주", "경남 거제",
    "제주 제주시", "제주 서귀포",
]


def slugify(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣_-]+", "-", text.strip()).strip("-") or "brand"


def review_date(value):
    if not value:
        return None
    s = str(value).strip()
    today = datetime.now(KST).date()
    if "오늘" in s or re.search(r"\d+시간 전|\d+분 전", s):
        return today
    if "어제" in s:
        return today - timedelta(days=1)
    m = re.search(r"(20\d{2})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})", s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=KST).date()
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})일 전", s)
    if m:
        return today - timedelta(days=int(m.group(1)))
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt.astimezone(KST).date()
    except Exception:
        return None


def recent(reviews, days):
    start = datetime.now(KST).date() - timedelta(days=days - 1)
    return [r for r in reviews if (review_date(r.get("created_at")) or datetime.min.date()) >= start]


def decode_js(s: str) -> str:
    return html.unescape(s.replace("\\u002F", "/").replace("\\u0026", "&").replace("\\/", "/"))


def extract_map_rows(text: str, brand: str):
    text = decode_js(text)
    out, seen = [], set()
    patterns = [re.compile(r'"id"\s*:\s*"?([0-9]{5,})"?'), re.compile(r'"placeId"\s*:\s*"?([0-9]{5,})"?'), re.compile(r'/place/([0-9]{5,})')]
    candidates = []
    for pattern in patterns:
        candidates.extend(pattern.finditer(text))
    candidates.sort(key=lambda m: m.start())
    for m in candidates:
        pid = m.group(1)
        if pid in seen:
            continue
        block = text[max(0, m.start() - 1500): min(len(text), m.start() + 2500)]
        if brand.lower() not in block.lower():
            continue
        name = brand
        for p in [r'"name"\s*:\s*"([^"]+)"', r'"businessName"\s*:\s*"([^"]+)"']:
            mm = re.search(p, block)
            if mm and brand.lower() in mm.group(1).lower():
                name = decode_js(mm.group(1)).strip()
                break
        address = ""
        for p in [r'"roadAddress"\s*:\s*"([^"]+)"', r'"address"\s*:\s*"([^"]+)"']:
            mm = re.search(p, block)
            if mm:
                address = decode_js(mm.group(1)).strip()
                break
        seen.add(pid)
        out.append({"name": name, "address": address, "place_id": pid, "place_type": "restaurant"})
    return out


def _walk_place_rows(obj, brand: str, out: dict):
    if isinstance(obj, dict):
        name = obj.get("name") or obj.get("businessName") or obj.get("title")
        pid = obj.get("id") or obj.get("placeId") or obj.get("businessId")
        if isinstance(name, str) and brand.lower() in html.unescape(name).lower() and str(pid or "").isdigit():
            address = obj.get("roadAddress") or obj.get("address") or obj.get("jibunAddress") or ""
            out[str(pid)] = {
                "name": re.sub(r"<[^>]+>", "", html.unescape(name)).strip(),
                "address": html.unescape(str(address)).strip(),
                "place_id": str(pid),
                "place_type": str(obj.get("businessType") or obj.get("type") or "restaurant").lower(),
            }
        for value in obj.values():
            _walk_place_rows(value, brand, out)
    elif isinstance(obj, list):
        for value in obj:
            _walk_place_rows(value, brand, out)


def _api_search(crawler: NaverPlaceCrawler, query: str, brand: str, coord):
    lon, lat = coord
    referer = f"https://map.naver.com/p/search/{quote(query)}"
    headers = {"Referer": referer, "Accept": "application/json, text/plain, */*", "Origin": "https://map.naver.com", "User-Agent": crawler.session.headers.get("User-Agent", "Mozilla/5.0")}
    found = {}
    try:
        r = crawler.session.get("https://map.naver.com/p/api/search/allSearch", params={"query": query, "type": "all", "searchCoord": f"{lon};{lat}", "boundary": ""}, timeout=20, headers=headers)
        if r.status_code == 200:
            try:
                _walk_place_rows(r.json(), brand, found)
            except ValueError:
                for row in extract_map_rows(r.text, brand):
                    found[row["place_id"]] = row
    except Exception:
        pass
    return list(found.values())


def _coord_for_area(area: str):
    prefix = area.split()[0]
    return REGIONS.get(prefix, REGIONS["서울"])


def search_one_area(crawler: NaverPlaceCrawler, brand: str, area: str):
    query = f"{brand} {area}".strip()
    found = {}
    for row in _api_search(crawler, query, brand, _coord_for_area(area)):
        found[row["place_id"]] = row
    # 지도 API 결과 유무와 상관없이 통합검색 1건을 합산한다. 기존에는 지도 결과가 있으면 폴백을 건너뛰어 누락이 컸다.
    try:
        match = crawler.resolve_place(query)
        found.setdefault(match.place_id, {"name": brand, "address": area, "place_id": match.place_id, "place_type": match.place_type or "restaurant"})
    except Exception:
        pass
    return list(found.values())


def discover_stores(crawler: NaverPlaceCrawler, brand: str):
    stores = {}
    # 광역 단위 지도검색
    for query, coord in [(brand, REGIONS["서울"])] + [(f"{brand} {region}", coord) for region, coord in REGIONS.items()]:
        for row in _api_search(crawler, query, brand, coord):
            stores[row["place_id"]] = row
        time.sleep(0.08)
    # 시군구 단위 지도검색 + 통합검색을 항상 추가해 결과 누락을 줄인다.
    for area in SEARCH_AREAS:
        for row in search_one_area(crawler, brand, area):
            stores[row["place_id"]] = row
        time.sleep(0.06)
    return sorted(stores.values(), key=lambda x: (x.get("name", ""), x.get("address", "")))


def load_index():
    if not INDEX.exists():
        return {"brands": []}
    try:
        return json.loads(INDEX.read_text(encoding="utf-8"))
    except Exception:
        return {"brands": []}


def save_index(brand, slug, payload):
    idx = load_index()
    rows = [x for x in idx.get("brands", []) if x.get("slug") != slug]
    rows.append({"name": brand, "slug": slug, "generated_at": payload["generated_at"], "stores_total": payload["stores_total"], "stores_ok": payload["stores_ok"], "stores_failed": payload["stores_failed"], "window_days": payload["window_days"]})
    rows.sort(key=lambda x: x.get("name", ""))
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps({"brands": rows}, ensure_ascii=False, indent=2), encoding="utf-8")


def main(brand: str, days: int = 7):
    brand = brand.strip()
    if len(brand) < 2:
        raise SystemExit("브랜드명을 2글자 이상 입력하세요")
    days = max(1, min(30, int(days)))
    crawler = NaverPlaceCrawler(timeout=18, pause=0.35)
    stores = discover_stores(crawler, brand)
    if not stores:
        raise SystemExit(f"네이버 검색에서 '{brand}' 매장을 찾지 못했습니다")
    rows = []
    for i, store in enumerate(stores, 1):
        row = {**store, "reviews": [], "error": None}
        try:
            reviews, review_url = crawler._graphql_reviews(store["place_id"], store.get("place_type") or "restaurant", 50)
            row["review_url"] = review_url
            row["reviews"] = recent([{"id": r.review_id, "text": r.text, "created_at": r.created_at, "rating": r.rating} for r in reviews], days)
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)
        print(f"[{i}/{len(stores)}] {row['name']} {'OK' if not row['error'] else 'FAIL'}")
    generated = datetime.now(timezone.utc).isoformat()
    failed = [r for r in rows if r.get("error")]
    payload = {"brand": brand, "generated_at": generated, "window_days": days, "window_label": f"최근 {days}일", "stores_total": len(rows), "stores_ok": len(rows) - len(failed), "stores_failed": len(failed), "stores": rows}
    slug = slugify(brand)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{slug}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    save_index(brand, slug, payload)
    print(f"saved brand={brand} stores={len(rows)} ok={payload['stores_ok']} failed={len(failed)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--brand", required=True)
    p.add_argument("--days", type=int, default=7)
    args = p.parse_args()
    main(args.brand, args.days)
