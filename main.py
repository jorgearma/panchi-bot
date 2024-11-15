from flask import Flask, request , jsonify ,render_template
from controllers.registro import manejar_registro
from controllers.mensajes_registrados import manejar_mensajes_registrados
from data.usuarios import guardar_usuario_bd
from data.carrito import carrito
from data.estado_usuarios import estado_usuarios
from database import conectar_bd
import json
import unicodedata
from flask_cors import CORS

app = Flask(__name__)
CORS(app)



from data.carrito import carrito  # Suponiendo que el carrito está en otro archivo

app = Flask(__name__)

from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins=["http://127.0.0.1:5500"])  # Permite solo este origen

@app.route('/api/agregar_pedido', methods=['OPTIONS', 'POST'])
def agregar_pedido():
    if request.method == 'OPTIONS':
        response = app.make_response('')
        response.headers.add("Access-Control-Allow-Origin", "http://127.0.0.1:5500")
        response.headers.add("Access-Control-Allow-Methods", "POST, OPTIONS")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        return response, 204

    if request.method == 'POST':
        data = request.json
        print(data)  # Verifica qué JSON se recibe

        # Extraer el número de WhatsApp y los productos del pedido
        for numero_whatsapp, productos in data.items():
            # Verificar si el número de WhatsApp ya está en el carrito
            if numero_whatsapp in carrito:
                # Si ya existe, agregar los productos al carrito
                carrito[numero_whatsapp].extend(productos)
            else:
                # Si no existe, crear una nueva entrada para el número de WhatsApp
                carrito[numero_whatsapp] = productos

        return jsonify({"message": "Pedido recibido correctamente"}), 200



def limpiar_texto(texto):
    # Convierte a minúsculas y elimina espacios en los extremos
    texto = texto.strip().lower()
    # Elimina acentos y tildes
    texto = ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )
    return texto

def verificar_usuario_bd(numero_cliente):
    try:
        connection = conectar_bd()
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM usuarios WHERE numero_cliente = ?", numero_cliente)
        result = cursor.fetchone()
        return result[0] > 0
    except Exception as e:
        print("Error al verificar el usuario en la base de datos:", e)
        return False
    finally:
        if connection:
            connection.close()

@app.route('/comandas', methods=['GET'])
def ver_comandas():
    try:
        with conectar_bd() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM comandas ORDER BY fecha DESC;")
                comandas = cur.fetchall()

                # Formatear los resultados en una lista de diccionarios
                result = []
                for c in comandas:
                    try:
                        contenido = json.loads(c[2])  # Deserializar el campo 'contenido'
                    except json.JSONDecodeError:
                        contenido = c[2]  # Si no es JSON válido, dejarlo como está

                    result.append({
                        "id": c[0],
                        "id_pedido": c[1],
                        "contenido": contenido,  # Agregar el contenido deserializado
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
    print("mensaje-cliente",mensaje_cliente)

    # Verificar si el usuario está registrado en la base de datos
    if not verificar_usuario_bd(numero_cliente):
        return manejar_registro(numero_cliente, mensaje_cliente)
    else:
        return manejar_mensajes_registrados(numero_cliente, mensaje_cliente)

if __name__ == "__main__":
    db_conn = conectar_bd()
    if db_conn:
        db_conn.close()
    app.run(debug=True, port=5000)

