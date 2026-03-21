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

    def test_devuelve_lista(self, app):
        from datetime import datetime, timedelta
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_pedido = MagicMock()
                mock_pedido.DireccionEntrega = 'Calle Mayor 10'
                mock_pedido.detalles = [MagicMock(), MagicMock(), MagicMock()]

                mock_rep = MagicMock()
                mock_rep.id = 1
                mock_rep.pedido_id = 42
                mock_rep.pedido = mock_pedido
                mock_rep.created_at = datetime.utcnow() - timedelta(minutes=3)

                mock_q = MagicMock()
                mock_q.join.return_value = mock_q
                mock_q.filter.return_value = mock_q
                mock_q.order_by.return_value = mock_q
                mock_q.all.return_value = [mock_rep]
                mock_sess.query.return_value = mock_q

                result = self.gd.repartos_sin_asignar()

                assert len(result) == 1
                assert result[0]['reparto_id'] == 1
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
                mock_q = MagicMock()
                mock_q.join.return_value = mock_q
                mock_q.filter.return_value = mock_q
                mock_q.order_by.return_value = mock_q
                mock_q.all.return_value = []
                mock_sess.query.return_value = mock_q

                result = self.gd.repartos_sin_asignar()
                assert result == []
            finally:
                patcher.stop()

    def test_hace_join_y_filter(self, app):
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_q = MagicMock()
                mock_q.join.return_value = mock_q
                mock_q.filter.return_value = mock_q
                mock_q.order_by.return_value = mock_q
                mock_q.all.return_value = []
                mock_sess.query.return_value = mock_q

                self.gd.repartos_sin_asignar()

                assert mock_q.join.called, "Debe hacer JOIN con Pedido"
                assert mock_q.filter.called
            finally:
                patcher.stop()


class TestReclamarReparto:

    def setup_method(self):
        from services import gestor_dashboard
        self.gd = gestor_dashboard

    def test_ok(self, app):
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_rep = MagicMock()
                mock_rep.id = 5

                mock_q_exist = MagicMock()
                mock_q_exist.filter_by.return_value = mock_q_exist
                mock_q_exist.first.return_value = mock_rep

                mock_q_update = MagicMock()
                mock_q_update.filter.return_value = mock_q_update
                mock_q_update.update.return_value = 1

                mock_sess.query.side_effect = [mock_q_exist, mock_q_update]

                with patch.object(self.gd, '_actualizar_estado_operativo') as mock_aso:
                    ok, msg = self.gd.reclamar_reparto(5, empleado_id=7)
                    assert ok is True
                    assert msg == 'ok'
                    mock_aso.assert_called_once_with(7, 'ocupado')
            finally:
                patcher.stop()

    def test_no_encontrado(self, app):
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
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_rep = MagicMock()

                mock_q_exist = MagicMock()
                mock_q_exist.filter_by.return_value = mock_q_exist
                mock_q_exist.first.return_value = mock_rep

                mock_q_update = MagicMock()
                mock_q_update.filter.return_value = mock_q_update
                mock_q_update.update.return_value = 0  # otro se adelantó

                mock_sess.query.side_effect = [mock_q_exist, mock_q_update]

                ok, msg = self.gd.reclamar_reparto(5, empleado_id=7)
                assert ok is False
                assert msg == 'ya_cogido'
            finally:
                patcher.stop()

    def test_error_bd(self, app):
        with app.app_context():
            patcher, mock_sess = _mock_session(self.gd)
            try:
                mock_rep = MagicMock()

                mock_q_exist = MagicMock()
                mock_q_exist.filter_by.return_value = mock_q_exist
                mock_q_exist.first.return_value = mock_rep

                mock_q_update = MagicMock()
                mock_q_update.filter.return_value = mock_q_update
                mock_q_update.update.side_effect = SQLAlchemyError("DB error")

                mock_sess.query.side_effect = [mock_q_exist, mock_q_update]

                ok, msg = self.gd.reclamar_reparto(5, empleado_id=7)
                assert ok is False
                assert msg == 'error'
                mock_sess.rollback.assert_called_once()
            finally:
                patcher.stop()
