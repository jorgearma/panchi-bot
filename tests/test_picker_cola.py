import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from sqlalchemy.exc import SQLAlchemyError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_session(manager):
    """Parchea la propiedad session de GestorDashboard con un mock."""
    patcher = patch.object(type(manager), 'session', new_callable=PropertyMock)
    mock_prop = patcher.start()
    mock_sess = MagicMock()
    mock_prop.return_value = mock_sess
    return patcher, mock_sess


# ---------------------------------------------------------------------------
# TestGestorDashboardCola
# ---------------------------------------------------------------------------

class TestGestorDashboardCola:

    def setup_method(self):
        from container import gestor_dashboard
        self.gd = gestor_dashboard

    def test_pickings_sin_asignar_devuelve_lista(self, app):
        from datetime import datetime, timedelta
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_picking = MagicMock()
                mock_picking.id = 1
                mock_picking.pedido_id = 100
                mock_picking.items = [MagicMock(), MagicMock()]
                mock_picking.created_at = datetime.utcnow() - timedelta(minutes=5)

                mock_q = MagicMock()
                mock_q.join.return_value = mock_q
                mock_q.filter.return_value = mock_q
                mock_q.order_by.return_value = mock_q
                mock_q.options.return_value = mock_q
                mock_q.all.return_value = [mock_picking]
                mock_sess.query.return_value = mock_q

                result = self.gd.pickings_sin_asignar()

                assert len(result) == 1
                assert result[0]['picking_id'] == 1
                assert result[0]['pedido_id'] == 100
                assert result[0]['n_items'] == 2
                assert result[0]['segundos_esperando'] >= 0
            finally:
                patcher.stop()

    def test_pickings_sin_asignar_vacio(self, app):
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_q = MagicMock()
                mock_q.join.return_value = mock_q
                mock_q.filter.return_value = mock_q
                mock_q.order_by.return_value = mock_q
                mock_q.all.return_value = []
                mock_sess.query.return_value = mock_q

                result = self.gd.pickings_sin_asignar()
                assert result == []
            finally:
                patcher.stop()

    def test_pickings_sin_asignar_llama_join_y_filter(self, app):
        """Verifica que el query hace JOIN con Pedido y aplica .filter() —
        no hay modo de comprobar los valores del filtro sin BD real."""
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_q = MagicMock()
                mock_q.join.return_value = mock_q
                mock_q.filter.return_value = mock_q
                mock_q.order_by.return_value = mock_q
                mock_q.options.return_value = mock_q
                mock_q.all.return_value = []
                mock_sess.query.return_value = mock_q

                self.gd.pickings_sin_asignar()

                assert mock_q.join.called, "Debe hacer JOIN con Pedido"
                assert mock_q.filter.called, "Debe filtrar por estado y empleado_id"
            finally:
                patcher.stop()

    def test_reclamar_picking_ok(self, app):
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_picking = MagicMock()
                mock_picking.id = 7
                mock_picking.pedido_id = 10

                # Primera query: existencia check (PickingPedido)
                # Segunda query: UPDATE atómico (PickingPedido)
                # Tercera query: Pedido para transicionar a EN_PREPARACION
                mock_q_exist = MagicMock()
                mock_q_exist.filter_by.return_value = mock_q_exist
                mock_q_exist.first.return_value = mock_picking

                mock_q_update = MagicMock()
                mock_q_update.filter.return_value = mock_q_update
                mock_q_update.update.return_value = 1   # 1 row updated

                mock_pedido = MagicMock()
                mock_pedido.PedidoID = 10
                mock_pedido.Estado = 'pagado'
                mock_q_pedido = MagicMock()
                mock_q_pedido.filter_by.return_value = mock_q_pedido
                mock_q_pedido.first.return_value = mock_pedido

                mock_sess.query.side_effect = [mock_q_exist, mock_q_update, mock_q_pedido]

                ok, msg = self.gd.reclamar_picking(7, empleado_id=3)
                assert ok is True
                assert msg == 'ok'
            finally:
                patcher.stop()

    def test_reclamar_picking_no_encontrado(self, app):
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_q = MagicMock()
                mock_q.filter_by.return_value = mock_q
                mock_q.first.return_value = None
                mock_sess.query.return_value = mock_q

                ok, msg = self.gd.reclamar_picking(999, empleado_id=3)

                assert ok is False
                assert msg == 'no_encontrado'
            finally:
                patcher.stop()

    def test_reclamar_picking_ya_cogido(self, app):
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_picking = MagicMock()
                mock_picking.id = 7

                mock_q_exist = MagicMock()
                mock_q_exist.filter_by.return_value = mock_q_exist
                mock_q_exist.first.return_value = mock_picking

                mock_q_update = MagicMock()
                mock_q_update.filter.return_value = mock_q_update
                mock_q_update.update.return_value = 0  # 0 rows = ya cogido

                mock_sess.query.side_effect = [mock_q_exist, mock_q_update]

                ok, msg = self.gd.reclamar_picking(7, empleado_id=3)

                assert ok is False
                assert msg == 'ya_cogido'
            finally:
                patcher.stop()

