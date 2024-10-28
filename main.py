from flask import Flask, request
from controllers.registro import manejar_registro
from controllers.mensajes_registrados import manejar_mensajes_registrados
from data.usuarios import usuarios_registrados
from data.carrito import carrito
from data.estado_usuarios import estado_usuarios

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    numero_cliente = request.form['From']
    mensaje_cliente = request.form['Body'].strip().lower()

    if numero_cliente not in usuarios_registrados:
        return manejar_registro(numero_cliente, mensaje_cliente)
    else:
        return manejar_mensajes_registrados(numero_cliente, mensaje_cliente)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
