def test_health_devuelve_200(client):
    resp = client.get('/health')
    assert resp.status_code == 200


def test_health_incluye_componentes(client):
    resp = client.get('/health')
    data = resp.get_json()
    assert 'redis' in data
    assert 'database' in data
