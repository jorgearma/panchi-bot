"""Tests para el módulo sms_verification."""

import fakeredis
import pytest
from unittest.mock import patch

from sms_verification import enviar_codigo, verificar_codigo, requiere_verificacion
from sms_verification import config as sms_config


@pytest.fixture
def redis():
    return fakeredis.FakeRedis(server=fakeredis.FakeServer())


# ---------------------------------------------------------------------------
# requiere_verificacion
# ---------------------------------------------------------------------------

class TestRequiereVerificacion:
    def test_ya_verificado_no_requiere(self):
        assert requiere_verificacion(True, False, 10.0) is False

    def test_tiene_pago_online_no_requiere(self):
        assert requiere_verificacion(False, True, 10.0) is False

    def test_sin_verificar_sin_pagos_requiere(self):
        assert requiere_verificacion(False, False, 10.0) is True

    def test_importe_alto_sin_verificar_requiere(self):
        assert requiere_verificacion(False, True, 50.0) is True

    def test_importe_alto_verificado_no_requiere(self):
        assert requiere_verificacion(True, False, 50.0) is False

    def test_importe_exacto_al_umbral(self):
        assert requiere_verificacion(False, False, sms_config.VERIFICATION_THRESHOLD) is True


# ---------------------------------------------------------------------------
# enviar_codigo
# ---------------------------------------------------------------------------

class TestEnviarCodigo:
    @patch("sms_verification.gateway_client.enviar_sms", return_value=True)
    def test_envio_exitoso(self, mock_sms, redis):
        ok, reason = enviar_codigo("+34612345678", redis)
        assert ok is True
        assert reason == "ok"
        # Código guardado en Redis
        assert redis.get("sms_verify:+34612345678") is not None
        # Cooldown activo
        assert redis.exists("sms_cooldown:+34612345678")

    @patch("sms_verification.gateway_client.enviar_sms", return_value=True)
    def test_cooldown_bloquea_reenvio(self, mock_sms, redis):
        enviar_codigo("+34612345678", redis)
        ok, reason = enviar_codigo("+34612345678", redis)
        assert ok is False
        assert reason == "cooldown"

    @patch("sms_verification.verification.enviar_sms", return_value=False)
    def test_fallo_envio(self, mock_sms, redis):
        ok, reason = enviar_codigo("+34612345678", redis)
        assert ok is False
        assert reason == "error"
        # No debe guardar código si el envío falló
        assert redis.get("sms_verify:+34612345678") is None


# ---------------------------------------------------------------------------
# verificar_codigo
# ---------------------------------------------------------------------------

class TestVerificarCodigo:
    @patch("sms_verification.gateway_client.enviar_sms", return_value=True)
    def test_codigo_correcto(self, mock_sms, redis):
        enviar_codigo("+34612345678", redis)
        codigo = redis.get("sms_verify:+34612345678").decode()
        ok, reason = verificar_codigo("+34612345678", codigo, redis)
        assert ok is True
        assert reason == "ok"
        # Claves limpiadas
        assert redis.get("sms_verify:+34612345678") is None
        assert redis.get("sms_cooldown:+34612345678") is None

    @patch("sms_verification.gateway_client.enviar_sms", return_value=True)
    def test_codigo_incorrecto(self, mock_sms, redis):
        enviar_codigo("+34612345678", redis)
        ok, reason = verificar_codigo("+34612345678", "000000", redis)
        assert ok is False
        assert reason == "incorrecto"

    def test_codigo_expirado(self, redis):
        ok, reason = verificar_codigo("+34612345678", "123456", redis)
        assert ok is False
        assert reason == "expirado"

    @patch("sms_verification.gateway_client.enviar_sms", return_value=True)
    def test_bloqueo_tras_max_intentos(self, mock_sms, redis):
        enviar_codigo("+34612345678", redis)
        for _ in range(sms_config.MAX_ATTEMPTS):
            verificar_codigo("+34612345678", "000000", redis)
        ok, reason = verificar_codigo("+34612345678", "000000", redis)
        assert ok is False
        assert reason == "bloqueado"

    @patch("sms_verification.gateway_client.enviar_sms", return_value=True)
    def test_codigo_con_espacios(self, mock_sms, redis):
        enviar_codigo("+34612345678", redis)
        codigo = redis.get("sms_verify:+34612345678").decode()
        ok, reason = verificar_codigo("+34612345678", f"  {codigo}  ", redis)
        assert ok is True


# ---------------------------------------------------------------------------
# gateway_client mock mode
# ---------------------------------------------------------------------------

class TestGatewayMock:
    def test_mock_mode_sin_gateway_url(self, redis):
        """Sin SMS_GATEWAY_URL el módulo loguea y devuelve True."""
        ok, reason = enviar_codigo("+34612345678", redis)
        assert ok is True
        assert reason == "ok"
