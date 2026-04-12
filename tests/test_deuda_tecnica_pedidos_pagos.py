"""Tests para los bugs documentados en docs/deuda_tecnica_pedidos_pagos.md.

Cada clase corresponde a un bug del informe. Mock-only — no requiere BD ni Redis real
(fakeredis del conftest).
"""
import json
import pytest
from unittest.mock import MagicMock, patch

from states import EstadoPedido


# ---------------------------------------------------------------------------
# Helpers compartidos
# ---------------------------------------------------------------------------

def _mock_session_with_query_result(result_list):
    """Devuelve un mock de session cuyo query().filter().filter().all() = result_list."""
    session = MagicMock()
    chain = session.query.return_value
    chain.filter.return_value.filter.return_value.all.return_value = result_list
    return session


# ===========================================================================
# Bug I — cancelar_pedidos_caducados incluye CONFIRMANDO_PAGO
# ===========================================================================

class TestBugICancelarConfirmandoPago:
    def _make_gestor(self, pedidos_resultantes):
        from managers.gestor_pedidos import GestorPedidos
        g = GestorPedidos()
        session = _mock_session_with_query_result(pedidos_resultantes)
        return g, session

    def test_cancela_pedido_confirmando_pago_caducado(self):
        pedido = MagicMock()
        pedido.PedidoID = 42
        pedido.Estado = EstadoPedido.CONFIRMANDO_PAGO
        g, session = self._make_gestor([pedido])

        with patch.object(type(g), "session", new_callable=lambda: property(lambda self: session)):
            with patch.object(g, "_set_estado", return_value=True) as mock_set:
                cancelados = g.cancelar_pedidos_caducados(umbral_minutos=60)

        assert cancelados == 1
        mock_set.assert_called_once()
        # _set_estado debe ser llamado pidiendo CANCELADO
        assert mock_set.call_args.args[1] == EstadoPedido.CANCELADO
        session.commit.assert_called_once()

    def test_filtro_estados_incluye_confirmando_pago(self):
        """El filtro IN debe contener los tres estados (ENLACE, ENLACE2, CONFIRMANDO_PAGO)."""
        from sqlalchemy.sql.elements import BinaryExpression
        g, session = self._make_gestor([])

        with patch.object(type(g), "session", new_callable=lambda: property(lambda self: session)):
            g.cancelar_pedidos_caducados(umbral_minutos=60)

        # session.query(Pedido).filter(Pedido.Estado.in_(estados)).filter(...).all()
        # primer filter es el .in_
        primer_filter = session.query.return_value.filter.call_args.args[0]
        # El BinaryExpression.right contiene los valores del IN
        # Convertimos a string para comprobar presencia de los tres estados
        sql_text = str(primer_filter.compile(compile_kwargs={"literal_binds": True}))
        assert EstadoPedido.ENLACE.value in sql_text
        assert EstadoPedido.ENLACE2.value in sql_text
        assert EstadoPedido.CONFIRMANDO_PAGO.value in sql_text

    def test_no_toca_pedidos_pagados_o_en_preparacion(self):
        """Sin pedidos en los estados objetivo → 0 cancelaciones, 0 commits."""
        g, session = self._make_gestor([])

        with patch.object(type(g), "session", new_callable=lambda: property(lambda self: session)):
            cancelados = g.cancelar_pedidos_caducados(umbral_minutos=60)

        assert cancelados == 0
        session.commit.assert_not_called()


# ===========================================================================
# Bug A — Bot maneja fallo de cancelación en CONFIRMANDO_PAGO con enlace nulo
# ===========================================================================

NUMERO = "whatsapp:+34600000000"
USUARIO_DATOS = {"id": 1, "nombre": "Ana", "direccion": "Calle Mayor 1"}


def _make_pedido_confirmando_sin_enlace():
    p = MagicMock()
    p.Estado = EstadoPedido.CONFIRMANDO_PAGO
    p.PedidoID = 99
    p.enlace = None
    p.reparto = None
    return p


