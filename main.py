from flask import Flask, request , jsonify ,render_template
from controllers.registro_de_usuarios.registro import manejar_registro
from controllers.mensajes_registrados import manejar_mensajes_registrados
from data.usuarios import guardar_usuario_bd , verificar_usuario_bd
from data.carrito import carrito_instancia
from data.estado_usuarios import estado_usuarios
from utils.text_utils import limpiar_texto
from database import conectar_bd
import json
from flask_cors import CORS 


from data.usuarios import GestorUsuariosBD , Usuario

app = Flask(__name__)

CORS(app, resources={r"/api/*": {"origins": ["http://127.0.0.1:5500", "http://localhost:5000"]}})
  # Permite solo este origen

@app.route('/api/usuario/<numero_cliente>', methods=['GET'])
def obtener_usuario(numero_cliente):
    datos = GestorUsuariosBD.obtener_usuario(numero_cliente)  # Usa el método existente
    if datos is None:
        return jsonify({"error": "Usuario no encontrado"}), 404
    
    # Crear una instancia de Usuario
    usuario = Usuario(datos['nombre'], datos['numero'], datos['direccion'])
    return jsonify(usuario.to_dict()), 200


@app.route('/api/agregar_pedido', methods=['OPTIONS', 'POST'])
def agregar_pedido():
    if request.method == 'OPTIONS':
        # Respuesta al preflight
        response = app.make_response('')
        response.headers.add("Access-Control-Allow-Origin", "http://localhost:5000")  # Ajusta al origen correcto
        response.headers.add("Access-Control-Allow-Methods", "POST, OPTIONS")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        return response, 200  # HTTP 200 es requerido aquí

    if request.method == 'POST':
        data = request.json
        print(data)  # Verifica el JSON recibido

        for numero_whatsapp, productos in data.items():
            carrito_instancia.agregar_productos(numero_whatsapp, productos)

        response = jsonify({"message": "Pedido recibido correctamente"})
        response.headers.add("Access-Control-Allow-Origin", "http://localhost:5000")  # Ajusta al origen correcto
        return response, 200


@app.route('/quiniela/<numero_cliente>', methods=['GET'])
def quiniela(numero_cliente):
    # Obtener los datos del usuario utilizando el método GestorUsuariosBD.obtener_usuario
    datos = GestorUsuariosBD.obtener_usuario(numero_cliente)
    
    if datos is None:
        return jsonify({"error": "Usuario no encontrado"}), 404

    # Crear una instancia de Usuario
    usuario = Usuario(datos['nombre'], datos['numero'], datos['direccion'])
    
    # Renderizar una plantilla personalizada para el cliente, pasando los datos del usuario
    return render_template('quiniela.html', usuario=usuario)


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

