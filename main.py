import Monei
from Monei import ApiException
from flask import Flask, request, jsonify, render_template, redirect , session, jsonify
from pprint import pprint
from controllers.registro_de_usuarios.registro import manejar_registro
from controllers.mensajes_registrados import manejar_mensajes_registrados
from data.usuarios import  GestorUsuariosBD, Usuario_web , ProductoManager
from data.carrito import carrito_instancia
from data.estado_usuarios import estado_usuarios
from utils.text_utils import limpiar_texto
from database import conectar_bd1 , db_session
from flask_cors import CORS 
import json
import redis
import os
from utils.crear_token import   obtener_numero_cliente , generar_token_y_guardar_cliente

from data.order import GestorPedidos

gestor_pedidos = GestorPedidos(db_session)
gestor_usuarios = GestorUsuariosBD()
gestor_productos = ProductoManager()

# Instanciar el cliente de Monei con tu API key
monei = Monei.MoneiClient(api_key='pk_test_d0b6b6a4723919770f88997d1dbe584b')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')
CORS(app, resources={r"/api/*": {"origins": ["http://127.0.0.1:5500", "http://localhost:5000"]}})

# Endpoint para agregar pedido y crear el pago
@app.route('/api/agregar_pedido', methods=['OPTIONS', 'POST'])
def agregar_pedido():
    if request.method == 'OPTIONS':
        # Respuesta al preflight
        response = app.make_response('')
        response.headers.add("Access-Control-Allow-Origin", "http://localhost:5000")
        response.headers.add("Access-Control-Allow-Methods", "POST, OPTIONS")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        return response, 200

    if request.method == 'POST':
        data = request.json
        print("Datos recibidos en agregar pedido:", data)
        
        # Se espera que el JSON del cliente tenga la siguiente estructura:
        # {
        #   "userId": "123",
        #   "name": "Juan Pérez",
        #   "numero": "555-1234",
        #   "direccion": "Calle Falsa 123",
        #   "productos": [
        #         {"codigo": 301, "cantidad": 2},
        #         {"codigo": 302, "cantidad": 1}
        #   ]
        # }
        productos_recibidos = data.get("productos", [])
        productos_validos = []
        total_calculado = 0.0
        
        # Validar cada producto y recalcular el precio usando la base de datos
        for item in productos_recibidos:
            codigo = item.get("codigo")
            cantidad = item.get("cantidad", 1)
            
            # Consulta el producto por código en la base de datos
            producto_db = gestor_productos.obtener_producto_por_codigo(codigo)
            print("Producto DB:", producto_db)
            if not producto_db:
                return jsonify({"error": f"Producto con código {codigo} no encontrado"}), 400
            
            precio_db = float(producto_db["Precio"])
            print("Precio DB:", precio_db)
            total_calculado += precio_db * cantidad
            productos_validos.append([codigo, cantidad])
            print("Productos válidos:", productos_validos)
        
        id_usuario = data.get("userID")
        numero_cliente = data.get("numero")
        nombre_cliente = data.get("name")
        direccion_cliente = data.get("direccion")
        
        print(nombre_cliente, "nombre cliente")
        print("ID pasado:", id_usuario)
        print("Nombre de agregar:", nombre_cliente)
        
        # Obtener el pedido activo para el usuario y agregar los productos validados
        pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(id_usuario)
        print("Pedido activo:", pedido_activo)
        pedido_activo_id = pedido_activo.PedidoID
        pedido_activo_id_srt = str(pedido_activo_id)
        gestor_pedidos.agregar_productos_a_pedido(pedido_activo_id, productos_validos)
        
        print(pedido_activo_id, "ID pedido /api")
        
        # Convertir el total calculado a céntimos (por ejemplo, 12.50€ -> 1250)
        amount_in_cents = int(round(total_calculado * 100))
        
        # Datos de pago. Aquí se utiliza el total recalculado para evitar depender del precio enviado desde el cliente.
        payment_data = {
            'amount': amount_in_cents,
            'order_id': pedido_activo_id_srt,
            'currency': 'EUR',
            'description': nombre_cliente,
            'customer': {
                'email': 'john.doe@monei.com',  # Asegúrate de obtener el email real si está disponible
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
            print("Datos de pago enviados a Monei:", payment_data)
            result = monei.payments.create(payment_data)
            print("Respuesta de pago:", result)
            
            redirect_url = result.get('next_action', {}).get('redirect_url')
            print("URL de redirección obtenida:", redirect_url)
            
            gestor_pedidos.actualizar_estado(pedido_activo_id, "confirmando-pago")
            gestor_pedidos.guardar_enlace(pedido_activo_id, redirect_url)
            
            if redirect_url:
                return jsonify({"redirect_url": redirect_url, "message": "Pedido enviado correctamente."}), 200
            else:
                print("Error: No se encontró la URL de redirección en la respuesta")
                return jsonify({"error": "No se encontró la URL de redirección en la respuesta"}), 500
        except ApiException as e:
            print("Error al crear el pago:", e)
            return jsonify({"error": str(e)}), 500




cache = redis.Redis(host='localhost', port=6379, db=0)

@app.route('/menu/<token>', methods=['GET'])
def quiniela(token=None):
    numero_cliente = obtener_numero_cliente(numero_cliente_token_global)
    print(numero_cliente,"cleinte numeor")
    if not numero_cliente:
        return jsonify({"error": "Enlace no válido o expirado"}), 403

    
    datos_completos = gestor_usuarios.obtener_usuario_completo(numero_cliente)
    id_usuario_activo = datos_completos["id"]
    print("usuario id activo " , id_usuario_activo)

    print(datos_completos,"datos")
    if datos_completos is None:
        return jsonify({"error": "Usuario no encontrado"}), 404

    usuario = Usuario_web(datos_completos)
    
    print(usuario,"user")
    return render_template('quiniela.html', usuario=usuario)


#esta ruta esta conectada con tiwlio  cuando el usuario envia un mensaje este end point 
#   fix-bug corregir variable goblam
     
numero_cliente_token_global = None

@app.route('/webhook', methods=['POST'])
def webhook():
    global numero_cliente_token_global

    numero_cliente = request.form['From']
    mensaje_cliente1 = request.form['Body'].strip().lower()
    mensaje_cliente = limpiar_texto(mensaje_cliente1)

    numero_cliente_token_global = generar_token_y_guardar_cliente(numero_cliente)
    print("mensaje-cliente", mensaje_cliente)
    if not gestor_usuarios.obtener_usuario(numero_cliente):
        return manejar_registro(numero_cliente, mensaje_cliente)
    else:
        return manejar_mensajes_registrados(numero_cliente, mensaje_cliente)






import hmac
import hashlib
from utils.mensajes import enviar_mensaje_whatsapp

WEBHOOK_SECRET = b'tu_clave_secreta'

def verify_signature(request_data, received_signature):
    computed_signature = hmac.new(WEBHOOK_SECRET, request_data, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed_signature, received_signature)


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
    
    print("Data recibida:", data)
    
    # Condición para determinar si el pedido está pagado
    # Puedes adaptar esta condición según lo que envíe Monei
    if data.get('object', {}).get('status') == 'SUCCEEDED' or data.get('type') == 'charge.succeeded':
        gestor_pedidos.actualizar_estado(order_id, "pagado")
        mensaje = f"❕*Pedido registrado*❕\n      ------------------  \n▪️Nombre: *{nombre_usuario}* ▪️importe: *{importe_euros}*€\n▪️ID pedido: *#{order_id}*\n▪️Tiempo estimado: *30m*\n▪️Direccion: 👇🏼 \n\n{costumer_adress}"
        enviar_mensaje_whatsapp(mensaje, customer_phone )

        print("El pedido está pagado")
    
    return jsonify({'message': 'Webhook recibido correctamente'}), 200



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








import uuid  # Para generar un identificador único

@app.route('/api/confirmacion', methods=['OPTIONS', 'POST'])
def agregar_pedido_confirmacion():
    if request.method == 'OPTIONS':
        response = app.make_response('')
        response.headers.add("Access-Control-Allow-Origin", "http://localhost:5000")
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
        productos_recibidos = data.get("productos", [])

        productos = []
        total = 0

        for p in productos_recibidos:
            nombre_producto = p.get("nombre", "Producto desconocido")
            cantidad = p.get("cantidad", 1)
            precio_unitario = p.get("precio_unitario", 0.0)
            codigo = p.get("Codigo")
            precio_total = precio_unitario * cantidad

            productos.append({
                "nombre": nombre_producto,
                "cantidad": cantidad,
                "precio": precio_total,
                "codigo": codigo
                
            })

            total += precio_total

        # Generar un ID único para este pedido
        pedido_id = str(uuid.uuid4())

        # Guardar los datos en Redis
        cache.set(pedido_id, json.dumps({"name": name, "userID":userID, "numero": numero,"direccion": direccion, "productos": productos, "total": total}), ex=3600)

        confirmacion_url = f"http://localhost:5000/confirmacion_pago?pedido_id={pedido_id}"

        return jsonify({"redirect_url": confirmacion_url})

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

    print("productos, confirmas pago",productos)

    return render_template("confirmacion_pago.html", name=name,userID=userID, numero=numero, direccion=direccion, total=total, productos=productos)
    
if __name__ == "__main__":
    db_conn = conectar_bd1()
    if db_conn:
        db_conn.close()
    app.run(debug=True, port=5000)





