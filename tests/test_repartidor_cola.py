import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from sqlalchemy.exc import SQLAlchemyError


def _mock_session(manager):
    patcher = patch.object(type(manager), 'session', new_callable=PropertyMock)
    mock_prop = patcher.start()
    mock_sess = MagicMock()
    mock_prop.return_value = mock_sess
    return patcher, mock_sess


class TestRepartosSinAsignar:

    def setup_method(self):
        from services import gestor_dashboard
        self.gd = gestor_dashboard

    def _mock_q_vacio(self):
        mock_q = MagicMock()
        mock_q.join.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.outerjoin.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = []
        return mock_q

    def test_devuelve_lista(self, app):
        from datetime import datetime, timedelta
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_pedido = MagicMock()
                mock_pedido.DireccionEntrega = 'Calle Mayor 10'
                mock_pedido.detalles = [MagicMock(), MagicMock(), MagicMock()]

                mock_rep = MagicMock()
                mock_rep.pedido_id = 42
                mock_rep.pedido = mock_pedido
                mock_rep.created_at = datetime.utcnow() - timedelta(minutes=3)

                # Primera query: Repartos PENDIENTE
                mock_q1 = self._mock_q_vacio()
                mock_q1.all.return_value = [mock_rep]
                # Segunda query: Pedidos sin Reparto (vacía — el pedido ya está en la primera)
                mock_q2 = self._mock_q_vacio()

                mock_sess.query.side_effect = [mock_q1, mock_q2]

                result = self.gd.repartos_sin_asignar()

                assert len(result) == 1
                assert result[0]['pedido_id'] == 42
                assert result[0]['n_items'] == 3
                assert result[0]['direccion_entrega'] == 'Calle Mayor 10'
                assert result[0]['segundos_esperando'] >= 0
            finally:
                patcher.stop()

    def test_vacio(self, app):
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_q = self._mock_q_vacio()
                mock_sess.query.return_value = mock_q

                result = self.gd.repartos_sin_asignar()
                assert result == []
            finally:
                patcher.stop()

    def test_hace_join_y_filter(self, app):
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_q = self._mock_q_vacio()
                mock_sess.query.return_value = mock_q

                self.gd.repartos_sin_asignar()

                assert mock_q.join.called or mock_q.outerjoin.called
                assert mock_q.filter.called
            finally:
                patcher.stop()


class TestReclamarReparto:

    def setup_method(self):
        from services import gestor_dashboard
        self.gd = gestor_dashboard

    def test_ok(self, app):
        """Reparto ya existe con repartidor_id=None — UPDATE atómico."""
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                from states import EstadoPedido
                mock_pedido = MagicMock()
                mock_pedido.Estado = EstadoPedido.PREPARADO.value

                mock_rep = MagicMock()
                mock_rep.repartidor_id = None

                mock_q_pedido = MagicMock()
                mock_q_pedido.filter_by.return_value = mock_q_pedido
                mock_q_pedido.first.return_value = mock_pedido

                mock_q_reparto = MagicMock()
                mock_q_reparto.filter_by.return_value = mock_q_reparto
                mock_q_reparto.first.return_value = mock_rep

                mock_q_update = MagicMock()
                mock_q_update.filter.return_value = mock_q_update
                mock_q_update.update.return_value = 1

                mock_sess.query.side_effect = [mock_q_pedido, mock_q_reparto, mock_q_update]

                with patch.object(self.gd, '_actualizar_estado_operativo') as mock_aso:
                    ok, msg = self.gd.reclamar_reparto(42, empleado_id=7)
                    assert ok is True
                    assert msg == 'ok'
                    mock_aso.assert_called_once_with(7, 'ocupado')
            finally:
                patcher.stop()

    def test_no_encontrado(self, app):
        """Pedido no existe o no está en PREPARADO."""
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_q = MagicMock()
                mock_q.filter_by.return_value = mock_q
                mock_q.first.return_value = None
                mock_sess.query.return_value = mock_q

                ok, msg = self.gd.reclamar_reparto(999, empleado_id=7)
                assert ok is False
                assert msg == 'no_encontrado'
            finally:
                patcher.stop()

    def test_ya_cogido(self, app):
        """Reparto ya tiene repartidor_id — ya_cogido inmediato."""
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                from states import EstadoPedido
                mock_pedido = MagicMock()
                mock_pedido.Estado = EstadoPedido.PREPARADO.value

                mock_rep = MagicMock()
                mock_rep.repartidor_id = 99  # ya asignado

                mock_q_pedido = MagicMock()
                mock_q_pedido.filter_by.return_value = mock_q_pedido
                mock_q_pedido.first.return_value = mock_pedido

                mock_q_reparto = MagicMock()
                mock_q_reparto.filter_by.return_value = mock_q_reparto
                mock_q_reparto.first.return_value = mock_rep

                mock_sess.query.side_effect = [mock_q_pedido, mock_q_reparto]

                ok, msg = self.gd.reclamar_reparto(42, empleado_id=7)
                assert ok is False
                assert msg == 'ya_cogido'
            finally:
                patcher.stop()

    def test_error_bd(self, app):
        """SQLAlchemyError → retorna 'error' y hace rollback."""
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_q = MagicMock()
                mock_q.filter_by.return_value = mock_q
                mock_q.first.side_effect = SQLAlchemyError("DB error")
                mock_sess.query.return_value = mock_q

                ok, msg = self.gd.reclamar_reparto(42, empleado_id=7)
                assert ok is False
                assert msg == 'error'
                mock_sess.rollback.assert_called_once()
            finally:
                patcher.stop()


