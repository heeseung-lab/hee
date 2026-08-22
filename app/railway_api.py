import os
from flask import Flask, jsonify, request, send_from_directory

from app.brand_export import discover_stores, recent
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
    return jsonify({"ok": True, "service": "brand-review-railway", "version": "1.0"})


@app.post("/api/search")
def search_brand():
    body = request.get_json(silent=True) or {}
    brand = str(body.get("brand", "")).strip()
    if len(brand) < 2:
        return jsonify({"ok": False, "error": "브랜드명을 2글자 이상 입력하세요"}), 400
    try:
        crawler = NaverPlaceCrawler(timeout=18, pause=0.25)
        stores = discover_stores(crawler, brand)
        return jsonify({"ok": True, "brand": brand, "count": len(stores), "stores": stores})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 502


@app.post("/api/check")
def check_store():
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip()
    address = str(body.get("address", "")).strip()
    days = max(1, min(30, int(body.get("days", 7) or 7)))
    if len(name) < 2:
        return jsonify({"ok": False, "error": "매장명이 필요합니다"}), 400
    try:
        crawler = NaverPlaceCrawler(timeout=18, pause=0.25)
        match, reviews, review_url = crawler.fetch_latest_reviews(name, address, limit=50)
        rows = recent([
            {"id": r.review_id, "text": r.text, "created_at": r.created_at, "rating": r.rating}
            for r in reviews
        ], days)
        analyzed = []
        for row in rows:
            a = analyze_review(row.get("text", ""))
            analyzed.append({
                **row,
                "bad_hits": a.bad_hits,
                "good_hits": a.good_hits,
                "score": a.score,
                "level": a.level,
            })
        return jsonify({
            "ok": True,
            "name": name,
            "address": address,
            "place_id": match.place_id,
            "review_url": review_url,
            "days": days,
            "count": len(analyzed),
            "reviews": analyzed,
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 502


@app.get("/")
def dashboard():
    return send_from_directory(os.path.join(os.path.dirname(__file__), "..", "railway_site"), "index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
