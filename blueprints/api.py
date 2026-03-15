import os
import uuid
from flask import Blueprint, request, jsonify, make_response

from services import gestor_pedidos, gestor_productos, monei, cache
from states import EstadoPedido
from controllers.pedido import confirmar_carrito
from controllers.pago import iniciar_pago

blueprint_api = Blueprint('api', __name__)


@blueprint_api.route('/api/confirmacion', methods=['OPTIONS', 'POST'])
def agregar_pedido_confirmacion():
    if request.method == 'OPTIONS':
        response = make_response('')
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Methods", "POST, OPTIONS")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        return response, 200

    data = request.json
    print("Datos recibidos pai confimacion:", data)

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
        public_url=os.environ.get("PUBLIC_URL", ""),
    )

    if not success:
        return jsonify({"error": result}), 404

    return jsonify({"redirect_url": result})


@blueprint_api.route('/api/agregar_pedido', methods=['OPTIONS', 'POST'])
def agregar_pedido():
    if request.method == 'OPTIONS':
        response = make_response('')
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Methods", "POST, OPTIONS")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        return response, 200

    data = request.json
    print("Datos recibidos en agregar pedido:", data)

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
        monei=monei,
        public_url=os.environ.get("PUBLIC_URL", ""),
    )

    if not success:
        if "no encontrado" in result.lower():
            return jsonify({"error": result}), 404
        return jsonify({"error": result}), 400 if "Producto" in result else 500

    if result == "El pedido ya está en proceso de pago.":
        return jsonify({"message": result}), 200

    return jsonify({"redirect_url": result, "message": "Pedido enviado correctamente."}), 200


@blueprint_api.route('/api/cambiar_estado_a_enlace', methods=['POST'])
def cambiar_estado_a_enlace():
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


@blueprint_api.route('/api/productos', methods=['GET'])
def obtener_productos():
    try:
        productos = gestor_productos.obtener_productos()
        print("aqui", productos)

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
