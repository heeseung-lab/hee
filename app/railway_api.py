import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, request, send_from_directory

from app.brand_export import SEARCH_AREAS, search_brand_places
from app.naver_crawler import NaverPlaceCrawler
from app.review_analyzer import analyze_review

app = Flask(__name__, static_folder=None)
KST = ZoneInfo("Asia/Seoul")
APP_VERSION = "3.0"
MAX_SEARCH_CONCURRENCY = 4
MAX_REVIEW_CONCURRENCY = 3
REVIEW_LIMIT = 5
STATE_DIR = Path(os.getenv("APP_STATE_DIR", "/tmp/brand-review-monitor"))
SCHEDULE_FILE = STATE_DIR / "schedule.json"
RESULT_FILE = STATE_DIR / "last_result.json"
ALLOWED_ORIGINS = {"https://heeseung-lab.github.io", "http://localhost:8000", "http://127.0.0.1:8000"}
SCHEDULE_LOCK = threading.Lock()
SCHEDULE = {"enabled": False, "brand": "", "frequency": "daily", "time": "09:00", "weekday": "mon", "last_run_key": None}
LAST_RESULT = None
SCHEDULER_STARTED = False


def _load_json(path: Path, fallback):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return fallback


def _save_json(path: Path, payload):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _init_state():
    global LAST_RESULT
    SCHEDULE.update(_load_json(SCHEDULE_FILE, {}))
    LAST_RESULT = _load_json(RESULT_FILE, None)


def _weekday_key(dt):
    return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][dt.weekday()]


def _run_key(dt, schedule):
    return dt.strftime("%G-W%V") if schedule.get("frequency") == "weekly" else dt.strftime("%Y-%m-%d")


def _schedule_due(now, schedule):
    if not schedule.get("enabled") or len(str(schedule.get("brand", "")).strip()) < 2:
        return False
    if now.strftime("%H:%M") != str(schedule.get("time") or "09:00")[:5]:
        return False
    if schedule.get("frequency") == "weekly" and schedule.get("weekday") != _weekday_key(now):
        return False
    return schedule.get("last_run_key") != _run_key(now, schedule)


def _set_last_result(result):
    global LAST_RESULT
    LAST_RESULT = result
    _save_json(RESULT_FILE, result)


def _scheduler_loop():
    while True:
        time.sleep(20)
        now = datetime.now(KST)
        with SCHEDULE_LOCK:
            schedule = dict(SCHEDULE)
        if not _schedule_due(now, schedule):
            continue
        result = run_full_check(schedule["brand"])
        with SCHEDULE_LOCK:
            SCHEDULE["last_run_key"] = _run_key(now, SCHEDULE)
            _save_json(SCHEDULE_FILE, SCHEDULE)
            _set_last_result(result)


def _ensure_scheduler():
    global SCHEDULER_STARTED
    if SCHEDULER_STARTED:
        return
    SCHEDULER_STARTED = True
    threading.Thread(target=_scheduler_loop, daemon=True).start()


@app.after_request
def add_cors(resp):
    origin = request.headers.get("Origin", "")
    if origin in ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,OPTIONS"
    return resp


@app.route("/api/<path:_>", methods=["OPTIONS"])
def options(_):
    return ("", 204)


@app.get("/api/health")
def health():
    return jsonify({
        "ok": True,
        "service": "naver-place-review-monitor",
        "version": APP_VERSION,
        "review_limit": REVIEW_LIMIT,
        "search_areas": len(SEARCH_AREAS),
        "max_search_concurrency": MAX_SEARCH_CONCURRENCY,
        "max_review_concurrency": MAX_REVIEW_CONCURRENCY,
    })


@app.get("/api/search-plan")
def search_plan():
    return jsonify({"ok": True, "areas": SEARCH_AREAS, "count": len(SEARCH_AREAS), "batch_size": MAX_SEARCH_CONCURRENCY})


@app.post("/api/search")
def search_brand():
    body = request.get_json(silent=True) or {}
    brand = str(body.get("brand", "")).strip()
    if len(brand) < 2:
        return jsonify({"ok": False, "error": "브랜드명을 2글자 이상 입력하세요"}), 400
    try:
        stores = search_brand_places(brand, concurrency=MAX_SEARCH_CONCURRENCY)
        return jsonify({"ok": True, "brand": brand, "count": len(stores), "stores": stores, "source": "naver-place"})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 502


@app.post("/api/search-batch")
def search_batch_compat():
    body = request.get_json(silent=True) or {}
    brand = str(body.get("brand", "")).strip()
    if len(brand) < 2:
        return jsonify({"ok": False, "error": "브랜드명을 2글자 이상 입력하세요"}), 400
    stores = search_brand_places(brand, concurrency=MAX_SEARCH_CONCURRENCY)
    return jsonify({"ok": True, "brand": brand, "stores": stores, "count": len(stores), "results": [{"ok": True, "area": "네이버플레이스", "count": len(stores), "stores": stores}]})


