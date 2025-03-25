import Monei
from Monei import ApiException
from flask import Flask, request, jsonify, render_template, redirect , jsonify
from controllers.registro_de_usuarios.registro import manejar_registro
from controllers.mensajes_registrados import   ManejadorMensajesRegistrados
from managers.gestor_productos import ProductoManager
from models import Usuario_web
from managers.gestor_usuarios import GestorUsuariosBD
from utils.text_utils import limpiar_texto
from database import conectar_bd1 , db_session
from flask_cors import CORS 
import json
import redis
import os
from utils.crear_token import   obtener_numero_cliente , generar_token_y_guardar_cliente
import uuid  # Para generar un identificador único
from urllib.parse import unquote

import hmac
import hashlib
from utils.mensajes import enviar_mensaje_whatsapp

from data.order import GestorPedidos

gestor_pedidos = GestorPedidos(db_session)
gestor_usuarios = GestorUsuariosBD()
gestor_productos = ProductoManager()

# Instanciar el cliente de Monei con tu API key
monei = Monei.MoneiClient(api_key='pk_test_d0b6b6a4723919770f88997d1dbe584b')
cache = redis.Redis(host='localhost', port=6379, db=0)

app = Flask(__name__)

app.secret_key = os.environ.get('SECRET_KEY')
CORS(app, resources={r"/api/*": {"origins": "*"}})


 




# # Esta ruta se encarga de mostrar el menú de la quiniela.
# # si el estado en la base de datos de pedido es enlace2 se le redirige
# # a la página de confirmación de pago.
# # si el estado es enlace se le muestra el menú de la quiniela
@app.route('/menu/<numero_cliente>/<token>', methods=['GET'])
def quiniela(numero_cliente, token=None):

    numero_cliente = unquote(numero_cliente)
    print("numero_cliente", numero_cliente)
    if not numero_cliente:
        return jsonify({"error": "Enlace no válido o expirado"}), 403

    datos_completos = gestor_usuarios.obtener_usuario_completo(numero_cliente)
    if datos_completos is None:
        return jsonify({"error": "Usuario no encontrado"}), 404

    last_pedido = gestor_pedidos.obtener_pedido_mas_reciente(datos_completos["id"])
    estado = last_pedido.Estado

    datos_completos["token"] = token

    usuario = Usuario_web(datos_completos)
    print(datos_completos, "user")

    # Lógica para redirigir o renderizar según el estado
    if estado == "enlace":
        return render_template('quiniela.html', usuario=usuario)
    elif estado == "enlace2":
        pedido_id = last_pedido.redisID  # Asegúrate de que PedidoID esté disponible en last_pedido
        return redirect(f'/confirmacion_pago?pedido_id={pedido_id}')
    else:
        return jsonify({"error": "Estado no reconocido"}), 400



# # Esta ruta se encarga de recibir la confirmación del pedido y redirigir al usuario a la página de confirmación de pago.
# # Se espera que el JSON del cliente tenga la siguiente estructura:
# # {
# #   "userId": "123",
# #   "name": "Juan Pérez",
# #   "numero": "555-1234",
# #   "direccion": "Calle Falsa 123",       
# #   "productos": [
# #         {"codigo": 301, "cantidad": 2},
# #         {"codigo": 302, "cantidad": 1}
# #   ]
# # }
@app.route('/api/confirmacion', methods=['OPTIONS', 'POST'])
def agregar_pedido_confirmacion():

    if request.method == 'OPTIONS':
        response = app.make_response('')
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Methods", "POST, OPTIONS")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        return response, 200

    if request.method == 'POST':
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

        # Generar un ID único para este pedido
        pedido_id = str(uuid.uuid4())


        pedidoID = gestor_pedidos.obtener_pedido_mas_reciente(userID)
        pedido_ID_DB = pedidoID.PedidoID
        # Guardar los datos en Redis

        cache.set(pedido_id, json.dumps({"name": name, "token":token ,"userID":userID, "pedidoID":pedido_ID_DB, "numero": numero,"direccion": direccion, "productos": productos, "total": total}), ex=3600)
        
        gestor_pedidos.introudcir_dato_redisID(pedidoID.PedidoID, pedido_id)
        if pedidoID.Estado != "enlace":
            print(f"No se puede cambiar el estado. Estado actual: '{pedidoID.Estado}'")
        else:
            gestor_pedidos.actualizar_estado(pedidoID.PedidoID, "enlace2")

        confirmacion_url = f"https://9fc0-62-116-223-170.ngrok-free.app/confirmacion_pago?pedido_id={pedido_id}" 
        

        return jsonify({"redirect_url": confirmacion_url})



