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

                with patch.object(self.gd, '_actualizar_estado_operativo') as mock_aso:
                    ok, msg = self.gd.reclamar_picking(7, empleado_id=3)
                    assert ok is True
                    assert msg == 'ok'
                    mock_aso.assert_called_once_with(3, 'ocupado')
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
