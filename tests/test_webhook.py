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
        with patch("services.inbound_whatsapp.redismanager") as mock_redis:
            mock_redis.esta_bloqueado.return_value = True
            resp = client.post("/webhook", data={"From": TWILIO_FROM, "Body": TWILIO_BODY})
        assert resp.status_code == 403

    def test_firma_invalida_retorna_403(self, client, app):
        """Con TESTING=False, una firma Twilio inválida → 403."""
        app.config["TESTING"] = False
        try:
            with patch("services.inbound_whatsapp.RequestValidator") as mock_cls:
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
            with patch("services.inbound_whatsapp.RequestValidator") as mock_cls:
                mock_cls.return_value.validate.return_value = True
                with patch("blueprints.webhook.config") as mock_cfg:
                    mock_cfg.TWILIO_AUTH_TOKEN = "tok"
                    mock_cfg.PUBLIC_URL = "https://test.com"
                    with patch("services.inbound_whatsapp.redismanager") as mock_redis:
                        mock_redis.esta_bloqueado.return_value = False
                        with patch("services.inbound_whatsapp.gestor_usuarios") as mock_gu:
                            mock_gu.verificar_usuario.return_value = None
                            with patch("services.inbound_whatsapp.manejar_registro", return_value=("ok", 200)):
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
        with patch("services.inbound_whatsapp.redismanager") as mock_redis:
            mock_redis.esta_bloqueado.return_value = False
            with patch("services.inbound_whatsapp.gestor_usuarios") as mock_gu:
                mock_gu.verificar_usuario.return_value = None
                with patch("services.inbound_whatsapp.manejar_registro", return_value=("ok", 200)) as mock_reg:
                    resp = client.post("/webhook", data={"From": TWILIO_FROM, "Body": TWILIO_BODY})
        assert resp.status_code == 200
        mock_reg.assert_called_once()

    def test_usuario_registrado_llama_manejador(self, client):
        """Usuario registrado → delega a ManejadorMensajesRegistrados."""
        usuario_mock = MagicMock()
        with patch("services.inbound_whatsapp.redismanager") as mock_redis:
            mock_redis.esta_bloqueado.return_value = False
            with patch("services.inbound_whatsapp.gestor_usuarios") as mock_gu:
                mock_gu.verificar_usuario.return_value = usuario_mock
                with patch(
                    "services.inbound_whatsapp.ManejadorMensajesRegistrados.manejar_mensajes_registrados",
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
            with patch("services.inbound_whatsapp.gestor_pedidos") as mock_gp:
                with patch("services.inbound_whatsapp.enviar_mensaje_whatsapp"):
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
            with patch("services.inbound_whatsapp.gestor_pedidos") as mock_gp:
                resp = self._post(client, body, signature=sig)
        assert resp.status_code == 200
        mock_gp.actualizar_estado.assert_not_called()


# ─────────────────────────────────────────────
# GET + POST /webhook/meta — Meta Cloud API
# ─────────────────────────────────────────────

META_SECRET = "meta_app_secret_test"
META_VERIFY = "mi_verify_token"


def make_meta_signature(secret: str, body: bytes) -> str:
    """Genera el header X-Hub-Signature-256 que Meta envía."""
    sig = hmac.HMAC(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def meta_body(from_number="34600000000", text="hola", msg_type="text"):
    return json.dumps({
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": from_number,
                        "type": msg_type,
                        "text": {"body": text},
                    }]
                }
            }]
        }]
    }).encode()