# ---------------------------------------------------------------------------
# TestBlueprintPickerCola
# ---------------------------------------------------------------------------

class TestBlueprintPickerCola:

    def test_cola_sin_sesion_rechazado(self, client):
        resp = client.get('/picker/cola')
        # Redirige al login si no hay sesión
        assert resp.status_code in (302, 401, 403)

    def test_cola_devuelve_json(self, client, app):
        from unittest.mock import patch
        from container import gestor_dashboard

        with client.session_transaction() as sess:
            sess['empleado_id'] = 1
            sess['rol'] = 'picker'

        with patch.object(gestor_dashboard, 'pickings_sin_asignar', return_value=[
            {'picking_id': 5, 'pedido_id': 200, 'n_items': 3, 'segundos_esperando': 120}
        ]):
            resp = client.get('/picker/cola')

        assert resp.status_code == 200
        data = resp.get_json()
        assert 'cola' in data
        assert 'total' in data
        assert data['total'] == 1
        assert data['cola'][0]['picking_id'] == 5

    def test_coger_ok(self, client, app):
        from unittest.mock import patch
        from container import gestor_dashboard

        with client.session_transaction() as sess:
            sess['empleado_id'] = 3
            sess['rol'] = 'picker'

        with patch.object(gestor_dashboard, 'reclamar_picking', return_value=(True, 'ok')) as mock_rec:
            resp = client.post('/picker/cola/coger/7')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['picking_id'] == 7
        mock_rec.assert_called_once_with(7, 3)

    def test_coger_409_ya_cogido(self, client, app):
        from unittest.mock import patch
        from container import gestor_dashboard

        with client.session_transaction() as sess:
            sess['empleado_id'] = 3
            sess['rol'] = 'picker'

        with patch.object(gestor_dashboard, 'reclamar_picking', return_value=(False, 'ya_cogido')):
            resp = client.post('/picker/cola/coger/7')

        assert resp.status_code == 409
        assert resp.get_json()['error'] == 'ya_cogido'

    def test_coger_404_no_encontrado(self, client, app):
        from unittest.mock import patch
        from container import gestor_dashboard

        with client.session_transaction() as sess:
            sess['empleado_id'] = 3
            sess['rol'] = 'picker'

        with patch.object(gestor_dashboard, 'reclamar_picking', return_value=(False, 'no_encontrado')):
            resp = client.post('/picker/cola/coger/999')

        assert resp.status_code == 404
        assert resp.get_json()['error'] == 'no_encontrado'


# ---------------------------------------------------------------------------
# TestModoRestaurant — listo_para_finalizar sin items
# ---------------------------------------------------------------------------

