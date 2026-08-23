import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, jsonify, request, send_from_directory

from app.brand_export import SEARCH_AREAS as BASE_SEARCH_AREAS, discover_stores, recent, search_one_area
from app.naver_crawler import NaverPlaceCrawler
from app.review_analyzer import analyze_review

app = Flask(__name__, static_folder=None)

# 네이버 지도는 검색 좌표와 지역어에 따라 결과가 달라져서 시군구 검색망을 넓게 둔다.
EXTRA_AREAS = [
    "인천 계양", "인천 미추홀", "인천 동구", "인천 강화", "인천 옹진", "인천 검단",
    "경기 동두천", "경기 여주", "경기 과천", "경기 가평", "경기 양평", "경기 연천",
    "부산 강서", "부산 금정", "부산 기장", "부산 남구", "부산 동구", "부산 사상", "부산 서구", "부산 수영", "부산 연제", "부산 영도", "부산 중구",
    "대구 중구", "대구 동구", "대구 서구", "대구 남구", "대구 달성", "대구 군위",
    "대전 동구", "대전 중구", "대전 대덕", "광주 동구", "광주 남구", "광주 광산", "울산 중구", "울산 동구", "울산 울주",
    "강원 동해", "강원 삼척", "강원 태백", "강원 홍천", "강원 횡성", "강원 영월", "강원 평창", "강원 정선", "강원 철원", "강원 화천", "강원 양구", "강원 인제", "강원 고성", "강원 양양",
    "충북 보은", "충북 옥천", "충북 영동", "충북 증평", "충북 진천", "충북 괴산", "충북 음성", "충북 단양",
    "충남 공주", "충남 보령", "충남 논산", "충남 계룡", "충남 당진", "충남 금산", "충남 부여", "충남 서천", "충남 청양", "충남 홍성", "충남 예산", "충남 태안",
    "전북 남원", "전북 김제", "전북 완주", "전북 진안", "전북 무주", "전북 장수", "전북 임실", "전북 순창", "전북 고창", "전북 부안",
    "전남 나주", "전남 담양", "전남 곡성", "전남 구례", "전남 고흥", "전남 보성", "전남 화순", "전남 장흥", "전남 강진", "전남 해남", "전남 영암", "전남 무안", "전남 함평", "전남 영광", "전남 장성", "전남 완도", "전남 진도", "전남 신안",
    "경북 김천", "경북 영주", "경북 영천", "경북 상주", "경북 문경", "경북 의성", "경북 청송", "경북 영양", "경북 영덕", "경북 청도", "경북 고령", "경북 성주", "경북 칠곡", "경북 예천", "경북 봉화", "경북 울진", "경북 울릉",
    "경남 통영", "경남 사천", "경남 밀양", "경남 의령", "경남 함안", "경남 창녕", "경남 고성", "경남 남해", "경남 하동", "경남 산청", "경남 함양", "경남 거창", "경남 합천",
]
SEARCH_AREAS = list(dict.fromkeys(BASE_SEARCH_AREAS + EXTRA_AREAS))
MAX_SEARCH_CONCURRENCY = 5
APP_VERSION = "1.7"

ALLOWED_ORIGINS = {"https://heeseung-lab.github.io", "http://localhost:8000", "http://127.0.0.1:8000"}


@app.after_request
def add_cors(resp):
    origin = request.headers.get("Origin", "")
    if origin in ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp


@app.route("/api/<path:_>", methods=["OPTIONS"])
def options(_):
    return ("", 204)


@app.get("/api/health")
def health():
    return jsonify({
        "ok": True,
        "service": "brand-review-railway",
        "version": APP_VERSION,
        "search_areas": len(SEARCH_AREAS),
        "max_search_concurrency": MAX_SEARCH_CONCURRENCY,
    })


@app.get("/api/search-plan")
def search_plan():
    return jsonify({"ok": True, "areas": SEARCH_AREAS, "count": len(SEARCH_AREAS), "batch_size": MAX_SEARCH_CONCURRENCY})


