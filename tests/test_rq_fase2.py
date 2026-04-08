import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, call


# ── Task 1: Models ────────────────────────────────────────────────────────────

def test_failed_job_model_campos():
    """FailedJob tiene todos los campos requeridos."""
    from models import FailedJob
    fj = FailedJob(
        job_id="abc123",
        job_type="descontar_stock_picking_job",
        queue_name="dashboard",
        payload='["picking_id_42"]',
        error="Connection refused",
        retries=3,
    )
    assert fj.job_id == "abc123"
    assert fj.job_type == "descontar_stock_picking_job"
    assert fj.queue_name == "dashboard"
    assert fj.retries == 3
    assert fj.resolved_at is None


def test_picking_pedido_tiene_stock_descontado():
    """PickingPedido tiene columna stock_descontado NOT NULL DEFAULT False."""
    from models import PickingPedido
    from sqlalchemy import inspect as sa_inspect

    mapper = sa_inspect(PickingPedido)
    col = mapper.columns['stock_descontado']
    assert col is not None, "stock_descontado no definido en PickingPedido"
    assert col.nullable is False
    # default aplicado en SQL INSERT, no en construcción Python
    assert col.default.arg is False


# ── Task 2: rq_callbacks ──────────────────────────────────────────────────────

def test_on_job_failure_persiste_en_bd(app):
    """on_job_failure crea FailedJob en BD."""
    from utils.rq_callbacks import on_job_failure
    from models import FailedJob

    job = MagicMock()
    job.id = "job-123"
    job.func_name = "descontar_stock_picking_job"
    job.origin = "dashboard"
    job.args = (42,)
    job.retries_left = 0

    error = Exception("Connection refused")

    with app.app_context():
        with patch('database.SessionLocal') as mock_sl, \
             patch('utils.rq_callbacks.sentry_sdk') as mock_sentry:
            mock_s = MagicMock()
            mock_sl.return_value = mock_s

            on_job_failure(job, None, type(error), error, None)

            mock_s.add.assert_called_once()
            added = mock_s.add.call_args[0][0]
            assert isinstance(added, FailedJob)
            assert added.job_id == "job-123"
            assert added.job_type == "descontar_stock_picking_job"
            assert added.queue_name == "dashboard"
            mock_s.commit.assert_called_once()
            mock_sentry.capture_exception.assert_called_once_with(error)


def test_on_job_failure_sentry_si_bd_cae(app):
    """Si BD falla en on_job_failure, Sentry recibe alerta igualmente."""
    from utils.rq_callbacks import on_job_failure

    job = MagicMock()
    job.id = "job-456"
    job.func_name = "notificar_picker_job"
    job.origin = "whatsapp"
    job.args = ("+34600000001", 99)
    job.retries_left = 0
    error = Exception("timeout")

    with app.app_context():
        with patch('database.SessionLocal') as mock_sl, \
             patch('utils.rq_callbacks.sentry_sdk') as mock_sentry:
            mock_s = MagicMock()
            mock_s.commit.side_effect = Exception("BD caída")
            mock_sl.return_value = mock_s

            on_job_failure(job, None, type(error), error, None)

            mock_sentry.capture_exception.assert_called_once_with(error)


def test_sentry_job_decorator_propaga_excepcion():
    """@sentry_job propaga excepciones del job."""
    from utils.rq_callbacks import sentry_job

    @sentry_job(op_name="rq.test")
    def job_que_falla():
        raise ValueError("algo salió mal")

    with patch('utils.rq_callbacks.sentry_sdk'):
        with pytest.raises(ValueError, match="algo salió mal"):
            job_que_falla()


def test_sentry_job_decorator_devuelve_resultado():
    """@sentry_job devuelve el resultado del job correctamente."""
    from utils.rq_callbacks import sentry_job

    @sentry_job(op_name="rq.test")
    def job_exitoso(x):
        return x * 2

    with patch('utils.rq_callbacks.sentry_sdk') as mock_sentry:
        mock_tx = MagicMock()
        mock_sentry.start_transaction.return_value.__enter__ = MagicMock(return_value=mock_tx)
        mock_sentry.start_transaction.return_value.__exit__ = MagicMock(return_value=False)

        result = job_exitoso(5)
        assert result == 10


# ── Task 3: picking_flujo ─────────────────────────────────────────────────────

def test_completar_picking_sin_thread():
    """completar_picking NO usa threading.Thread."""
    import managers.dashboard.picking_flujo as modulo
    import inspect

    source = inspect.getsource(modulo)
    assert 'Thread(' not in source, "picking_flujo.py todavía tiene Thread() — eliminar daemon threads"


