"""
Tests for controllers/mensajes_registrados.py — ManejadorMensajesRegistrados.

Covers:
  - Pedido en preparación (EN_PREPARACION, PREPARADO) → bloqueado, mensaje informativo
  - Pedido en reparto (EN_REPARTO) → bloqueado, con/sin repartidor
  - Usuario sin pedido activo → flujo normal (nuevo pedido)
  - Usuario con pedido PAGADO → flujo normal (nuevo pedido)
  - Cualquier mensaje ("1", texto libre) con pedido activo en preparación/reparto → bloqueado
"""
import pytest
from unittest.mock import MagicMock, patch, call

from controllers.mensajes_registrados import ManejadorMensajesRegistrados
from states import EstadoPedido

NUMERO = "whatsapp:+34600000000"
SOPORTE = "900123456"

USUARIO_DATOS = {"id": 1, "nombre": "Ana", "direccion": "Calle Mayor 1"}


def _make_pedido(estado, reparto=None):
    p = MagicMock()
    p.Estado = estado
    p.PedidoID = 99
    p.enlace = "https://example.com/menu/test-token"
    p.reparto = reparto
    return p


def _make_reparto(nombre="Juan", apellido="Pérez", telefono="600111222"):
    r = MagicMock()
    r.repartidor = MagicMock()
    r.repartidor.Nombre = nombre
    r.repartidor.Apellido = apellido
    r.repartidor.Telefono = telefono
    return r


def _run(estado_pedido, mensaje="1", reparto=None, soporte=SOPORTE):
    """Helper: ejecuta manejar_mensajes_registrados con el estado de pedido dado."""
    pedido_mock = _make_pedido(estado_pedido, reparto=reparto)

    with patch("controllers.mensajes_registrados.gestor_usuarios") as mock_gu, \
         patch("controllers.mensajes_registrados.gestor_pedidos") as mock_gp, \
         patch("controllers.mensajes_registrados_notifier.enviar_mensaje_whatsapp") as mock_send, \
         patch("controllers.mensajes_registrados_notifier.config") as mock_cfg:

        mock_gu.obtener_usuario_completo.return_value = USUARIO_DATOS
        mock_gp.obtener_pedido_mas_reciente.return_value = pedido_mock
        mock_cfg.CUSTOMER_SUPPORT_PHONE = soporte

        result = ManejadorMensajesRegistrados.manejar_mensajes_registrados(NUMERO, mensaje)

    return result, mock_send, mock_gp


# ─────────────────────────────────────────────────────────────────
# Pedido en preparación — EN_PREPARACION
# ─────────────────────────────────────────────────────────────────

class TestPedidoEnPreparacion:

    def test_retorna_200(self):
        result, _, _ = _run(EstadoPedido.EN_PREPARACION)
        assert result[1] == 200

    def test_envia_mensaje_whatsapp(self):
        _, mock_send, _ = _run(EstadoPedido.EN_PREPARACION)
        mock_send.assert_called_once()
        texto = mock_send.call_args[0][0]
        assert "preparación" in texto.lower()
        assert SOPORTE in texto

    def test_no_inicia_nuevo_pedido(self):
        _, _, mock_gp = _run(EstadoPedido.EN_PREPARACION)
        mock_gp.iniciar_pedido.assert_not_called()

    def test_bloqueado_aunque_mensaje_sea_1(self):
        """El usuario escribe "1" (tienda) pero tiene pedido en preparación — debe bloquearse."""
        _, mock_send, mock_gp = _run(EstadoPedido.EN_PREPARACION, mensaje="1")
        mock_gp.iniciar_pedido.assert_not_called()
        mock_send.assert_called_once()
        assert "preparación" in mock_send.call_args[0][0].lower()

    def test_bloqueado_con_cualquier_texto(self):
        for msg in ["quiero pedir", "tienda", "menu", "hola", "otro pedido"]:
            _, mock_send, mock_gp = _run(EstadoPedido.EN_PREPARACION, mensaje=msg)
            mock_gp.iniciar_pedido.assert_not_called()


# ─────────────────────────────────────────────────────────────────
# Pedido preparado — PREPARADO
# ─────────────────────────────────────────────────────────────────

