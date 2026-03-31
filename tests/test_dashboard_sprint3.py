# tests/test_dashboard_sprint3.py
from unittest.mock import patch, PropertyMock, MagicMock


# ── Task 1: Manager ──────────────────────────────────────────────────────────

def test_turnos_hoy_devuelve_claves_esperadas(app):
    """turnos_hoy() devuelve dict con empleados y resumen."""
    from container import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_session.return_value.query.return_value.filter_by.return_value.order_by.return_value.all.return_value = []
            mock_session.return_value.query.return_value.filter.return_value.all.return_value = []

            result = gestor_dashboard.turnos_hoy()

            assert 'empleados' in result
            assert 'resumen' in result
            assert isinstance(result['empleados'], list)
            assert 'con_checkin' in result['resumen']
            assert 'en_pausa' in result['resumen']
            assert 'desconectados' in result['resumen']
            assert 'total' in result['resumen']


def test_turnos_hoy_resumen_sin_empleados(app):
    """turnos_hoy() con lista vacía da resumen a cero."""
    from container import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_session.return_value.query.return_value.filter_by.return_value.order_by.return_value.all.return_value = []
            mock_session.return_value.query.return_value.filter.return_value.all.return_value = []

            result = gestor_dashboard.turnos_hoy()

            assert result['resumen']['total'] == 0
            assert result['resumen']['con_checkin'] == 0


def test_turnos_historial_devuelve_claves_esperadas(app):
    """turnos_historial() devuelve dict con turnos, total, page, pages."""
    from container import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_q = mock_session.return_value.query.return_value
            mock_q.join.return_value = mock_q
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.count.return_value = 0
            mock_q.offset.return_value = mock_q
            mock_q.limit.return_value = mock_q
            mock_q.all.return_value = []

            result = gestor_dashboard.turnos_historial()

            assert 'turnos' in result
            assert 'total' in result
            assert 'page' in result
            assert 'pages' in result
            assert result['turnos'] == []
            assert result['total'] == 0


def test_turnos_historial_paginacion_por_defecto(app):
    """turnos_historial() usa page=1 y per_page=25 por defecto."""
    from container import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_q = mock_session.return_value.query.return_value
            mock_q.join.return_value = mock_q
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.count.return_value = 50
            mock_q.offset.return_value = mock_q
            mock_q.limit.return_value = mock_q
            mock_q.all.return_value = []

            result = gestor_dashboard.turnos_historial()

            assert result['page'] == 1
            assert result['pages'] == 2   # ceil(50/25)


# ── Task 2: Routes ───────────────────────────────────────────────────────────

def test_turnos_html_devuelve_200(client):
    """GET /dashboard/turnos devuelve 200 para admin autenticado."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/turnos')
    assert resp.status_code == 200
    assert b'turno' in resp.data.lower()


def test_turnos_html_requiere_auth(client):
    """GET /dashboard/turnos redirige sin sesión."""
    resp = client.get('/dashboard/turnos')
    assert resp.status_code in (302, 401)


def test_turnos_hoy_json_devuelve_estructura(client):
    """GET /dashboard/turnos/hoy devuelve {empleados, resumen}."""
    from unittest.mock import patch
    from container import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(
        gestor_dashboard, 'turnos_hoy',
        return_value={'empleados': [], 'resumen': {'con_checkin': 0, 'en_pausa': 0, 'desconectados': 0, 'total': 0}}
    ):
        resp = client.get('/dashboard/turnos/hoy')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'empleados' in data
        assert 'resumen' in data


def test_turnos_historial_json_devuelve_estructura(client):
    """GET /dashboard/turnos/historial devuelve {turnos, total, page, pages}."""
    from unittest.mock import patch
    from container import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(
        gestor_dashboard, 'turnos_historial',
        return_value={'turnos': [], 'total': 0, 'page': 1, 'pages': 1}
    ):
        resp = client.get('/dashboard/turnos/historial')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'turnos' in data
        assert 'total' in data


def test_turnos_historial_json_pasa_filtros(client):
    """GET /dashboard/turnos/historial pasa params al manager."""
    from unittest.mock import patch
    from container import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(
        gestor_dashboard, 'turnos_historial',
        return_value={'turnos': [], 'total': 0, 'page': 1, 'pages': 1}
    ) as mock_hist:
        client.get('/dashboard/turnos/historial?rol=picker&page=2')
        mock_hist.assert_called_once_with(
            desde=None, hasta=None, empleado_id=None,
            rol='picker', page=2, per_page=25
        )


# ── Task 3: Template ─────────────────────────────────────────────────────────

def test_turnos_template_cargable_en_jinja2(app):
    """turnos.html se puede cargar en Jinja2 sin errores de sintaxis."""
    with app.app_context():
        template = app.jinja_env.get_template('dashboard/turnos.html')
        assert template is not None


def test_turnos_html_contiene_nav_links(client):
    """GET /dashboard/turnos incluye los links de navegación."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/turnos')
    assert resp.status_code == 200
    html = resp.data.decode()
    for ruta in ['/dashboard', '/dashboard/monitor', '/dashboard/historial',
                 '/dashboard/rendimiento', '/dashboard/estadisticas']:
        assert ruta in html, f"Link {ruta} no encontrado en turnos.html"


def test_turnos_html_contiene_alpine_app(client):
    """GET /dashboard/turnos incluye x-data turnosApp()."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/turnos')
    assert resp.status_code == 200
    assert b'turnosApp' in resp.data
