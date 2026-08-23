from app import railway_api


def test_railway_health_exposes_v18_batch_settings():
    client = railway_api.app.test_client()

    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["version"] == "1.8"
    assert payload["max_search_concurrency"] == 5


def test_search_batch_deduplicates_by_place_id(monkeypatch):
    def fake_search(brand, area):
        return {
            "ok": True,
            "brand": brand,
            "area": area,
            "count": 1,
            "stores": [{"name": f"{brand} {area}", "address": area, "place_id": "12345", "place_type": "restaurant"}],
        }

    monkeypatch.setattr(railway_api, "_search_area_result", fake_search)
    client = railway_api.app.test_client()

    response = client.post("/api/search-batch", json={"brand": "은화수식당", "areas": ["서울 강남", "서울 서초"], "concurrency": 9})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["concurrency"] == 5
    assert [row["area"] for row in payload["results"]] == ["서울 강남", "서울 서초"]
