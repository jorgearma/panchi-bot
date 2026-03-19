def test_login_sin_credenciales_devuelve_400(client):
    resp = client.post('/auth/login', json={})
    assert resp.status_code == 400

def test_login_credenciales_invalidas_devuelve_401(client):
    resp = client.post('/auth/login', json={
        'email': 'noexiste@test.com',
        'password': '1234'
    })
    assert resp.status_code == 401

def test_dashboard_sin_sesion_redirige_a_login(client):
    resp = client.get('/dashboard')
    assert resp.status_code in (302, 401)

def test_picker_sin_sesion_redirige_a_login(client):
    resp = client.get('/picker')
    assert resp.status_code in (302, 401)

def test_repartidor_sin_sesion_redirige_a_login(client):
    resp = client.get('/repartidor')
    assert resp.status_code in (302, 401)