class TestModoRestaurant:
    """En modo restaurant, pickings_del_picker debe marcar listo_para_finalizar=True
    incluso sin items (modo='restaurant' en el PickingPedido)."""

    def setup_method(self):
        from container import gestor_dashboard
        self.gd = gestor_dashboard

    def test_listo_para_finalizar_sin_items_en_restaurant(self, app):
        """APP_MODE=restaurant y sin items debe tener listo_para_finalizar=True."""
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_picking = MagicMock()
                mock_picking.id = 1
                mock_picking.pedido_id = 100
                mock_picking.estado = 'en_proceso'
                mock_picking.items = []
                mock_picking.iniciado_en = None
                mock_picking.pedido = MagicMock()
                mock_picking.pedido.DireccionEntrega = 'C/ Test 1'
                mock_picking.pedido.TelefonoEntrega = '600000000'
                mock_picking.pedido.Total = 25.50
                mock_picking.pedido.cliente = MagicMock()
                mock_picking.pedido.cliente.nombre = 'Test'

                mock_q = MagicMock()
                mock_q.filter.return_value = mock_q
                mock_q.order_by.return_value = mock_q
                mock_q.options.return_value = mock_q
                mock_q.all.return_value = [mock_picking]
                mock_sess.query.return_value = mock_q

                import managers.dashboard.picking_basico as pb
                with patch.object(pb.app_config, 'APP_MODE', 'restaurant', create=True):
                    result = self.gd.pickings_del_picker(1)

                assert len(result) == 1
                assert result[0]['listo_para_finalizar'] is True
                assert result[0]['picking_completo'] is True
                assert result[0]['modo'] == 'restaurant'
            finally:
                patcher.stop()

    def test_listo_para_finalizar_false_en_warehouse_con_items_pendientes(self, app):
        """picking con modo='warehouse' e items pendientes NO debe estar listo."""
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                item_mock = MagicMock()
                item_mock.estado = 'pendiente'
                item_mock.pedido_detalle = MagicMock()
                item_mock.pedido_detalle.NombreProducto = 'Producto A'
                item_mock.pedido_detalle.Cantidad = 2
                item_mock.pedido_detalle.producto = MagicMock()
                item_mock.pedido_detalle.producto.Nombre = 'Producto A'
                item_mock.pedido_detalle.producto.Ubicacion = 'A1'
                item_mock.pedido_detalle.producto.ImagenURL = None
                item_mock.pedido_detalle.ProductoID = 5
                item_mock.item_id = 10
                item_mock.id = 10
                item_mock.cantidad_encontrada = None
                item_mock.notas = None
                item_mock.pedido_detalle_id = 20

                mock_picking = MagicMock()
                mock_picking.id = 2
                mock_picking.pedido_id = 200
                mock_picking.estado = 'en_proceso'
                mock_picking.modo = 'warehouse'
                mock_picking.items = [item_mock]
                mock_picking.iniciado_en = None
                mock_picking.pedido = MagicMock()
                mock_picking.pedido.DireccionEntrega = 'C/ Test 2'
                mock_picking.pedido.TelefonoEntrega = '600000001'
                mock_picking.pedido.Total = 15.00
                mock_picking.pedido.cliente = MagicMock()
                mock_picking.pedido.cliente.nombre = 'Test2'

                mock_q = MagicMock()
                mock_q.filter.return_value = mock_q
                mock_q.order_by.return_value = mock_q
                mock_q.options.return_value = mock_q
                mock_q.all.return_value = [mock_picking]
                mock_sess.query.return_value = mock_q

                import managers.dashboard.picking_basico as pb
                with patch.object(pb.app_config, 'APP_MODE', 'warehouse', create=True):
                    result = self.gd.pickings_del_picker(2)

                assert len(result) == 1
                assert result[0]['listo_para_finalizar'] is False
                assert result[0]['picking_completo'] is False
            finally:
                patcher.stop()


# ---------------------------------------------------------------------------
# TestBlueprintCocina — rutas /cocina
# ---------------------------------------------------------------------------

class TestBlueprintCocina:

    def test_cocina_sin_sesion_rechazado(self, client):
        resp = client.get('/cocina')
        assert resp.status_code in (302, 401, 403)

    def test_cocina_con_sesion_ok(self, client, app):
        with client.session_transaction() as sess:
            sess['empleado_id'] = 1
            sess['rol'] = 'picker'
        with app.app_context():
            resp = client.get('/cocina')
        assert resp.status_code == 200

    def test_cocina_cola_devuelve_json(self, client, app):
        from unittest.mock import patch
        from container import gestor_dashboard

        with client.session_transaction() as sess:
            sess['empleado_id'] = 1
            sess['rol'] = 'picker'

        with patch.object(gestor_dashboard, 'pickings_sin_asignar', return_value=[
            {'picking_id': 9, 'pedido_id': 300, 'n_items': 0, 'segundos_esperando': 60}
        ]):
            resp = client.get('/cocina/cola')

        assert resp.status_code == 200
        data = resp.get_json()
        assert 'cola' in data
        assert data['total'] == 1

    def test_cocina_coger_ok(self, client, app):
        from unittest.mock import patch
        from container import gestor_dashboard

        with client.session_transaction() as sess:
            sess['empleado_id'] = 4
            sess['rol'] = 'picker'

        with patch.object(gestor_dashboard, 'reclamar_picking', return_value=(True, 'ok')) as mock_rec:
            resp = client.post('/cocina/cola/coger/9')

        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True
        mock_rec.assert_called_once_with(9, 4)

    def test_cocina_finalizar_ok(self, client, app):
        from unittest.mock import patch
        from container import gestor_dashboard

        with client.session_transaction() as sess:
            sess['empleado_id'] = 4
            sess['rol'] = 'picker'

        with patch.object(gestor_dashboard, 'completar_picking', return_value=(True, 'Picking completado')):
            resp = client.post('/cocina/preparacion/9/finalizar')

        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True
