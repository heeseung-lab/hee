import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.naver_crawler import NaverPlaceCrawler
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


def load_previous():
    if not OUT.exists():
        return {"stores": [], "generated_at": None}
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return {"stores": [], "generated_at": None}


def previous_map(payload):
    return {
        (str(row.get("name", "")).strip(), str(row.get("address", "")).strip()): row
        for row in payload.get("stores", [])
    }


def build_store_master(stores, previous):
    old = previous_map(previous)
    rows = []
    for name, address in stores:
        prior = old.get((name, address), {})
        rows.append({
            "name": name,
            "address": address,
            "place_id": prior.get("place_id"),
            "review_url": prior.get("review_url"),
            "reviews": prior.get("reviews", []),
            "error": prior.get("error"),
        })
    return rows


def write_payload(rows, generated_at, store_synced_at):
    failed = [
        {"name": row["name"], "address": row["address"], "error": row.get("error")}
        for row in rows
        if row.get("error")
    ]
    ok = sum(1 for row in rows if row.get("reviews"))
    payload = {
        "generated_at": generated_at,
        "store_synced_at": store_synced_at,
        "stores_total": len(rows),
        "stores_ok": ok,
        "stores_failed": len(failed),
        "stores": rows,
        "failed": failed,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main(stores_only=False):
    crawler = NaverPlaceCrawler(timeout=15, pause=0.7)
    stores = fetch_store_list(crawler.session)
    previous = load_previous()
    rows = build_store_master(stores, previous)
    now = datetime.now(timezone.utc).isoformat()

    if stores_only:
        payload = write_payload(rows, previous.get("generated_at"), now)
        print(f"synced store master={payload['stores_total']} reviews_preserved={sum(len(x.get('reviews', [])) for x in rows)}")
        return

    for row in rows:
        name = row["name"]
        address = row["address"]
        full_name = name if "청년다방" in name else f"청년다방 {name}"
        try:
            match, reviews, review_url = crawler.fetch_latest_reviews(full_name, address, limit=20)
            row.update({
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
                "error": None,
            })
        except Exception as exc:
            # Keep the last successful reviews visible even when a transient crawl fails.
            row["error"] = f"{type(exc).__name__}: {exc}"

    payload = write_payload(rows, now, now)
    print(
        f"exported stores={payload['stores_total']} ok={payload['stores_ok']} "
        f"failed={payload['stores_failed']} reviews={sum(len(x.get('reviews', [])) for x in rows)}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stores-only", action="store_true", help="Refresh store master without crawling reviews")
    args = parser.parse_args()
    main(stores_only=args.stores_only)
