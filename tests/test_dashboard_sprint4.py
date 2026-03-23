# tests/test_dashboard_sprint4.py
from unittest.mock import patch, PropertyMock, MagicMock


# ── Task 1: Manager ──────────────────────────────────────────────────────────

def test_rendimiento_resumen_devuelve_claves_esperadas(app):
    """rendimiento_resumen() devuelve dict con empleados list."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_q = mock_session.return_value.query.return_value
            mock_q.filter.return_value = mock_q
            mock_q.group_by.return_value = mock_q
            mock_q.all.return_value = []

            result = gestor_dashboard.rendimiento_resumen()

            assert 'empleados' in result
            assert isinstance(result['empleados'], list)


def test_rendimiento_resumen_acepta_filtro_rol(app):
    """rendimiento_resumen() acepta filtro por rol sin error."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_q = mock_session.return_value.query.return_value
            mock_q.filter.return_value = mock_q
            mock_q.group_by.return_value = mock_q
            mock_q.all.return_value = []

            result = gestor_dashboard.rendimiento_resumen(rol='picker')
            assert 'empleados' in result

            result = gestor_dashboard.rendimiento_resumen(periodo='semana', rol='repartidor')
            assert 'empleados' in result


def test_rendimiento_empleado_devuelve_none_si_no_existe(app):
    """rendimiento_empleado() devuelve None si el empleado no existe."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_session.return_value.query.return_value.filter_by.return_value.first.return_value = None

            result = gestor_dashboard.rendimiento_empleado(99999)
            assert result is None


def test_rendimiento_empleado_devuelve_claves_esperadas(app):
    """rendimiento_empleado() devuelve kpis, pedidos_por_dia, turnos_recientes, ultimos_pedidos."""
    from services import gestor_dashboard
    with app.app_context():
        emp_mock = MagicMock()
        emp_mock.EmpleadoID = 1
        emp_mock.Nombre = 'Ana'
        emp_mock.Apellido = 'García'
        emp_mock.rol = MagicMock()
        emp_mock.rol.nombre = 'picker'

        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_session.return_value.query.return_value.filter_by.return_value.first.return_value = emp_mock
            mock_q = mock_session.return_value.query.return_value
            mock_q.filter.return_value = mock_q
            mock_q.group_by.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.limit.return_value = mock_q
            mock_q.all.return_value = []
            mock_q.first.return_value = (None, None, None, None)

            result = gestor_dashboard.rendimiento_empleado(1)

            assert result is not None
            assert 'kpis' in result
            assert 'pedidos_por_dia' in result
            assert 'turnos_recientes' in result
            assert 'ultimos_pedidos' in result
            assert 'nombre' in result


# ── Task 2: Routes ───────────────────────────────────────────────────────────

def test_rendimiento_html_devuelve_200(client):
    """GET /dashboard/rendimiento devuelve 200 para admin autenticado."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/rendimiento')
    assert resp.status_code == 200
    assert b'rendimiento' in resp.data.lower()


def test_rendimiento_html_requiere_auth(client):
    """GET /dashboard/rendimiento redirige sin sesión."""
    resp = client.get('/dashboard/rendimiento')
    assert resp.status_code in (302, 401)


def test_rendimiento_resumen_json_devuelve_estructura(client):
    """GET /dashboard/rendimiento-datos devuelve {empleados}."""
    from unittest.mock import patch
    from services import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(gestor_dashboard, 'rendimiento_resumen', return_value={'empleados': []}):
        resp = client.get('/dashboard/rendimiento-datos')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'empleados' in data


def test_rendimiento_resumen_json_pasa_filtros(client):
    """GET /dashboard/rendimiento-datos pasa periodo y rol al manager."""
    from unittest.mock import patch
    from services import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(
        gestor_dashboard, 'rendimiento_resumen', return_value={'empleados': []}
    ) as mock_res:
        client.get('/dashboard/rendimiento-datos?periodo=semana&rol=picker')
        mock_res.assert_called_once_with(periodo='semana', rol='picker')


def test_rendimiento_empleado_json_devuelve_404_si_no_existe(client):
    """GET /dashboard/rendimiento/<id> devuelve 404 si no existe."""
    from unittest.mock import patch
    from services import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(gestor_dashboard, 'rendimiento_empleado', return_value=None):
        resp = client.get('/dashboard/rendimiento/99999')
        assert resp.status_code == 404


def test_rendimiento_empleado_json_devuelve_datos(client):
    """GET /dashboard/rendimiento/<id> devuelve los datos del empleado."""
    from unittest.mock import patch
    from services import gestor_dashboard

    fake = {
        'nombre': 'Ana García',
        'rol_sistema': 'picker',
        'kpis': {'pedidos': 5, 'tiempo_medio_min': 12, 'mejor_tiempo_min': 8, 'incidencias': 1},
        'pedidos_por_dia': [],
        'turnos_recientes': [],
        'ultimos_pedidos': [],
    }

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(gestor_dashboard, 'rendimiento_empleado', return_value=fake):
        resp = client.get('/dashboard/rendimiento/1')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['nombre'] == 'Ana García'
        assert 'kpis' in data


# ── Task 3: Template ─────────────────────────────────────────────────────────

def test_rendimiento_template_cargable_en_jinja2(app):
    """rendimiento.html se puede cargar en Jinja2 sin errores."""
    with app.app_context():
        template = app.jinja_env.get_template('dashboard/rendimiento.html')
        assert template is not None


def test_rendimiento_html_contiene_nav_links(client):
    """GET /dashboard/rendimiento incluye los links de navegación."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/rendimiento')
    assert resp.status_code == 200
    html = resp.data.decode()
    for ruta in ['/dashboard', '/dashboard/monitor', '/dashboard/historial',
                 '/dashboard/turnos', '/dashboard/estadisticas']:
        assert ruta in html, f"Link {ruta} no encontrado en rendimiento.html"


def test_rendimiento_html_contiene_alpine_app(client):
    """GET /dashboard/rendimiento incluye x-data rendimientoApp()."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/rendimiento')
    assert resp.status_code == 200
    assert b'rendimientoApp' in resp.data