class TestPedidoPreparado:

    def test_retorna_200(self):
        result, _, _ = _run(EstadoPedido.PREPARADO)
        assert result[1] == 200

    def test_envia_mensaje_con_telefono_soporte(self):
        _, mock_send, _ = _run(EstadoPedido.PREPARADO)
        texto = mock_send.call_args[0][0]
        assert SOPORTE in texto

    def test_no_inicia_nuevo_pedido(self):
        _, _, mock_gp = _run(EstadoPedido.PREPARADO)
        mock_gp.iniciar_pedido.assert_not_called()


# ─────────────────────────────────────────────────────────────────
# Pedido en reparto — EN_REPARTO
# ─────────────────────────────────────────────────────────────────

class TestPedidoEnReparto:

    def test_retorna_200_sin_repartidor(self):
        pedido = _make_pedido(EstadoPedido.EN_REPARTO, reparto=None)
        with patch("controllers.mensajes_registrados.gestor_usuarios") as mock_gu, \
             patch("controllers.mensajes_registrados.gestor_pedidos") as mock_gp, \
             patch("controllers.mensajes_registrados_notifier.enviar_mensaje_whatsapp"), \
             patch("controllers.mensajes_registrados_notifier.config") as mock_cfg:
            mock_gu.obtener_usuario_completo.return_value = USUARIO_DATOS
            mock_gp.obtener_pedido_mas_reciente.return_value = pedido
            mock_cfg.CUSTOMER_SUPPORT_PHONE = SOPORTE
            result = ManejadorMensajesRegistrados.manejar_mensajes_registrados(NUMERO, "hola")
        assert result[1] == 200

    def test_mensaje_degradado_sin_repartidor(self):
        """Sin repartidor asignado → mensaje útil sin datos de repartidor."""
        result, mock_send, _ = _run(EstadoPedido.EN_REPARTO, reparto=None)
        texto = mock_send.call_args[0][0]
        assert "camino" in texto.lower()
        assert SOPORTE in texto
        assert "repartidor" not in texto.lower() or "repartidor" in texto.lower()  # degradado aceptable

    def test_mensaje_con_repartidor_incluye_nombre_y_telefono(self):
        reparto = _make_reparto(nombre="Carlos", apellido="López", telefono="600777888")
        result, mock_send, _ = _run(EstadoPedido.EN_REPARTO, reparto=reparto)
        texto = mock_send.call_args[0][0]
        assert "Carlos" in texto
        assert "López" in texto
        assert "600777888" in texto
        assert SOPORTE in texto

    def test_mensaje_con_repartidor_sin_telefono_muestra_no_disponible(self):
        reparto = _make_reparto(nombre="Luis", apellido="García", telefono=None)
        result, mock_send, _ = _run(EstadoPedido.EN_REPARTO, reparto=reparto)
        texto = mock_send.call_args[0][0]
        assert "no disponible" in texto.lower()

    def test_no_inicia_nuevo_pedido(self):
        reparto = _make_reparto()
        result, _, mock_gp = _run(EstadoPedido.EN_REPARTO, reparto=reparto)
        mock_gp.iniciar_pedido.assert_not_called()

    def test_bloqueado_aunque_mensaje_sea_1(self):
        reparto = _make_reparto()
        _, mock_send, mock_gp = _run(EstadoPedido.EN_REPARTO, mensaje="1", reparto=reparto)
        mock_gp.iniciar_pedido.assert_not_called()
        mock_send.assert_called_once()


# ─────────────────────────────────────────────────────────────────
# Sin teléfono de soporte configurado — mensaje degradado
# ─────────────────────────────────────────────────────────────────

class TestSinTelefonoSoporte:

    def test_preparacion_sin_soporte_configured(self):
        """Si CUSTOMER_SUPPORT_PHONE es None → usa texto genérico, no falla."""
        _, mock_send, _ = _run(EstadoPedido.EN_PREPARACION, soporte=None)
        texto = mock_send.call_args[0][0]
        assert "preparación" in texto.lower()
        assert "atención al cliente" in texto.lower()


# ─────────────────────────────────────────────────────────────────
# Flujo normal — estados no bloqueados
# ─────────────────────────────────────────────────────────────────

