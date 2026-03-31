"""
Tests for:
  - controllers.pedido.confirmar_carrito (unit, no Flask client)
  - controllers.pago.iniciar_pago        (unit, no Flask client)
  - POST /api/cambiar_estado_a_enlace    (integration, Flask client)
"""
import json
import pytest
from unittest.mock import MagicMock, patch
from states import EstadoPedido

import config as app_config

INTERNAL_TOKEN = "test-internal-token"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_pedido(estado: str, pedido_id: int = 1, redis_id: str = "redis-abc") -> MagicMock:
    p = MagicMock()
    p.PedidoID = pedido_id
    p.Estado = estado
    p.redisID = redis_id
    return p


def make_cache() -> MagicMock:
    store = {}
    c = MagicMock()
    c.set.side_effect = lambda k, v, ex=None: store.update({k: v})
    c.get.side_effect = lambda k: store.get(k)
    return c


def make_gestor_pedidos(pedido: MagicMock) -> MagicMock:
    g = MagicMock()
    g.obtener_pedido_mas_reciente.return_value = pedido
    g.guardar_redis_id.return_value = True
    g.actualizar_estado.return_value = True
    g.agregar_productos_a_pedido.return_value = True
    g.guardar_enlace.return_value = True
    return g


PRODUCTOS_RECIBIDOS = [
    {"nombre": "Bocadillo", "cantidad": 2, "precio_unitario": 3.5, "Codigo": "BOC001"},
]

PRODUCTOS_VALIDOS_PAGO = [
    {"codigo": "BOC001", "cantidad": 2},
]

PUBLIC_URL = "https://example.com"


# ---------------------------------------------------------------------------
# confirmar_carrito
# ---------------------------------------------------------------------------

