"""
Cliente HTTP para el Android SMS Gateway (capcom6/android-sms-gateway).

Sin SMS_GATEWAY_URL configurado, funciona en modo mock: loguea los mensajes
en vez de enviarlos. Útil para desarrollo y tests.
"""

import logging

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from sms_verification import config as sms_config

logger = logging.getLogger(__name__)


class SmsGatewayError(Exception):
    """Error al comunicar con el Android SMS Gateway."""


def _is_mock_mode() -> bool:
    return not sms_config.GATEWAY_URL


@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    reraise=True,
)
def _send_via_gateway(phone: str, message: str) -> None:
    """Llama a la API REST del Android SMS Gateway con retry automático."""
    url = f"{sms_config.GATEWAY_URL.rstrip('/')}/api/v1/message"
    response = requests.post(
        url,
        json={"message": message, "phoneNumbers": [phone]},
        auth=(sms_config.GATEWAY_USER, sms_config.GATEWAY_PASSWORD),
        timeout=10,
    )
    response.raise_for_status()


def enviar_sms(phone: str, message: str) -> bool:
    """
    Envía un SMS al número indicado.

    En modo mock (sin SMS_GATEWAY_URL) solo loguea el mensaje.
    Devuelve True si el envío tuvo éxito, False en caso de error.
    """
    if _is_mock_mode():
        logger.warning("[SMS MOCK] Para %s: %s", phone, message)
        return True

    try:
        _send_via_gateway(phone, message)
        logger.info("SMS enviado a %s", phone)
        return True
    except Exception as e:
        logger.error("Error enviando SMS a %s: %s", phone, e)
        return False
