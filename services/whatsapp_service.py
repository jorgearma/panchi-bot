import os
import logging
from concurrent.futures import ThreadPoolExecutor
import config
import requests
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    """Inicializa y reutiliza el cliente de Twilio."""
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
    """Envia un mensaje usando el proveedor Twilio."""
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
    """Envia un mensaje usando la API de WhatsApp de Meta."""
    numero = destinatario.replace("whatsapp:+", "")
    url = f"https://graph.facebook.com/v21.0/{config.META_PHONE_NUMBER_ID}/messages"
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
    if not resp.ok:
        logger.error("Meta API error %s: %s", resp.status_code, resp.text)
    resp.raise_for_status()
    logger.info("Mensaje enviado (Meta) a %s", destinatario)


def enviar_mensaje_whatsapp(mensaje: str, destinatario: str) -> None:
    """Selecciona proveedor y envia el mensaje de WhatsApp."""
    provider = os.getenv("WHATSAPP_PROVIDER", "twilio")
    if provider == "meta":
        _enviar_meta(mensaje, destinatario)
    else:
        _enviar_twilio(mensaje, destinatario)


# Pool acotado para notificaciones async — máximo 10 threads concurrentes hacia Twilio/Meta.
# Evita la proliferación de threads zombie que ocurre con Thread().start() por cada pedido.
_notif_pool = ThreadPoolExecutor(max_workers=10, thread_name_prefix="whatsapp_notif")


def notificar_async(telefono: str, mensaje: str) -> None:
    """Envía un WhatsApp en segundo plano sin bloquear la respuesta HTTP.

    Usa un pool acotado en lugar de un thread por notificación.
    Los errores se loguean y no se propagan al caller.
    """
    if not telefono:
        return

    def _enviar():
        try:
            enviar_mensaje_whatsapp(mensaje, telefono)
        except Exception as exc:
            logger.error("Error enviando WhatsApp a %s: %s", telefono, exc)

    _notif_pool.submit(_enviar)
