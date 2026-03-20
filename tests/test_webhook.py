"""
Tests for blueprints/webhook.py:
  - POST /webhook  (Twilio)
  - POST /webhook/monei  (Monei)
"""
import hmac
import hashlib
import json
import pytest
from unittest.mock import MagicMock, patch

from states import EstadoPedido


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

TWILIO_FROM = "whatsapp:+34600000000"
TWILIO_BODY = "hola"


def monei_body(order_id=1, status="SUCCEEDED"):
    return json.dumps({
        "type": "charge.succeeded",
        "object": {
            "orderId": str(order_id),
            "status": status,
            "amount": 1000,
            "description": "Test User",
            "customer": {"phone": TWILIO_FROM},
            "billingDetails": {"address": {"line1": "Calle Mayor 1"}},
        }
    }).encode()


MONEI_TIMESTAMP = "1700000000"


def make_monei_signature(secret: str, body: bytes, timestamp: str = MONEI_TIMESTAMP) -> str:
    """Devuelve el header MONEI-SIGNATURE completo: t=<ts>,v1=<hmac>"""
    signed_payload = f"{timestamp}.".encode() + body
    sig = hmac.HMAC(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


# ─────────────────────────────────────────────
# POST /webhook — Twilio
# ─────────────────────────────────────────────

class TestWebhookTwilio:

    def test_payload_invalido_retorna_400(self, client):
        """Payload sin From ni Body → 400."""
        resp = client.post("/webhook", data={"Campo": "basura"})
        assert resp.status_code == 400

    def test_body_vacio_retorna_400(self, client):
        """Body vacío → falla la validación de WebhookRequest."""
        resp = client.post("/webhook", data={"From": TWILIO_FROM, "Body": "  "})
        assert resp.status_code == 400

    def test_usuario_bloqueado_retorna_403(self, client):
        """Si el número está bloqueado por rate-limit → 403 sin procesar."""
        with patch("blueprints.webhook.redismanager") as mock_redis:
            mock_redis.esta_bloqueado.return_value = True
            resp = client.post("/webhook", data={"From": TWILIO_FROM, "Body": TWILIO_BODY})
        assert resp.status_code == 403

    def test_firma_invalida_retorna_403(self, client, app):
        """Con TESTING=False, una firma Twilio inválida → 403."""
        app.config["TESTING"] = False
        try:
            with patch("blueprints.webhook.RequestValidator") as mock_cls:
                mock_cls.return_value.validate.return_value = False
                with patch("blueprints.webhook.config") as mock_cfg:
                    mock_cfg.TWILIO_AUTH_TOKEN = "tok"
                    mock_cfg.PUBLIC_URL = "https://test.com"
                    resp = client.post(
                        "/webhook",
                        data={"From": TWILIO_FROM, "Body": TWILIO_BODY},
                        headers={"X-Twilio-Signature": "firma-falsa"},
                    )
        finally:
            app.config["TESTING"] = True
        assert resp.status_code == 403

    def test_firma_valida_no_bloquea(self, client, app):
        """Con TESTING=False, una firma Twilio válida pasa la verificación."""
        app.config["TESTING"] = False
        try:
            with patch("blueprints.webhook.RequestValidator") as mock_cls:
                mock_cls.return_value.validate.return_value = True
                with patch("blueprints.webhook.config") as mock_cfg:
                    mock_cfg.TWILIO_AUTH_TOKEN = "tok"
                    mock_cfg.PUBLIC_URL = "https://test.com"
                    with patch("blueprints.webhook.redismanager") as mock_redis:
                        mock_redis.esta_bloqueado.return_value = False
                        with patch("blueprints.webhook.gestor_usuarios") as mock_gu:
                            mock_gu.verificar_usuario.return_value = None
                            with patch("blueprints.webhook.manejar_registro", return_value=("ok", 200)):
                                resp = client.post(
                                    "/webhook",
                                    data={"From": TWILIO_FROM, "Body": TWILIO_BODY},
                                    headers={"X-Twilio-Signature": "firma-valida"},
                                )
        finally:
            app.config["TESTING"] = True
        assert resp.status_code == 200

    def test_usuario_no_registrado_llama_manejar_registro(self, client):
        """Usuario desconocido → delega a manejar_registro."""
        with patch("blueprints.webhook.redismanager") as mock_redis:
            mock_redis.esta_bloqueado.return_value = False
            with patch("blueprints.webhook.gestor_usuarios") as mock_gu:
                mock_gu.verificar_usuario.return_value = None
                with patch("blueprints.webhook.manejar_registro", return_value=("ok", 200)) as mock_reg:
                    resp = client.post("/webhook", data={"From": TWILIO_FROM, "Body": TWILIO_BODY})
        assert resp.status_code == 200
        mock_reg.assert_called_once()

    def test_usuario_registrado_llama_manejador(self, client):
        """Usuario registrado → delega a ManejadorMensajesRegistrados."""
        usuario_mock = MagicMock()
        with patch("blueprints.webhook.redismanager") as mock_redis:
            mock_redis.esta_bloqueado.return_value = False
            with patch("blueprints.webhook.gestor_usuarios") as mock_gu:
                mock_gu.verificar_usuario.return_value = usuario_mock
                with patch(
                    "blueprints.webhook.ManejadorMensajesRegistrados.manejar_mensajes_registrados",
                    return_value=("ok", 200)
                ) as mock_man:
                    resp = client.post("/webhook", data={"From": TWILIO_FROM, "Body": TWILIO_BODY})
        assert resp.status_code == 200
        mock_man.assert_called_once()


# ─────────────────────────────────────────────
# POST /webhook/monei — Monei
# ─────────────────────────────────────────────

MONEI_SECRET = "test_webhook_secret"


class TestWebhookMonei:

    def _post(self, client, body: bytes, signature: str = ""):
        return client.post(
            "/webhook/monei",
            data=body,
            content_type="application/json",
            headers={"MONEI-SIGNATURE": signature},
        )

    def test_sin_secret_configurado_retorna_401(self, client):
        """Sin MONEI_WEBHOOK_SECRET configurado → 401."""
        with patch("blueprints.webhook.config") as mock_cfg:
            mock_cfg.MONEI_WEBHOOK_SECRET = None
            resp = self._post(client, monei_body(), "cualquier-cosa")
        assert resp.status_code == 401

    def test_sin_header_firma_retorna_401(self, client):
        """Sin header MONEI-SIGNATURE → firma vacía → mismatch → 401."""
        body = monei_body()
        with patch("blueprints.webhook.config") as mock_cfg:
            mock_cfg.MONEI_WEBHOOK_SECRET = MONEI_SECRET
            resp = self._post(client, body, signature="")
        assert resp.status_code == 401

    def test_firma_incorrecta_retorna_401(self, client):
        """HMAC incorrecto → 401."""
        body = monei_body()
        with patch("blueprints.webhook.config") as mock_cfg:
            mock_cfg.MONEI_WEBHOOK_SECRET = MONEI_SECRET
            resp = self._post(client, body, signature="firma-incorrecta")
        assert resp.status_code == 401

    def test_order_id_no_numerico_retorna_400(self, client):
        """orderId no numérico → 400 tras pasar la firma."""
        bad_body = json.dumps({
            "type": "charge.succeeded",
            "object": {"orderId": "abc-no-es-numero", "status": "SUCCEEDED",
                       "amount": 0, "description": "", "customer": {}, "billingDetails": {}}
        }).encode()
        sig = make_monei_signature(MONEI_SECRET, bad_body)
        with patch("blueprints.webhook.config") as mock_cfg:
            mock_cfg.MONEI_WEBHOOK_SECRET = MONEI_SECRET
            resp = self._post(client, bad_body, signature=sig)
        assert resp.status_code == 400

    def test_pago_exitoso_actualiza_estado_y_retorna_200(self, client):
        """HMAC correcto + SUCCEEDED → actualiza estado del pedido a PAGADO."""
        body = monei_body(order_id=42)
        sig = make_monei_signature(MONEI_SECRET, body)
        with patch("blueprints.webhook.config") as mock_cfg:
            mock_cfg.MONEI_WEBHOOK_SECRET = MONEI_SECRET
            with patch("blueprints.webhook.gestor_pedidos") as mock_gp:
                with patch("blueprints.webhook.enviar_mensaje_whatsapp"):
                    resp = self._post(client, body, signature=sig)
        assert resp.status_code == 200
        mock_gp.actualizar_estado.assert_called_once_with(42, EstadoPedido.PAGADO)

    def test_pago_no_succeeded_no_actualiza_estado(self, client):
        """HMAC correcto pero status PENDING y tipo desconocido → no actualiza estado."""
        # Usar type desconocido para no activar el OR de la condición
        body = json.dumps({
            "type": "charge.pending",
            "object": {
                "orderId": "5",
                "status": "PENDING",
                "amount": 0,
                "description": "",
                "customer": {},
                "billingDetails": {},
            }
        }).encode()
        sig = make_monei_signature(MONEI_SECRET, body)
        with patch("blueprints.webhook.config") as mock_cfg:
            mock_cfg.MONEI_WEBHOOK_SECRET = MONEI_SECRET
            with patch("blueprints.webhook.gestor_pedidos") as mock_gp:
                resp = self._post(client, body, signature=sig)
        assert resp.status_code == 200
        mock_gp.actualizar_estado.assert_not_called()
