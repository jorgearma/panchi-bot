
from flask import  request , blueprint

from controllers.registro_de_usuarios.registro import manejar_registro
from controllers.mensajes_registrados import manejar_mensajes_registrados

from utils.text_utils import limpiar_texto
from database import  db_session

from utils.crear_token import  generar_token_y_guardar_cliente


webhook = blueprint('webhook', __name__)

@webhook.route('/webhook', methods=['POST'])
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
