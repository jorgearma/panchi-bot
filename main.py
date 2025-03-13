import Monei
from Monei import ApiException
from flask import Flask, request, jsonify, render_template, redirect , session, jsonify
from pprint import pprint
from controllers.registro_de_usuarios.registro import manejar_registro
from controllers.mensajes_registrados import manejar_mensajes_registrados
from data.usuarios import  GestorUsuariosBD, Usuario_web 
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
        print("Datos recibidos:", data)
        
        productos = [[1, 4], [2, 4], [3, 4]] #aqui  devo recoger los datos enviados desde la pagina 
        print("prudcutos" , productos)
        id_usuario = data.get("userId")
        numero_cliente = data.get("numero")
        nombre_cliente = data.get("name")
        
        print(nombre_cliente, "nombre cliente ")
        direccion_cliente = data.get("direccion")

        print("id pasado" , id_usuario)
        print("nombre de agregar" , nombre_cliente)

        pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(id_usuario)
        pedido_activo_id = pedido_activo.PedidoID
        pedido_activo_id_srt = str(pedido_activo_id)
        gestor_pedidos.agregar_productos_a_pedido(pedido_activo_id , productos)

        print(pedido_activo_id , "id  pedido /api")

        
        
        # Datos de pago. Puedes extraerlos del request o definirlos aquí.
        payment_data = {
        'amount': 1250,  # 12.50€
        'order_id': pedido_activo_id_srt,  # Usar order_id en lugar de orderId
        'currency': 'EUR',
        'description': nombre_cliente,
        'customer': {
            'email': 'john.doe@monei.com',
            'name': "nombre",
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
            # Crear el pago usando la API de Monei
            result = monei.payments.create(payment_data)
            print("Respuesta de pago:", result)

            # Extraer la URL de redirección desde next_action
            
            redirect_url = result.get('next_action', {}).get('redirect_url')
            gestor_pedidos.actualizar_estado(pedido_activo_id,"confirmando-pago")
            gestor_pedidos.guardar_enlace(pedido_activo_id, redirect_url)
            print("url =>",redirect_url)

            if redirect_url:
        # Retornar la URL en un JSON en lugar de hacer redirect
                return jsonify({"redirect_url": redirect_url, "message": "Pedido enviado correctamente."}), 200
            else:
                return jsonify({"error": "No se encontró la URL de redirección en la respuesta"}), 500
        except ApiException as e:
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


if __name__ == "__main__":
    db_conn = conectar_bd1()
    if db_conn:
        db_conn.close()
    app.run(debug=True, port=5000)
