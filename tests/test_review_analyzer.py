from app.review_analyzer import analyze_review


def test_bad_review():
    r = analyze_review("음식은 맛있지만 직원이 너무 불친절하고 오래 걸렸어요")
    assert "불친절" in r.bad_hits
    assert "친절" not in r.good_hits
    assert r.level in ("주의", "집중관리")


def test_good_review():
    r = analyze_review("직원분이 친절하고 음식도 맛있어요. 재방문할게요")
    assert not r.bad_hits
    assert "친절" in r.good_hits
    assert "맛있" in r.good_hits
    assert r.level == "정상"


def test_negated_friendly_is_not_positive():
    r = analyze_review("직원이 친절하지 않았어요")
    assert "친절" not in r.good_hits