class TestBugAFalloCancelacionEnlaceNulo:
    def test_fallo_cancelar_envia_error_sistema_y_no_envia_enlace_caducado(self):
        from controllers.mensajes_registrados import ManejadorMensajesRegistrados

        pedido = _make_pedido_confirmando_sin_enlace()
        with patch("controllers.mensajes_registrados.gestor_usuarios") as mock_gu, \
             patch("controllers.mensajes_registrados.gestor_pedidos") as mock_gp, \
             patch("controllers.mensajes_registrados._enviar_error_sistema") as mock_err, \
             patch("controllers.mensajes_registrados._enviar_enlace_pago_caducado") as mock_caducado:

            mock_gu.obtener_usuario_completo.return_value = USUARIO_DATOS
            mock_gp.obtener_pedido_mas_reciente.return_value = pedido
            mock_gp.actualizar_estado.side_effect = RuntimeError("DB caída")

            result = ManejadorMensajesRegistrados.manejar_mensajes_registrados(NUMERO, "hola")

        assert result == ("error cancelando pedido", 200)
        mock_err.assert_called_once_with(NUMERO)
        mock_caducado.assert_not_called()

    def test_camino_feliz_cancelacion_exitosa_envia_enlace_caducado(self):
        from controllers.mensajes_registrados import ManejadorMensajesRegistrados

        pedido = _make_pedido_confirmando_sin_enlace()
        with patch("controllers.mensajes_registrados.gestor_usuarios") as mock_gu, \
             patch("controllers.mensajes_registrados.gestor_pedidos") as mock_gp, \
             patch("controllers.mensajes_registrados._enviar_error_sistema") as mock_err, \
             patch("controllers.mensajes_registrados._enviar_enlace_pago_caducado") as mock_caducado:

            mock_gu.obtener_usuario_completo.return_value = USUARIO_DATOS
            mock_gp.obtener_pedido_mas_reciente.return_value = pedido
            mock_gp.actualizar_estado.return_value = True

            result = ManejadorMensajesRegistrados.manejar_mensajes_registrados(NUMERO, "hola")

        assert result == ("mensaje enviado", 200)
        mock_caducado.assert_called_once_with(NUMERO)
        mock_err.assert_not_called()


# ===========================================================================
# Bug C — Webhook Monei usa TelefonoEntrega/DireccionEntrega del pedido en BD
# ===========================================================================

def _payload_monei(order_id=42, customer_phone=None, billing_line1=None):
    return {
        "type": "charge.succeeded",
        "object": {
            "orderId": str(order_id),
            "id": "ch_test_123",
            "status": "SUCCEEDED",
            "amount": 1500,
            "description": "Pedido Ana",
            "customer": {"phone": customer_phone} if customer_phone is not None else {},
            "billingDetails": {"address": {"line1": billing_line1}} if billing_line1 else {},
        },
    }