def test_asignar_picker_race_condition_devuelve_ok(app):
    """IntegrityError en asignar_picker → (True, msg), no 500."""
    from container import gestor_dashboard
    from sqlalchemy.exc import IntegrityError
    from unittest.mock import PropertyMock

    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            s = mock_session.return_value
            pedido_mock = MagicMock()
            pedido_mock.Estado = 'pagado'
            pedido_mock.detalles = []
            empleado_mock = MagicMock()
            empleado_mock.EmpleadoID = 5
            empleado_mock.Telefono = "+34600000001"

            # pedido, empleado, picking (no existe → INSERT → IntegrityError)
            s.query.return_value.filter_by.return_value.first.side_effect = [
                pedido_mock, empleado_mock, None,
            ]
            s.flush = MagicMock()
            s.add = MagicMock()
            s.commit.side_effect = IntegrityError("UNIQUE constraint", None, None)

            ok, msg = gestor_dashboard.asignar_picker(1, 5)

            assert ok is True
            assert "asignado" in msg.lower()


def test_asignar_picker_encola_notificacion_post_commit(app):
    """asignar_picker encola notificar_picker_job tras commit exitoso."""
    from container import gestor_dashboard
    from unittest.mock import PropertyMock
    import message_queue

    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session, \
        patch.object(message_queue.queue_whatsapp, 'enqueue') as mock_enqueue, \
        patch('managers.dashboard.jobs.notificar_picker_job', create=True):
            s = mock_session.return_value
            pedido_mock = MagicMock()
            pedido_mock.Estado = 'pagado'
            pedido_mock.detalles = []
            empleado_mock = MagicMock()
            empleado_mock.EmpleadoID = 5
            empleado_mock.Telefono = "+34600000001"
            picking_mock = MagicMock()

            s.query.return_value.filter_by.return_value.first.side_effect = [
                pedido_mock, empleado_mock, picking_mock,
            ]
            s.commit = MagicMock()

            with patch.object(gestor_dashboard, '_actualizar_estado_operativo'):
                gestor_dashboard.asignar_picker(1, 5)

            mock_enqueue.assert_called_once()
            call_kwargs = mock_enqueue.call_args[1]
            assert call_kwargs.get('retry') == 3


def test_completar_picking_encola_picking_id_no_lista(app):
    """completar_picking encola descontar_stock_picking_job con picking_id int."""
    from container import gestor_dashboard
    from unittest.mock import PropertyMock
    from states import EstadoPicking, EstadoPedido
    import message_queue

    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session, \
        patch.object(message_queue.queue_dashboard, 'enqueue') as mock_enqueue, \
        patch('managers.dashboard.jobs.descontar_stock_picking_job', create=True):
            s = mock_session.return_value
            picking_mock = MagicMock()
            picking_mock.id = 77
            picking_mock.empleado_id = 5
            picking_mock.estado = EstadoPicking.EN_PROCESO.value
            picking_mock.items = []
            pedido_mock = MagicMock()
            pedido_mock.Estado = EstadoPedido.EN_PREPARACION.value
            pedido_mock.PedidoID = 10
            picking_mock.pedido = pedido_mock

            s.query.return_value.filter_by.return_value.first.side_effect = [
                picking_mock,
                None,  # reparto_existente check → None → crea Reparto
            ]
            s.commit = MagicMock()
            s.add = MagicMock()
            s.expire_all = MagicMock()
            s.query.return_value.filter.return_value.count.return_value = 1

            with patch.object(gestor_dashboard, '_actualizar_estado_operativo'):
                ok, msg, _ = gestor_dashboard.completar_picking(77)

            assert ok is True
            # Verificar que se encoló con picking_id=77 (int), no lista
            enqueue_calls = mock_enqueue.call_args_list
            # queue_dashboard.enqueue puede ser llamado desde _actualizar_estado_operativo también
            # Verificar que alguna llamada pasó picking_id=77 como arg posicional
            stock_calls = [c for c in enqueue_calls if 77 in c[0]]
            assert len(stock_calls) >= 1, f"No se encoló con picking_id=77. Calls: {enqueue_calls}"


# ── Task 4: reparto_asignacion ────────────────────────────────────────────────

def test_asignar_repartidor_race_condition_devuelve_ok(app):
    """IntegrityError en asignar_repartidor → (True, msg), no 500."""
    from container import gestor_dashboard
    from sqlalchemy.exc import IntegrityError
    from unittest.mock import PropertyMock
    from states import EstadoPedido

    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session:
            s = mock_session.return_value
            pedido_mock = MagicMock()
            pedido_mock.Estado = EstadoPedido.PREPARADO.value
            empleado_mock = MagicMock()
            empleado_mock.EmpleadoID = 3
            empleado_mock.Telefono = "+34600000002"

            s.query.return_value.filter_by.return_value.first.side_effect = [
                pedido_mock, empleado_mock, None,
            ]
            s.add = MagicMock()
            s.commit.side_effect = IntegrityError("UNIQUE constraint", None, None)

            ok, msg = gestor_dashboard.asignar_repartidor(10, 3)

            assert ok is True


