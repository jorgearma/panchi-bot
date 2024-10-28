from twilio.rest import Client
from flask import Flask, request
import urllib.parse

from menu import mostrar_menu, procesar_pedido, mostrar_carrito, mostrar_carrito_sin_mensaje
from openai_api import obtener_respuesta_openai
from pago import preguntar_metodo_pago, procesar_pago

usuarios_registrados = {
    "whatsapp:+453182209": {"nombre": "pendejo", "numero": "whatsapp:+4531822092", "direccion": "Calle Falsa 123"},
}

app = Flask(__name__)
carrito = {}
estado_usuarios = {}

TWILIO_ACCOUNT_SID = 'AC01bddb839117c02af0a1fe2ade2e1d4e'
TWILIO_AUTH_TOKEN = '6817bfa1828c017d726821d6f6934f2a'
TWILIO_PHONE_NUMBER = 'whatsapp:+14155238886'

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

def enviar_mensaje_whatsapp(mensaje, destinatario):

    print(f"bot {mensaje}")
    client.messages.create(
        body=mensaje,
        from_=TWILIO_PHONE_NUMBER,
        to=f'{destinatario}'
    )

def generar_enlace_google_maps(direccion):
    direccion_codificada = urllib.parse.quote(direccion)
    url = f"https://www.google.com/maps/place/{direccion_codificada},+16400+Taranc%C3%B3n,+Cuenca,+Espa%C3%B1a/"
    return url

def registrar_usuario(numero, nombre, direccion):
    usuarios_registrados[numero] = {
        "nombre": nombre,
        "numero": numero,
        "direccion": direccion
    }
    return usuarios_registrados[numero]

@app.route('/webhook', methods=['POST'])
def webhook():
    numero_cliente = request.form['From']
    mensaje_cliente = request.form['Body'].strip().lower()

    print(f"Mensaje recibido de {numero_cliente}: {mensaje_cliente}")
    
    print(carrito)
    print(usuarios_registrados)

    if numero_cliente not in usuarios_registrados:
        return manejar_registro(numero_cliente, mensaje_cliente)
    else:
        return manejar_mensajes_registrados(numero_cliente, mensaje_cliente)

def manejar_registro(numero_cliente, mensaje_cliente):
    estado = estado_usuarios.get(numero_cliente, {"estado": "saludo_inicial"})

    if estado["estado"] == "saludo_inicial":
        enviar_mensaje_whatsapp("Hola! No estás registrado en nuestro sistema. Vamos a proceder con tu registro.", numero_cliente)
        estado_usuarios[numero_cliente] = {"estado": "esperando_nombre"}
        enviar_mensaje_whatsapp("Por favor, envía tu nombre para continuar.", numero_cliente)
        return "Saludo enviado y solicitud de nombre", 200

    elif estado["estado"] == "esperando_nombre":
        estado_usuarios[numero_cliente] = {"estado": "esperando_direccion", "nombre": mensaje_cliente}
        enviar_mensaje_whatsapp("Gracias. Ahora, por favor envía tu dirección. EJEMPLO: calle los labradores 3 1b", numero_cliente)
        return "Solicitud de dirección enviada", 200

    elif estado["estado"] == "esperando_direccion":
        estado["direccion"] = mensaje_cliente
        estado["estado"] = "confirmando_direccion"
        enlace_maps = generar_enlace_google_maps(mensaje_cliente)
        enviar_mensaje_whatsapp(f"Aquí tienes un enlace de Google Maps con la ubicación de tu calle: {enlace_maps}", numero_cliente)
        enviar_mensaje_whatsapp("si tu direccion es esta  responde si para confirmar", numero_cliente)
        return "Solicitud de confirmación de dirección enviada", 200

    elif estado["estado"] == "confirmando_direccion":
        if mensaje_cliente == 'si':
            registrar_usuario(numero_cliente, estado["nombre"], estado["direccion"])
            menu_despues_registro = mostrar_menu()
            enviar_mensaje_whatsapp(f"¡Gracias {estado['nombre']}! Ahora estás registrado. {menu_despues_registro}", numero_cliente)
            estado_usuarios[numero_cliente] = {"recien_registrado": True}
            carrito[numero_cliente] = []
            return "Usuario registrado", 200
        else:
            estado_usuarios[numero_cliente]["estado"] = "esperando_direccion"
            enviar_mensaje_whatsapp("Vamos a intentar de nuevo. Por favor envía tu dirección.", numero_cliente)
            return "Solicitud de dirección enviada de nuevo", 200

def manejar_mensajes_registrados(numero_cliente, mensaje_cliente):
    # Verificar si el usuario recién se registró
    if estado_usuarios.get(numero_cliente, {}).get("recien_registrado"):
        # Eliminar el indicador para futuras interacciones
        del estado_usuarios[numero_cliente]["recien_registrado"]
    else:
        # Envía el menú solo si el usuario no es recién registrado
        if numero_cliente not in carrito:
            carrito[numero_cliente] = []
            menu_texto = mostrar_menu()
            enviar_mensaje_whatsapp(f"¡Hola {usuarios_registrados[numero_cliente]['nombre']}! Bienvenido de nuevo. {menu_texto}", numero_cliente)
            return "Mensaje enviado", 200

    if mensaje_cliente in ["revisar pedido", "ver carrito", "revisar", "carrito"]:
        contenido_carrito = mostrar_carrito(carrito[numero_cliente])
        enviar_mensaje_whatsapp(contenido_carrito, numero_cliente)
        return "Mensaje enviado", 200

    if mensaje_cliente in ["salir", "nada más", "eso es todo", "pagar"]:
        if not carrito[numero_cliente]:
            enviar_mensaje_whatsapp("No tienes ningún pedido. ¡Gracias y que tenga un buen día!", numero_cliente)
        else:
            total = mostrar_carrito_sin_mensaje(carrito[numero_cliente])
            enviar_mensaje_whatsapp(total, numero_cliente)
            preguntar_metodo_pago(numero_cliente, enviar_mensaje_whatsapp)
            return "Mensaje enviado", 200

    if mensaje_cliente in ["efectivo", "tarjeta"]:
        productos, total = mostrar_carrito(carrito[numero_cliente])
        procesar_pago(total, mensaje_cliente, numero_cliente, enviar_mensaje_whatsapp)
        carrito.pop(numero_cliente, None)
        return "Mensaje enviado", 200

    respuesta_camarero = procesar_pedido(mensaje_cliente, carrito[numero_cliente])
    if "no reconocí ningún ítem" in respuesta_camarero:
        respuesta_openai = obtener_respuesta_openai(mensaje_cliente, carrito[numero_cliente])
        enviar_mensaje_whatsapp(f"Camarero: {respuesta_openai}", numero_cliente)
    else:
        enviar_mensaje_whatsapp(f"Camarero: {respuesta_camarero}", numero_cliente)
        if "Has agregado" in respuesta_camarero:
            contenido_carrito = mostrar_carrito(carrito[numero_cliente])
            enviar_mensaje_whatsapp(contenido_carrito, numero_cliente)

    return "Mensaje recibido", 200

if __name__ == "__main__":
    app.run(debug=True, port=5000)
