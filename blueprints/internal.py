import logging

import config
from flask import Blueprint, jsonify, request
from sqlalchemy.exc import SQLAlchemyError
from tenacity import RetryError

from container import gestor_pedidos

blueprint_internal = Blueprint('internal', __name__)
logger = logging.getLogger(__name__)


@blueprint_internal.route('/internal/limpiar-pedidos-caducados', methods=['POST'])
def limpiar_pedidos_caducados():
    """Cancela pedidos en ENLACE/ENLACE2 con más de 1h de antigüedad. Llamado desde cron."""
    token = request.headers.get("Authorization", "")
    expected = f"Bearer {config.INTERNAL_API_TOKEN}"
    if not config.INTERNAL_API_TOKEN or token != expected:
        logger.warning("limpiar_pedidos_caducados: intento no autorizado desde %s", request.remote_addr)
        return jsonify({"error": "No autorizado"}), 401

    try:
        cancelados = gestor_pedidos.cancelar_pedidos_caducados()
    except (SQLAlchemyError, RetryError) as e:
        logger.error("limpiar_pedidos_caducados: error=%s", e)
        return jsonify({"error": "Error interno"}), 500

    return jsonify({"cancelados": cancelados}), 200
