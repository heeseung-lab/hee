from app.db import get_keywords, save_review, update_store_result, upsert_store
from app.naver_crawler import CrawlError, NaverPlaceCrawler
from app.review_analyzer import analyze_review

crawler = NaverPlaceCrawler()


def inspect_store(name: str, address: str = "", limit: int = 30):
    store_id = upsert_store(name, address)
    keywords = get_keywords()
    try:
        match, reviews, review_url = crawler.fetch_latest_reviews(name, address, limit=limit)
    except CrawlError as exc:
        update_store_result(store_id, "failed", str(exc))
        raise

    rows = []
    new_count = 0
    for review in reviews:
        analysis = analyze_review(review.text, keywords["bad"], keywords["good"])
        inserted = save_review(
            store_id,
            review.review_id,
            review.text,
            review.created_at,
            review.rating,
            analysis.bad_hits,
            analysis.good_hits,
            analysis.score,
            analysis.level,
        )
        new_count += int(inserted)
        rows.append({
            "id": review.review_id,
            "text": review.text,
            "created_at": review.created_at,
            "rating": review.rating,
            "bad_hits": analysis.bad_hits,
            "good_hits": analysis.good_hits,
            "score": analysis.score,
            "level": analysis.level,
        })

    update_store_result(store_id, "ok", None, match.place_id, match.place_type)
    return {
        "store_id": store_id,
        "place_id": match.place_id,
        "place_type": match.place_type,
        "review_url": review_url,
        "reviews": rows,
        "new_reviews": new_count,
    }