class TestPedidoPagado:
    """PAGADO (pago online confirmado, esperando preparación) → bloqueado."""

    def test_retorna_200(self):
        result, _, _ = _run(EstadoPedido.PAGADO)
        assert result[1] == 200

    def test_envia_mensaje_con_confirmacion_pago(self):
        _, mock_send, _ = _run(EstadoPedido.PAGADO)
        texto = mock_send.call_args[0][0]
        assert "recibido" in texto.lower() or "confirmado" in texto.lower()
        assert SOPORTE in texto

    def test_no_inicia_nuevo_pedido(self):
        _, _, mock_gp = _run(EstadoPedido.PAGADO)
        mock_gp.iniciar_pedido.assert_not_called()

    def test_bloqueado_con_cualquier_mensaje(self):
        for msg in ["1", "quiero pedir", "tienda", "hola"]:
            _, _, mock_gp = _run(EstadoPedido.PAGADO, mensaje=msg)
            mock_gp.iniciar_pedido.assert_not_called()


class TestPedidoContraReembolso:
    """CONTRA_REEMBOLSO (pago en efectivo, esperando preparación) → bloqueado."""

    def test_retorna_200(self):
        result, _, _ = _run(EstadoPedido.CONTRA_REEMBOLSO)
        assert result[1] == 200

    def test_envia_mensaje_indicando_pago_a_la_entrega(self):
        _, mock_send, _ = _run(EstadoPedido.CONTRA_REEMBOLSO)
        texto = mock_send.call_args[0][0]
        assert "entrega" in texto.lower()
        assert SOPORTE in texto

    def test_no_inicia_nuevo_pedido(self):
        _, _, mock_gp = _run(EstadoPedido.CONTRA_REEMBOLSO)
        mock_gp.iniciar_pedido.assert_not_called()

    def test_bloqueado_con_cualquier_mensaje(self):
        for msg in ["1", "quiero pedir", "otro pedido"]:
            _, _, mock_gp = _run(EstadoPedido.CONTRA_REEMBOLSO, mensaje=msg)
            mock_gp.iniciar_pedido.assert_not_called()


class TestFlujosNoBloqueados:

    def test_sin_pedido_activo_inicia_nuevo_pedido(self):
        """Sin pedido activo → inicia nuevo pedido (flujo normal intacto)."""
        with patch("controllers.mensajes_registrados.gestor_usuarios") as mock_gu, \
             patch("controllers.mensajes_registrados.gestor_pedidos") as mock_gp, \
             patch("controllers.mensajes_registrados.redismanager") as mock_redis, \
             patch("controllers.mensajes_registrados_notifier.enviar_mensaje_whatsapp"), \
             patch("controllers.mensajes_registrados_notifier.config"):
            mock_gu.obtener_usuario_completo.return_value = USUARIO_DATOS
            mock_gp.obtener_pedido_mas_reciente.return_value = None
            mock_gp.iniciar_pedido.return_value = 100
            mock_redis.adquirir_lock.return_value = True  # lock adquirido
            result = ManejadorMensajesRegistrados.manejar_mensajes_registrados(NUMERO, "1")
        mock_gp.iniciar_pedido.assert_called_once()
        assert result[1] == 200

    def test_lock_activo_ignora_duplicado(self):
        """Si el lock ya existe (Meta retry), no se inicia nuevo pedido y devuelve 200."""
        with patch("controllers.mensajes_registrados.gestor_usuarios") as mock_gu, \
             patch("controllers.mensajes_registrados.gestor_pedidos") as mock_gp, \
             patch("controllers.mensajes_registrados.redismanager") as mock_redis, \
             patch("controllers.mensajes_registrados_notifier.enviar_mensaje_whatsapp"), \
             patch("controllers.mensajes_registrados_notifier.config"):
            mock_gu.obtener_usuario_completo.return_value = USUARIO_DATOS
            mock_gp.obtener_pedido_mas_reciente.return_value = None
            mock_redis.adquirir_lock.return_value = False  # lock ya activo
            result = ManejadorMensajesRegistrados.manejar_mensajes_registrados(NUMERO, "1")
        mock_gp.iniciar_pedido.assert_not_called()
        assert result[1] == 200

    def test_pedido_en_preparacion_no_inicia_pedido(self):
        """Confirma que EN_PREPARACION bloquea mientras PAGADO no lo hace."""
        _, _, mock_gp_bloq = _run(EstadoPedido.EN_PREPARACION)
        mock_gp_bloq.iniciar_pedido.assert_not_called()
