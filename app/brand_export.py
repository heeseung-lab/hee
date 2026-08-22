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
    out = []
    seen = set()
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
        out.append({"name": name, "address": address, "place_id": pid})
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
            }
        for value in obj.values():
            _walk_place_rows(value, brand, out)
    elif isinstance(obj, list):
        for value in obj:
            _walk_place_rows(value, brand, out)


def _api_search(crawler: NaverPlaceCrawler, query: str, brand: str, coord):
    lon, lat = coord
    referer = f"https://map.naver.com/p/search/{quote(query)}"
    headers = {"Referer": referer, "Accept": "application/json, text/plain, */*"}
    endpoints = [
        ("https://map.naver.com/p/api/search/allSearch", {
            "query": query, "type": "all", "searchCoord": f"{lon};{lat}", "boundary": ""
        }),
        ("https://map.naver.com/v5/api/search", {
            "caller": "pcweb", "query": query, "type": "all", "page": 1,
            "displayCount": 100, "lang": "ko"
        }),
        ("https://map.naver.com/v5/api/search/instant-search", {
            "query": query, "type": "all", "coords": f"{lat},{lon}", "lang": "ko", "caller": "pcweb"
        }),
    ]
    found = {}
    for url, params in endpoints:
        try:
            r = crawler.session.get(url, params=params, timeout=20, headers=headers)
            if r.status_code != 200:
                continue
            try:
                data = r.json()
                _walk_place_rows(data, brand, found)
            except ValueError:
                for row in extract_map_rows(r.text, brand):
                    found[row["place_id"]] = row
            if found:
                break
        except Exception:
            continue
    return list(found.values())


def discover_stores(crawler: NaverPlaceCrawler, brand: str):
    stores = {}
    # 전국 단일 검색 + 17개 시도 검색을 병행한다. 네이버 지도 API는 검색좌표 영향이 있어 지역 좌표를 함께 준다.
    queries = [(brand, REGIONS["서울"])] + [(f"{brand} {region}", coord) for region, coord in REGIONS.items()]
    for query, coord in queries:
        for row in _api_search(crawler, query, brand, coord):
            stores[row["place_id"]] = row
        time.sleep(0.25)
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
    crawler = NaverPlaceCrawler(timeout=18, pause=0.5)
    stores = discover_stores(crawler, brand)
    if not stores:
        raise SystemExit(f"네이버 지도에서 '{brand}' 매장을 찾지 못했습니다")
    rows = []
    for i, store in enumerate(stores, 1):
        row = {**store, "reviews": [], "error": None}
        try:
            reviews, review_url = crawler._graphql_reviews(store["place_id"], "restaurant", 50)
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
