import re
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from app.db import upsert_store
from app.naver_crawler import MOBILE_UA

BASE_URL = "https://www.youngdabang.com/board/index.php"
PHONE_RE = re.compile(r"(?:0\d{1,2})[)-]?\s*\d{3,4}-\d{4}")


class StoreSyncError(RuntimeError):
    pass


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _parse_page(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    stores: list[tuple[str, str]] = []
    seen = set()

    # 공식 목록은 각 매장 블록에 매장명/주소/전화번호를 함께 노출한다.
    # 클래스명이 바뀌어도 전화번호가 포함된 가까운 블록을 기준으로 복구한다.
    for text_node in soup.find_all(string=PHONE_RE):
        block = text_node.parent
        for _ in range(7):
            if not block:
                break
            lines = [_clean(x) for x in block.get_text("\n", strip=True).splitlines() if _clean(x)]
            phone_idx = next((i for i, line in enumerate(lines) if PHONE_RE.search(line)), None)
            # 전화번호 앞에 최소 매장명과 주소 두 줄이 있어야 완전한 매장 블록이다.
            if phone_idx is not None and phone_idx >= 2 and len(_clean(block.get_text(" ", strip=True))) < 900:
                break
            block = block.parent
        if not block:
            continue
        lines = [_clean(x) for x in block.get_text("\n", strip=True).splitlines() if _clean(x)]
        phone_idx = next((i for i, line in enumerate(lines) if PHONE_RE.search(line)), None)
        if phone_idx is None or phone_idx < 2:
            continue
        before = [x for x in lines[:phone_idx] if x not in {"NEW OPEN", "전체"}]
        if len(before) < 2:
            continue
        name = before[-2]
        address = before[-1]
        if len(name) > 60 or len(address) < 5:
            continue
        key = (name, address)
        if key not in seen:
            seen.add(key)
            stores.append(key)
    return stores


def fetch_official_stores(max_pages: int = 60) -> list[tuple[str, str]]:
    session = requests.Session()
    session.headers.update({"User-Agent": MOBILE_UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    all_stores: list[tuple[str, str]] = []
    seen = set()
    empty_pages = 0

    for page in range(1, max_pages + 1):
        query = urlencode({"board": "map_01", "page": page, "sca": "all", "type": "list"})
        response = session.get(f"{BASE_URL}?{query}", timeout=20)
        if response.status_code != 200:
            raise StoreSyncError(f"공식 매장 페이지 HTTP {response.status_code} (page={page})")
        page_stores = _parse_page(response.text)
        new_on_page = 0
        for item in page_stores:
            if item in seen:
                continue
            seen.add(item)
            all_stores.append(item)
            new_on_page += 1
        if new_on_page == 0:
            empty_pages += 1
            if page > 2 and empty_pages >= 2:
                break
        else:
            empty_pages = 0

    if not all_stores:
        raise StoreSyncError("공식 매장 목록을 파싱하지 못했습니다")
    return all_stores


def sync_official_stores() -> dict:
    stores = fetch_official_stores()
    for name, address in stores:
        upsert_store(f"청년다방 {name}" if not name.startswith("청년다방") else name, address)
    return {"count": len(stores)}


if __name__ == "__main__":
    print(sync_official_stores())
