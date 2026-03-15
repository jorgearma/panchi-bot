import logging
import config
from twilio.rest import Client

logger = logging.getLogger(__name__)


_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    return _client


def enviar_mensaje_whatsapp(mensaje, destinatario):
    _get_client().messages.create(
        body=mensaje,
        from_=config.TWILIO_WHATSAPP_NUMBER,
        to=destinatario
    )

    logger.info("Mensaje enviado a %s", destinatario)