class TestBugCWebhookMoneiTelefonoDesdeBD:
    def test_phone_none_envia_a_telefono_real_del_pedido(self, app):
        from services import inbound_whatsapp

        pedido_db = MagicMock()
        pedido_db.TelefonoEntrega = "whatsapp:+34611222333"
        pedido_db.DireccionEntrega = "Calle Real 7"

        with app.app_context(), \
             patch.object(inbound_whatsapp, "gestor_pedidos") as mock_gp, \
             patch.object(inbound_whatsapp, "enviar_mensaje_whatsapp") as mock_send:

            mock_gp.procesar_pago_confirmado.return_value = True
            mock_gp.obtener_pedido.return_value = pedido_db

            resp, status = inbound_whatsapp.procesar_pago_monei(_payload_monei(customer_phone=None))

        assert status == 200
        mock_send.assert_called_once()
        args = mock_send.call_args.args
        assert args[1] == "whatsapp:+34611222333"
        assert "Calle Real 7" in args[0]

    def test_pedido_inexistente_no_envia_mensaje(self, app):
        from services import inbound_whatsapp

        with app.app_context(), \
             patch.object(inbound_whatsapp, "gestor_pedidos") as mock_gp, \
             patch.object(inbound_whatsapp, "enviar_mensaje_whatsapp") as mock_send:

            mock_gp.procesar_pago_confirmado.return_value = True
            mock_gp.obtener_pedido.return_value = None

            resp, status = inbound_whatsapp.procesar_pago_monei(_payload_monei())

        assert status == 200
        mock_send.assert_not_called()

    def test_db_error_cargando_pedido_no_rompe_webhook(self, app):
        from services import inbound_whatsapp
        from sqlalchemy.exc import SQLAlchemyError

        with app.app_context(), \
             patch.object(inbound_whatsapp, "gestor_pedidos") as mock_gp, \
             patch.object(inbound_whatsapp, "enviar_mensaje_whatsapp") as mock_send:

            mock_gp.procesar_pago_confirmado.return_value = True
            mock_gp.obtener_pedido.side_effect = SQLAlchemyError("timeout")

            resp, status = inbound_whatsapp.procesar_pago_monei(_payload_monei())

        # El pago YA se procesó: no rompemos el webhook ni reintentamos
        assert status == 200
        mock_send.assert_not_called()


# ===========================================================================
# Bug B — Reintento RQ tras fallo de confirmación efectivo
# ===========================================================================

def _make_gestor_pedidos_efectivo():
    g = MagicMock()
    pedido = MagicMock()
    pedido.PedidoID = 1
    pedido.Estado = EstadoPedido.ENLACE2
    pedido.redisID = "redis-abc"
    g.obtener_pedido_mas_reciente.return_value = pedido
    g.confirmar_pago_efectivo.return_value = True
    return g


def _make_gestor_productos():
    gp = MagicMock()
    gp.obtener_productos_por_codigos.return_value = {1: {"Precio": 3.5}}
    return gp


class TestBugBReintentoRQEfectivo:
    PRODUCTOS = [{"codigo": 1, "cantidad": 2}]

    def test_fallo_envio_encola_reintento_en_queue_whatsapp(self):
        from controllers.pago import iniciar_pago_efectivo
        import controllers.pago_notifier as notifier

        gestor = _make_gestor_pedidos_efectivo()

        # Forzar fallo del envío síncrono
        with patch.object(notifier, "enviar_mensaje_whatsapp", side_effect=RuntimeError("twilio 503")), \
             patch("message_queue.queue_whatsapp") as mock_queue:

            success, _ = iniciar_pago_efectivo(
                user_id=10,
                productos_recibidos=self.PRODUCTOS,
                nombre_cliente="Ana",
                numero_cliente="whatsapp:+34600000000",
                direccion_cliente="C/ Test 1",
                gestor_pedidos=gestor,
                gestor_productos=_make_gestor_productos(),
                public_url="https://example.com",
            )

        assert success is True  # el pedido sigue OK aunque falle WhatsApp
        mock_queue.enqueue.assert_called_once()
        # Primer arg posicional del enqueue debe ser el job de reintento
        first_arg = mock_queue.enqueue.call_args.args[0]
        assert first_arg.__name__ == "_job_reintentar_confirmacion_efectivo"

    def test_fallo_de_encolar_no_rompe_endpoint(self):
        from controllers.pago import iniciar_pago_efectivo
        import controllers.pago_notifier as notifier

        gestor = _make_gestor_pedidos_efectivo()

        with patch.object(notifier, "enviar_mensaje_whatsapp", side_effect=RuntimeError("twilio 503")), \
             patch("message_queue.queue_whatsapp") as mock_queue:
            mock_queue.enqueue.side_effect = RuntimeError("redis caído")

            success, _ = iniciar_pago_efectivo(
                user_id=10,
                productos_recibidos=self.PRODUCTOS,
                nombre_cliente="Ana",
                numero_cliente="whatsapp:+34600000000",
                direccion_cliente="C/ Test 1",
                gestor_pedidos=gestor,
                gestor_productos=_make_gestor_productos(),
                public_url="https://example.com",
            )

        # Aunque encolar falle, el pedido sigue confirmado
        assert success is True


