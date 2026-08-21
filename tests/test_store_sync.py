from app.store_sync import _parse_page


def test_parse_official_store_block():
    html = '''
    <ul><li><strong>명동역점</strong><span>서울 중구 명동8나길 30-1 3층</span><em>02)752-3335</em></li></ul>
    '''
    stores = _parse_page(html)
    assert ("명동역점", "서울 중구 명동8나길 30-1 3층") in stores