# # Esta ruta se encarga de mostrar la página de confirmación de pago.
@app.route('/confirmacion_pago')
def mostrar_confirmacion():
    pedido_id = request.args.get("pedido_id")
    if not pedido_id:
        return jsonify({"error": "Pedido no encontrado"}), 404

    # Recuperar los datos del pedido desde Redis
    pedido_data = cache.get(pedido_id)
    if not pedido_data:
        return jsonify({"error": "Pedido expirado o no encontrado"}), 404

    pedido = json.loads(pedido_data)
    name = pedido["name"]
    userID = pedido["userID"]
    direccion = pedido["direccion"]
    total = pedido["total"]
    productos = pedido["productos"]
    numero = pedido["numero"]
    pedidoID = pedido["pedidoID"]
    token = pedido["token"] 

    print("productos, confirmas pago",productos)
    

    return render_template("confirmacion_pago.html", name=name,userID=userID,token=token, numero=numero, direccion=direccion, total=total, productos=productos, pedidoID=pedidoID)

# # Esta ruta se encarga de mostrar la página de confirmación de pago.
@app.route('/pago_confirmado')
def mostrar_confirmacion_depago():
    pedido_id = request.args.get("pedido_id")
    if not pedido_id:
        return jsonify({"error": "Pedido no encontrado"}), 404

    # Recuperar los datos del pedido desde Redis
    pedido_data = cache.get(pedido_id)
    if not pedido_data:
        return jsonify({"error": "Pedido expirado o no encontrado"}), 404

    pedido = json.loads(pedido_data)
    name = pedido["name"]
    userID = pedido["userID"]
    direccion = pedido["direccion"]
    total = pedido["total"]
    productos = pedido["productos"]
    numero = pedido["numero"]
    pedidoID = pedido["pedidoID"]
    token = pedido["token"] 

    print("productos, confirmas pago",productos)
    

    return render_template("ver_comandas.html", name=name,userID=userID,token=token, numero=numero, direccion=direccion, total=total, productos=productos, pedidoID=pedidoID)




