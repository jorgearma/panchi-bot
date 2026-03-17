import uuid
import logging
import config
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

from services import gestor_pedidos, gestor_productos, get_monei, cache
from states import EstadoPedido
from controllers.pedido import confirmar_carrito
from controllers.pago import iniciar_pago, iniciar_pago_efectivo

blueprint_api = Blueprint('api', __name__)


@blueprint_api.route('/api/confirmacion', methods=['POST'])
def agregar_pedido_confirmacion():
    data = request.json
    logger.debug("Datos recibidos en confirmacion: %s", data)

    token = data.get("token", "")
    if not token or not cache.get(token):
        return jsonify({"error": "Sesión inválida o expirada"}), 401

    pedido_id_redis = str(uuid.uuid4())
    success, result = confirmar_carrito(
        pedido_id_redis=pedido_id_redis,
        name=data.get("name", "Nombre no especificado"),
        token=data.get("token", ""),
        user_id=data.get("userId", "ID no especificado"),
        numero=data.get("numero", "Numero no especificado"),
        direccion=data.get("direccion", "Dirección no especificada"),
        productos_recibidos=data.get("productos", []),
        cache=cache,
        gestor_pedidos=gestor_pedidos,
        public_url=config.PUBLIC_URL or "",
    )

    if not success:
        return jsonify({"error": result}), 404

    return jsonify({"redirect_url": result})


@blueprint_api.route('/api/agregar_pedido', methods=['POST'])
def agregar_pedido():
    data = request.json
    logger.debug("Datos recibidos en agregar pedido: %s", data)

    token = data.get("token", "")
    if not token or not cache.get(token):
        return jsonify({"error": "Sesión inválida o expirada"}), 401

    id_usuario = data.get("userID")
    if not id_usuario:
        return jsonify({"error": "ID de usuario no proporcionado"}), 400

    success, result = iniciar_pago(
        user_id=id_usuario,
        productos_recibidos=data.get("productos", []),
        nombre_cliente=data.get("name"),
        numero_cliente=data.get("numero"),
        direccion_cliente=data.get("direccion"),
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


@blueprint_api.route('/api/cambiar_estado_a_enlace', methods=['POST'])
def cambiar_estado_a_enlace():
    token = request.headers.get("X-Internal-Token", "")
    if not config.INTERNAL_API_TOKEN or token != config.INTERNAL_API_TOKEN:
        return jsonify({"error": "No autorizado"}), 401

    data = request.json
    pedido_id = data.get("pedidoID")

    if not pedido_id:
        return jsonify({"error": "Pedido ID no proporcionado"}), 400

    pedido = gestor_pedidos.obtener_pedido(pedido_id)
    if not pedido:
        return jsonify({"error": "Pedido no encontrado"}), 404

    if pedido.Estado == EstadoPedido.CONFIRMANDO_PAGO:
        return jsonify({"error": "error'"}), 400

    gestor_pedidos.actualizar_estado(pedido.PedidoID, EstadoPedido.ENLACE)
    return jsonify({"message": "Estado actualizado a 'enlace'"}), 200


@blueprint_api.route('/api/agregar_pedido_efectivo', methods=['POST'])
def agregar_pedido_efectivo():
    data = request.json
    logger.debug("Datos recibidos en agregar_pedido_efectivo: %s", data)

    token = data.get("token", "")
    if not token or not cache.get(token):
        return jsonify({"error": "Sesión inválida o expirada"}), 401

    id_usuario = data.get("userID")
    if not id_usuario:
        return jsonify({"error": "ID de usuario no proporcionado"}), 400

    success, result = iniciar_pago_efectivo(
        user_id=id_usuario,
        productos_recibidos=data.get("productos", []),
        nombre_cliente=data.get("name"),
        numero_cliente=data.get("numero"),
        direccion_cliente=data.get("direccion"),
        cache=cache,
        gestor_pedidos=gestor_pedidos,
        gestor_productos=gestor_productos,
        public_url=config.PUBLIC_URL or "",
    )

    if not success:
        return jsonify({"error": result}), 400

    return jsonify({"redirect_url": result, "message": "Pedido confirmado. Pago a la entrega."}), 200


@blueprint_api.route('/api/volver_al_menu', methods=['POST'])
def volver_al_menu():
    """Resets an ENLACE2 order back to ENLACE when the user presses back on the confirmation page."""
    data = request.json
    token = data.get("token", "")
    if not token or not cache.get(token):
        return jsonify({"error": "Sesión inválida o expirada"}), 401

    user_id = data.get("userID")
    if not user_id:
        return jsonify({"error": "Usuario no identificado"}), 400

    pedido = gestor_pedidos.obtener_pedido_mas_reciente(user_id)
    if not pedido:
        return jsonify({"error": "Pedido no encontrado"}), 404

    if pedido.Estado == EstadoPedido.ENLACE2:
        gestor_pedidos.actualizar_estado(pedido.PedidoID, EstadoPedido.ENLACE)

    return jsonify({"ok": True})


@blueprint_api.route('/api/productos', methods=['GET'])
def obtener_productos():
    try:
        productos = gestor_productos.obtener_productos()
        logger.debug("Productos obtenidos: %s", productos)

        if not productos:
            return jsonify({"error": "No se encontraron productos"}), 404

        menu = {}
        for producto in productos:
            categoria = producto["Categoria"]
            nombre = producto["Nombre"]

            if categoria not in menu:
                menu[categoria] = {}
            menu[categoria][nombre] = {
                "Codigo": producto["Codigo"],
                "Precio": producto["Precio"],
                "ingredientes": producto["Ingredientes"],
                "Imagen": producto["Imagen"]
            }

        return jsonify(menu)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
