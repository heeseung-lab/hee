import json
from datetime import datetime, timezone
from pathlib import Path

from app.naver_crawler import CrawlError, NaverPlaceCrawler
from app.store_sync import StoreSyncError, _parse_page

OUT = Path("site/data/reviews.json")
STORES_URL = "https://youngdabang.com/board/index.php?board=map_01"


def fetch_store_list(session):
    r = session.get(STORES_URL, timeout=20)
    r.raise_for_status()
    stores = _parse_page(r.text)
    if not stores:
        raise StoreSyncError("공식 청년다방 매장목록을 읽지 못했습니다")
    return stores


def main():
    crawler = NaverPlaceCrawler(timeout=15, pause=0.7)
    stores = fetch_store_list(crawler.session)
    rows = []
    failed = []

    for name, address in stores:
        full_name = name if "청년다방" in name else f"청년다방 {name}"
        try:
            match, reviews, review_url = crawler.fetch_latest_reviews(full_name, address, limit=20)
            rows.append({
                "name": name,
                "address": address,
                "place_id": match.place_id,
                "review_url": review_url,
                "reviews": [
                    {
                        "id": r.review_id,
                        "text": r.text,
                        "created_at": r.created_at,
                        "rating": r.rating,
                    }
                    for r in reviews
                ],
            })
        except Exception as exc:
            failed.append({"name": name, "address": address, "error": f"{type(exc).__name__}: {exc}"})

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stores_total": len(stores),
        "stores_ok": len(rows),
        "stores_failed": len(failed),
        "stores": rows,
        "failed": failed,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"exported stores={len(rows)} failed={len(failed)} reviews={sum(len(x['reviews']) for x in rows)}")


if __name__ == "__main__":
    main()
