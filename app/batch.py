import sys
from datetime import datetime, timezone

from app.db import connect, init_db, list_stores
from app.service import inspect_store
from app.store_sync import StoreSyncError, sync_official_stores


def run_all(limit_per_store: int = 30) -> int:
    init_db()
    try:
        synced = sync_official_stores()
        print(f"STORE_SYNC count={synced['count']}")
    except StoreSyncError as exc:
        print(f"STORE_SYNC_FAIL {exc}", file=sys.stderr)

    stores = list_stores()
    with connect() as con:
        cur = con.execute("INSERT INTO runs(stores_total) VALUES(?)", (len(stores),))
        run_id = cur.lastrowid
        con.commit()

    ok = failed = new_reviews = 0
    for store in stores:
        try:
            result = inspect_store(store["name"], store.get("address") or "", limit=limit_per_store)
            ok += 1
            new_reviews += result["new_reviews"]
            print(f"OK {store['name']} new={result['new_reviews']}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {store['name']} {type(exc).__name__}: {exc}", file=sys.stderr)

    status = "ok" if failed == 0 else "partial" if ok else "failed"
    with connect() as con:
        con.execute(
            "UPDATE runs SET finished_at=?, stores_ok=?, stores_failed=?, new_reviews=?, status=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), ok, failed, new_reviews, status, run_id),
        )
        con.commit()
    print(f"DONE stores={len(stores)} ok={ok} failed={failed} new_reviews={new_reviews}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(run_all())