class TestConfirmarCarrito:
    def test_happy_path_returns_true_and_url(self):
        from controllers.pedido import confirmar_carrito

        pedido = make_pedido(EstadoPedido.ENLACE)
        cache = make_cache()
        gestor = make_gestor_pedidos(pedido)

        mock_gp = MagicMock()
        mock_gp.obtener_producto_por_codigo.return_value = {"Precio": 3.5}

        success, result = confirmar_carrito(
            pedido_id_redis="uuid-001",
            name="Ana",
            token="tok",
            user_id=99,
            numero="+34600000001",
            direccion="Calle Mayor 1",
            productos_recibidos=PRODUCTOS_RECIBIDOS,
            cache=cache,
            gestor_pedidos=gestor,
            gestor_productos=mock_gp,
            public_url=PUBLIC_URL,
        )

        assert success is True
        assert result == f"{PUBLIC_URL}/confirmacion_pago?pedido_id=uuid-001"

    def test_cart_stored_in_cache(self):
        from controllers.pedido import confirmar_carrito

        pedido = make_pedido(EstadoPedido.ENLACE)
        store = {}
        cache = MagicMock()
        cache.set.side_effect = lambda k, v, ex=None: store.update({k: v})
        gestor = make_gestor_pedidos(pedido)

        mock_gp = MagicMock()
        mock_gp.obtener_producto_por_codigo.return_value = {"Precio": 3.5}

        confirmar_carrito(
            pedido_id_redis="uuid-002",
            name="Juan",
            token="tok2",
            user_id=42,
            numero="+34600000002",
            direccion="Calle Ancha 5",
            productos_recibidos=PRODUCTOS_RECIBIDOS,
            cache=cache,
            gestor_pedidos=gestor,
            gestor_productos=mock_gp,
            public_url=PUBLIC_URL,
        )

        assert "uuid-002" in store
        payload = json.loads(store["uuid-002"])
        assert payload["name"] == "Juan"
        assert payload["total"] == round(3.5 * 2, 2)  # precio de BD mock = 3.5

    def test_state_transition_to_enlace2_called(self):
        from controllers.pedido import confirmar_carrito

        pedido = make_pedido(EstadoPedido.ENLACE)
        gestor = make_gestor_pedidos(pedido)

        confirmar_carrito(
            pedido_id_redis="uuid-003",
            name="X",
            token="t",
            user_id=1,
            numero="+34600000003",
            direccion="C/ Test 1",
            productos_recibidos=[],
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=MagicMock(),
            public_url=PUBLIC_URL,
        )

        gestor.actualizar_estado.assert_called_once_with(pedido.PedidoID, EstadoPedido.ENLACE2)

    def test_wrong_state_does_not_call_actualizar_estado(self):
        """If the order is not in ENLACE state, no state transition is attempted."""
        from controllers.pedido import confirmar_carrito

        pedido = make_pedido(EstadoPedido.ENLACE2)  # already past ENLACE
        gestor = make_gestor_pedidos(pedido)

        confirmar_carrito(
            pedido_id_redis="uuid-004",
            name="X",
            token="t",
            user_id=1,
            numero="+34600000004",
            direccion="C/ Test 2",
            productos_recibidos=[],
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=MagicMock(),
            public_url=PUBLIC_URL,
        )

        gestor.actualizar_estado.assert_not_called()

    def test_no_active_order_returns_false(self):
        from controllers.pedido import confirmar_carrito

        gestor = MagicMock()
        gestor.obtener_pedido_mas_reciente.return_value = None

        success, msg = confirmar_carrito(
            pedido_id_redis="uuid-005",
            name="X",
            token="t",
            user_id=1,
            numero="+34",
            direccion="C/",
            productos_recibidos=[],
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=MagicMock(),
            public_url=PUBLIC_URL,
        )

        assert success is False
        assert "pedido activo" in msg.lower()

    def test_confirmacion_ignora_precio_frontend(self):
        """El total en Redis usa precio de BD, no precio_unitario del frontend."""
        from controllers.pedido import confirmar_carrito
        from decimal import Decimal

        precio_frontend_manipulado = 0.01
        precio_bd = Decimal("5.00")
        cantidad = 2

        pedido = make_pedido(EstadoPedido.ENLACE)
        store = {}
        cache = MagicMock()
        cache.set.side_effect = lambda k, v, ex=None: store.update({k: v})
        gestor = make_gestor_pedidos(pedido)
        mock_gp = MagicMock()
        mock_gp.obtener_producto_por_codigo.return_value = {"Precio": precio_bd}

        confirmar_carrito(
            pedido_id_redis="uuid-precio-test",
            name="Test",
            token="tok",
            user_id=1,
            numero="+34600000000",
            direccion="Calle Mayor 1",
            productos_recibidos=[{
                "Codigo": "P001",
                "nombre": "Producto Test",
                "cantidad": cantidad,
                "precio_unitario": precio_frontend_manipulado,
            }],
            cache=cache,
            gestor_pedidos=gestor,
            gestor_productos=mock_gp,
            public_url=PUBLIC_URL,
        )

        stored = json.loads(store["uuid-precio-test"])
        assert stored["total"] == round(float(precio_bd) * cantidad, 2)
        assert stored["productos"][0]["precio"] == round(float(precio_bd) * cantidad, 2)

    def test_confirmacion_codigo_ausente_devuelve_error(self):
        """Si un item no tiene 'Codigo', confirmar_carrito devuelve (False, mensaje)."""
        from controllers.pedido import confirmar_carrito

        pedido = make_pedido(EstadoPedido.ENLACE)
        gestor = make_gestor_pedidos(pedido)
        mock_gp = MagicMock()

        success, msg = confirmar_carrito(
            pedido_id_redis="uuid-sin-codigo",
            name="Test",
            token="tok",
            user_id=1,
            numero="+34600000000",
            direccion="Calle Mayor 1",
            productos_recibidos=[{"nombre": "X", "cantidad": 1}],
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=mock_gp,
            public_url=PUBLIC_URL,
        )

        assert success is False
        assert "código" in msg.lower() or "codigo" in msg.lower()

    def test_confirmacion_cantidad_cero_devuelve_error(self):
        """Si cantidad <= 0, confirmar_carrito devuelve (False, mensaje)."""
        from controllers.pedido import confirmar_carrito

        pedido = make_pedido(EstadoPedido.ENLACE)
        gestor = make_gestor_pedidos(pedido)
        mock_gp = MagicMock()

        success, msg = confirmar_carrito(
            pedido_id_redis="uuid-cant-cero",
            name="Test",
            token="tok",
            user_id=1,
            numero="+34600000000",
            direccion="Calle Mayor 1",
            productos_recibidos=[{"Codigo": "P001", "nombre": "X", "cantidad": 0}],
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=mock_gp,
            public_url=PUBLIC_URL,
        )

        assert success is False
        assert "cantidad" in msg.lower()

    def test_confirmacion_producto_no_encontrado_devuelve_error(self):
        """Si gestor_productos no encuentra el código, confirmar_carrito devuelve error."""
        from controllers.pedido import confirmar_carrito

        pedido = make_pedido(EstadoPedido.ENLACE)
        gestor = make_gestor_pedidos(pedido)
        mock_gp = MagicMock()
        mock_gp.obtener_producto_por_codigo.return_value = None

        success, msg = confirmar_carrito(
            pedido_id_redis="uuid-no-producto",
            name="Test",
            token="tok",
            user_id=1,
            numero="+34600000000",
            direccion="Calle Mayor 1",
            productos_recibidos=[{"Codigo": "INEXISTENTE", "nombre": "X", "cantidad": 1}],
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=mock_gp,
            public_url=PUBLIC_URL,
        )

        assert success is False
        assert "INEXISTENTE" in msg or "no encontrado" in msg.lower()

    def test_confirmacion_precio_null_devuelve_error(self):
        """Si Precio en BD es NULL, confirmar_carrito devuelve (False, mensaje)."""
        from controllers.pedido import confirmar_carrito

        pedido = make_pedido(EstadoPedido.ENLACE)
        gestor = make_gestor_pedidos(pedido)
        mock_gp = MagicMock()
        mock_gp.obtener_producto_por_codigo.return_value = {"Precio": None}

        success, msg = confirmar_carrito(
            pedido_id_redis="uuid-null-precio",
            name="Test",
            token="tok",
            user_id=1,
            numero="+34600000000",
            direccion="Calle Mayor 1",
            productos_recibidos=[{"Codigo": "P001", "nombre": "X", "cantidad": 1}],
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=mock_gp,
            public_url=PUBLIC_URL,
        )

        assert success is False
        assert "precio" in msg.lower() or "disponible" in msg.lower()


