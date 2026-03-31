import json
import logging
import hmac
import hashlib
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy.exc import SQLAlchemyError
from tenacity import RetryError
from pydantic import ValidationError
from twilio.request_validator import RequestValidator

import config
from controllers.registro import manejar_registro
from controllers.mensajes_registrados import ManejadorMensajesRegistrados
from utils.text_utils import limpiar_texto
from services.whatsapp_service import enviar_mensaje_whatsapp
from schemas.twilio import WebhookRequest
from managers.gestor_redis import redismanager
from container import gestor_usuarios, gestor_pedidos
from states import EstadoPedido

blueprint_webhook = Blueprint('webhook', __name__)
logger = logging.getLogger(__name__)


@blueprint_webhook.route('/webhook', methods=['POST'])
def webhook():
    """Recibe mensajes de Twilio, valida la firma y los deriva al flujo correcto."""
    if not current_app.config.get("TESTING"):
        validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
        signature = request.headers.get("X-Twilio-Signature", "")
        url = config.PUBLIC_URL + "/webhook"
        if not validator.validate(url, request.form, signature):
            logger.warning("Twilio webhook signature inválida")
            return jsonify({"error": "Firma inválida"}), 403

    try:
        data = WebhookRequest(**request.form.to_dict())
    except ValidationError as e:
        logger.error("Datos de entrada inválidos: %s", e)
        return jsonify({"error": "Datos de entrada inválidos"}), 400

    numero_cliente = data.From
    mensaje_cliente = limpiar_texto(data.Body.lower())

    logger.info("Mensaje recibido de %s: %s", numero_cliente, mensaje_cliente)

    bloqueo = redismanager.esta_bloqueado(numero_cliente)
    if bloqueo:
        return "Número bloqueado", 403

    redismanager.bloquear_usuario(numero_cliente, duracion=4)

    try:
        usuario = gestor_usuarios.verificar_usuario(numero_cliente)
    except RetryError as re:
        logger.error("Error de conexión tras varios intentos: %s", re)
        enviar_mensaje_whatsapp(
            "Lo sentimos, se presentó un error en el sistema. Por favor, intente más tarde.",
            numero_cliente
        )
        return jsonify({"error": "Error en la base de datos"}), 500
    except SQLAlchemyError as e:
        logger.error("Error al verificar el usuario: %s", e)
        enviar_mensaje_whatsapp(
            "Lo sentimos, se presentó un error en el sistema. Por favor, intente más tarde.",
            numero_cliente
        )
        return jsonify({"error": "Error en la base de datos"}), 500
    except Exception as e:
        logger.exception("Error inesperado:")
        enviar_mensaje_whatsapp(
            "Lo sentimos, se presentó un error inesperado. Por favor, intente más tarde.",
            numero_cliente
        )
        return jsonify({"error": "Error inesperado"}), 500

    try:
        if not usuario:
            return manejar_registro(numero_cliente, mensaje_cliente, redismanager)
        else:
            return ManejadorMensajesRegistrados.manejar_mensajes_registrados(numero_cliente, mensaje_cliente)
    except Exception as e:
        logger.exception("Error procesando el mensaje del usuario:")
        enviar_mensaje_whatsapp(
            "Se presentó un problema al procesar su mensaje. Intente nuevamente.",
            numero_cliente
        )
        return jsonify({"error": "Error procesando el mensaje"}), 500


@blueprint_webhook.route('/webhoo/monei', methods=['POST'])  # TODO: remove once Monei dashboard points to /webhook/monei
@blueprint_webhook.route('/webhook/monei', methods=['POST'])
def webhook_monei():
    """Procesa pagos confirmados por Monei y actualiza el pedido asociado."""
    raw_body = request.get_data()

    secret = config.MONEI_WEBHOOK_SECRET
    if secret:
        received_header = request.headers.get("MONEI-SIGNATURE", "")

        # Header format: t=<timestamp>,v1=<hex_signature>
        # Signed payload: "<timestamp>.<raw_body>"
        parts = dict(item.split("=", 1) for item in received_header.split(",") if "=" in item)
        timestamp = parts.get("t", "")
        received_signature = parts.get("v1", "")

        if not timestamp or not received_signature:
            logger.warning("MONEI-SIGNATURE header malformado: %s", received_header)
            return jsonify({"error": "Invalid signature"}), 401

        signed_payload = f"{timestamp}.".encode() + raw_body
        computed = hmac.HMAC(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed, received_signature):
            logger.warning("Monei webhook signature mismatch")
            return jsonify({"error": "Invalid signature"}), 401
    else:
        logger.warning("MONEI_WEBHOOK_SECRET not configured — rejecting webhook")
        return jsonify({"error": "Invalid signature"}), 401

    data = request.get_json()
    if data.get('type') == 'webhook.test':
        logger.info("Monei webhook test recibido — OK")
        return jsonify({"ok": True}), 200

    order_id_raw = data.get('object', {}).get('orderId')
    try:
        order_id = int(order_id_raw)
    except (TypeError, ValueError):
        logger.error("webhook_monei: orderId inválido: %s", order_id_raw)
        return jsonify({"error": "orderId inválido"}), 400
    nombre_usuario = data.get('object', {}).get('description')
    customer_phone = data.get('object', {}).get('customer', {}).get('phone')
    costumer_adress = data.get('object', {}).get('billingDetails', {}).get('address', {}).get("line1")

    importe_cents = data.get('object', {}).get('amount', 0)
    importe_euros = importe_cents / 100

    if data.get('object', {}).get('status') == 'SUCCEEDED' or data.get('type') == 'charge.succeeded':
        gestor_pedidos.actualizar_estado(order_id, EstadoPedido.PAGADO)
        gestor_pedidos.registrar_pago(
            pedido_id=order_id,
            importe_euros=importe_euros,
            referencia_externa=data.get('object', {}).get('id'),
            datos_raw=json.dumps(data),
        )
        mensaje = (
            f"❕*Pedido registrado*❕\n      ------------------  \n"
            f"▪️Nombre: *{nombre_usuario}*\n▪️importe: *{importe_euros}*€\n"
            f"▪️ID pedido: *#{order_id}*\n▪️Tiempo estimado: *15m*\n"
            f"▪️Direccion: 👇🏼 \n\n{costumer_adress}"
        )
        enviar_mensaje_whatsapp(mensaje, customer_phone)
        logger.info("Pedido %s marcado como pagado", order_id)

    return jsonify({'message': 'Webhook recibido correctamente'}), 200


