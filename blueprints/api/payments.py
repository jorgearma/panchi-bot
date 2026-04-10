import logging

import config
from flask import jsonify, request

from container import gestor_pedidos, gestor_productos, get_monei
from controllers.pago import iniciar_pago, iniciar_pago_efectivo
from blueprints.api.cart import _user_id_del_token

logger = logging.getLogger(__name__)


def register(bp):
    """Registra las rutas de creación de pedidos con pago online o efectivo."""
    @bp.route('/api/agregar_pedido', methods=['POST'])
    def agregar_pedido():
        """Inicia el flujo de pago online para el carrito recibido."""
        data = request.json
        logger.debug("Datos recibidos en agregar pedido: %s", data)

        ip = request.remote_addr
        token = data.get("token", "")
        token_user_id = _user_id_del_token(token)
        if not token or not token_user_id:
            return jsonify({"error": "Sesión inválida o expirada"}), 401

        post_user_id = data.get("userID")
        if str(post_user_id) != str(token_user_id):
            logger.warning("TOKEN_MISMATCH  endpoint=/api/agregar_pedido  token_user=%s  post_user=%s  ip=%s", token_user_id, post_user_id, ip)
            return jsonify({"error": "No autorizado"}), 403

        carrito = data.get("productos", data.get("carrito", []))
        if not carrito:
            return jsonify({"error": "El carrito está vacío"}), 400

        notas = data.get("notas", "")

        success, result = iniciar_pago(
            user_id=token_user_id,
            productos_recibidos=carrito,
            nombre_cliente=data.get("name"),
            numero_cliente=data.get("numero"),
            direccion_cliente=data.get("direccion"),
            notas=notas,
            gestor_pedidos=gestor_pedidos,
            gestor_productos=gestor_productos,
            monei=get_monei(),
            public_url=config.PUBLIC_URL or "",
        )

        if not success:
            return jsonify({"error": result}), 400

        logger.info("API_PEDIDO_ONLINE  user_id=%s  productos=%d  ip=%s", token_user_id, len(carrito), ip)
        return jsonify({"redirect_url": result, "message": "Pedido enviado correctamente."}), 200

    @bp.route('/api/agregar_pedido_efectivo', methods=['POST'])
    def agregar_pedido_efectivo():
        """Confirma un pedido con pago contra entrega."""
        data = request.json
        logger.debug("Datos recibidos en agregar_pedido_efectivo: %s", data)

        ip = request.remote_addr
        token = data.get("token", "")
        token_user_id = _user_id_del_token(token)
        if not token or not token_user_id:
            return jsonify({"error": "Sesión inválida o expirada"}), 401

        post_user_id = data.get("userID")
        if str(post_user_id) != str(token_user_id):
            logger.warning("TOKEN_MISMATCH  endpoint=/api/agregar_pedido_efectivo  token_user=%s  post_user=%s  ip=%s", token_user_id, post_user_id, ip)
            return jsonify({"error": "No autorizado"}), 403

        notas = data.get("notas", "")

        success, result = iniciar_pago_efectivo(
            user_id=token_user_id,
            productos_recibidos=data.get("productos", []),
            nombre_cliente=data.get("name"),
            numero_cliente=data.get("numero"),
            direccion_cliente=data.get("direccion"),
            notas=notas,
            gestor_pedidos=gestor_pedidos,
            gestor_productos=gestor_productos,
            public_url=config.PUBLIC_URL or "",
        )

        if not success:
            return jsonify({"error": result}), 400

        logger.info("API_PEDIDO_EFECTIVO  user_id=%s  productos=%d  ip=%s", token_user_id, len(data.get("productos", [])), ip)
        return jsonify({"redirect_url": result, "message": "Pedido confirmado. Pago a la entrega."}), 200