def _search_area_result(brand: str, area: str):
    crawler = NaverPlaceCrawler(timeout=18, pause=0.06)
    stores = search_one_area(crawler, brand, area)
    return {"ok": True, "brand": brand, "area": area, "count": len(stores), "stores": stores}


@app.post("/api/search-area")
def search_area():
    body = request.get_json(silent=True) or {}
    brand = str(body.get("brand", "")).strip()
    area = str(body.get("area", "")).strip()
    if len(brand) < 2 or not area:
        return jsonify({"ok": False, "error": "브랜드명과 검색지역이 필요합니다"}), 400
    try:
        return jsonify(_search_area_result(brand, area))
    except Exception as exc:
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 502


@app.post("/api/search-batch")
def search_batch():
    body = request.get_json(silent=True) or {}
    brand = str(body.get("brand", "")).strip()
    areas = [str(x).strip() for x in (body.get("areas") or []) if str(x).strip()]
    requested = int(body.get("concurrency") or MAX_SEARCH_CONCURRENCY)
    concurrency = max(1, min(MAX_SEARCH_CONCURRENCY, requested, len(areas) or 1))
    if len(brand) < 2 or not areas:
        return jsonify({"ok": False, "error": "브랜드명과 검색지역 목록이 필요합니다"}), 400
    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(_search_area_result, brand, area): area for area in areas}
        for future in as_completed(futures):
            area = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append({"ok": False, "area": area, "error": f"{type(exc).__name__}: {exc}", "stores": []})
    results.sort(key=lambda row: areas.index(row.get("area")))
    stores_by_id = {}
    for result in results:
        for store in result.get("stores") or []:
            place_id = str(store.get("place_id") or "").strip()
            if place_id and place_id not in stores_by_id:
                stores_by_id[place_id] = store
    return jsonify({
        "ok": True,
        "brand": brand,
        "areas": areas,
        "results": results,
        "stores": list(stores_by_id.values()),
        "count": len(stores_by_id),
        "concurrency": concurrency,
    })


@app.post("/api/search")
def search_brand():
    body = request.get_json(silent=True) or {}
    brand = str(body.get("brand", "")).strip()
    if len(brand) < 2:
        return jsonify({"ok": False, "error": "브랜드명을 2글자 이상 입력하세요"}), 400
    try:
        crawler = NaverPlaceCrawler(timeout=18, pause=0.06)
        stores = discover_stores(crawler, brand)
        return jsonify({"ok": True, "brand": brand, "count": len(stores), "stores": stores, "source": "naver-map-plus-search"})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 502


@app.post("/api/check")
def check_store():
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip()
    address = str(body.get("address", "")).strip()
    place_id = str(body.get("place_id", "")).strip()
    place_type = str(body.get("place_type", "restaurant") or "restaurant").strip()
    days = max(1, min(30, int(body.get("days", 7) or 7)))
    if len(name) < 2:
        return jsonify({"ok": False, "error": "매장명이 필요합니다"}), 400
    try:
        crawler = NaverPlaceCrawler(timeout=18, pause=0.10)
        if place_id.isdigit():
            try:
                reviews, review_url = crawler._graphql_reviews(place_id, place_type, 50)
            except Exception:
                reviews, review_url = crawler._apollo_reviews(place_id, place_type, 50)
            resolved_place_id = place_id
        else:
            match, reviews, review_url = crawler.fetch_latest_reviews(name, address, limit=50)
            resolved_place_id = match.place_id
        rows = recent([{"id": r.review_id, "text": r.text, "created_at": r.created_at, "rating": r.rating} for r in reviews], days)
        analyzed = []
        for row in rows:
            analysis = analyze_review(row.get("text", ""))
            analyzed.append({**row, "bad_hits": analysis.bad_hits, "good_hits": analysis.good_hits, "score": analysis.score, "level": analysis.level})
        return jsonify({"ok": True, "name": name, "address": address, "place_id": resolved_place_id, "review_url": review_url, "days": days, "count": len(analyzed), "reviews": analyzed})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 502


@app.get("/")
def dashboard():
    return send_from_directory(os.path.join(os.path.dirname(__file__), "..", "railway_site"), "index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
