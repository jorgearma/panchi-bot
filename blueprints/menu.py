import json
import logging
from flask import Blueprint, request, jsonify, render_template, redirect

logger = logging.getLogger(__name__)
from urllib.parse import unquote
from sqlalchemy.exc import SQLAlchemyError
from tenacity import RetryError
from pydantic import ValidationError
import redis

import config
from schemas.usuario import UsuarioDatos
from managers.gestor_redis import redismanager
from services import gestor_pedidos, cache
from states import EstadoPedido

blueprint_menu = Blueprint('menu', __name__)


def _extraer_calle(direccion: str) -> str:
    """Returns street + number from an address string.

    Handles two common formats:
      "Calle Mayor 12, 16400 Tarancón"  → "Calle Mayor 12"
      "Calle Mayor, 12, 16400 Tarancón" → "Calle Mayor 12"
    """
    parts = [p.strip() for p in direccion.split(',')]
    if len(parts) >= 2 and parts[1].isdigit():
        return f"{parts[0]} {parts[1]}"
    return parts[0]


@blueprint_menu.route('/menu/<token>', methods=['GET'])
def quiniela(token=None):
    logger.debug("token recibido: %s", token)
    try:
        try:
            datos_completos_redis = redismanager.get(token)
            if not datos_completos_redis:
                return render_template("error.html",
                    titulo='Enlace caducado',
                    mensaje='Tu enlace ha caducado. Vuelve a WhatsApp y escribe 1 para obtener uno nuevo.'
                ), 403
        except redis.exceptions.ResponseError as e:
            logger.error("Error al obtener datos de Redis: %s", e)
            return jsonify({"error": "Error al obtener los datos de Redis"}), 400

        try:
            datos_str = unquote(datos_completos_redis)
            datos_completos_json = json.loads(datos_str)
        except Exception as e:
            return jsonify({"error": "Error al cargar los datos desde Redis"}), 400

        logger.debug("Datos completos desde Redis: user_id=%s", datos_completos_json.get("id"))

        try:
            datos_completos_validados = UsuarioDatos(**datos_completos_json)
        except ValidationError as e:
            logger.error("Error de validación en datos_completos: %s", e)
            return "Datos de usuario inválidos.", 400

        datos_completos_validados.token = token

        logger.debug("Datos validados del usuario: user_id=%s", datos_completos_validados.id)

        id_user = datos_completos_validados.id
        try:
            last_pedido = gestor_pedidos.obtener_pedido_mas_reciente(id_user)
        except (SQLAlchemyError, RetryError) as e:
            logger.error("Error al obtener el pedido tras varios intentos: %s", e)
            return jsonify({"error": "Error en la base de datos. Intente más tarde."}), 500

        if last_pedido is None:
            return render_template("error.html",
                titulo='Sin pedido activo',
                mensaje='No tienes ningún pedido activo.'
            ), 404

        estado = last_pedido.Estado
        logger.debug("Estado del pedido: %s, user_id=%s", estado, id_user)

        if estado == EstadoPedido.ENLACE:
            return render_template(
                'quiniela.html',
                usuario=datos_completos_validados,
                calle=_extraer_calle(datos_completos_validados.direccion),
                public_url=config.PUBLIC_URL or "",
            )
        elif estado == EstadoPedido.ENLACE2:
            pedido_id = last_pedido.redisID
            return redirect(f'/confirmacion_pago?pedido_id={pedido_id}')
        else:
            return jsonify({"error": "Estado no reconocido"}), 400

    except Exception as e:
        logger.exception("Error inesperado en quiniela:")
        return jsonify({"error": "Ocurrió un error inesperado"}), 500


@blueprint_menu.route('/confirmacion_pago')
def mostrar_confirmacion():
    pedido_id = request.args.get("pedido_id")
    if not pedido_id:
        return jsonify({"error": "Pedido no encontrado"}), 404

    pedido_data = cache.get(pedido_id)
    if not pedido_data:
        return jsonify({"error": "Pedido expirado o no encontrado"}), 404

    pedido = json.loads(pedido_data)
    return render_template(
        "confirmacion_pago.html",
        name=pedido["name"],
        userID=pedido["userID"],
        token=pedido["token"],
        numero=pedido["numero"],
        direccion=pedido["direccion"],
        calle=_extraer_calle(pedido["direccion"]),
        total=pedido["total"],
        productos=pedido["productos"],
        pedidoID=pedido["pedidoID"],
        public_url=config.PUBLIC_URL or "",
    )


@blueprint_menu.route('/pago_confirmado')
def mostrar_confirmacion_depago():
    pedido_id = request.args.get("pedido_id")
    if not pedido_id:
        return jsonify({"error": "Pedido no encontrado"}), 404

    pedido_data = cache.get(pedido_id)
    if not pedido_data:
        return jsonify({"error": "Pedido expirado o no encontrado"}), 404

    pedido = json.loads(pedido_data)
    return render_template(
        "ver_comandas.html",
        name=pedido["name"],
        userID=pedido["userID"],
        token=pedido["token"],
        numero=pedido["numero"],
        direccion=pedido["direccion"],
        calle=_extraer_calle(pedido["direccion"]),
        total=pedido["total"],
        productos=pedido["productos"],
        pedidoID=pedido["pedidoID"],
        public_url=config.PUBLIC_URL or "",
    )