# ---------------------------------------------------------------------------
# iniciar_pago
# ---------------------------------------------------------------------------

class TestIniciarPago:
    def _make_monei(self, redirect_url: str = "https://monei.com/pay/xyz") -> MagicMock:
        m = MagicMock()
        m.payments.create.return_value = {
            "next_action": {"redirect_url": redirect_url}
        }
        return m

    def _make_gestor_productos(self, precio: float = 3.5) -> MagicMock:
        gp = MagicMock()
        gp.obtener_producto_por_codigo.return_value = {"Precio": precio}
        return gp

    def test_happy_path_returns_redirect_url(self):
        from controllers.pago import iniciar_pago

        pedido = make_pedido(EstadoPedido.ENLACE2)
        gestor = make_gestor_pedidos(pedido)

        success, result = iniciar_pago(
            user_id=10,
            productos_recibidos=PRODUCTOS_VALIDOS_PAGO,
            nombre_cliente="Maria",
            numero_cliente="+34600000005",
            direccion_cliente="C/ Test 3",
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=self._make_gestor_productos(),
            monei=self._make_monei("https://monei.com/pay/123"),
            public_url=PUBLIC_URL,
        )

        assert success is True
        assert result == "https://monei.com/pay/123"

    def test_state_transitioned_to_confirmando_pago(self):
        from controllers.pago import iniciar_pago

        pedido = make_pedido(EstadoPedido.ENLACE2)
        gestor = make_gestor_pedidos(pedido)

        iniciar_pago(
            user_id=10,
            productos_recibidos=PRODUCTOS_VALIDOS_PAGO,
            nombre_cliente="Maria",
            numero_cliente="+34600000005",
            direccion_cliente="C/ Test 3",
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=self._make_gestor_productos(),
            monei=self._make_monei(),
            public_url=PUBLIC_URL,
        )

        gestor.actualizar_estado.assert_called_once_with(pedido.PedidoID, EstadoPedido.CONFIRMANDO_PAGO)

    def test_product_not_found_returns_false(self):
        from controllers.pago import iniciar_pago

        pedido = make_pedido(EstadoPedido.ENLACE2)
        gestor = make_gestor_pedidos(pedido)

        gp = MagicMock()
        gp.obtener_producto_por_codigo.return_value = None  # product missing

        success, msg = iniciar_pago(
            user_id=10,
            productos_recibidos=PRODUCTOS_VALIDOS_PAGO,
            nombre_cliente="Maria",
            numero_cliente="+34",
            direccion_cliente="C/",
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=gp,
            monei=self._make_monei(),
            public_url=PUBLIC_URL,
        )

        assert success is False
        assert "BOC001" in msg

    def test_no_active_order_returns_false(self):
        from controllers.pago import iniciar_pago

        gestor = MagicMock()
        gestor.obtener_pedido_mas_reciente.return_value = None

        success, msg = iniciar_pago(
            user_id=99,
            productos_recibidos=[],
            nombre_cliente="X",
            numero_cliente="+34",
            direccion_cliente="C/",
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=self._make_gestor_productos(),
            monei=self._make_monei(),
            public_url=PUBLIC_URL,
        )

        assert success is False
        assert "pedido activo" in msg.lower()

    def test_already_in_confirmando_pago_returns_true(self):
        from controllers.pago import iniciar_pago

        pedido = make_pedido(EstadoPedido.CONFIRMANDO_PAGO)
        gestor = make_gestor_pedidos(pedido)

        success, msg = iniciar_pago(
            user_id=10,
            productos_recibidos=PRODUCTOS_VALIDOS_PAGO,
            nombre_cliente="X",
            numero_cliente="+34",
            direccion_cliente="C/",
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=self._make_gestor_productos(),
            monei=self._make_monei(),
            public_url=PUBLIC_URL,
        )

        assert success is True
        assert "proceso de pago" in msg.lower()

    def test_monei_api_exception_returns_false(self):
        from controllers.pago import iniciar_pago
        from Monei import ApiException

        pedido = make_pedido(EstadoPedido.ENLACE2)
        gestor = make_gestor_pedidos(pedido)

        monei_mock = MagicMock()
        monei_mock.payments.create.side_effect = ApiException(status=500, reason="Server Error")

        success, msg = iniciar_pago(
            user_id=10,
            productos_recibidos=PRODUCTOS_VALIDOS_PAGO,
            nombre_cliente="X",
            numero_cliente="+34",
            direccion_cliente="C/",
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=self._make_gestor_productos(),
            monei=monei_mock,
            public_url=PUBLIC_URL,
        )

        assert success is False

    def test_monei_missing_redirect_url_returns_false(self):
        from controllers.pago import iniciar_pago

        pedido = make_pedido(EstadoPedido.ENLACE2)
        gestor = make_gestor_pedidos(pedido)

        monei_mock = MagicMock()
        monei_mock.payments.create.return_value = {"next_action": {}}  # no redirect_url

        success, msg = iniciar_pago(
            user_id=10,
            productos_recibidos=PRODUCTOS_VALIDOS_PAGO,
            nombre_cliente="X",
            numero_cliente="+34",
            direccion_cliente="C/",
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=self._make_gestor_productos(),
            monei=monei_mock,
            public_url=PUBLIC_URL,
        )

        assert success is False
        assert "redirección" in msg.lower()

    def test_notas_se_asigna_al_pedido(self):
        """iniciar_pago debe asignar notas al objeto pedido."""
        from controllers.pago import iniciar_pago

        pedido = make_pedido(EstadoPedido.ENLACE2)
        gestor = make_gestor_pedidos(pedido)

        iniciar_pago(
            user_id=10,
            productos_recibidos=PRODUCTOS_VALIDOS_PAGO,
            nombre_cliente="Maria",
            numero_cliente="+34600000005",
            direccion_cliente="C/ Test 3",
            notas="No tocar el timbre",
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=self._make_gestor_productos(),
            monei=self._make_monei("https://monei.com/pay/123"),
            public_url=PUBLIC_URL,
        )

        assert pedido.Notas == "No tocar el timbre"

    def test_notas_vacio_por_defecto(self):
        """iniciar_pago sin notas no debe fallar (backward compat)."""
        from controllers.pago import iniciar_pago

        pedido = make_pedido(EstadoPedido.ENLACE2)
        gestor = make_gestor_pedidos(pedido)

        success, _ = iniciar_pago(
            user_id=10,
            productos_recibidos=PRODUCTOS_VALIDOS_PAGO,
            nombre_cliente="Maria",
            numero_cliente="+34600000005",
            direccion_cliente="C/ Test 3",
            cache=make_cache(),
            gestor_pedidos=gestor,
            gestor_productos=self._make_gestor_productos(),
            monei=self._make_monei(),
            public_url=PUBLIC_URL,
        )

        assert success is True


