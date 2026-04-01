"""
Tests for blueprints/menu.py:
  - GET /menu/<token>
  - GET /confirmacion_pago
"""
import json
import pytest
from unittest.mock import MagicMock, patch

from states import EstadoPedido


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

VALID_TOKEN = "tok-abc123"
USER_DATA = {
    "id": 1,
    "nombre": "Ana García",
    "numero": "whatsapp:+34600000000",
    "direccion": "Calle Mayor 1",
}


def make_pedido(estado: str, redis_id: str = "redis-xyz"):
    p = MagicMock()
    p.PedidoID = 10
    p.Estado = estado
    p.redisID = redis_id
    return p


# ─────────────────────────────────────────────
# GET /menu/<token>
# ─────────────────────────────────────────────

class TestMenuToken:

    def _get(self, client, token=VALID_TOKEN):
        return client.get(f"/menu/{token}")

    def test_token_expirado_retorna_403(self, client):
        """Token no encontrado en Redis → 403."""
        with patch("blueprints.menu.navegacion.redismanager") as mock_redis:
            mock_redis.get.return_value = None
            resp = self._get(client)
        assert resp.status_code == 403

    def test_datos_redis_invalidos_retorna_400(self, client):
        """Datos en Redis con JSON mal formado → 400."""
        with patch("blueprints.menu.navegacion.redismanager") as mock_redis:
            mock_redis.get.return_value = "esto-no-es-json-{"
            resp = self._get(client)
        assert resp.status_code == 400

    def test_estado_enlace_renderiza_quiniela(self, client):
        """Token válido + pedido en ENLACE → 200 con quiniela.html."""
        with patch("blueprints.menu.navegacion.redismanager") as mock_redis:
            mock_redis.get.return_value = json.dumps(USER_DATA)
            with patch("blueprints.menu.navegacion.gestor_pedidos") as mock_gp:
                mock_gp.obtener_pedido_mas_reciente.return_value = make_pedido(EstadoPedido.ENLACE)
                resp = self._get(client)
        assert resp.status_code == 200

    def test_estado_enlace2_redirige_a_confirmacion(self, client):
        """Token válido + pedido en ENLACE2 → redirige a /confirmacion_pago."""
        with patch("blueprints.menu.navegacion.redismanager") as mock_redis:
            mock_redis.get.return_value = json.dumps(USER_DATA)
            with patch("blueprints.menu.navegacion.gestor_pedidos") as mock_gp:
                mock_gp.obtener_pedido_mas_reciente.return_value = make_pedido(EstadoPedido.ENLACE2)
                resp = self._get(client)
        assert resp.status_code == 302
        assert "/confirmacion_pago" in resp.headers["Location"]

    def test_sin_pedido_activo_retorna_404(self, client):
        """Token válido pero usuario sin pedido activo → 404."""
        with patch("blueprints.menu.navegacion.redismanager") as mock_redis:
            mock_redis.get.return_value = json.dumps(USER_DATA)
            with patch("blueprints.menu.navegacion.gestor_pedidos") as mock_gp:
                mock_gp.obtener_pedido_mas_reciente.return_value = None
                resp = self._get(client)
        assert resp.status_code == 404

    def test_estado_desconocido_retorna_400(self, client):
        """Token válido + pedido en estado no reconocido → 400."""
        with patch("blueprints.menu.navegacion.redismanager") as mock_redis:
            mock_redis.get.return_value = json.dumps(USER_DATA)
            with patch("blueprints.menu.navegacion.gestor_pedidos") as mock_gp:
                mock_gp.obtener_pedido_mas_reciente.return_value = make_pedido(EstadoPedido.PAGADO)
                resp = self._get(client)
        assert resp.status_code == 400


# ─────────────────────────────────────────────
# GET /confirmacion_pago
# ─────────────────────────────────────────────

PEDIDO_CACHE = {
    "name": "Ana",
    "userID": 1,
    "token": VALID_TOKEN,
    "numero": "whatsapp:+34600000000",
    "direccion": "Calle Mayor 1",
    "total": 7.0,
    "productos": [],
    "pedidoID": 10,
}


class TestConfirmacionPago:

    def test_sin_pedido_id_retorna_404(self, client):
        resp = client.get("/confirmacion_pago")
        assert resp.status_code == 404

    def test_pedido_expirado_retorna_404(self, client):
        with patch("blueprints.menu.sesion.cache") as mock_cache:
            mock_cache.get.return_value = None
            resp = client.get("/confirmacion_pago?pedido_id=no-existe")
        assert resp.status_code == 404

    def test_pedido_valido_retorna_200(self, client):
        with patch("blueprints.menu.sesion.cache") as mock_cache:
            mock_cache.get.return_value = json.dumps(PEDIDO_CACHE)
            resp = client.get("/confirmacion_pago?pedido_id=abc123")
        assert resp.status_code == 200
