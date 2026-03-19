import logging
import config
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
def enviar_mensaje_whatsapp(mensaje, destinatario):
    _get_client().messages.create(
        body=mensaje,
        from_=config.TWILIO_WHATSAPP_NUMBER,
        to=destinatario
    )

    logger.info("Mensaje enviado a %s", destinatario)