class TestCompletarPickingCreaReparto:

    def setup_method(self):
        from services import gestor_dashboard
        self.gd = gestor_dashboard

    def test_crea_reparto_si_no_existe(self, app):
        """Tras completar picking y pasar a PREPARADO, se crea Reparto PENDIENTE."""
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                from states import EstadoPicking, EstadoPedido, EstadoReparto

                mock_picking = MagicMock()
                mock_picking.id = 1
                mock_picking.empleado_id = 3
                mock_picking.estado = EstadoPicking.EN_PROCESO.value
                mock_picking.items = []

                mock_pedido = MagicMock()
                mock_pedido.PedidoID = 10
                mock_pedido.Estado = EstadoPedido.EN_PREPARACION.value
                mock_pedido.TelefonoEntrega = None
                mock_picking.pedido = mock_pedido

                # Primera query: picking by id
                mock_q_picking = MagicMock()
                mock_q_picking.filter_by.return_value = mock_q_picking
                mock_q_picking.first.return_value = mock_picking

                # Segunda query: Reparto existente (None = no existe)
                mock_q_reparto = MagicMock()
                mock_q_reparto.filter_by.return_value = mock_q_reparto
                mock_q_reparto.first.return_value = None

                # Tercera query: pickings activos del picker
                mock_q_activos = MagicMock()
                mock_q_activos.filter.return_value = mock_q_activos
                mock_q_activos.count.return_value = 0

                mock_sess.query.side_effect = [mock_q_picking, mock_q_reparto, mock_q_activos]

                with patch.object(self.gd, '_actualizar_estado_operativo'):
                    ok, msg, _ = self.gd.completar_picking(1, picker_id=3)

                assert ok is True
                # Verificar que se llamó s.add() con un Reparto (instancia real, no mock)
                from models import Reparto
                add_calls = mock_sess.add.call_args_list
                reparto_adds = [c for c in add_calls if isinstance(c.args[0], Reparto)]
                assert len(reparto_adds) == 1
            finally:
                patcher.stop()

    def test_integrity_error_no_falla_picking(self, app):
        """Si hay IntegrityError al crear el Reparto (race condition), el picking sigue ok."""
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                from states import EstadoPicking, EstadoPedido
                from sqlalchemy.exc import IntegrityError

                mock_picking = MagicMock()
                mock_picking.id = 1
                mock_picking.empleado_id = 3
                mock_picking.items = []

                mock_pedido = MagicMock()
                mock_pedido.PedidoID = 10
                mock_pedido.Estado = EstadoPedido.EN_PREPARACION.value
                mock_pedido.TelefonoEntrega = None
                mock_picking.pedido = mock_pedido

                mock_q_picking = MagicMock()
                mock_q_picking.filter_by.return_value = mock_q_picking
                mock_q_picking.first.return_value = mock_picking

                # Reparto no existe — pero el commit de creación lanzará IntegrityError
                mock_q_reparto = MagicMock()
                mock_q_reparto.filter_by.return_value = mock_q_reparto
                mock_q_reparto.first.return_value = None

                mock_q_activos = MagicMock()
                mock_q_activos.filter.return_value = mock_q_activos
                mock_q_activos.count.return_value = 0

                mock_sess.query.side_effect = [mock_q_picking, mock_q_reparto, mock_q_activos]

                # Simular que el segundo commit (creación de Reparto) lanza IntegrityError
                call_count = {'n': 0}
                def commit_side_effect():
                    call_count['n'] += 1
                    if call_count['n'] == 2:
                        raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint"))
                mock_sess.commit.side_effect = commit_side_effect

                with patch.object(self.gd, '_actualizar_estado_operativo'):
                    ok, msg, _ = self.gd.completar_picking(1, picker_id=3)

                # El picking debe reportar éxito a pesar del error en el Reparto
                assert ok is True
            finally:
                patcher.stop()

    def test_no_duplica_reparto_existente(self, app):
        """Si ya existe Reparto, completar_picking no crea otro."""
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                from states import EstadoPicking, EstadoPedido, EstadoReparto
                from models import Reparto

                mock_picking = MagicMock()
                mock_picking.id = 1
                mock_picking.empleado_id = 3
                mock_picking.items = []

                mock_pedido = MagicMock()
                mock_pedido.PedidoID = 10
                mock_pedido.Estado = EstadoPedido.EN_PREPARACION.value
                mock_pedido.TelefonoEntrega = None
                mock_picking.pedido = mock_pedido

                mock_q_picking = MagicMock()
                mock_q_picking.filter_by.return_value = mock_q_picking
                mock_q_picking.first.return_value = mock_picking

                # Reparto ya existe
                mock_reparto_existente = MagicMock(spec=Reparto)
                mock_q_reparto = MagicMock()
                mock_q_reparto.filter_by.return_value = mock_q_reparto
                mock_q_reparto.first.return_value = mock_reparto_existente

                mock_q_activos = MagicMock()
                mock_q_activos.filter.return_value = mock_q_activos
                mock_q_activos.count.return_value = 0

                mock_sess.query.side_effect = [mock_q_picking, mock_q_reparto, mock_q_activos]

                with patch.object(self.gd, '_actualizar_estado_operativo'):
                    ok, msg, _ = self.gd.completar_picking(1, picker_id=3)

                assert ok is True
                from models import Reparto
                add_calls = mock_sess.add.call_args_list
                reparto_adds = [c for c in add_calls if isinstance(c.args[0], Reparto)]
                assert len(reparto_adds) == 0  # No se añade uno nuevo
            finally:
                patcher.stop()


