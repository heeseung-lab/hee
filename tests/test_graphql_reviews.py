from app.naver_crawler import NaverPlaceCrawler


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.calls = 0

    def post(self, *args, **kwargs):
        self.calls += 1
        return FakeResponse(200, [{"data": {"visitorReviews": {"items": [
            {"id": "r1", "rating": 2, "body": "직원이 불친절하고 너무 오래 걸렸어요", "created": "2026-08-21"},
            {"id": "r2", "rating": 5, "body": "맛있고 친절해요", "created": "2026-08-20"},
        ], "total": 2}}}])


def test_graphql_review_objects_are_parsed():
    crawler = NaverPlaceCrawler(pause=0)
    crawler.session = FakeSession()
    items, _ = crawler._graphql_reviews("123456789", "restaurant", 20)
    assert [x.review_id for x in items] == ["r1", "r2"]
    assert items[0].text.startswith("직원이 불친절")
    assert items[0].rating == 2.0
