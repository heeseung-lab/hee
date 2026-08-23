from app.brand_export import better_place_name, clean_place_name, extract_map_rows, merge_store


def test_extract_map_rows_prefers_branch_place_name():
    body = r'''{"id":"2080955779","name":"은화수식당 이천점","roadAddress":"경기 이천시"}'''

    rows = extract_map_rows(body, "은화수식당")

    assert rows[0]["name"] == "은화수식당 이천점"


def test_better_place_name_replaces_generic_brand_name():
    assert better_place_name("은화수식당", "은화수식당 화성봉담점", "은화수식당") == "은화수식당 화성봉담점"


def test_clean_place_name_repairs_mojibake_address():
    broken = "서울 강남구 테헤란로 410".encode("utf-8").decode("latin1")

    assert clean_place_name(broken) == "서울 강남구 테헤란로 410"


def test_extract_map_rows_reads_place_id_from_naver_map_search_url():
    body = r'''<a href="https://map.naver.com/p/search/은화수식당/place/1652721564">은화수식당 서울고덕점</a>'''

    rows = extract_map_rows(body, "은화수식당")

    assert rows[0]["place_id"] == "1652721564"
    assert rows[0]["name"] == "은화수식당 서울고덕점"


def test_merge_store_keeps_naver_map_branch_name():
    stores = {"1652721564": {"name": "은화수식당", "address": "", "place_id": "1652721564", "place_type": "restaurant"}}

    merge_store(stores, {"name": "은화수식당 서울고덕점", "address": "서울 강동구", "place_id": "1652721564", "place_type": "restaurant"}, "은화수식당")

    assert stores["1652721564"]["name"] == "은화수식당 서울고덕점"
    assert stores["1652721564"]["address"] == "서울 강동구"
