from datetime import datetime
from zoneinfo import ZoneInfo

from app.export_static import _filter_recent


def test_filter_recent_keeps_today_and_yesterday():
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    today = now.strftime("%Y-%m-%d")
    yesterday = (now.date().fromordinal(now.date().toordinal() - 1)).isoformat()
    two_days_ago = (now.date().fromordinal(now.date().toordinal() - 2)).isoformat()
    rows = [
        {"created_at": today, "text": "today"},
        {"created_at": yesterday, "text": "yesterday"},
        {"created_at": two_days_ago, "text": "older"},
    ]
    out = _filter_recent(rows, days=2)
    assert [x["text"] for x in out] == ["today", "yesterday"]


def test_filter_recent_supports_relative_korean_dates():
    rows = [
        {"created_at": "오늘", "text": "a"},
        {"created_at": "어제", "text": "b"},
        {"created_at": "2일 전", "text": "c"},
    ]
    out = _filter_recent(rows, days=2)
    assert [x["text"] for x in out] == ["a", "b"]