# ---------------------------------------------------------------------------
# iniciar_pago_efectivo
# ---------------------------------------------------------------------------

class TestIniciarPagoEfectivo:
    def _make_gestor_productos(self, precio: float = 3.5) -> MagicMock:
        gp = MagicMock()
        gp.obtener_producto_por_codigo.return_value = {"Precio": precio}
        return gp

    def test_notas_se_asigna_al_pedido(self):
        from controllers.pago import iniciar_pago_efectivo

        pedido = make_pedido(EstadoPedido.ENLACE2)
        gestor = make_gestor_pedidos(pedido)

        with patch("controllers.pago_notifier.enviar_mensaje_whatsapp"):
            iniciar_pago_efectivo(
                user_id=10,
                productos_recibidos=PRODUCTOS_VALIDOS_PAGO,
                nombre_cliente="Maria",
                numero_cliente="+34600000005",
                direccion_cliente="C/ Test 3",
                notas="Dejar en portería",
                cache=make_cache(),
                gestor_pedidos=gestor,
                gestor_productos=self._make_gestor_productos(),
                public_url=PUBLIC_URL,
            )

        assert pedido.Notas == "Dejar en portería"

    def test_notas_vacio_por_defecto(self):
        from controllers.pago import iniciar_pago_efectivo

        pedido = make_pedido(EstadoPedido.ENLACE2)
        gestor = make_gestor_pedidos(pedido)

        with patch("controllers.pago_notifier.enviar_mensaje_whatsapp"):
            success, _ = iniciar_pago_efectivo(
                user_id=10,
                productos_recibidos=PRODUCTOS_VALIDOS_PAGO,
                nombre_cliente="Maria",
                numero_cliente="+34600000005",
                direccion_cliente="C/ Test 3",
                cache=make_cache(),
                gestor_pedidos=gestor,
                gestor_productos=self._make_gestor_productos(),
                public_url=PUBLIC_URL,
            )

        assert success is True


