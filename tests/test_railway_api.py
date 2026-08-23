from app import railway_api


def test_railway_health_exposes_v30_settings():
    client = railway_api.app.test_client()
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["version"] == "3.0"
    assert payload["review_limit"] == 5


def test_check_batch_preserves_order(monkeypatch):
    def fake_inspect(store):
        return {**store, "checked": True, "reviews": [], "error": None}

    monkeypatch.setattr(railway_api, "inspect_store", fake_inspect)
    client = railway_api.app.test_client()
    response = client.post("/api/check-batch", json={"stores": [
        {"name": "A", "place_id": "1"},
        {"name": "B", "place_id": "2"},
    ]})
    payload = response.get_json()
    assert response.status_code == 200
    assert [row["name"] for row in payload["stores"]] == ["A", "B"]


def test_schedule_accepts_daily_time():
    client = railway_api.app.test_client()
    response = client.put("/api/schedule", json={"enabled": True, "brand": "은화수식당", "frequency": "daily", "time": "10:30"})
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["schedule"]["enabled"] is True
    assert payload["schedule"]["time"] == "10:30"