@blueprint_webhook.route('/webhook/meta', methods=['GET'])
def webhook_meta_verify():
    """Responde al challenge de verificación del webhook de Meta."""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge', '')
    if mode == 'subscribe' and token == config.META_VERIFY_TOKEN:
        return challenge, 200
    logger.warning("Meta webhook verify_token incorrecto — mode=%s", mode)
    return jsonify({"error": "Forbidden"}), 403


@blueprint_webhook.route('/webhook/meta', methods=['POST'])
def webhook_meta():
    """Recibe mensajes de Meta, valida la firma y los deriva al mismo flujo de negocio."""
    raw_body = request.get_data()

    # Verificar firma
    if not config.META_APP_SECRET:
        logger.warning("META_APP_SECRET not configured — rejecting webhook")
        return jsonify({"error": "Invalid signature"}), 401

    sig_header = request.headers.get('X-Hub-Signature-256', '')
    if not sig_header.startswith('sha256='):
        logger.warning("Meta webhook sin X-Hub-Signature-256")
        return jsonify({"error": "Invalid signature"}), 401

    received_sig = sig_header[len('sha256='):]
    computed = hmac.HMAC(config.META_APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_sig):
        logger.warning("Meta webhook signature mismatch")
        return jsonify({"error": "Invalid signature"}), 401

    # Parsear payload
    data = request.get_json()
    try:
        messages = data['entry'][0]['changes'][0]['value'].get('messages', [])
    except (KeyError, IndexError, TypeError):
        return jsonify({"ok": True}), 200

    if not messages:
        return jsonify({"ok": True}), 200

    for message in messages:
        if message.get('type') != 'text':
            continue

        # Normalizar número al formato interno whatsapp:+XXXXXXXXX
        numero_cliente = f"whatsapp:+{message['from']}"
        mensaje_cliente = limpiar_texto(message['text']['body'].lower())

        logger.info("Mensaje Meta recibido de %s: %s", numero_cliente, mensaje_cliente)

        # Rate limiting
        if redismanager.esta_bloqueado(numero_cliente):
            continue
        redismanager.bloquear_usuario(numero_cliente, duracion=4)

        # Routing a lógica de negocio
        try:
            usuario = gestor_usuarios.verificar_usuario(numero_cliente)
        except RetryError as re:
            logger.error("Error de conexión tras varios intentos: %s", re)
            enviar_mensaje_whatsapp(
                "Lo sentimos, se presentó un error en el sistema. Por favor, intente más tarde.",
                numero_cliente,
            )
            continue
        except SQLAlchemyError as e:
            logger.error("Error al verificar el usuario: %s", e)
            enviar_mensaje_whatsapp(
                "Lo sentimos, se presentó un error en el sistema. Por favor, intente más tarde.",
                numero_cliente,
            )
            continue
        except Exception as e:
            logger.exception("Error inesperado:")
            enviar_mensaje_whatsapp(
                "Lo sentimos, se presentó un error inesperado. Por favor, intente más tarde.",
                numero_cliente,
            )
            continue

        try:
            if not usuario:
                manejar_registro(numero_cliente, mensaje_cliente, redismanager)
            else:
                ManejadorMensajesRegistrados.manejar_mensajes_registrados(
                    numero_cliente, mensaje_cliente
                )
        except Exception as e:
            logger.exception("Error procesando el mensaje del usuario:")
            enviar_mensaje_whatsapp(
                "Se presentó un problema al procesar su mensaje. Intente nuevamente.",
                numero_cliente,
            )

    return jsonify({"ok": True}), 200
