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
from services.twilio_service import enviar_mensaje_whatsapp
from schemas.twilio import WebhookRequest
from managers.gestor_redis import redismanager
from services import gestor_usuarios, gestor_pedidos
from states import EstadoPedido

blueprint_webhook = Blueprint('webhook', __name__)
logger = logging.getLogger(__name__)


@blueprint_webhook.route('/webhook', methods=['POST'])
def webhook():
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
    raw_body = request.get_data()

    secret = config.MONEI_WEBHOOK_SECRET
    if not secret:
        logger.warning("MONEI_WEBHOOK_SECRET not configured — rejecting webhook")
        return jsonify({"error": "Invalid signature"}), 401

    received_signature = request.headers.get("MONEI-SIGNATURE", "")
    computed = hmac.HMAC(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_signature):
        logger.warning("Monei webhook signature mismatch")
        return jsonify({"error": "Invalid signature"}), 401

    data = request.get_json()
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
        mensaje = (
            f"❕*Pedido registrado*❕\n      ------------------  \n"
            f"▪️Nombre: *{nombre_usuario}*\n▪️importe: *{importe_euros}*€\n"
            f"▪️ID pedido: *#{order_id}*\n▪️Tiempo estimado: *15m*\n"
            f"▪️Direccion: 👇🏼 \n\n{costumer_adress}"
        )
        enviar_mensaje_whatsapp(mensaje, customer_phone)
        logger.info("Pedido %s marcado como pagado", order_id)

    return jsonify({'message': 'Webhook recibido correctamente'}), 200
