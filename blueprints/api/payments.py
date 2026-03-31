import logging

import config
from flask import jsonify, request

from services import gestor_pedidos, gestor_productos, get_monei, cache
from controllers.pago import iniciar_pago, iniciar_pago_efectivo

logger = logging.getLogger(__name__)


def register(bp):
    """Registra las rutas de creación de pedidos con pago online o efectivo."""
    @bp.route('/api/agregar_pedido', methods=['POST'])
    def agregar_pedido():
        """Inicia el flujo de pago online para el carrito recibido."""
        data = request.json
        logger.debug("Datos recibidos en agregar pedido: %s", data)

        token = data.get("token", "")
        if not token or not cache.get(token):
            return jsonify({"error": "Sesión inválida o expirada"}), 401

        id_usuario = data.get("userID")
        if not id_usuario:
            return jsonify({"error": "ID de usuario no proporcionado"}), 400

        carrito = data.get("productos", data.get("carrito", []))
        if not carrito:
            return jsonify({"error": "El carrito está vacío"}), 400

        notas = data.get("notas", "")

        success, result = iniciar_pago(
            user_id=id_usuario,
            productos_recibidos=carrito,
            nombre_cliente=data.get("name"),
            numero_cliente=data.get("numero"),
            direccion_cliente=data.get("direccion"),
            notas=notas,
            cache=cache,
            gestor_pedidos=gestor_pedidos,
            gestor_productos=gestor_productos,
            monei=get_monei(),
            public_url=config.PUBLIC_URL or "",
        )

        if not success:
            return jsonify({"error": result}), 400

        if result == "El pedido ya está en proceso de pago.":
            return jsonify({"message": result}), 200

        return jsonify({"redirect_url": result, "message": "Pedido enviado correctamente."}), 200

    @bp.route('/api/agregar_pedido_efectivo', methods=['POST'])
    def agregar_pedido_efectivo():
        """Confirma un pedido con pago contra entrega."""
        data = request.json
        logger.debug("Datos recibidos en agregar_pedido_efectivo: %s", data)

        token = data.get("token", "")
        if not token or not cache.get(token):
            return jsonify({"error": "Sesión inválida o expirada"}), 401

        id_usuario = data.get("userID")
        if not id_usuario:
            return jsonify({"error": "ID de usuario no proporcionado"}), 400

        notas = data.get("notas", "")

        success, result = iniciar_pago_efectivo(
            user_id=id_usuario,
            productos_recibidos=data.get("productos", []),
            nombre_cliente=data.get("name"),
            numero_cliente=data.get("numero"),
            direccion_cliente=data.get("direccion"),
            notas=notas,
            cache=cache,
            gestor_pedidos=gestor_pedidos,
            gestor_productos=gestor_productos,
            public_url=config.PUBLIC_URL or "",
        )

        if not success:
            return jsonify({"error": result}), 400

        return jsonify({"redirect_url": result, "message": "Pedido confirmado. Pago a la entrega."}), 200
