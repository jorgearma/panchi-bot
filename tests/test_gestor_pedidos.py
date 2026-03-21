"""
Tests de GestorPedidos.actualizar_estado() con SQLAlchemy mockeado.
Verifica que la validación de transiciones bloquea correctamente sin tocar la DB.
"""
import logging
import pytest
from unittest.mock import MagicMock, patch
from states import EstadoPedido


# ---------------------------------------------------------------------------
# Fixture: pedido simulado
# ---------------------------------------------------------------------------

def make_pedido(estado: str) -> MagicMock:
    pedido = MagicMock()
    pedido.PedidoID = 42
    pedido.Estado = estado
    return pedido


@pytest.fixture
def gestor():
    """GestorPedidos con sesión de DB completamente mockeada."""
    from managers.gestor_pedidos import GestorPedidos
    g = GestorPedidos()
    return g


# ---------------------------------------------------------------------------
# Transiciones válidas — deben escribir en DB y devolver True
# ---------------------------------------------------------------------------

class TestActualizarEstadoValido:
    def test_pendiente_a_enlace(self, gestor):
        pedido = make_pedido(EstadoPedido.PENDIENTE)
        with patch.object(type(gestor), "session", new_callable=lambda: property(lambda self: _mock_session(pedido))):
            result = gestor.actualizar_estado(42, EstadoPedido.ENLACE)
        assert result is True
        assert pedido.Estado == EstadoPedido.ENLACE

    def test_enlace_a_enlace2(self, gestor):
        pedido = make_pedido(EstadoPedido.ENLACE)
        with patch.object(type(gestor), "session", new_callable=lambda: property(lambda self: _mock_session(pedido))):
            result = gestor.actualizar_estado(42, EstadoPedido.ENLACE2)
        assert result is True
        assert pedido.Estado == EstadoPedido.ENLACE2

    def test_enlace2_a_confirmando_pago(self, gestor):
        pedido = make_pedido(EstadoPedido.ENLACE2)
        with patch.object(type(gestor), "session", new_callable=lambda: property(lambda self: _mock_session(pedido))):
            result = gestor.actualizar_estado(42, EstadoPedido.CONFIRMANDO_PAGO)
        assert result is True

    def test_confirmando_pago_a_pagado(self, gestor):
        pedido = make_pedido(EstadoPedido.CONFIRMANDO_PAGO)
        with patch.object(type(gestor), "session", new_callable=lambda: property(lambda self: _mock_session(pedido))):
            result = gestor.actualizar_estado(42, EstadoPedido.PAGADO)
        assert result is True

    def test_confirmando_pago_a_pagado_crea_picking_pendiente(self, gestor):
        pedido = make_pedido(EstadoPedido.CONFIRMANDO_PAGO)
        detalle = MagicMock()
        detalle.DetalleID = 9
        pedido.detalles = [detalle]

        session = MagicMock()
        pedido_query = MagicMock()
        pedido_query.filter_by.return_value.first.return_value = pedido
        picking_query = MagicMock()
        picking_query.filter_by.return_value.first.return_value = None
        session.query.side_effect = [pedido_query, picking_query]

        with patch.object(type(gestor), "session", new_callable=lambda: property(lambda self: session)):
            result = gestor.actualizar_estado(42, EstadoPedido.PAGADO)

        assert result is True
        assert session.add.call_count >= 3
        creado = [call.args[0] for call in session.add.call_args_list]
        assert any(obj.__class__.__name__ == "PickingPedido" for obj in creado)
        assert any(obj.__class__.__name__ == "PickingItem" for obj in creado)
        session.flush.assert_called_once()
        session.commit.assert_called_once()

    def test_enlace_a_pendiente_rollback_error(self, gestor):
        pedido = make_pedido(EstadoPedido.ENLACE)
        with patch.object(type(gestor), "session", new_callable=lambda: property(lambda self: _mock_session(pedido))):
            result = gestor.actualizar_estado(42, EstadoPedido.PENDIENTE)
        assert result is True

    def test_enlace2_a_enlace_boton_atras(self, gestor):
        pedido = make_pedido(EstadoPedido.ENLACE2)
        with patch.object(type(gestor), "session", new_callable=lambda: property(lambda self: _mock_session(pedido))):
            result = gestor.actualizar_estado(42, EstadoPedido.ENLACE)
        assert result is True


# ---------------------------------------------------------------------------
# Transiciones inválidas — deben devolver False y NO tocar la DB
# ---------------------------------------------------------------------------

class TestActualizarEstadoInvalido:
    def test_saltar_a_pagado_desde_pendiente(self, gestor):
        pedido = make_pedido(EstadoPedido.PENDIENTE)
        session = _mock_session(pedido)
        with patch.object(type(gestor), "session", new_callable=lambda: property(lambda self: session)):
            result = gestor.actualizar_estado(42, EstadoPedido.PAGADO)
        assert result is False
        session.commit.assert_not_called()

    def test_pagado_es_terminal(self, gestor):
        pedido = make_pedido(EstadoPedido.PAGADO)
        session = _mock_session(pedido)
        with patch.object(type(gestor), "session", new_callable=lambda: property(lambda self: session)):
            result = gestor.actualizar_estado(42, EstadoPedido.ENLACE)
        assert result is False
        session.commit.assert_not_called()

    def test_confirmando_pago_no_retrocede(self, gestor):
        pedido = make_pedido(EstadoPedido.CONFIRMANDO_PAGO)
        session = _mock_session(pedido)
        with patch.object(type(gestor), "session", new_callable=lambda: property(lambda self: session)):
            result = gestor.actualizar_estado(42, EstadoPedido.ENLACE2)
        assert result is False
        session.commit.assert_not_called()

    def test_estado_desconocido_en_db(self, gestor):
        """Estado legacy en BD que no está en el enum → bloquear."""
        pedido = make_pedido("estado_legacy")
        session = _mock_session(pedido)
        with patch.object(type(gestor), "session", new_callable=lambda: property(lambda self: session)):
            result = gestor.actualizar_estado(42, EstadoPedido.ENLACE)
        assert result is False
        session.commit.assert_not_called()

    def test_transicion_invalida_loguea_error(self, gestor, caplog):
        pedido = make_pedido(EstadoPedido.PAGADO)
        with patch.object(type(gestor), "session", new_callable=lambda: property(lambda self: _mock_session(pedido))):
            with caplog.at_level(logging.ERROR, logger="managers.gestor_pedidos"):
                gestor.actualizar_estado(42, EstadoPedido.ENLACE)
        assert "Transición de pedido inválida" in caplog.text
        assert "pagado" in caplog.text
        assert "enlace" in caplog.text


# ---------------------------------------------------------------------------
# Pedido no encontrado
# ---------------------------------------------------------------------------

class TestActualizarEstadoPedidoNoEncontrado:
    def test_devuelve_false_si_pedido_no_existe(self, gestor):
        session = _mock_session(None)
        with patch.object(type(gestor), "session", new_callable=lambda: property(lambda self: session)):
            result = gestor.actualizar_estado(999, EstadoPedido.ENLACE)
        assert result is False
        session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_session(pedido):
    session = MagicMock()
    query_mock = MagicMock()
    query_mock.filter_by.return_value.first.return_value = pedido
    session.query.return_value = query_mock
    return session
