from app.brand_export import extract_map_rows


def test_extract_map_rows_prefers_branch_place_name():
    body = r'''{"id":"2080955779","name":"은화수식당 이천점","roadAddress":"경기 이천시"}'''

    rows = extract_map_rows(body, "은화수식당")

    assert rows[0]["name"] == "은화수식당 이천점"
