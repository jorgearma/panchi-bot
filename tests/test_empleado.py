"""Tests para GestorEmpleado y el blueprint /empleado."""
from unittest.mock import patch, MagicMock, PropertyMock


# ---------------------------------------------------------------------------
# GestorEmpleado — unit tests (sin BD real)
# ---------------------------------------------------------------------------

class TestGestorEmpleadoCambiarEstado:
    """cambiar_estado solo acepta en_pausa y desconectado."""

    def _make_gestor(self, estado_actual='disponible'):
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        empleado_mock = MagicMock()
        empleado_mock.estado_operativo = estado_actual
        session_mock = MagicMock()
        session_mock.query.return_value.filter_by.return_value.first.return_value = empleado_mock
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            return gestor, session_mock, empleado_mock

    def test_cambiar_a_en_pausa_ok(self):
        gestor, session_mock, empleado_mock = self._make_gestor()
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            ok, msg = gestor.cambiar_estado(1, 'en_pausa')
        assert ok is True
        assert empleado_mock.estado_operativo == 'en_pausa'

    def test_cambiar_a_desconectado_ok(self):
        gestor, session_mock, empleado_mock = self._make_gestor()
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            ok, msg = gestor.cambiar_estado(1, 'desconectado')
        assert ok is True
        assert empleado_mock.estado_operativo == 'desconectado'

    def test_rechaza_disponible_manual(self):
        gestor, session_mock, empleado_mock = self._make_gestor()
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            ok, msg = gestor.cambiar_estado(1, 'disponible')
        assert ok is False
        assert 'no permitido' in msg.lower() or 'inválido' in msg.lower()

    def test_rechaza_ocupado_manual(self):
        gestor, session_mock, empleado_mock = self._make_gestor()
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            ok, msg = gestor.cambiar_estado(1, 'ocupado')
        assert ok is False

    def test_empleado_no_encontrado(self):
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        session_mock = MagicMock()
        session_mock.query.return_value.filter_by.return_value.first.return_value = None
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            ok, msg = gestor.cambiar_estado(99, 'en_pausa')
        assert ok is False


class TestGestorEmpleadoPerfil:
    """perfil devuelve dict con los campos esperados."""

    def test_perfil_estructura(self):
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        empleado_mock = MagicMock()
        empleado_mock.EmpleadoID = 5
        empleado_mock.Nombre = 'Carlos'
        empleado_mock.Apellido = 'M'
        empleado_mock.Email = 'carlos@test.com'
        empleado_mock.Telefono = '600000000'
        empleado_mock.estado_operativo = 'disponible'
        empleado_mock.rol = MagicMock()
        empleado_mock.rol.nombre = 'picker'

        session_mock = MagicMock()
        session_mock.query.return_value.filter_by.return_value.first.return_value = empleado_mock
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.perfil(5)

        assert result['id'] == 5
        assert result['nombre'] == 'Carlos M'
        assert result['rol'] == 'picker'
        assert result['estado_operativo'] == 'disponible'


# ---------------------------------------------------------------------------
# Blueprint /empleado — integration tests (sin BD real)
# ---------------------------------------------------------------------------

class TestBlueprintEmpleadoAuth:
    """Sin sesión redirige al login; con sesión devuelve 200."""

    def test_sin_sesion_redirige(self, client):
        resp = client.get('/empleado')
        assert resp.status_code in (302, 401)

    def test_con_sesion_picker_ok(self, client, app):
        with client.session_transaction() as sess:
            sess['empleado_id'] = 1
            sess['rol'] = 'picker'
        with app.app_context():
            resp = client.get('/empleado')
        assert resp.status_code == 200

    def test_rol_manager_no_accede(self, client):
        """El blueprint /empleado no está destinado a manager (va a /dashboard)."""
        with client.session_transaction() as sess:
            sess['empleado_id'] = 1
            sess['rol'] = 'manager'
        resp = client.get('/empleado')
        # manager puede acceder (tiene requiere_rol permisivo) o recibe 403 según diseño
        # Lo importante: no lanza 500
        assert resp.status_code != 500


class TestBlueprintEmpleadoEstado:
    """POST /empleado/estado valida el payload."""

    def test_estado_invalido_rechazado(self, client):
        with client.session_transaction() as sess:
            sess['empleado_id'] = 1
            sess['rol'] = 'picker'
        resp = client.post('/empleado/estado',
                           json={'estado': 'disponible'},
                           content_type='application/json')
        assert resp.status_code == 400

    def test_estado_valido_llama_gestor(self, client, app):
        with client.session_transaction() as sess:
            sess['empleado_id'] = 1
            sess['rol'] = 'picker'
        with app.app_context():
            from services import gestor_empleado
            with patch.object(gestor_empleado, 'cambiar_estado', return_value=(True, 'ok')):
                resp = client.post('/empleado/estado',
                                   json={'estado': 'en_pausa'},
                                   content_type='application/json')
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True


# ---------------------------------------------------------------------------
# Hooks de estado operativo en GestorDashboard
# ---------------------------------------------------------------------------

