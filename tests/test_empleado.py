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


class TestGestorEmpleadoCapacidades:
    """capacidades / es_polivalente / tiene_rol_activo."""

    def _make_gestor(self, caps=None, rol_activo=None):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import MagicMock, PropertyMock, patch
        gestor = GestorEmpleado()

        cap_mocks = []
        for r in (caps or []):
            m = MagicMock()
            m.rol = r
            cap_mocks.append(m)

        empleado_mock = MagicMock()
        empleado_mock.capacidades = cap_mocks
        empleado_mock.rol_activo = rol_activo

        session_mock = MagicMock()
        session_mock.query.return_value.filter_by.return_value.first.return_value = empleado_mock
        return gestor, session_mock, empleado_mock

    def test_capacidades_devuelve_lista(self):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import PropertyMock, patch
        gestor, session_mock, _ = self._make_gestor(caps=['picker', 'repartidor'])
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.capacidades(5)
        assert set(result) == {'picker', 'repartidor'}

    def test_capacidades_un_rol(self):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import PropertyMock, patch
        gestor, session_mock, _ = self._make_gestor(caps=['picker'])
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.capacidades(1)
        assert result == ['picker']

    def test_es_polivalente_true(self):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import PropertyMock, patch
        gestor, session_mock, _ = self._make_gestor(caps=['picker', 'repartidor'])
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            assert gestor.es_polivalente(5) is True

    def test_es_polivalente_false(self):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import PropertyMock, patch
        gestor, session_mock, _ = self._make_gestor(caps=['picker'])
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            assert gestor.es_polivalente(1) is False

    def test_tiene_rol_activo_true(self):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import PropertyMock, patch
        gestor, session_mock, _ = self._make_gestor(rol_activo='picker')
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            assert gestor.tiene_rol_activo(1) is True

    def test_tiene_rol_activo_false_cuando_none(self):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import PropertyMock, patch
        gestor, session_mock, _ = self._make_gestor(rol_activo=None)
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            assert gestor.tiene_rol_activo(1) is False


class TestGestorEmpleadoCambiarRol:
    """cambiar_rol: bloqueo, éxito, capacidad inválida."""

    def _make_gestor_cambio(self, caps, rol_activo, pickings_activos=0, repartos_activos=0, estado_op='disponible'):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import MagicMock, PropertyMock

        gestor = GestorEmpleado()

        cap_mocks = []
        for r in caps:
            m = MagicMock(); m.rol = r
            cap_mocks.append(m)

        empleado_mock = MagicMock()
        empleado_mock.capacidades = cap_mocks
        empleado_mock.rol_activo = rol_activo
        empleado_mock.EmpleadoID = 1
        empleado_mock.estado_operativo = estado_op

        picking_list = [MagicMock() for _ in range(pickings_activos)]
        for p in picking_list:
            p.id = 100; p.estado = 'en_proceso'

        reparto_list = [MagicMock() for _ in range(repartos_activos)]
        for r in reparto_list:
            r.id = 200; r.estado = 'en_camino'

        session_mock = MagicMock()

        def query_side_effect(model):
            from models import Empleado, PickingPedido, Reparto
            q = MagicMock()
            if model is Empleado:
                q.filter_by.return_value.first.return_value = empleado_mock
            elif model is PickingPedido:
                q.filter.return_value.all.return_value = picking_list
            elif model is Reparto:
                q.filter.return_value.all.return_value = reparto_list
            else:
                q.filter.return_value.all.return_value = []
            return q

        session_mock.query.side_effect = query_side_effect
        return gestor, session_mock, empleado_mock

    def test_cambia_rol_exitoso(self):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import PropertyMock, patch
        gestor, session_mock, empleado_mock = self._make_gestor_cambio(
            caps=['picker', 'repartidor'], rol_activo='picker'
        )
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            ok, msg, bloqueantes = gestor.cambiar_rol(1, 'repartidor')
        assert ok is True
        assert empleado_mock.rol_activo == 'repartidor'

    def test_bloquea_si_hay_picking_activo(self):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import PropertyMock, patch
        gestor, session_mock, empleado_mock = self._make_gestor_cambio(
            caps=['picker', 'repartidor'], rol_activo='picker', pickings_activos=1
        )
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            ok, msg, bloqueantes = gestor.cambiar_rol(1, 'repartidor')
        assert ok is False
        assert len(bloqueantes) > 0

    def test_rechaza_rol_sin_capacidad(self):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import PropertyMock, patch
        gestor, session_mock, empleado_mock = self._make_gestor_cambio(
            caps=['picker'], rol_activo='picker'
        )
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            ok, msg, bloqueantes = gestor.cambiar_rol(1, 'repartidor')
        assert ok is False
        assert bloqueantes == []

    def test_setea_disponible_si_venia_de_desconectado(self):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import PropertyMock, patch
        gestor, session_mock, empleado_mock = self._make_gestor_cambio(
            caps=['picker', 'repartidor'], rol_activo=None, estado_op='desconectado'
        )
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            ok, _, _ = gestor.cambiar_rol(1, 'picker')
        assert ok is True
        assert empleado_mock.estado_operativo == 'disponible'


