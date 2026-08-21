from app.main import app


def test_health_is_public():
    client = app.test_client()
    response = client.get('/health')
    assert response.status_code == 200
    assert response.get_json()['ok'] is True


def test_dashboard_redirects_to_login():
    client = app.test_client()
    response = client.get('/')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_default_dev_admin_can_login():
    client = app.test_client()
    response = client.post('/login', data={'username': 'admin', 'password': 'change-me-now'})
    assert response.status_code == 302
    with client:
        client.post('/login', data={'username': 'admin', 'password': 'change-me-now'})
        summary = client.get('/api/summary')
        assert summary.status_code == 200