class TestWebhookMeta:

    def _post(self, client, body: bytes, signature: str = ""):
        return client.post(
            "/webhook/meta",
            data=body,
            content_type="application/json",
            headers={"X-Hub-Signature-256": signature},
        )

    def _get(self, client, mode="subscribe", token=META_VERIFY, challenge="abc123"):
        return client.get(
            "/webhook/meta",
            query_string={
                "hub.mode": mode,
                "hub.verify_token": token,
                "hub.challenge": challenge,
            },
        )

    # ── GET: verificación de webhook ──────────────────────────

    def test_get_verify_token_correcto_retorna_challenge(self, client):
        """GET con token correcto → 200 con el challenge."""
        with patch("blueprints.webhook.config") as mock_cfg:
            mock_cfg.META_VERIFY_TOKEN = META_VERIFY
            resp = self._get(client)
        assert resp.status_code == 200
        assert resp.data == b"abc123"

    def test_get_verify_token_incorrecto_retorna_403(self, client):
        """GET con token incorrecto → 403."""
        with patch("blueprints.webhook.config") as mock_cfg:
            mock_cfg.META_VERIFY_TOKEN = META_VERIFY
            resp = self._get(client, token="token-malo")
        assert resp.status_code == 403

    # ── POST: validación de firma ─────────────────────────────

    def test_post_sin_firma_retorna_401(self, client):
        """POST sin X-Hub-Signature-256 → 401."""
        body = meta_body()
        with patch("blueprints.webhook.config") as mock_cfg:
            mock_cfg.META_APP_SECRET = META_SECRET
            resp = self._post(client, body, signature="")
        assert resp.status_code == 401

    def test_post_firma_incorrecta_retorna_401(self, client):
        """POST con HMAC incorrecto → 401."""
        body = meta_body()
        with patch("blueprints.webhook.config") as mock_cfg:
            mock_cfg.META_APP_SECRET = META_SECRET
            resp = self._post(client, body, signature="sha256=firma-mala")
        assert resp.status_code == 401

    # ── POST: parseo de payload ───────────────────────────────

    def test_post_sin_messages_retorna_200_sin_procesar(self, client):
        """Notificación de estado (sin messages) → 200, no llama a manejar_registro."""
        body = json.dumps({"entry": [{"changes": [{"value": {}}]}]}).encode()
        sig = make_meta_signature(META_SECRET, body)
        with patch("blueprints.webhook.config") as mock_cfg:
            mock_cfg.META_APP_SECRET = META_SECRET
            with patch("services.inbound_whatsapp.manejar_registro") as mock_reg:
                resp = self._post(client, body, signature=sig)
        assert resp.status_code == 200
        mock_reg.assert_not_called()

    def test_post_mensaje_no_texto_retorna_200_sin_procesar(self, client):
        """Mensaje de tipo imagen/audio → 200, no procesa."""
        body = meta_body(msg_type="image")
        sig = make_meta_signature(META_SECRET, body)
        with patch("blueprints.webhook.config") as mock_cfg:
            mock_cfg.META_APP_SECRET = META_SECRET
            with patch("services.inbound_whatsapp.manejar_registro") as mock_reg:
                with patch("services.inbound_whatsapp.redismanager") as mock_redis:
                    mock_redis.esta_bloqueado.return_value = False
                    resp = self._post(client, body, signature=sig)
        assert resp.status_code == 200
        mock_reg.assert_not_called()

    def test_post_payload_malformado_retorna_200_sin_procesar(self, client):
        """Payload sin clave 'entry' → 200, no procesa."""
        body = json.dumps({"unexpected": "structure"}).encode()
        sig = make_meta_signature(META_SECRET, body)
        with patch("blueprints.webhook.config") as mock_cfg:
            mock_cfg.META_APP_SECRET = META_SECRET
            with patch("services.inbound_whatsapp.manejar_registro") as mock_reg:
                resp = self._post(client, body, signature=sig)
        assert resp.status_code == 200
        mock_reg.assert_not_called()

    # ── POST: routing a lógica de negocio ────────────────────

    def test_post_usuario_no_registrado_llama_manejar_registro(self, client):
        """Mensaje válido de usuario no registrado → llama a manejar_registro."""
        body = meta_body(from_number="34600000000", text="hola")
        sig = make_meta_signature(META_SECRET, body)
        with patch("blueprints.webhook.config") as mock_cfg:
            mock_cfg.META_APP_SECRET = META_SECRET
            with patch("services.inbound_whatsapp.redismanager") as mock_redis:
                mock_redis.esta_bloqueado.return_value = False
                with patch("services.inbound_whatsapp.gestor_usuarios") as mock_gu:
                    mock_gu.verificar_usuario.return_value = None
                    with patch("services.inbound_whatsapp.manejar_registro", return_value=("ok", 200)) as mock_reg:
                        resp = self._post(client, body, signature=sig)
        assert resp.status_code == 200
        mock_reg.assert_called_once()
        # Verificar que el número se normaliza correctamente
        args = mock_reg.call_args.args
        assert args[0] == "whatsapp:+34600000000"

    def test_post_usuario_registrado_llama_manejador(self, client):
        """Mensaje válido de usuario registrado → llama a ManejadorMensajesRegistrados."""
        body = meta_body(from_number="34600000001", text="ver pedido")
        sig = make_meta_signature(META_SECRET, body)
        usuario_mock = MagicMock()
        with patch("blueprints.webhook.config") as mock_cfg:
            mock_cfg.META_APP_SECRET = META_SECRET
            with patch("services.inbound_whatsapp.redismanager") as mock_redis:
                mock_redis.esta_bloqueado.return_value = False
                with patch("services.inbound_whatsapp.gestor_usuarios") as mock_gu:
                    mock_gu.verificar_usuario.return_value = usuario_mock
                    with patch(
                        "services.inbound_whatsapp.ManejadorMensajesRegistrados.manejar_mensajes_registrados",
                        return_value=("ok", 200)
                    ) as mock_man:
                        resp = self._post(client, body, signature=sig)
        assert resp.status_code == 200
        mock_man.assert_called_once()
