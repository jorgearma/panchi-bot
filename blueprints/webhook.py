import logging

from flask import Blueprint, current_app, jsonify, request

import config
from pydantic import ValidationError
from schemas.twilio import WebhookRequest
from services import inbound_whatsapp as inbound
from utils.text_utils import limpiar_texto

blueprint_webhook = Blueprint('webhook', __name__)
logger = logging.getLogger(__name__)


@blueprint_webhook.route('/webhook', methods=['POST'])
def webhook():
    """Recibe mensajes de Twilio, valida la firma y delega al servicio de entrada."""
    if not inbound.verificar_firma_twilio(request, testing=current_app.config.get("TESTING")):
        logger.warning("Twilio webhook signature inválida")
        return jsonify({"error": "Firma inválida"}), 403

    try:
        data = WebhookRequest(**request.form.to_dict())
    except ValidationError as e:
        logger.error("Datos de entrada inválidos: %s", e)
        return jsonify({"error": "Datos de entrada inválidos"}), 400

    numero = data.From
    mensaje = limpiar_texto(data.Body.lower())
    logger.info("Mensaje Twilio recibido de %s: %s", numero, mensaje)
    return inbound.enrutar_mensaje(numero, mensaje)


@blueprint_webhook.route('/webhoo/monei', methods=['POST'])  # TODO: remove once Monei dashboard points to /webhook/monei
@blueprint_webhook.route('/webhook/monei', methods=['POST'])
def webhook_monei():
    """Verifica la firma Monei y procesa el pago confirmado."""
    raw_body = request.get_data()
    ok, err = inbound.verificar_firma_monei(
        raw_body,
        request.headers.get("MONEI-SIGNATURE", ""),
        config.MONEI_WEBHOOK_SECRET,
    )
    if not ok:
        logger.warning("Monei webhook signature rechazada: %s", err)
        return jsonify({"error": "Invalid signature"}), 401

    data = request.get_json()
    if data.get('type') == 'webhook.test':
        logger.info("Monei webhook test recibido — OK")
        return jsonify({"ok": True}), 200

    return inbound.procesar_pago_monei(data)


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
    """Verifica la firma Meta, extrae mensajes y los enruta al servicio de entrada."""
    raw_body = request.get_data()
    if not inbound.verificar_firma_meta(
        raw_body,
        request.headers.get('X-Hub-Signature-256', ''),
        config.META_APP_SECRET,
    ):
        logger.warning("Meta webhook signature rechazada")
        return jsonify({"error": "Invalid signature"}), 401

    for item in inbound.extraer_mensajes_meta(request.get_json()):
        logger.info("Mensaje Meta de %s: %s", item['numero'], item['mensaje'])
        inbound.enrutar_mensaje(item['numero'], limpiar_texto(item['mensaje']))

    return jsonify({"ok": True}), 200
