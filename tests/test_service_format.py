from app.naver_crawler import PlaceMatch, ReviewItem
from app import service


class FakeCrawler:
    def fetch_latest_reviews(self, name, address, limit=30):
        return (
            PlaceMatch("123456789", "restaurant", "https://search.naver.com"),
            [ReviewItem("r-1", "직원이 불친절했지만 음식은 맛있어요", "2026-08-21", 2.0)],
            "https://m.place.naver.com/restaurant/123456789/review/visitor",
        )


def test_service_returns_dashboard_safe_keyword_strings(monkeypatch):
    monkeypatch.setattr(service, "crawler", FakeCrawler())
    result = service.inspect_store("청년다방 테스트점", "서울 테스트로 1", limit=5)
    row = result["reviews"][0]
    assert isinstance(row["bad_hits"], str)
    assert isinstance(row["good_hits"], str)
    assert "불친절" in row["bad_hits"]
    assert "친절" not in row["good_hits"]
