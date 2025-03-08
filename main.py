import Monei
from Monei import ApiException
from flask import Flask, request, jsonify, render_template, redirect
from pprint import pprint
from controllers.registro_de_usuarios.registro import manejar_registro
from controllers.mensajes_registrados import manejar_mensajes_registrados
from data.usuarios import guardar_usuario_bd, verificar_usuario_bd, GestorUsuariosBD, Usuario
from data.carrito import carrito_instancia
from data.estado_usuarios import estado_usuarios
from utils.text_utils import limpiar_texto
from database import conectar_bd
from flask_cors import CORS 
import json
import redis
from utils.crear_token import generar_enlace

# Instanciar el cliente de Monei con tu API key
monei = Monei.MoneiClient(api_key='pk_test_d0b6b6a4723919770f88997d1dbe584b')

app = Flask(__name__)
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
        print("Datos recibidos:", data)  # Verificar el JSON recibido

        # Procesa el pedido (por ejemplo, agregar productos al carrito)
        for numero_whatsapp, productos in data.items():
            carrito_instancia.agregar_productos(numero_whatsapp, productos)
            xxx = carrito_instancia.obtener_carrito_cliente(numero_whatsapp)
            print("este es el carrito " , xxx)
        # Datos de pago. Puedes extraerlos del request o definirlos aquí.
        payment_data = {
            'amount': 1250,  # 12.50€
            'order_id': '100200000008',  # Usar order_id en lugar de orderId
            'currency': 'EUR',
            'description': 'Items description',
            'customer': {
                'email': 'john.doe@monei.com',
                'name': 'John Doe'
            }
        }
        
        try:
            # Crear el pago usando la API de Monei
            result = monei.payments.create(payment_data)
            print("Respuesta de pago:", result)

            # Extraer la URL de redirección desde next_action
            
            redirect_url = result.get('next_action', {}).get('redirect_url')
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
def quiniela(token):
    numero_cliente = cache.get(token)
    if not numero_cliente:
        return jsonify({"error": "Enlace no válido o expirado"}), 403

    numero_cliente = numero_cliente.decode()
    datos = GestorUsuariosBD.obtener_usuario(numero_cliente)
    if datos is None:
        return jsonify({"error": "Usuario no encontrado"}), 404

    usuario = Usuario(datos['nombre'], datos['numero'], datos['direccion'])
    return render_template('quiniela.html', usuario=usuario)

@app.route('/comandas', methods=['GET'])
def ver_comandas():
    try:
        with conectar_bd() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM comandas ORDER BY fecha DESC;")
                comandas = cur.fetchall()
                result = []
                for c in comandas:
                    try:
                        contenido = json.loads(c[2])
                    except json.JSONDecodeError:
                        contenido = c[2]
                    result.append({
                        "id": c[0],
                        "id_pedido": c[1],
                        "contenido": contenido,
                        "fecha": c[3]
                    })
                return render_template('ver_comandas.html', comandas=result)
    except Exception as e:
        print("Error al obtener las comandas:", e)
        return jsonify({"error": "Error al obtener las comandas"}), 500           

@app.route('/webhook', methods=['POST'])
def webhook():
    numero_cliente = request.form['From']
    mensaje_cliente1 = request.form['Body'].strip().lower()
    mensaje_cliente = limpiar_texto(mensaje_cliente1)
    print("mensaje-cliente", mensaje_cliente)
    if not verificar_usuario_bd(numero_cliente):
        return manejar_registro(numero_cliente, mensaje_cliente)
    else:
        return manejar_mensajes_registrados(numero_cliente, mensaje_cliente)

if __name__ == "__main__":
    db_conn = conectar_bd()
    if db_conn:
        db_conn.close()
    app.run(debug=True, port=5000)