def test_asignar_repartidor_encola_notificacion_post_commit(app):
    """asignar_repartidor encola notificar_repartidor_job tras commit exitoso."""
    from container import gestor_dashboard
    from unittest.mock import PropertyMock
    from states import EstadoPedido
    import message_queue

    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session, \
        patch.object(message_queue.queue_whatsapp, 'enqueue') as mock_enqueue, \
        patch('managers.dashboard.jobs.notificar_repartidor_job', create=True):
            s = mock_session.return_value
            pedido_mock = MagicMock()
            pedido_mock.Estado = EstadoPedido.PREPARADO.value
            empleado_mock = MagicMock()
            empleado_mock.EmpleadoID = 3
            empleado_mock.Telefono = "+34600000002"
            reparto_mock = MagicMock()

            s.query.return_value.filter_by.return_value.first.side_effect = [
                pedido_mock, empleado_mock, reparto_mock,
            ]
            s.commit = MagicMock()

            with patch.object(gestor_dashboard, '_actualizar_estado_operativo'):
                gestor_dashboard.asignar_repartidor(10, 3)

            mock_enqueue.assert_called_once()
            call_kwargs = mock_enqueue.call_args[1]
            assert call_kwargs.get('retry') == 3


# ── Task 5: RQ Dashboard ─────────────────────────────────────────────────────

def test_rq_dashboard_requiere_login(app):
    """GET /rq-dashboard sin sesión activa → redirect a login."""
    with app.test_client() as client:
        response = client.get('/rq-dashboard', follow_redirects=False)
        assert response.status_code in (301, 302)
        assert '/auth/login' in response.headers.get('Location', '')


def test_completar_picking_operational_error_reintenta(app):
    """OperationalError en completar_picking.commit → reintenta hasta 3 veces."""
    from container import gestor_dashboard
    from sqlalchemy.exc import OperationalError
    from unittest.mock import PropertyMock
    from states import EstadoPicking, EstadoPedido

    with app.app_context():
        with patch.object(
            type(gestor_dashboard), 'session', new_callable=PropertyMock
        ) as mock_session, \
        patch('managers.dashboard.picking_flujo.time') as mock_time:
            s = mock_session.return_value
            mock_time.sleep = MagicMock()
            picking_mock = MagicMock()
            picking_mock.id = 1
            picking_mock.empleado_id = 5
            picking_mock.estado = EstadoPicking.EN_PROCESO.value
            picking_mock.items = []
            pedido_mock = MagicMock()
            pedido_mock.Estado = EstadoPedido.EN_PREPARACION.value
            pedido_mock.PedidoID = 1
            picking_mock.pedido = pedido_mock

            s.query.return_value.filter_by.return_value.first.return_value = picking_mock
            s.commit.side_effect = OperationalError("Connection reset", None, None)

            ok, msg, _ = gestor_dashboard.completar_picking(1)

            assert ok is False
            assert s.commit.call_count == 3


# ── Task 6: jobs.py ───────────────────────────────────────────────────────────

def test_notificar_picker_job_llama_whatsapp(app):
    """notificar_picker_job llama enviar_mensaje_whatsapp con teléfono y pedido_id."""
    from managers.dashboard.jobs import notificar_picker_job

    with app.app_context():
        with patch('services.whatsapp_service.enviar_mensaje_whatsapp') as mock_send:
            notificar_picker_job("+34600000001", 42)
            mock_send.assert_called_once()
            args = mock_send.call_args[0]
            assert "+34600000001" in args
            assert "42" in str(args)


def test_notificar_repartidor_job_llama_whatsapp(app):
    """notificar_repartidor_job llama enviar_mensaje_whatsapp con teléfono."""
    from managers.dashboard.jobs import notificar_repartidor_job

    with app.app_context():
        with patch('services.whatsapp_service.enviar_mensaje_whatsapp') as mock_send:
            notificar_repartidor_job("+34600000002", 99)
            mock_send.assert_called_once()
            args = mock_send.call_args[0]
            assert "+34600000002" in args


