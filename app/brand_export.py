import argparse
import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from app.naver_crawler import NaverPlaceCrawler

KST = ZoneInfo("Asia/Seoul")
OUT_DIR = Path("site/data/brands")
INDEX = OUT_DIR / "index.json"
NAVER_MAP_AREA = "네이버플레이스 검색"
REGION_COORDS = [
    ("서울", 126.9780, 37.5665), ("부산", 129.0756, 35.1796), ("대구", 128.6014, 35.8714),
    ("인천", 126.7052, 37.4563), ("광주", 126.8526, 35.1595), ("대전", 127.3845, 36.3504),
    ("울산", 129.3114, 35.5384), ("세종", 127.2890, 36.4800), ("경기", 127.0095, 37.2749),
    ("강원", 127.7298, 37.8854), ("충북", 127.4917, 36.6357), ("충남", 126.6728, 36.6588),
    ("전북", 127.1088, 35.8203), ("전남", 126.4629, 34.8161), ("경북", 128.5056, 36.5760),
    ("경남", 128.6919, 35.2383), ("제주", 126.5312, 33.4996),
]
SEARCH_AREAS = [NAVER_MAP_AREA] + [name for name, _, _ in REGION_COORDS]


def slugify(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣_-]+", "-", text.strip()).strip("-") or "brand"


def _text_quality(value: str) -> int:
    hangul = sum("\uac00" <= ch <= "\ud7a3" for ch in value)
    mojibake = sum(ch in "ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõö÷øùúûüýþÿ�" for ch in value)
    return hangul * 3 - mojibake * 2


def repair_mojibake(value: str) -> str:
    text = str(value or "")
    best = text
    for encoding in ("latin1", "cp1252"):
        try:
            candidate = text.encode(encoding).decode("utf-8")
        except UnicodeError:
            continue
        if _text_quality(candidate) > _text_quality(best):
            best = candidate
    return best


def decode_js(value: str) -> str:
    decoded = html.unescape(str(value or "").replace("\\u002F", "/").replace("\\u0026", "&").replace("\\/", "/"))
    return repair_mojibake(decoded)


def clean_place_name(value: str) -> str:
    text = decode_js(value)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_address(value: str) -> str:
    return clean_place_name(value)


def normalize_brand(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\uac00-\ud7a3]+", "", clean_place_name(value)).lower()


def brand_matches(name: str, brand: str) -> bool:
    name_key = normalize_brand(name)
    brand_key = normalize_brand(brand)
    if not name_key or not brand_key:
        return False
    if brand_key in name_key:
        return True
    variants = {brand_key}
    variants.add(brand_key.replace("솥", "솔"))
    variants.add(brand_key.replace("솔", "솥"))
    return any(candidate and candidate in name_key for candidate in variants)


def better_place_name(current: str | None, candidate: str | None, brand: str) -> str:
    current = clean_place_name(current or brand)
    candidate = clean_place_name(candidate or "")
    if candidate and brand_matches(candidate, brand) and (current == brand or len(candidate) > len(current)):
        return candidate
    return current


def better_place_address(current: str | None, candidate: str | None) -> str:
    current = clean_address(current or "")
    candidate = clean_address(candidate or "")
    if not candidate:
        return current
    if not current or _text_quality(candidate) > _text_quality(current):
        return candidate
    if len(candidate) > len(current) and re.search(r"\d", candidate):
        return candidate
    return current


def merge_store(stores: dict, store: dict, brand: str):
    place_id = str(store.get("place_id") or "").strip()
    if not place_id:
        return
    row = {
        "name": clean_place_name(store.get("name") or brand),
        "address": clean_address(store.get("address") or ""),
        "place_id": place_id,
        "place_type": str(store.get("place_type") or "restaurant").lower(),
        "source": store.get("source") or "naver-place",
    }
    current = stores.get(place_id)
    if not current:
        stores[place_id] = row
        return
    current["name"] = better_place_name(current.get("name"), row.get("name"), brand)
    current["address"] = better_place_address(current.get("address"), row.get("address"))
    current["place_type"] = current.get("place_type") or row.get("place_type") or "restaurant"


