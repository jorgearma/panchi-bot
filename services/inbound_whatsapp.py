"""Adaptador de entrada para mensajes WhatsApp (Twilio y Meta) y confirmaciones Monei.

Responsabilidades:
- Verificar firmas de cada proveedor (Twilio, Meta, Monei)
- Extraer y normalizar mensajes del payload de Meta
- Aplicar rate-limit y enrutar al controlador correcto
- Procesar la confirmación de pago Monei

Las blueprints solo llaman a estas funciones y serializan la respuesta HTTP.
"""
import hmac
import hashlib
import json
import logging

from flask import jsonify
from sqlalchemy.exc import SQLAlchemyError
from tenacity import RetryError
from twilio.request_validator import RequestValidator

import config
from managers.gestor_redis import redismanager
from container import gestor_usuarios, gestor_pedidos
from controllers.registro import manejar_registro
from controllers.mensajes_registrados import ManejadorMensajesRegistrados
from services.whatsapp_service import enviar_mensaje_whatsapp

logger = logging.getLogger(__name__)

_MSG_ERROR_SISTEMA = "Lo sentimos, se presentó un error en el sistema. Por favor, intente más tarde."
_MSG_ERROR_INESPERADO = "Lo sentimos, se presentó un error inesperado. Por favor, intente más tarde."
_MSG_ERROR_PROCESANDO = "Se presentó un problema al procesar su mensaje. Intente nuevamente."


# ── Verificación de firmas ────────────────────────────────────────────────────

def verificar_firma_twilio(request, testing: bool = False) -> bool:
    """Verifica la firma HMAC de Twilio. En testing siempre aprueba."""
    if testing:
        return True
    validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
    signature = request.headers.get("X-Twilio-Signature", "")
    url = config.PUBLIC_URL + "/webhook"
    return validator.validate(url, request.form, signature)


def verificar_firma_meta(raw_body: bytes, sig_header: str, secret: str) -> bool:
    """Verifica la firma X-Hub-Signature-256 de Meta."""
    if not secret or not sig_header.startswith('sha256='):
        return False
    received = sig_header[len('sha256='):]
    computed = hmac.HMAC(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, received)


def verificar_firma_monei(raw_body: bytes, header: str, secret: str) -> tuple:
    """Verifica MONEI-SIGNATURE. Devuelve (ok: bool, error_msg: str)."""
    if not secret:
        return False, "secret not configured"
    parts = dict(item.split("=", 1) for item in header.split(",") if "=" in item)
    timestamp = parts.get("t", "")
    received = parts.get("v1", "")
    if not timestamp or not received:
        return False, f"malformed header: {header}"
    signed_payload = f"{timestamp}.".encode() + raw_body
    computed = hmac.HMAC(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received):
        return False, "signature mismatch"
    return True, ""


# ── Extracción de mensajes Meta ───────────────────────────────────────────────

def extraer_mensajes_meta(data: dict) -> list:
    """Extrae lista normalizada de {numero, mensaje} del payload Meta."""
    try:
        messages = data['entry'][0]['changes'][0]['value'].get('messages', [])
    except (KeyError, IndexError, TypeError):
        return []

    result = []
    for message in messages:
        msg_type = message.get('type')
        if msg_type == 'text':
            result.append({
                'numero': f"whatsapp:+{message['from']}",
                'mensaje': message['text']['body'].lower(),
            })
        elif msg_type == 'interactive':
            interactive = message.get('interactive', {}) or {}
            if interactive.get('type') != 'button_reply':
                continue
            button_id = (interactive.get('button_reply') or {}).get('id')
            if button_id in {"registro_si", "direccion_si", "registro_continuar"}:
                texto = "si"
            elif button_id in {"registro_no", "direccion_no"}:
                texto = "no"
            else:
                continue
            result.append({'numero': f"whatsapp:+{message['from']}", 'mensaje': texto})
    return result


# ── Routing ───────────────────────────────────────────────────────────────────

def enrutar_mensaje(numero_cliente: str, mensaje_cliente: str):
    """Aplica rate-limit y enruta al controlador correcto.

    Devuelve una tupla compatible con Flask (response, status_code).
    Para el flujo Meta el valor de retorno puede ignorarse — los errores
    quedan manejados internamente y el loop continúa naturalmente.
    """
    if redismanager.esta_bloqueado(numero_cliente):
        return "Número bloqueado", 403
    redismanager.bloquear_usuario(numero_cliente, duracion=4)

    try:
        usuario = gestor_usuarios.verificar_usuario(numero_cliente)
    except (RetryError, SQLAlchemyError) as e:
        logger.error("Error al verificar usuario %s [%s]: %s", numero_cliente, type(e).__name__, e)
        enviar_mensaje_whatsapp(_MSG_ERROR_SISTEMA, numero_cliente)
        return jsonify({"error": "Error en la base de datos"}), 500
    except Exception:
        logger.exception("Error inesperado verificando usuario %s:", numero_cliente)
        enviar_mensaje_whatsapp(_MSG_ERROR_INESPERADO, numero_cliente)
        return jsonify({"error": "Error inesperado"}), 500

    try:
        if not usuario:
            return manejar_registro(numero_cliente, mensaje_cliente, redismanager)
        return ManejadorMensajesRegistrados.manejar_mensajes_registrados(numero_cliente, mensaje_cliente)
    except Exception:
        logger.exception("Error procesando mensaje de %s:", numero_cliente)
        enviar_mensaje_whatsapp(_MSG_ERROR_PROCESANDO, numero_cliente)
        return jsonify({"error": "Error procesando el mensaje"}), 500


# ── Pago Monei ────────────────────────────────────────────────────────────────

def procesar_pago_monei(data: dict):
    """Procesa la confirmación de pago Monei y notifica al cliente.

    Devuelve una tupla (response, status_code) para la blueprint.
    """
    order_id_raw = data.get('object', {}).get('orderId')
    try:
        order_id = int(order_id_raw)
    except (TypeError, ValueError):
        logger.error("procesar_pago_monei: orderId inválido: %s", order_id_raw)
        return jsonify({"error": "orderId inválido"}), 400

    nombre_usuario = data.get('object', {}).get('description')
    customer_phone = data.get('object', {}).get('customer', {}).get('phone')
    customer_address = data.get('object', {}).get('billingDetails', {}).get('address', {}).get("line1")
    importe_euros = data.get('object', {}).get('amount', 0) / 100

    if data.get('object', {}).get('status') == 'SUCCEEDED' or data.get('type') == 'charge.succeeded':
        gestor_pedidos.procesar_pago_confirmado(
            pedido_id=order_id,
            importe_euros=importe_euros,
            referencia_externa=data.get('object', {}).get('id'),
            datos_raw=json.dumps(data),
        )
        mensaje = (
            f"❕*Pedido registrado*❕\n      ------------------  \n"
            f"▪️Nombre: *{nombre_usuario}*\n▪️importe: *{importe_euros}*€\n"
            f"▪️ID pedido: *#{order_id}*\n▪️Tiempo estimado: *15m*\n"
            f"▪️Direccion: 👇🏼 \n\n{customer_address}"
        )
        enviar_mensaje_whatsapp(mensaje, customer_phone)
        logger.info("Pedido %s marcado como pagado", order_id)

    return jsonify({'message': 'Webhook recibido correctamente'}), 200
