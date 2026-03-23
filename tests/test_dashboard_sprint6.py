# tests/test_dashboard_sprint6.py
from unittest.mock import patch, PropertyMock, MagicMock
import pytest


# ── Task 1: Manager ──────────────────────────────────────────────────────────

def test_turnos_planificacion_devuelve_claves_esperadas(app):
    """turnos_planificacion() devuelve {turnos, total, page, pages}."""
    from services import gestor_dashboard
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

            result = gestor_dashboard.turnos_planificacion()

            assert 'turnos' in result
            assert 'total' in result
            assert 'page' in result
            assert 'pages' in result
            assert isinstance(result['turnos'], list)


def test_crear_turno_devuelve_ok_con_datos_validos(app):
    """crear_turno() devuelve {ok: True, turno_id} cuando el empleado existe."""
    from services import gestor_dashboard
    with app.app_context():
        emp_mock = MagicMock()
        emp_mock.EmpleadoID = 1

        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            s = mock_session.return_value
            s.query.return_value.filter_by.return_value.first.return_value = emp_mock
            s.add = MagicMock()
            s.flush = MagicMock()
            s.commit = MagicMock()

            # Simulate ORM populating turno.id after flush() (not after add())
            def flush_side_effect():
                for call in s.add.call_args_list:
                    obj = call[0][0]
                    obj.id = 42
            s.flush.side_effect = flush_side_effect

            result = gestor_dashboard.crear_turno(
                empleado_id=1,
                fecha='2026-04-01',
                hora_inicio='09:00',
                hora_fin='17:00',
            )

            assert result['ok'] is True
            assert 'turno_id' in result
            s.flush.assert_called_once()


def test_crear_turno_devuelve_error_si_empleado_no_existe(app):
    """crear_turno() devuelve {ok: False} si el empleado no existe."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_session.return_value.query.return_value.filter_by.return_value.first.return_value = None

            result = gestor_dashboard.crear_turno(
                empleado_id=99999,
                fecha='2026-04-01',
                hora_inicio='09:00',
                hora_fin='17:00',
            )

            assert result['ok'] is False
            assert 'error' in result


def test_editar_turno_devuelve_ok_si_turno_existe(app):
    """editar_turno() devuelve {ok: True} cuando el turno existe y no está cancelado."""
    from services import gestor_dashboard
    with app.app_context():
        turno_mock = MagicMock()
        turno_mock.estado = 'planificado'

        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            s = mock_session.return_value
            s.query.return_value.filter_by.return_value.first.return_value = turno_mock
            s.commit = MagicMock()

            result = gestor_dashboard.editar_turno(
                turno_id=1,
                hora_inicio='10:00',
                hora_fin='18:00',
            )

            assert result['ok'] is True


def test_editar_turno_devuelve_error_si_no_existe(app):
    """editar_turno() devuelve {ok: False} si el turno no existe."""
    from services import gestor_dashboard
    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            mock_session.return_value.query.return_value.filter_by.return_value.first.return_value = None

            result = gestor_dashboard.editar_turno(turno_id=99999, hora_inicio='09:00')

            assert result['ok'] is False
            assert 'error' in result


def test_cancelar_turno_devuelve_ok_si_turno_existe(app):
    """cancelar_turno() devuelve {ok: True} cuando el turno existe."""
    from services import gestor_dashboard
    with app.app_context():
        turno_mock = MagicMock()
        turno_mock.estado = 'planificado'

        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            s = mock_session.return_value
            s.query.return_value.filter_by.return_value.first.return_value = turno_mock
            s.commit = MagicMock()

            result = gestor_dashboard.cancelar_turno(turno_id=1)

            assert result['ok'] is True
            assert turno_mock.estado == 'cancelado'


# ── Task 2: Routes ────────────────────────────────────────────────────────────

def test_turnos_planificacion_json_devuelve_estructura(client):
    """GET /dashboard/turnos/planificacion devuelve {turnos, total, page, pages}."""
    from unittest.mock import patch
    from services import gestor_dashboard

    fake = {'turnos': [], 'total': 0, 'page': 1, 'pages': 1}

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(gestor_dashboard, 'turnos_planificacion', return_value=fake):
        resp = client.get('/dashboard/turnos/planificacion')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'turnos' in data
        assert 'total' in data


def test_crear_turno_route_devuelve_ok(client):
    """POST /dashboard/turnos/crear devuelve {ok: True}."""
    from unittest.mock import patch
    from services import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(gestor_dashboard, 'crear_turno', return_value={'ok': True, 'turno_id': 10}):
        resp = client.post('/dashboard/turnos/crear', json={
            'empleado_id': 1, 'fecha': '2026-04-01',
            'hora_inicio': '09:00', 'hora_fin': '17:00',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True


def test_crear_turno_route_400_si_faltan_campos(client):
    """POST /dashboard/turnos/crear devuelve 400 si faltan campos obligatorios."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    resp = client.post('/dashboard/turnos/crear', json={})
    assert resp.status_code == 400


def test_editar_turno_route_devuelve_ok(client):
    """POST /dashboard/turnos/<id>/editar devuelve {ok: True}."""
    from unittest.mock import patch
    from services import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(gestor_dashboard, 'editar_turno', return_value={'ok': True}):
        resp = client.post('/dashboard/turnos/1/editar', json={'hora_inicio': '10:00'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True


def test_cancelar_turno_route_devuelve_ok(client):
    """POST /dashboard/turnos/<id>/cancelar devuelve {ok: True}."""
    from unittest.mock import patch
    from services import gestor_dashboard

    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    with patch.object(gestor_dashboard, 'cancelar_turno', return_value={'ok': True}):
        resp = client.post('/dashboard/turnos/1/cancelar')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True


# ── Task 3: Template ──────────────────────────────────────────────────────────

def test_turnos_template_cargable_jinja2(app):
    """turnos.html se puede cargar en Jinja2 sin errores tras los cambios."""
    with app.app_context():
        template = app.jinja_env.get_template('dashboard/turnos.html')
        assert template is not None


def test_turnos_html_contiene_tab_planificacion(client):
    """GET /dashboard/turnos incluye el tab de Planificación."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/turnos')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Planificación' in html
    assert "tab = 'plan'" in html


def test_turnos_html_contiene_estado_alpine_planificacion(client):
    """GET /dashboard/turnos incluye estado Alpine para planificación."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'
    resp = client.get('/dashboard/turnos')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'planTurnos' in html
    assert 'cargarPlan' in html
    assert 'modalAbierto' in html