def extract_map_rows(text: str, brand: str):
    text = decode_js(text)
    rows, seen = [], set()
    patterns = [
        re.compile(r'"(?:id|placeId|businessId)"\s*:\s*"?([0-9]{5,})"?'),
        re.compile(r'/place/([0-9]{5,})'),
        re.compile(r'entry/place/([0-9]{5,})'),
        re.compile(r'(?:placeId|entryId)[="\':]+([0-9]{5,})'),
    ]
    matches = []
    for pattern in patterns:
        matches.extend(pattern.finditer(text))
    matches.sort(key=lambda match: match.start())
    for match in matches:
        place_id = match.group(1)
        if place_id in seen:
            continue
        block = text[max(0, match.start() - 1800): min(len(text), match.start() + 2800)]
        if not brand_matches(block, brand):
            continue
        names = []
        for pattern in [
            r'"(?:name|businessName|title|displayName)"\s*:\s*"([^"]+)"',
            r'"name"\s*:\s*\{[^{}]*"text"\s*:\s*"([^"]+)"',
            r'>\s*([^<>"\']*' + re.escape(brand) + r'[^<>"\']*)\s*<',
        ]:
            for item in re.finditer(pattern, block):
                name = clean_place_name(item.group(1))
                if brand_matches(name, brand) and name not in names:
                    names.append(name)
        names.sort(key=lambda value: (value == brand, -len(value)))
        address = ""
        for pattern in [r'"(?:roadAddress|address|jibunAddress)"\s*:\s*"([^"]+)"']:
            item = re.search(pattern, block)
            if item:
                address = clean_address(item.group(1))
                break
        seen.add(place_id)
        rows.append({"name": names[0] if names else brand, "address": address, "place_id": place_id, "place_type": "restaurant", "source": "map-page"})
    return rows


def _balanced_json_after(text: str, marker: str):
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
        if ch in ("'", '"'):
            in_str = True
            quote_ch = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:pos + 1])
                except ValueError:
                    return None
    return None


def _apollo_place_rows(text: str, brand: str):
    state = _balanced_json_after(text, "__APOLLO_STATE__")
    if not isinstance(state, dict):
        return []
    rows = []
    for obj in state.values():
        if not isinstance(obj, dict):
            continue
        place_id = str(obj.get("id") or "")
        name = clean_place_name(obj.get("name") or obj.get("normalizedName") or "")
        if not place_id.isdigit() or not brand_matches(name, brand):
            continue
        address = obj.get("fullAddress") or obj.get("roadAddress") or obj.get("commonAddress") or obj.get("address") or ""
        rows.append({
            "name": name,
            "address": clean_address(address),
            "place_id": place_id,
            "place_type": "restaurant",
            "source": "pcmap-apollo",
        })
    return rows


def _walk_place_rows(obj, brand: str, out: dict):
    if isinstance(obj, dict):
        raw_name = obj.get("name") or obj.get("businessName") or obj.get("title") or obj.get("displayName")
        name = raw_name.get("text") if isinstance(raw_name, dict) else raw_name
        place_id = obj.get("id") or obj.get("placeId") or obj.get("businessId") or obj.get("entryId")
        if isinstance(name, str) and brand_matches(name, brand) and str(place_id or "").isdigit():
            address = obj.get("roadAddress") or obj.get("address") or obj.get("jibunAddress") or ""
            out[str(place_id)] = {
                "name": clean_place_name(name),
                "address": clean_address(address),
                "place_id": str(place_id),
                "place_type": str(obj.get("businessType") or obj.get("type") or "restaurant").lower(),
                "source": "map-api",
            }
        for value in obj.values():
            _walk_place_rows(value, brand, out)
    elif isinstance(obj, list):
        for value in obj:
            _walk_place_rows(value, brand, out)


def _api_search(crawler: NaverPlaceCrawler, brand: str, coord):
    lon, lat = coord
    headers = {
        "Referer": f"https://map.naver.com/p/search/{quote(brand)}",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://map.naver.com",
        "User-Agent": crawler.session.headers.get("User-Agent", "Mozilla/5.0"),
    }
    found = {}
    try:
        response = crawler.session.get(
            "https://map.naver.com/p/api/search/allSearch",
            params={"query": brand, "type": "all", "searchCoord": f"{lon};{lat}", "boundary": ""},
            timeout=crawler.timeout,
            headers=headers,
        )
    except Exception:
        return []
    if response.status_code != 200:
        return []
    try:
        _walk_place_rows(response.json(), brand, found)
    except ValueError:
        response.encoding = "utf-8"
        for row in extract_map_rows(response.text, brand):
            found[row["place_id"]] = row
    return list(found.values())