# ===========================================================================
# Bug D — Lock por usuario en confirmar_carrito
# ===========================================================================

class TestBugDLockCarrito:
    PRODUCTOS = [{"Codigo": 1, "nombre": "X", "cantidad": 1}]

    def _gp(self):
        gp = MagicMock()
        gp.obtener_productos_por_codigos.return_value = {1: {"Precio": 3.5}}
        return gp

    def _pedidos_manager(self):
        from unittest.mock import MagicMock
        m = MagicMock()
        pedido = MagicMock()
        pedido.PedidoID = 1
        pedido.Estado = EstadoPedido.ENLACE
        pedido.redisID = "rid"
        m.obtener_pedido_mas_reciente.return_value = pedido
        m.fijar_carrito_confirmado.return_value = True
        return m

    def _cache(self):
        c = MagicMock()
        c.set.return_value = True
        return c

    def test_segunda_llamada_simultanea_es_rechazada(self):
        from controllers.carrito import confirmar_carrito
        from container import redismanager

        # Pre-adquirir el lock manualmente para simular llamada en curso
        assert redismanager.adquirir_lock("carrito_lock:99", ttl=10) is True

        success, msg = confirmar_carrito(
            pedido_id_redis="uuid-x",
            name="Ana",
            token="t",
            user_id=99,
            numero="+34",
            direccion="C/",
            productos_recibidos=self.PRODUCTOS,
            cache=self._cache(),
            pedidos_manager=self._pedidos_manager(),
            gestor_productos=self._gp(),
            public_url="https://example.com",
        )

        assert success is False
        assert "espera" in msg.lower() or "procesando" in msg.lower()

    def test_primera_llamada_adquiere_lock_y_procede(self):
        from controllers.carrito import confirmar_carrito

        success, _ = confirmar_carrito(
            pedido_id_redis="uuid-y",
            name="Ana",
            token="t",
            user_id=100,
            numero="+34",
            direccion="C/",
            productos_recibidos=self.PRODUCTOS,
            cache=self._cache(),
            pedidos_manager=self._pedidos_manager(),
            gestor_productos=self._gp(),
            public_url="https://example.com",
        )

        assert success is True


# ===========================================================================
# Bug E — userId/userID ausente devuelve 400 (no 403)
# ===========================================================================

class TestBugEUserIdAusente400:
    def test_confirmacion_sin_userId_devuelve_400(self, client):
        with patch("blueprints.api.cart._user_id_del_token", return_value=42):
            resp = client.post("/api/confirmacion", json={"token": "tok"})
        assert resp.status_code == 400
        assert b"userId" in resp.data or b"falta" in resp.data.lower()

    def test_agregar_pedido_sin_userID_devuelve_400(self, client):
        with patch("blueprints.api.payments._user_id_del_token", return_value=42):
            resp = client.post("/api/agregar_pedido", json={"token": "tok"})
        assert resp.status_code == 400
        assert b"userID" in resp.data or b"falta" in resp.data.lower()

    def test_agregar_pedido_efectivo_sin_userID_devuelve_400(self, client):
        with patch("blueprints.api.payments._user_id_del_token", return_value=42):
            resp = client.post("/api/agregar_pedido_efectivo", json={"token": "tok"})
        assert resp.status_code == 400
        assert b"userID" in resp.data or b"falta" in resp.data.lower()

    def test_userId_mismatch_sigue_devolviendo_403(self, client):
        """No regresión: con userId presente pero distinto, sigue siendo 403."""
        with patch("blueprints.api.cart._user_id_del_token", return_value=42):
            resp = client.post("/api/confirmacion", json={"token": "tok", "userId": 99})
        assert resp.status_code == 403
