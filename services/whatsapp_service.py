import os
import logging
import config
import requests
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    return _client


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(TwilioRestException),
    reraise=True,
)
def _enviar_twilio(mensaje: str, destinatario: str) -> None:
    _get_client().messages.create(
        body=mensaje,
        from_=config.TWILIO_WHATSAPP_NUMBER,
        to=destinatario,
    )
    logger.info("Mensaje enviado (Twilio) a %s", destinatario)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    reraise=True,
)
def _enviar_meta(mensaje: str, destinatario: str) -> None:
    numero = destinatario.replace("whatsapp:+", "")
    url = f"https://graph.facebook.com/v19.0/{config.META_PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": mensaje},
    }
    resp = requests.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {config.META_ACCESS_TOKEN}"},
        timeout=10,
    )
    resp.raise_for_status()
    logger.info("Mensaje enviado (Meta) a %s", destinatario)


def enviar_mensaje_whatsapp(mensaje: str, destinatario: str) -> None:
    provider = os.getenv("WHATSAPP_PROVIDER", "twilio")
    if provider == "meta":
        _enviar_meta(mensaje, destinatario)
    else:
        _enviar_twilio(mensaje, destinatario)
