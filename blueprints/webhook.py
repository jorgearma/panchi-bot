import logging
import hmac
import hashlib
from flask import Blueprint, request, jsonify
from sqlalchemy.exc import SQLAlchemyError
from tenacity import RetryError
from pydantic import ValidationError

from controllers.no_resgistrados import manejar_registro
from controllers.mensajes_registrados import ManejadorMensajesRegistrados
from utils.text_utils import limpiar_texto
from utils.mensajes import enviar_mensaje_whatsapp
from modelos.validator_twilio import WebhookRequest
from managers.gestor_redis import redismanager
from services import gestor_usuarios, gestor_pedidos

blueprint_webhook = Blueprint('webhook', __name__)
logger = logging.getLogger(__name__)

WEBHOOK_SECRET = b'tu_clave_secreta'


def verify_signature(request_data, received_signature):
    computed_signature = hmac.new(WEBHOOK_SECRET, request_data, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed_signature, received_signature)


@blueprint_webhook.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = WebhookRequest(**request.form.to_dict())
    except ValidationError as e:
        logger.error("Datos de entrada inválidos: %s", e)
        return jsonify({"error": "Datos de entrada inválidos", "detail": e.errors()}), 400

    numero_cliente = data.From
    mensaje_cliente = limpiar_texto(data.Body.lower())

    logger.info(f"Mensaje recibido de {numero_cliente}: {mensaje_cliente}")

    bloqueo = redismanager.esta_bloqueado(numero_cliente)
    if bloqueo:
        return "Número bloqueado", 403

    redismanager.bloquear_usuario(numero_cliente, duracion=20)

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


@blueprint_webhook.route('/webhoo/monei', methods=['POST'])  # legacy — eliminar cuando Monei apunte a /webhook/monei
@blueprint_webhook.route('/webhook/monei', methods=['POST'])
def webhook_monei():
    request_data = request.get_data()
    print("Request data:", request_data)

    data = request.get_json()
    order_id = data.get('object', {}).get('orderId')
    nombre_usuario = data.get('object', {}).get('description')
    customer_phone = data.get('object', {}).get('customer', {}).get('phone')
    costumer_adress = data.get('object', {}).get('billingDetails', {}).get('address', {}).get("line1")

    importe_cents = data.get('object', {}).get('amount', 0)
    importe_euros = importe_cents / 100

    if data.get('object', {}).get('status') == 'SUCCEEDED' or data.get('type') == 'charge.succeeded':
        gestor_pedidos.actualizar_estado(order_id, "pagado")
        mensaje = (
            f"❕*Pedido registrado*❕\n      ------------------  \n"
            f"▪️Nombre: *{nombre_usuario}*\n▪️importe: *{importe_euros}*€\n"
            f"▪️ID pedido: *#{order_id}*\n▪️Tiempo estimado: *15m*\n"
            f"▪️Direccion: 👇🏼 \n\n{costumer_adress}"
        )
        enviar_mensaje_whatsapp(mensaje, customer_phone)
        print("El pedido está pagado")

    return jsonify({'message': 'Webhook recibido correctamente'}), 200