class TestBlueprintRepartidorCola:

    def test_cola_sin_sesion_rechazado(self, client):
        resp = client.get('/repartidor/cola')
        assert resp.status_code in (302, 401, 403)

    def test_cola_devuelve_json(self, client, app):
        from unittest.mock import patch
        from services import gestor_dashboard

        with client.session_transaction() as sess:
            sess['empleado_id'] = 1
            sess['rol'] = 'repartidor'

        with patch.object(gestor_dashboard, 'repartos_sin_asignar', return_value=[
            {'pedido_id': 10, 'n_items': 2,
             'direccion_entrega': 'Calle Test 1', 'segundos_esperando': 60}
        ]):
            resp = client.get('/repartidor/cola')

        assert resp.status_code == 200
        data = resp.get_json()
        assert 'cola' in data
        assert 'total' in data
        assert data['total'] == 1
        assert data['cola'][0]['pedido_id'] == 10

    def test_coger_ok(self, client, app):
        from unittest.mock import patch
        from services import gestor_dashboard

        with client.session_transaction() as sess:
            sess['empleado_id'] = 7
            sess['rol'] = 'repartidor'

        with patch.object(gestor_dashboard, 'reclamar_reparto', return_value=(True, 'ok')) as mock_rec:
            resp = client.post('/repartidor/cola/coger/3')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['pedido_id'] == 3
        mock_rec.assert_called_once_with(3, 7)

    def test_coger_409_ya_cogido(self, client, app):
        from unittest.mock import patch
        from services import gestor_dashboard

        with client.session_transaction() as sess:
            sess['empleado_id'] = 7
            sess['rol'] = 'repartidor'

        with patch.object(gestor_dashboard, 'reclamar_reparto', return_value=(False, 'ya_cogido')):
            resp = client.post('/repartidor/cola/coger/3')

        assert resp.status_code == 409
        assert resp.get_json()['error'] == 'ya_cogido'

    def test_coger_404_no_encontrado(self, client, app):
        from unittest.mock import patch
        from services import gestor_dashboard

        with client.session_transaction() as sess:
            sess['empleado_id'] = 7
            sess['rol'] = 'repartidor'

        with patch.object(gestor_dashboard, 'reclamar_reparto', return_value=(False, 'no_encontrado')):
            resp = client.post('/repartidor/cola/coger/999')

        assert resp.status_code == 404
        assert resp.get_json()['error'] == 'no_encontrado'
