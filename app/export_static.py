import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.naver_crawler import NaverPlaceCrawler
from app.store_sync import StoreSyncError, _parse_page

OUT = Path("site/data/reviews.json")
STORES_URL = "https://youngdabang.com/board/index.php?board=map_01"
KST = ZoneInfo("Asia/Seoul")


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


def _review_date(value):
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


def _filter_recent(reviews, days=2):
    start = datetime.now(KST).date() - timedelta(days=days - 1)
    return [r for r in reviews if (_review_date(r.get("created_at")) or datetime.min.date()) >= start]


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
            "reviews": _filter_recent(prior.get("reviews", []), days=2),
            "error": prior.get("error"),
        })
    return rows


def write_payload(rows, generated_at, store_synced_at):
    failed = [
        {"name": row["name"], "address": row["address"], "error": row.get("error")}
        for row in rows
        if row.get("error")
    ]
    ok = sum(1 for row in rows if not row.get("error"))
    payload = {
        "generated_at": generated_at,
        "store_synced_at": store_synced_at,
        "window_days": 2,
        "window_label": "전일+당일",
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
            match, reviews, review_url = crawler.fetch_latest_reviews(full_name, address, limit=50)
            filtered = _filter_recent([
                {"id": r.review_id, "text": r.text, "created_at": r.created_at, "rating": r.rating}
                for r in reviews
            ], days=2)
            row.update({
                "place_id": match.place_id,
                "review_url": review_url,
                "reviews": filtered,
                "error": None,
            })
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            row["reviews"] = _filter_recent(row.get("reviews", []), days=2)

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