#  aqui agregamos los productos al pedido y creamos el pago , devemso mejorar la logica para 
#  separar responsabilidades y no tener tanto codigo en la misma funcion
#  tambien comprobamos los precios en la base de datos  
@app.route('/api/agregar_pedido', methods=['OPTIONS', 'POST'])
def agregar_pedido():
    if request.method == 'OPTIONS':
        response = app.make_response('')
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Methods", "POST, OPTIONS")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        return response, 200

    if request.method == 'POST':
        data = request.json
        print("Datos recibidos en agregar pedido:", data)
        
        id_usuario = data.get("userID")
        if not id_usuario:
            return jsonify({"error": "ID de usuario no proporcionado"}), 400

        pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(id_usuario)
        estado1 = pedido_activo.Estado
        
        print("estado pedido activo", estado1)
        if not pedido_activo:
            return jsonify({"error": "No se encontró un pedido activo para este usuario"}), 404

        # Verificar si el pedido ya está en estado de confirmando-pago o pagado
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
            'completeUrl': f"https://9fc0-62-116-223-170.ngrok-free.app/pago_confirmado?pedido_id={redisID}",
            'customer': {
                'email': 'john.doe@monei.com',  # Obtener el email real si está disponible
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









########## utils ##########

# # Esta ruta se encarga de cambiar el estado del pedido a "enlace"
# # y redirigir al usuario a la página de confirmación de pago.
# # es un util extender para reutilizar el mismo endpoint


@app.route('/api/cambiar_estado_a_enlace', methods=['POST'])
def cambiar_estado_a_enlace():
    data = request.json
    pedido_id = data.get("pedidoID")

    if not pedido_id:
        return jsonify({"error": "Pedido ID no proporcionado"}), 400

    # Obtener el pedido desde la base de datos
    pedido = gestor_pedidos.obtener_pedido(pedido_id)
    if not pedido:
        return jsonify({"error": "Pedido no encontrado"}), 404

    # Verificar si el estado actual es "enlace2"
    if pedido.Estado == "confirmando-pago":
        return jsonify({"error": "error'"}), 400

    # Actualizar el estado del pedido a 'enlace'
    gestor_pedidos.actualizar_estado(pedido.PedidoID, "enlace")
    return jsonify({"message": "Estado actualizado a 'enlace'"}), 200





########### webhook ###########
import logging
from flask import request, jsonify
from sqlalchemy.exc import SQLAlchemyError
from tenacity import RetryError

logger = logging.getLogger(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    # Validar entrada
    if 'From' not in request.form or 'Body' not in request.form:
        logger.warning("Solicitud inválida: falta 'From' o 'Body'")
        return jsonify({"error": "Solicitud inválida"}), 400

    numero_cliente = request.form['From']
    mensaje_cliente1 = request.form['Body'].strip().lower()
    mensaje_cliente = limpiar_texto(mensaje_cliente1)

    logger.info(f"Mensaje recibido de {numero_cliente}: {mensaje_cliente}")

    try:
        # Verificar si el usuario existe
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

    # Procesamiento normal
    try:
        if not usuario:
            return manejar_registro(numero_cliente, mensaje_cliente)
        else:
            return ManejadorMensajesRegistrados.manejar_mensajes_registrados(
                numero_cliente, mensaje_cliente
            )
    except Exception as e:
        logger.exception("Error procesando el mensaje del usuario:")
        enviar_mensaje_whatsapp(
            "Se presentó un problema al procesar su mensaje. Intente nuevamente.",
            numero_cliente
        )
        return jsonify({"error": "Error procesando el mensaje"}), 500
    

    
WEBHOOK_SECRET = b'tu_clave_secreta'

def verify_signature(request_data, received_signature):
    computed_signature = hmac.new(WEBHOOK_SECRET, request_data, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed_signature, received_signature)

# # Esta ruta se encarga de recibir los
# # webhooks de Monei y procesar la información del pago.

@app.route('/webhoo/monei', methods=['POST'])
def webhoo():
    # Obtener el cuerpo de la petición
    request_data = request.get_data()
    print("Request data:", request_data)
    
    # Parsear el JSON recibido
    data = request.get_json()
    order_id = data.get('object', {}).get('orderId')
    nombre_usuario = data.get('object', {}).get('description')
    customer_phone = data.get('object', {}).get('customer', {}).get('phone')
    costumer_adress = data.get('object', {}).get('billingDetails', {}).get('address',{}).get("line1")

    importe_cents = data.get('object', {}).get('amount', 0)
    importe_euros = importe_cents / 100  # Convertir a euros
    
    
    
    # Condición para determinar si el pedido está pagado
    # Puedes adaptar esta condición según lo que envíe Monei
    if data.get('object', {}).get('status') == 'SUCCEEDED' or data.get('type') == 'charge.succeeded':
        gestor_pedidos.actualizar_estado(order_id, "pagado")
        mensaje = f"❕*Pedido registrado*❕\n      ------------------  \n▪️Nombre: *{nombre_usuario}* ▪️importe: *{importe_euros}*€\n▪️ID pedido: *#{order_id}*\n▪️Tiempo estimado: *15m*\n▪️Direccion: 👇🏼 \n\n{costumer_adress}"
        enviar_mensaje_whatsapp(mensaje, customer_phone )

        print("El pedido está pagado")
    
    return jsonify({'message': 'Webhook recibido correctamente'}), 200

# # Esta ruta se encarga de obtener los productos de la base de datos

@app.route('/api/productos', methods=['GET'])
def obtener_productos():
    try:
        productos = gestor_productos.obtener_productos()
        print("aqui",productos)
        
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




if __name__ == "__main__":
    db_conn = conectar_bd1()
    if db_conn:
        db_conn.close()
    app.run(debug=True, host='0.0.0.0', port=5000)





