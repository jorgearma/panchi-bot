import json
import logging
from datetime import datetime
from decimal import Decimal
from threading import Thread

from flask import current_app, jsonify

from services.whatsapp_service import enviar_mensaje_whatsapp

logger = logging.getLogger(__name__)

_MOTIVOS_LABEL = {
    'cliente_cancelo':      'El cliente canceló',
    'falta_stock':          'Falta de stock',
    'direccion_incorrecta': 'Dirección incorrecta',
    'cliente_no_responde':  'Cliente no responde',
    'pedido_duplicado':     'Pedido duplicado',
    'otro':                 'Otro',
}


def _notificar(telefono: str, mensaje: str) -> None:
    """Envía un WhatsApp en segundo plano desde el dashboard."""
    if not telefono:
        return

    def _enviar():
        try:
            enviar_mensaje_whatsapp(mensaje, telefono)
        except Exception as exc:
            logger.error("Error enviando WhatsApp a %s: %s", telefono, exc)

    Thread(target=_enviar, daemon=True).start()


def _serial(obj):
    """Serializa tipos no JSON nativos usados por el dashboard."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def _ok(data):
    """Devuelve respuestas JSON usando el serializador común del dashboard."""
    return current_app.response_class(
        json.dumps(data, default=_serial),
        mimetype="application/json",
    )


def _err(msg, code=400):
    """Devuelve errores JSON con un formato homogéneo."""
    return jsonify({"error": msg}), code
