import os
import logging
from twilio.rest import Client

logger = logging.getLogger(__name__)

TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER')


_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    return _client


def enviar_mensaje_whatsapp(mensaje, destinatario):

    _get_client().messages.create(
        body=mensaje,
        from_=TWILIO_PHONE_NUMBER,
        to=destinatario
    )

    logger.info("Mensaje enviado a %s", destinatario)