def inspect_store(store):
    place_id = str(store.get("place_id", "")).strip()
    place_type = str(store.get("place_type") or "restaurant").strip()
    name = str(store.get("name") or "").strip()
    address = str(store.get("address") or "").strip()
    crawler = NaverPlaceCrawler(timeout=18, pause=0.08)
    if place_id.isdigit():
        try:
            reviews, review_url = crawler._graphql_reviews(place_id, place_type, REVIEW_LIMIT)
        except Exception:
            reviews, review_url = crawler._apollo_reviews(place_id, place_type, REVIEW_LIMIT)
        resolved_id = place_id
    else:
        match, reviews, review_url = crawler.fetch_latest_reviews(name, address, limit=REVIEW_LIMIT)
        resolved_id = match.place_id
        place_type = match.place_type
    analyzed = []
    for review in reviews[:REVIEW_LIMIT]:
        analysis = analyze_review(review.text)
        analyzed.append({
            "id": review.review_id,
            "text": review.text,
            "created_at": review.created_at,
            "rating": review.rating,
            "bad_hits": analysis.bad_hits,
            "good_hits": analysis.good_hits,
            "score": analysis.score,
            "level": analysis.level,
        })
    return {**store, "place_id": resolved_id, "place_type": place_type, "review_url": review_url, "reviews": analyzed, "checked": True, "error": None}


@app.post("/api/check")
def check_store():
    body = request.get_json(silent=True) or {}
    try:
        return jsonify({"ok": True, **inspect_store(body)})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 502


@app.post("/api/check-batch")
def check_batch():
    body = request.get_json(silent=True) or {}
    stores = body.get("stores") or []
    if not isinstance(stores, list) or not stores:
        return jsonify({"ok": False, "error": "검사할 매장 목록이 필요합니다"}), 400
    results = [None] * len(stores)
    workers = max(1, min(MAX_REVIEW_CONCURRENCY, len(stores)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(inspect_store, store): idx for idx, store in enumerate(stores)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as exc:
                results[idx] = {**stores[idx], "checked": False, "reviews": [], "error": f"{type(exc).__name__}: {exc}"}
    return jsonify({"ok": True, "count": len(results), "stores": results})


def run_full_check(brand: str):
    stores = search_brand_places(brand, concurrency=MAX_SEARCH_CONCURRENCY)
    checked = []
    with ThreadPoolExecutor(max_workers=MAX_REVIEW_CONCURRENCY) as executor:
        futures = {executor.submit(inspect_store, store): store for store in stores}
        for future in as_completed(futures):
            store = futures[future]
            try:
                checked.append(future.result())
            except Exception as exc:
                checked.append({**store, "checked": False, "reviews": [], "error": f"{type(exc).__name__}: {exc}"})
    checked.sort(key=lambda row: (row.get("name", ""), row.get("address", "")))
    return {"ok": True, "brand": brand, "generated_at": datetime.now(KST).isoformat(), "count": len(checked), "stores": checked}


@app.get("/api/schedule")
def get_schedule():
    with SCHEDULE_LOCK:
        return jsonify({"ok": True, "schedule": SCHEDULE, "last_result": LAST_RESULT})


@app.put("/api/schedule")
def put_schedule():
    body = request.get_json(silent=True) or {}
    frequency = body.get("frequency") if body.get("frequency") in ("daily", "weekly") else "daily"
    weekday = body.get("weekday") if body.get("weekday") in ("mon", "tue", "wed", "thu", "fri", "sat", "sun") else "mon"
    target_time = str(body.get("time") or "09:00")[:5]
    if len(target_time) != 5:
        target_time = "09:00"
    with SCHEDULE_LOCK:
        SCHEDULE.update({
            "enabled": bool(body.get("enabled")),
            "brand": str(body.get("brand") or "").strip(),
            "frequency": frequency,
            "time": target_time,
            "weekday": weekday,
        })
        _save_json(SCHEDULE_FILE, SCHEDULE)
    return jsonify({"ok": True, "schedule": SCHEDULE})


@app.post("/api/schedule/run")
def run_schedule_now():
    body = request.get_json(silent=True) or {}
    brand = str(body.get("brand") or SCHEDULE.get("brand") or "").strip()
    if len(brand) < 2:
        return jsonify({"ok": False, "error": "브랜드명을 먼저 입력하세요"}), 400
    try:
        result = run_full_check(brand)
        with SCHEDULE_LOCK:
            _set_last_result(result)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 502


@app.get("/api/schedule/result")
def schedule_result():
    return jsonify({"ok": True, "result": LAST_RESULT})


@app.get("/")
def dashboard():
    return send_from_directory(os.path.join(os.path.dirname(__file__), "..", "railway_site"), "index.html")


_init_state()
_ensure_scheduler()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