def test_descontar_stock_job_idempotente(app):
    """Segunda llamada con mismo picking_id → skip si stock_descontado == True."""
    from managers.dashboard.jobs import descontar_stock_picking_job

    with app.app_context():
        with patch('database.SessionLocal') as mock_sl:
            s = MagicMock()
            picking_mock = MagicMock()
            picking_mock.stock_descontado = True
            picking_mock.estado = 'completado'
            s.query.return_value.filter_by.return_value.first.return_value = picking_mock
            mock_sl.return_value = s

            descontar_stock_picking_job(77)

            s.commit.assert_not_called()


def test_descontar_stock_job_encontrado(app):
    """estado 'encontrado' → stock decrementado, stock_descontado = True."""
    from managers.dashboard.jobs import descontar_stock_picking_job
    from states import EstadoPicking

    with app.app_context():
        with patch('database.SessionLocal') as mock_sl:
            s = MagicMock()
            picking_mock = MagicMock()
            picking_mock.stock_descontado = False
            picking_mock.estado = EstadoPicking.COMPLETADO.value

            item_mock = MagicMock()
            item_mock.pedido_detalle = MagicMock(ProductoID=10, Cantidad=2)
            item_mock.estado = "encontrado"
            item_mock.cantidad_encontrada = 2
            picking_mock.items = [item_mock]

            producto_mock = MagicMock()
            producto_mock.Stock = 10
            producto_mock.Disponible = True

            s.query.return_value.filter_by.return_value.first.return_value = picking_mock
            s.query.return_value.filter_by.return_value.with_for_update.return_value.first.return_value = producto_mock
            mock_sl.return_value = s

            descontar_stock_picking_job(77)

            assert producto_mock.Stock == 8
            assert picking_mock.stock_descontado is True
            s.commit.assert_called_once()


def test_descontar_stock_job_sin_stock(app):
    """estado 'sin_stock' → stock=0, disponible=False, stock_descontado=True."""
    from managers.dashboard.jobs import descontar_stock_picking_job
    from states import EstadoPicking

    with app.app_context():
        with patch('database.SessionLocal') as mock_sl:
            s = MagicMock()
            picking_mock = MagicMock()
            picking_mock.stock_descontado = False
            picking_mock.estado = EstadoPicking.COMPLETADO.value

            item_mock = MagicMock()
            item_mock.pedido_detalle = MagicMock(ProductoID=5, Cantidad=1)
            item_mock.estado = "sin_stock"
            item_mock.cantidad_encontrada = None
            picking_mock.items = [item_mock]

            producto_mock = MagicMock()
            producto_mock.Stock = 3
            producto_mock.Disponible = True

            s.query.return_value.filter_by.return_value.first.return_value = picking_mock
            s.query.return_value.filter_by.return_value.with_for_update.return_value.first.return_value = producto_mock
            mock_sl.return_value = s

            descontar_stock_picking_job(77)

            assert producto_mock.Stock == 0
            assert producto_mock.Disponible is False
            assert picking_mock.stock_descontado is True


def test_descontar_stock_job_skip_si_no_completado(app):
    """picking.estado != COMPLETADO → skip sin commit."""
    from managers.dashboard.jobs import descontar_stock_picking_job

    with app.app_context():
        with patch('database.SessionLocal') as mock_sl:
            s = MagicMock()
            picking_mock = MagicMock()
            picking_mock.stock_descontado = False
            picking_mock.estado = 'en_proceso'
            mock_sl.return_value = s
            s.query.return_value.filter_by.return_value.first.return_value = picking_mock

            descontar_stock_picking_job(77)

            s.commit.assert_not_called()


# ── Task 7: _base.py ──────────────────────────────────────────────────────────

def test_actualizar_estado_operativo_usa_job_centralizado(app):
    """_actualizar_estado_operativo encola actualizar_estado_operativo_job de jobs.py."""
    from container import gestor_dashboard
    from managers.dashboard.jobs import actualizar_estado_operativo_job
    import message_queue

    with app.app_context():
        with patch.object(message_queue.queue_dashboard, 'enqueue') as mock_enqueue:
            gestor_dashboard._actualizar_estado_operativo(5, 'disponible')

            mock_enqueue.assert_called_once()
            call_args = mock_enqueue.call_args[0]
            assert call_args[0] is actualizar_estado_operativo_job
            assert call_args[1] == 5
            assert call_args[2] == 'disponible'


def test_base_no_tiene_ejecutar_actualizar_estado():
    """_base.py ya no tiene _ejecutar_actualizar_estado (movido a jobs.py)."""
    from managers.dashboard._base import GestorDashboardBase
    assert not hasattr(GestorDashboardBase, '_ejecutar_actualizar_estado'), \
        "_ejecutar_actualizar_estado debería estar en jobs.py, no en _base.py"
