from twilio.rest import Client
from flask import Flask, request
import urllib.parse  # Para codificar la dirección en una URL

# Importa tus funciones personalizadas
from menu import mostrar_menu, procesar_pedido, mostrar_carrito
from openai_api import obtener_respuesta_openai
from pago import preguntar_metodo_pago, procesar_pago

# Simulamos una "base de datos" de usuarios registrados.
usuarios_registrados = {
    "123": {"nombre": "Juan", "numero": "123", "direccion": "Calle Falsa 123"},
    # Puedes agregar más usuarios registrados aquí.
}

app = Flask(__name__)
carrito = {}

# Credenciales de Twilio (reemplaza con tus credenciales)
TWILIO_ACCOUNT_SID = 'AC01bddb839117c02af0a1fe2ade2e1d4e'
TWILIO_AUTH_TOKEN = '6817bfa1828c017d726821d6f6934f2a'
TWILIO_PHONE_NUMBER = 'whatsapp:+14155238886'  # Reemplaza con el número de WhatsApp de Twilio

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
destinatario = '+4531822092'
def enviar_mensaje_whatsapp(mensaje, destinatario):
    client.messages.create(
        body=mensaje,
        from_=TWILIO_PHONE_NUMBER,
        to=f'whatsapp:+4531822092'
    )



@app.route('/webhook', methods=['POST'])
def webhook():
    numero_cliente = request.form['From']
    mensaje_cliente = request.form['Body']

    print(f"Mensaje recibido de {numero_cliente}: {mensaje_cliente}") 
    
    # Identificamos al usuario por su número de WhatsApp
    if numero_cliente not in carrito:
        carrito[numero_cliente] = []
    
    if mensaje_cliente.lower() in ["revisar pedido", "ver carrito", "revisar", "carrito"]:
        contenido_carrito = mostrar_carrito(carrito[numero_cliente])
        enviar_mensaje_whatsapp(contenido_carrito, numero_cliente)
        return "Mensaje enviado", 200
    
    if mensaje_cliente.lower() in ["salir", "nada más", "eso es todo", "pagar"]:
        if not carrito[numero_cliente]:
            enviar_mensaje_whatsapp("No tienes ningún pedido. ¡Gracias y que tenga un buen día!", numero_cliente)
        else:
            total = mostrar_carrito(carrito[numero_cliente])
            confirmar = enviar_mensaje_whatsapp("\n¿Te gustaría proceder al pago? (sí/no):", numero_cliente)
            if confirmar.lower() == "si":
                metodo_pago = preguntar_metodo_pago()
                procesar_pago(total, metodo_pago)
                enviar_mensaje_whatsapp("Pago realizado con éxito. ¡Gracias por tu compra!", numero_cliente)
            else:
                enviar_mensaje_whatsapp("Pedido cancelado. ¡Que tenga un buen día!", numero_cliente)
        carrito.pop(numero_cliente, None)
        return "Mensaje enviado", 200

    # Procesa el pedido
    respuesta_camarero = procesar_pedido(mensaje_cliente, carrito[numero_cliente])
    
    if "no reconocí ningún ítem" in respuesta_camarero:
        # Si no se reconoció un ítem, se asume que el cliente hizo una pregunta
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