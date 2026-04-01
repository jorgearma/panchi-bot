# tests/test_dashboard_sprint5.py
from unittest.mock import patch, PropertyMock, MagicMock


# ── Task 1: Manager ──────────────────────────────────────────────────────────

def test_estadisticas_devuelve_claves_esperadas(app):
    """estadisticas() devuelve todas las claves requeridas."""
    from container import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_q = mock_session.return_value.query.return_value
            mock_q.filter.return_value = mock_q
            mock_q.all.return_value = []

            result = gestor_dashboard.estadisticas()

            assert 'kpis' in result
            assert 'serie_pedidos_ingresos' in result
            assert 'distribucion_estados' in result
            assert 'forma_pago' in result
            assert 'serie_tiempos' in result


def test_estadisticas_kpis_tienen_campos_requeridos(app):
    """estadisticas() kpis contiene todos los campos esperados."""
    from container import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_q = mock_session.return_value.query.return_value
            mock_q.filter.return_value = mock_q
            mock_q.all.return_value = []

            result = gestor_dashboard.estadisticas()
            kpis = result['kpis']

            assert 'ingresos' in kpis
            assert 'pedidos' in kpis
            assert 'entregados' in kpis
            assert 'cancelados' in kpis
            assert 'tasa_cancelacion_pct' in kpis
            assert 't_prep_min' in kpis
            assert 't_entrega_min' in kpis


def test_estadisticas_serie_vacia_si_no_hay_pedidos(app):
    """estadisticas() devuelve series con 0s cuando no hay pedidos."""
    from container import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_q = mock_session.return_value.query.return_value
            mock_q.filter.return_value = mock_q
            mock_q.all.return_value = []

            result = gestor_dashboard.estadisticas()

            assert isinstance(result['serie_pedidos_ingresos'], list)
            assert isinstance(result['serie_tiempos'], list)
            # With default 7-day range, serie should have 7 entries
            assert len(result['serie_pedidos_ingresos']) == 7
            assert all(e['pedidos'] == 0 for e in result['serie_pedidos_ingresos'])


def test_estadisticas_acepta_granularidad_semana(app):
    """estadisticas() acepta granularidad='semana' sin error."""
    from container import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_q = mock_session.return_value.query.return_value
            mock_q.filter.return_value = mock_q
            mock_q.all.return_value = []

            result = gestor_dashboard.estadisticas(
                desde='2026-01-01', hasta='2026-01-21', granularidad='semana'
            )
            assert 'serie_pedidos_ingresos' in result
            # 2026-01-01 (W01) → 2026-01-21 (W04) spans 4 ISO weeks
            assert len(result['serie_pedidos_ingresos']) == 4


# ── Task 2: Routes ────────────────────────────────────────────────────────────

def test_estadisticas_html_devuelve_200(client):
    """GET /dashboard/estadisticas devuelve 200 para admin autenticado."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/estadisticas')
    assert resp.status_code == 200
    assert b'estadistica' in resp.data.lower()


def test_estadisticas_html_requiere_auth(client):
    """GET /dashboard/estadisticas redirige sin sesión."""
    resp = client.get('/dashboard/estadisticas')
    assert resp.status_code in (302, 401)


def test_estadisticas_datos_json_devuelve_estructura(client):
    """GET /dashboard/estadisticas-datos devuelve estructura completa."""
    from unittest.mock import patch
    from container import gestor_dashboard

    fake = {
        'kpis': {
            'ingresos': 100.0, 'pedidos': 5, 'entregados': 4,
            'cancelados': 1, 'tasa_cancelacion_pct': 20.0,
            't_prep_min': 12.0, 't_entrega_min': 25.0,
        },
        'serie_pedidos_ingresos': [],
        'distribucion_estados': {},
        'forma_pago': {'online': 3, 'efectivo': 1, 'tarjeta': 1},
        'serie_tiempos': [],
    }

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(gestor_dashboard, 'estadisticas', return_value=fake):
        resp = client.get('/dashboard/estadisticas-datos')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'kpis' in data
        assert 'serie_pedidos_ingresos' in data
        assert 'forma_pago' in data


def test_estadisticas_datos_pasa_parametros(client):
    """GET /dashboard/estadisticas-datos pasa desde, hasta y granularidad al manager."""
    from unittest.mock import patch
    from container import gestor_dashboard

    fake = {
        'kpis': {'ingresos': 0, 'pedidos': 0, 'entregados': 0,
                 'cancelados': 0, 'tasa_cancelacion_pct': None,
                 't_prep_min': None, 't_entrega_min': None},
        'serie_pedidos_ingresos': [], 'distribucion_estados': {},
        'forma_pago': {}, 'serie_tiempos': [],
    }

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(
        gestor_dashboard, 'estadisticas', return_value=fake
    ) as mock_est:
        client.get('/dashboard/estadisticas-datos?desde=2026-01-01&hasta=2026-01-31&granularidad=semana')
        mock_est.assert_called_once_with(
            desde='2026-01-01', hasta='2026-01-31', granularidad='semana'
        )


# ── Task 3: Template ──────────────────────────────────────────────────────────

def test_estadisticas_template_cargable_en_jinja2(app):
    """estadisticas.html se puede cargar en Jinja2 sin errores."""
    with app.app_context():
        template = app.jinja_env.get_template('dashboard/estadisticas.html')
        assert template is not None


def test_estadisticas_html_contiene_nav_links(client):
    """GET /dashboard/estadisticas incluye links de navegación."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/estadisticas')
    assert resp.status_code == 200
    html = resp.data.decode()
    for ruta in ['/dashboard', '/dashboard/monitor', '/dashboard/historial',
                 '/dashboard/turnos', '/dashboard/rendimiento', '/dashboard/estadisticas']:
        assert ruta in html, f"Link {ruta} no encontrado en estadisticas.html"


def test_estadisticas_html_contiene_alpine_app(client):
    """GET /dashboard/estadisticas incluye x-data estadisticasApp()."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/estadisticas')
    assert resp.status_code == 200
    assert b'estadisticasApp' in resp.data