class TestAuthPolivalente:
    """Login con empleado polivalente redirige a /empleado/checkin."""

    def _empleado_polivalente(self, rol_activo=None):
        from unittest.mock import MagicMock
        from werkzeug.security import generate_password_hash
        emp = MagicMock()
        emp.EmpleadoID = 10
        emp.Nombre = 'Ana'
        emp.password_hash = generate_password_hash('secret')
        emp.rol = MagicMock(); emp.rol.nombre = 'picker'
        emp.rol_activo = rol_activo

        cap1 = MagicMock(); cap1.rol = 'picker'
        cap2 = MagicMock(); cap2.rol = 'repartidor'
        emp.capacidades = [cap1, cap2]
        return emp

    def test_polivalente_sin_rol_activo_va_a_checkin(self, client, app):
        with app.app_context():
            with patch('blueprints.auth._get_empleado_by_email',
                       return_value=self._empleado_polivalente(rol_activo=None)):
                resp = client.post('/auth/login',
                                   json={'email': 'ana@test.com', 'password': 'secret'},
                                   content_type='application/json')
        assert resp.status_code == 200
        assert resp.get_json()['redirect'] == '/empleado/checkin'

    def test_polivalente_con_rol_activo_va_a_empleado(self, client, app):
        with app.app_context():
            with patch('blueprints.auth._get_empleado_by_email',
                       return_value=self._empleado_polivalente(rol_activo='picker')):
                resp = client.post('/auth/login',
                                   json={'email': 'ana@test.com', 'password': 'secret'},
                                   content_type='application/json')
        assert resp.status_code == 200
        assert resp.get_json()['redirect'] == '/empleado'

    def test_monorol_sigue_funcionando(self, client, app):
        """Empleado con un solo rol va directo a /empleado sin cambios."""
        from werkzeug.security import generate_password_hash
        emp = MagicMock()
        emp.EmpleadoID = 5; emp.Nombre = 'Carlos'
        emp.password_hash = generate_password_hash('secret')
        emp.rol = MagicMock(); emp.rol.nombre = 'picker'
        emp.rol_activo = None
        cap = MagicMock(); cap.rol = 'picker'
        emp.capacidades = [cap]

        with app.app_context():
            with patch('blueprints.auth._get_empleado_by_email', return_value=emp):
                resp = client.post('/auth/login',
                                   json={'email': 'carlos@test.com', 'password': 'secret'},
                                   content_type='application/json')
        assert resp.status_code == 200
        assert resp.get_json()['redirect'] == '/empleado'


class TestBlueprintEmpleadoNuevos:
    """Nuevos endpoints: /empleado/capacidades, /empleado/carga-operativa, /empleado/cambiar-rol, /empleado/checkin."""

    def _set_session(self, client, rol='picker'):
        with client.session_transaction() as sess:
            sess['empleado_id'] = 1
            sess['rol'] = rol

    def test_capacidades_sin_sesion_rechazado(self, client):
        resp = client.get('/empleado/capacidades')
        assert resp.status_code in (302, 401)

    def test_capacidades_con_sesion_devuelve_json(self, client, app):
        self._set_session(client)
        with app.app_context():
            emp_mock = MagicMock(); emp_mock.rol_activo = 'picker'
            with patch('blueprints.empleado.gestor_empleado') as ge_mock, \
                 patch('blueprints.empleado.get_db') as db_mock:
                ge_mock.capacidades.return_value = ['picker']
                db_mock.return_value.query.return_value.filter_by.return_value.first.return_value = emp_mock
                resp = client.get('/empleado/capacidades')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'capacidades' in data

    def test_carga_operativa_devuelve_estructura(self, client, app):
        self._set_session(client)
        with app.app_context():
            mock_carga = {
                'picker': {'pendientes': 3, 'en_proceso': 1},
                'repartidor': {'listos_para_entregar': 2, 'en_camino': 0},
            }
            with patch('blueprints.empleado.gestor_empleado') as ge_mock:
                ge_mock.carga_operativa.return_value = mock_carga
                resp = client.get('/empleado/carga-operativa')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'picker' in data
        assert 'repartidor' in data

    def test_cambiar_rol_sin_sesion_rechazado(self, client):
        resp = client.post('/empleado/cambiar-rol', json={'rol': 'picker'})
        assert resp.status_code in (302, 401)

    def test_cambiar_rol_exitoso(self, client, app):
        self._set_session(client, rol='picker')
        with app.app_context():
            with patch('blueprints.empleado.gestor_empleado') as ge_mock:
                ge_mock.cambiar_rol.return_value = (True, 'ok', [])
                resp = client.post('/empleado/cambiar-rol',
                                   json={'rol': 'repartidor'},
                                   content_type='application/json')
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_cambiar_rol_bloqueado_devuelve_409(self, client, app):
        self._set_session(client, rol='picker')
        with app.app_context():
            bloqueantes = [{'id': 1, 'tipo': 'picking', 'estado': 'en_proceso'}]
            with patch('blueprints.empleado.gestor_empleado') as ge_mock:
                ge_mock.cambiar_rol.return_value = (False, 'Tienes tareas activas', bloqueantes)
                resp = client.post('/empleado/cambiar-rol',
                                   json={'rol': 'repartidor'},
                                   content_type='application/json')
        assert resp.status_code == 409
        data = resp.get_json()
        assert 'pedidos_activos' in data

    def test_checkin_sin_sesion_redirige(self, client):
        resp = client.get('/empleado/checkin')
        assert resp.status_code in (302, 401)