# ---------------------------------------------------------------------------
# POST /api/cambiar_estado_a_enlace
# ---------------------------------------------------------------------------

class TestCambiarEstadoAEnlace:

    def _post(self, client, pedido_id=1, token=INTERNAL_TOKEN):
        headers = {"X-Internal-Token": token} if token else {}
        return client.post(
            "/api/cambiar_estado_a_enlace",
            json={"pedidoID": pedido_id},
            headers=headers,
        )

    def test_sin_token_retorna_401(self, client):
        with patch("blueprints.api.cart.config") as mock_cfg:
            mock_cfg.INTERNAL_API_TOKEN = INTERNAL_TOKEN
            resp = self._post(client, token=None)
        assert resp.status_code == 401

    def test_token_incorrecto_retorna_401(self, client):
        with patch("blueprints.api.cart.config") as mock_cfg:
            mock_cfg.INTERNAL_API_TOKEN = INTERNAL_TOKEN
            resp = self._post(client, token="token-equivocado")
        assert resp.status_code == 401

    def test_sin_pedido_id_retorna_400(self, client):
        with patch("blueprints.api.cart.config") as mock_cfg:
            mock_cfg.INTERNAL_API_TOKEN = INTERNAL_TOKEN
            resp = client.post(
                "/api/cambiar_estado_a_enlace",
                json={},
                headers={"X-Internal-Token": INTERNAL_TOKEN},
            )
        assert resp.status_code == 400

    def test_pedido_no_encontrado_retorna_404(self, client):
        with patch("blueprints.api.cart.config") as mock_cfg:
            mock_cfg.INTERNAL_API_TOKEN = INTERNAL_TOKEN
            with patch("blueprints.api.cart.gestor_pedidos") as mock_gp:
                mock_gp.obtener_pedido.return_value = None
                resp = self._post(client, pedido_id=999)
        assert resp.status_code == 404

    def test_pedido_en_confirmando_pago_retorna_400(self, client):
        pedido = MagicMock()
        pedido.Estado = EstadoPedido.CONFIRMANDO_PAGO
        pedido.PedidoID = 5
        with patch("blueprints.api.cart.config") as mock_cfg:
            mock_cfg.INTERNAL_API_TOKEN = INTERNAL_TOKEN
            with patch("blueprints.api.cart.gestor_pedidos") as mock_gp:
                mock_gp.obtener_pedido.return_value = pedido
                resp = self._post(client, pedido_id=5)
        assert resp.status_code == 400

    def test_pedido_en_enlace2_actualiza_a_enlace(self, client):
        pedido = MagicMock()
        pedido.Estado = EstadoPedido.ENLACE2
        pedido.PedidoID = 7
        with patch("blueprints.api.cart.config") as mock_cfg:
            mock_cfg.INTERNAL_API_TOKEN = INTERNAL_TOKEN
            with patch("blueprints.api.cart.gestor_pedidos") as mock_gp:
                mock_gp.obtener_pedido.return_value = pedido
                mock_gp.actualizar_estado.return_value = True
                resp = self._post(client, pedido_id=7)
        assert resp.status_code == 200
        mock_gp.actualizar_estado.assert_called_once_with(7, EstadoPedido.ENLACE)


def test_agregar_pedido_carrito_vacio(client):
    """POST /api/agregar_pedido con carrito vacío debe devolver 400."""
    resp = client.post('/api/agregar_pedido', json={
        'token': 'token-invalido',
        'carrito': [],
    })
    assert resp.status_code in (400, 401, 422)