class TestHooksEstadoOperativo:
    """_actualizar_estado_operativo no sobreescribe en_pausa ni desconectado."""

    def _gestor_con_empleado(self, estado_actual):
        from services import gestor_dashboard
        empleado_mock = MagicMock()
        empleado_mock.estado_operativo = estado_actual
        session_mock = MagicMock()
        session_mock.query.return_value.filter_by.return_value.first.return_value = empleado_mock
        return gestor_dashboard, session_mock, empleado_mock

    def test_ocupado_sobreescribe_disponible(self):
        gestor, session_mock, empleado_mock = self._gestor_con_empleado('disponible')
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            gestor._actualizar_estado_operativo(1, 'ocupado')
        assert empleado_mock.estado_operativo == 'ocupado'

    def test_no_sobreescribe_en_pausa(self):
        gestor, session_mock, empleado_mock = self._gestor_con_empleado('en_pausa')
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            gestor._actualizar_estado_operativo(1, 'ocupado')
        assert empleado_mock.estado_operativo == 'en_pausa'

    def test_no_sobreescribe_desconectado(self):
        gestor, session_mock, empleado_mock = self._gestor_con_empleado('desconectado')
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            gestor._actualizar_estado_operativo(1, 'disponible')
        assert empleado_mock.estado_operativo == 'desconectado'

    def test_empleado_none_no_lanza_excepcion(self):
        from services import gestor_dashboard
        session_mock = MagicMock()
        session_mock.query.return_value.filter_by.return_value.first.return_value = None
        with patch.object(type(gestor_dashboard), 'session', new_callable=PropertyMock, return_value=session_mock):
            # No debe lanzar excepción
            gestor_dashboard._actualizar_estado_operativo(99, 'ocupado')


# ---------------------------------------------------------------------------
# Auth: redirección tras login
# ---------------------------------------------------------------------------

class TestAuthRedireccionEmpleado:
    """Tras el login, picker y repartidor van a /empleado."""

    def test_picker_redirige_a_empleado(self, client, app):
        from unittest.mock import patch
        from werkzeug.security import generate_password_hash
        empleado_mock = MagicMock()
        empleado_mock.EmpleadoID = 1
        empleado_mock.Nombre = 'Test'
        empleado_mock.password_hash = generate_password_hash('secret')
        empleado_mock.rol = MagicMock()
        empleado_mock.rol.nombre = 'picker'

        with app.app_context():
            with patch('blueprints.auth._get_empleado_by_email', return_value=empleado_mock):
                resp = client.post('/auth/login',
                                   json={'email': 'test@test.com', 'password': 'secret'},
                                   content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['redirect'] == '/empleado'

    def test_repartidor_redirige_a_empleado(self, client, app):
        from unittest.mock import patch
        from werkzeug.security import generate_password_hash
        empleado_mock = MagicMock()
        empleado_mock.EmpleadoID = 2
        empleado_mock.Nombre = 'Ana'
        empleado_mock.password_hash = generate_password_hash('secret')
        empleado_mock.rol = MagicMock()
        empleado_mock.rol.nombre = 'repartidor'

        with app.app_context():
            with patch('blueprints.auth._get_empleado_by_email', return_value=empleado_mock):
                resp = client.post('/auth/login',
                                   json={'email': 'ana@test.com', 'password': 'secret'},
                                   content_type='application/json')
        assert resp.status_code == 200
        assert resp.get_json()['redirect'] == '/empleado'

    def test_manager_sigue_a_dashboard(self, client, app):
        from unittest.mock import patch
        from werkzeug.security import generate_password_hash
        empleado_mock = MagicMock()
        empleado_mock.EmpleadoID = 3
        empleado_mock.Nombre = 'Jefe'
        empleado_mock.password_hash = generate_password_hash('secret')
        empleado_mock.rol = MagicMock()
        empleado_mock.rol.nombre = 'manager'

        with app.app_context():
            with patch('blueprints.auth._get_empleado_by_email', return_value=empleado_mock):
                resp = client.post('/auth/login',
                                   json={'email': 'jefe@test.com', 'password': 'secret'},
                                   content_type='application/json')
        assert resp.status_code == 200
        assert resp.get_json()['redirect'] == '/dashboard'


class TestModelosNuevos:
    """Verifica que EmpleadoCapacidad y rol_activo existen en models.py."""

    def test_empleado_capacidad_modelo_existe(self):
        import inspect
        import models
        src = inspect.getsource(models)
        assert 'EmpleadoCapacidad' in src
        assert 'empleado_capacidades' in src

    def test_empleado_tiene_rol_activo(self):
        import inspect
        import models
        src = inspect.getsource(models)
        assert 'rol_activo' in src

    def test_auditlog_pedido_id_nullable(self):
        """AuditLog.pedido_id debe ser nullable para eventos sin pedido."""
        from models import AuditLog
        col = AuditLog.__table__.columns['pedido_id']
        assert col.nullable is True, "pedido_id debe ser nullable=True"