def _pcmap_list_search(crawler: NaverPlaceCrawler, brand: str, coord):
    lon, lat = coord
    found = {}
    headers = {
        "Referer": f"https://map.naver.com/p/search/{quote(brand)}",
        "Accept": "text/html,application/json,application/xhtml+xml,*/*",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
        "User-Agent": crawler.session.headers.get("User-Agent", "Mozilla/5.0"),
    }
    for start in (1, 71):
        try:
            response = crawler.session.get(
                "https://pcmap.place.naver.com/place/list",
                params={
                    "query": brand,
                    "x": str(lon),
                    "y": str(lat),
                    "display": "70",
                    "start": str(start),
                    "adult": "false",
                    "spq": "false",
                    "deviceType": "pcmap",
                },
                timeout=crawler.timeout,
                headers=headers,
            )
        except Exception:
            continue
        if response.status_code != 200:
            continue
        response.encoding = "utf-8"
        text = decode_js(response.text)
        rows = _apollo_place_rows(text, brand)
        if not rows:
            rows = extract_map_rows(text, brand)
        before = len(found)
        for row in rows:
            found[row["place_id"]] = row
        if len(found) == before or len(rows) < 60:
            break
        time.sleep(0.08)
    return list(found.values())


def _map_page_search(crawler: NaverPlaceCrawler, brand: str):
    url = f"https://map.naver.com/p/search/{quote(brand)}"
    headers = {"Referer": "https://map.naver.com/", "User-Agent": crawler.session.headers.get("User-Agent", "Mozilla/5.0")}
    try:
        response = crawler.session.get(url, timeout=crawler.timeout, headers=headers)
    except Exception:
        return []
    if response.status_code != 200:
        return []
    response.encoding = "utf-8"
    return extract_map_rows(response.text, brand)


def search_one_area(crawler: NaverPlaceCrawler, brand: str, area: str):
    found = {}
    if area == NAVER_MAP_AREA:
        rows = _map_page_search(crawler, brand)
        coord = (126.9780, 37.5665)
    else:
        rows = []
        coord = next(((lon, lat) for name, lon, lat in REGION_COORDS if name == area), (126.9780, 37.5665))
    for row in rows + _pcmap_list_search(crawler, brand, coord) + _api_search(crawler, brand, coord):
        found[row["place_id"]] = row
    return list(found.values())


def search_brand_places(brand: str, concurrency: int = 4):
    brand = brand.strip()
    if len(brand) < 2:
        raise ValueError("브랜드명을 2글자 이상 입력하세요")
    stores = {}
    workers = max(1, min(6, int(concurrency or 4), len(SEARCH_AREAS)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(search_one_area, NaverPlaceCrawler(timeout=18, pause=0.05), brand, area): area for area in SEARCH_AREAS}
        for future in as_completed(futures):
            try:
                for row in future.result():
                    merge_store(stores, row, brand)
            except Exception:
                continue
    return sorted(stores.values(), key=lambda row: (row.get("name", ""), row.get("address", "")))


def discover_stores(crawler: NaverPlaceCrawler, brand: str):
    stores = {}
    for area in SEARCH_AREAS:
        for row in search_one_area(crawler, brand, area):
            merge_store(stores, row, brand)
        time.sleep(0.06)
    return sorted(stores.values(), key=lambda row: (row.get("name", ""), row.get("address", "")))


def review_date(value):
    if not value:
        return None
    text = str(value).strip()
    today = datetime.now(KST).date()
    if "오늘" in text or re.search(r"\d+시간 전|\d+분 전", text):
        return today
    if "어제" in text:
        return today - timedelta(days=1)
    match = re.search(r"(20\d{2})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})", text)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=KST).date()
        except ValueError:
            return None
    return None


def recent(reviews, days):
    start = datetime.now(KST).date() - timedelta(days=max(1, days) - 1)
    return [row for row in reviews if (review_date(row.get("created_at")) or datetime.min.date()) >= start]


def load_index():
    if not INDEX.exists():
        return {"brands": []}
    try:
        return json.loads(INDEX.read_text(encoding="utf-8"))
    except Exception:
        return {"brands": []}


def save_index(brand, slug, payload):
    rows = [row for row in load_index().get("brands", []) if row.get("slug") != slug]
    rows.append({"name": brand, "slug": slug, "generated_at": payload["generated_at"], "stores_total": payload["stores_total"]})
    rows.sort(key=lambda row: row.get("name", ""))
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps({"brands": rows}, ensure_ascii=False, indent=2), encoding="utf-8")


def main(brand: str, days: int = 7):
    stores = search_brand_places(brand)
    payload = {"brand": brand, "generated_at": datetime.now(timezone.utc).isoformat(), "stores_total": len(stores), "stores": stores}
    slug = slugify(brand)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{slug}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    save_index(brand, slug, payload)
    print(f"saved brand={brand} stores={len(stores)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand", required=True)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    main(args.brand, args.days)
