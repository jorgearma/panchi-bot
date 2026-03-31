"""
Tests para GET /api/seguimiento/<redis_id>
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


def make_pedido(estado, forma_pago="online", con_reparto=False, con_repartidor=False):
    pedido = MagicMock()
    pedido.PedidoID = 2045
    pedido.Estado = estado
    pedido.forma_pago = forma_pago
    pedido.DireccionEntrega = "Calle Mayor 5, Madrid"

    if con_reparto:
        reparto = MagicMock()
        reparto.estado = "en_camino"
        reparto.hora_salida = datetime(2026, 3, 21, 14, 52)
        reparto.hora_estimada_entrega = datetime(2026, 3, 21, 15, 5)
        if con_repartidor:
            repartidor = MagicMock()
            repartidor.Nombre = "Carlos"
            repartidor.Apellido = "Moreno"
            repartidor.Telefono = "612345678"
            reparto.repartidor = repartidor
        else:
            reparto.repartidor = None
        pedido.reparto = reparto
    else:
        pedido.reparto = None

    return pedido


FAKE_REDIS_ID = "abc-uuid-1234"


class TestSeguimientoEndpoint:

    def _patch_db(self, pedido_result):
        """Patch the DB query used by the endpoint."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = pedido_result
        return patch("blueprints.api.tracking.get_db", return_value=mock_db)

    def test_pedido_no_encontrado_devuelve_404(self, client):
        with self._patch_db(None):
            resp = client.get(f"/api/seguimiento/{FAKE_REDIS_ID}")
        assert resp.status_code == 404
        assert "error" in resp.get_json()

    def test_pedido_sin_reparto(self, client):
        # Estado real en BD: minúsculas (EstadoPedido.EN_PREPARACION = "en_preparacion")
        pedido = make_pedido("en_preparacion", con_reparto=False)
        with self._patch_db(pedido):
            resp = client.get(f"/api/seguimiento/{FAKE_REDIS_ID}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["estado"] == "en_preparacion"
        assert data["reparto"] is None

    def test_pedido_en_reparto_con_repartidor(self, client):
        pedido = make_pedido("en_reparto", con_reparto=True, con_repartidor=True)
        with self._patch_db(pedido):
            resp = client.get(f"/api/seguimiento/{FAKE_REDIS_ID}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["estado"] == "en_reparto"
        reparto = data["reparto"]
        assert reparto["repartidor_nombre"] == "Carlos Moreno"
        assert reparto["repartidor_telefono"] == "612345678"
        assert reparto["hora_estimada_entrega"] == "15:05"
        assert reparto["hora_salida"] == "14:52"
        assert reparto["calle_destino"] == "Calle Mayor 5, Madrid"

    def test_pedido_con_reparto_sin_repartidor_asignado(self, client):
        pedido = make_pedido("preparado", con_reparto=True, con_repartidor=False)
        with self._patch_db(pedido):
            resp = client.get(f"/api/seguimiento/{FAKE_REDIS_ID}")
        assert resp.status_code == 200
        data = resp.get_json()
        reparto = data["reparto"]
        assert reparto["repartidor_nombre"] is None
        assert reparto["repartidor_telefono"] is None

    def test_pedido_entregado(self, client):
        pedido = make_pedido("entregado", con_reparto=True, con_repartidor=True)
        with self._patch_db(pedido):
            resp = client.get(f"/api/seguimiento/{FAKE_REDIS_ID}")
        assert resp.status_code == 200
        assert resp.get_json()["estado"] == "entregado"

    def test_respuesta_incluye_forma_pago(self, client):
        pedido = make_pedido("en_preparacion", forma_pago="efectivo")
        with self._patch_db(pedido):
            resp = client.get(f"/api/seguimiento/{FAKE_REDIS_ID}")
        assert resp.get_json()["forma_pago"] == "efectivo"
