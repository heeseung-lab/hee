from app.naver_crawler import NaverPlaceCrawler


def test_balanced_apollo_json():
    html = '<script>window.__APOLLO_STATE__ = {"VisitorReview:1":{"id":"1","body":"너무 불친절했어요","createdAt":"2026-08-20"}};</script>'
    state = NaverPlaceCrawler._balanced_json(html, "window.__APOLLO_STATE__")
    assert state["VisitorReview:1"]["body"] == "너무 불친절했어요"


def test_structured_review_extraction_only():
    crawler = NaverPlaceCrawler()
    state = {
        "VisitorReview:1": {"id": "1", "body": "직원이 불친절했어요", "createdAt": "2026-08-20"},
        "PlaceDetail:1": {"id": "1", "description": "이 문장은 매장 소개이고 리뷰가 아닙니다"},
    }
    reviews = crawler._walk_reviews(state)
    assert len(reviews) == 1
    assert reviews[0].text == "직원이 불친절했어요"
