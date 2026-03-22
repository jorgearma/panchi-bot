# tests/test_dashboard_sprint2.py
from unittest.mock import patch, PropertyMock


# ── Task 1: Manager ──────────────────────────────────────────────────────────

def test_historial_pedidos_devuelve_claves_esperadas(app):
    """historial_pedidos() devuelve dict con pedidos, total, page, pages."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_q = mock_session.return_value.query.return_value
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.count.return_value = 0
            mock_q.offset.return_value = mock_q
            mock_q.limit.return_value = mock_q
            mock_q.all.return_value = []

            result = gestor_dashboard.historial_pedidos()

            assert 'pedidos' in result
            assert 'total' in result
            assert 'page' in result
            assert 'pages' in result
            assert result['pedidos'] == []
            assert result['total'] == 0


def test_historial_pedidos_paginacion_por_defecto(app):
    """historial_pedidos() usa page=1 y per_page=25 por defecto."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_q = mock_session.return_value.query.return_value
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.count.return_value = 100
            mock_q.offset.return_value = mock_q
            mock_q.limit.return_value = mock_q
            mock_q.all.return_value = []

            result = gestor_dashboard.historial_pedidos()

            assert result['page'] == 1
            assert result['pages'] == 4   # ceil(100/25)


def test_detalle_pedido_devuelve_none_si_no_existe(app):
    """detalle_pedido() devuelve None cuando el pedido_id no existe."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_session.return_value.query.return_value.filter_by.return_value.first.return_value = None

            result = gestor_dashboard.detalle_pedido(999999)

            assert result is None


def test_detalle_pedido_devuelve_claves_esperadas(app):
    """detalle_pedido() devuelve dict con pedido, items, historial, picking, reparto."""
    from unittest.mock import MagicMock
    from services import gestor_dashboard

    with app.app_context():
        pedido_mock = MagicMock()
        pedido_mock.PedidoID = 2001
        pedido_mock.FechaCreacion = None
        pedido_mock.FechaActualizacion = None
        pedido_mock.Estado = 'ENTREGADO'
        pedido_mock.forma_pago = 'online'
        pedido_mock.Total = None
        pedido_mock.TelefonoEntrega = '600000000'
        pedido_mock.DireccionEntrega = 'Calle Test 1'
        pedido_mock.Notas = None
        pedido_mock.cancel_reason = None
        pedido_mock.cliente = None
        pedido_mock.detalles = []
        pedido_mock.historial_estados = []
        pedido_mock.picking = None
        pedido_mock.reparto = None

        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_session.return_value.query.return_value.filter_by.return_value.first.return_value = pedido_mock

            result = gestor_dashboard.detalle_pedido(2001)

            assert result is not None
            assert 'pedido' in result
            assert 'items' in result
            assert 'historial' in result
            assert 'picking' in result
            assert 'reparto' in result


# ── Task 2: Routes ───────────────────────────────────────────────────────────

def test_historial_html_devuelve_200(client):
    """GET /dashboard/historial devuelve 200 para admin autenticado."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/historial')
    assert resp.status_code == 200
    assert b'historial' in resp.data.lower()


def test_historial_html_requiere_auth(client):
    """GET /dashboard/historial redirige a login sin sesión."""
    resp = client.get('/dashboard/historial')
    assert resp.status_code in (302, 401)


def test_historial_pedidos_json_devuelve_estructura(client):
    """GET /dashboard/historial-pedidos devuelve {pedidos, total, page, pages}."""
    from unittest.mock import patch
    from services import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(
        gestor_dashboard, 'historial_pedidos',
        return_value={"pedidos": [], "total": 0, "page": 1, "pages": 1}
    ):
        resp = client.get('/dashboard/historial-pedidos')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'pedidos' in data
        assert 'total' in data
        assert 'page' in data
        assert 'pages' in data


def test_historial_pedidos_json_pasa_filtros(client):
    """GET /dashboard/historial-pedidos pasa query params al manager."""
    from unittest.mock import patch, call
    from services import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(
        gestor_dashboard, 'historial_pedidos',
        return_value={"pedidos": [], "total": 0, "page": 1, "pages": 1}
    ) as mock_historial:
        client.get('/dashboard/historial-pedidos?estado=ENTREGADO&page=2')
        mock_historial.assert_called_once_with(
            desde=None, hasta=None, estado='ENTREGADO',
            forma_pago=None, q=None, page=2, per_page=25
        )


def test_detalle_pedido_json_devuelve_404_si_no_existe(client):
    """GET /dashboard/pedido/<id>/detalle devuelve 404 si no existe."""
    from unittest.mock import patch
    from services import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(gestor_dashboard, 'detalle_pedido', return_value=None):
        resp = client.get('/dashboard/pedido/999999/detalle')
        assert resp.status_code == 404


def test_detalle_pedido_json_devuelve_datos(client):
    """GET /dashboard/pedido/<id>/detalle devuelve los datos del pedido."""
    from unittest.mock import patch
    from services import gestor_dashboard

    fake_detalle = {
        "pedido": {"pedido_id": 2001, "estado": "ENTREGADO"},
        "items": [],
        "historial": [],
        "picking": None,
        "reparto": None,
    }

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(gestor_dashboard, 'detalle_pedido', return_value=fake_detalle):
        resp = client.get('/dashboard/pedido/2001/detalle')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['pedido']['pedido_id'] == 2001


# ── Task 3: Template ─────────────────────────────────────────────────────────

def test_historial_template_cargable_en_jinja2(app):
    """historial.html se puede cargar en Jinja2 sin errores de sintaxis."""
    with app.app_context():
        template = app.jinja_env.get_template('dashboard/historial.html')
        assert template is not None


def test_historial_html_contiene_nav_links(client):
    """GET /dashboard/historial incluye los links de navegación del partial."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/historial')
    assert resp.status_code == 200
    html = resp.data.decode()
    for ruta in ['/dashboard', '/dashboard/monitor', '/dashboard/turnos',
                 '/dashboard/rendimiento', '/dashboard/estadisticas']:
        assert ruta in html, f"Link {ruta} no encontrado en historial.html"


def test_historial_html_contiene_alpine_app(client):
    """GET /dashboard/historial incluye x-data historialApp()."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/historial')
    assert resp.status_code == 200
    assert b'historialApp' in resp.data
