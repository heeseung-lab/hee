import os
from flask import Flask, jsonify, request, send_from_directory

from app.brand_export import SEARCH_AREAS, REGIONS, discover_stores, recent, search_one_area
from app.naver_crawler import NaverPlaceCrawler
from app.review_analyzer import analyze_review

app = Flask(__name__, static_folder=None)

ALLOWED_ORIGINS = {
    "https://heeseung-lab.github.io",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
}


def cors(resp):
    origin = request.headers.get("Origin", "")
    if origin in ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp


@app.after_request
def add_cors(resp):
    return cors(resp)


@app.route("/api/<path:_>", methods=["OPTIONS"])
def options(_):
    return ("", 204)


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "brand-review-railway", "version": "1.3"})


@app.get("/api/search-plan")
def search_plan():
    # 화면에서 실제 수집 과정을 단계별로 보여주기 위한 검색 계획
    return jsonify({"ok": True, "areas": SEARCH_AREAS, "count": len(SEARCH_AREAS)})


@app.post("/api/search-area")
def search_area():
    body = request.get_json(silent=True) or {}
    brand = str(body.get("brand", "")).strip()
    area = str(body.get("area", "")).strip()
    if len(brand) < 2 or not area:
        return jsonify({"ok": False, "error": "브랜드명과 검색지역이 필요합니다"}), 400
    try:
        crawler = NaverPlaceCrawler(timeout=18, pause=0.08)
        stores = search_one_area(crawler, brand, area)
        return jsonify({"ok": True, "brand": brand, "area": area, "count": len(stores), "stores": stores})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 502


@app.post("/api/search")
def search_brand():
    body = request.get_json(silent=True) or {}
    brand = str(body.get("brand", "")).strip()
    if len(brand) < 2:
        return jsonify({"ok": False, "error": "브랜드명을 2글자 이상 입력하세요"}), 400
    try:
        crawler = NaverPlaceCrawler(timeout=18, pause=0.08)
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
        crawler = NaverPlaceCrawler(timeout=18, pause=0.12)
        if place_id.isdigit():
            try:
                reviews, review_url = crawler._graphql_reviews(place_id, place_type, 50)
            except Exception:
                reviews, review_url = crawler._apollo_reviews(place_id, place_type, 50)
            resolved_place_id = place_id
        else:
            match, reviews, review_url = crawler.fetch_latest_reviews(name, address, limit=50)
            resolved_place_id = match.place_id
        rows = recent([
            {"id": r.review_id, "text": r.text, "created_at": r.created_at, "rating": r.rating}
            for r in reviews
        ], days)
        analyzed = []
        for row in rows:
            a = analyze_review(row.get("text", ""))
            analyzed.append({**row, "bad_hits": a.bad_hits, "good_hits": a.good_hits, "score": a.score, "level": a.level})
        return jsonify({"ok": True, "name": name, "address": address, "place_id": resolved_place_id, "review_url": review_url, "days": days, "count": len(analyzed), "reviews": analyzed})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 502


@app.get("/")
def dashboard():
    return send_from_directory(os.path.join(os.path.dirname(__file__), "..", "railway_site"), "index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
