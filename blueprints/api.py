import json
import os
import uuid
from flask import Blueprint, request, jsonify, make_response
from Monei import ApiException

from services import gestor_pedidos, gestor_productos, monei, cache

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

    name = data.get("name", "Nombre no especificado")
    userID = data.get("userId", "ID no especificado")
    numero = data.get("numero", "Numero no especificado")
    direccion = data.get("direccion", "Dirección no especificada")
    token = data.get("token", "")
    productos_recibidos = data.get("productos", [])

    productos = []
    total = 0

    for p in productos_recibidos:
        nombre_producto = p.get("nombre", "Producto desconocido")
        cantidad = p.get("cantidad", 1)
        precio_unitario = p.get("precio_unitario", 0.0)
        codigo = p.get("Codigo")
        precio_total = round(precio_unitario * cantidad, 2)

        productos.append({
            "nombre": nombre_producto,
            "cantidad": cantidad,
            "precio": precio_total,
            "codigo": codigo
        })
        total += precio_total

    total = round(total, 2)
    pedido_id = str(uuid.uuid4())

    pedidoID = gestor_pedidos.obtener_pedido_mas_reciente(userID)
    pedido_ID_DB = pedidoID.PedidoID

    cache.set(pedido_id, json.dumps({
        "name": name, "token": token, "userID": userID,
        "pedidoID": pedido_ID_DB, "numero": numero,
        "direccion": direccion, "productos": productos, "total": total
    }), ex=3600)

    gestor_pedidos.introudcir_dato_redisID(pedidoID.PedidoID, pedido_id)
    if pedidoID.Estado != "enlace":
        print(f"No se puede cambiar el estado. Estado actual: '{pedidoID.Estado}'")
    else:
        gestor_pedidos.actualizar_estado(pedidoID.PedidoID, "enlace2")

    confirmacion_url = f"{os.environ.get('PUBLIC_URL')}/confirmacion_pago?pedido_id={pedido_id}"
    return jsonify({"redirect_url": confirmacion_url})


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

    pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(id_usuario)

    if not pedido_activo:
        return jsonify({"error": "No se encontró un pedido activo para este usuario"}), 404

    estado1 = pedido_activo.Estado
    print("estado pedido activo", estado1)

    if estado1 == "confirmando-pago":
        return jsonify({"message": "El pedido ya está en proceso de pago."}), 200

    productos_recibidos = data.get("productos", [])
    productos_validos = []
    total_calculado = 0.0

    for item in productos_recibidos:
        codigo = item.get("codigo")
        cantidad = item.get("cantidad", 1)

        producto_db = gestor_productos.obtener_producto_por_codigo(codigo)
        if not producto_db:
            return jsonify({"error": f"Producto con código {codigo} no encontrado"}), 400

        precio_db = float(producto_db["Precio"])
        total_calculado += precio_db * cantidad
        productos_validos.append([codigo, cantidad])

    numero_cliente = data.get("numero")
    nombre_cliente = data.get("name")
    direccion_cliente = data.get("direccion")

    pedido_activo_id = pedido_activo.PedidoID
    gestor_pedidos.agregar_productos_a_pedido(pedido_activo_id, productos_validos)
    redisID = pedido_activo.redisID

    amount_in_cents = int(round(total_calculado * 100))

    payment_data = {
        'amount': amount_in_cents,
        'order_id': str(pedido_activo_id),
        'currency': 'EUR',
        'description': nombre_cliente,
        'completeUrl': f"{os.environ.get('PUBLIC_URL')}/pago_confirmado?pedido_id={redisID}",
        'customer': {
            'email': 'john.doe@monei.com',
            'name': nombre_cliente,
            'phone': numero_cliente
        },
        'billingDetails': {
            'address': {
                'line1': direccion_cliente,
                'city': 'tarancon',
                'postalCode': '16400',
                'country': 'ES'
            }
        }
    }

    try:
        result = monei.payments.create(payment_data)
        print("Respuesta de pago:", result)

        redirect_url = result.get('next_action', {}).get('redirect_url')
        print("URL de redirección obtenida:", redirect_url)

        gestor_pedidos.actualizar_estado(pedido_activo_id, "confirmando-pago")
        gestor_pedidos.guardar_enlace(pedido_activo_id, redirect_url)

        if redirect_url:
            return jsonify({"redirect_url": redirect_url, "message": "Pedido enviado correctamente."}), 200
        else:
            return jsonify({"error": "No se encontró la URL de redirección en la respuesta"}), 500
    except ApiException as e:
        print("Error al crear el pago:", e)
        return jsonify({"error": str(e)}), 500


@blueprint_api.route('/api/cambiar_estado_a_enlace', methods=['POST'])
def cambiar_estado_a_enlace():
    data = request.json
    pedido_id = data.get("pedidoID")

    if not pedido_id:
        return jsonify({"error": "Pedido ID no proporcionado"}), 400

    pedido = gestor_pedidos.obtener_pedido(pedido_id)
    if not pedido:
        return jsonify({"error": "Pedido no encontrado"}), 404

    if pedido.Estado == "confirmando-pago":
        return jsonify({"error": "error'"}), 400

    gestor_pedidos.actualizar_estado(pedido.PedidoID, "enlace")
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
