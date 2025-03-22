import os
from dotenv import load_dotenv
from twilio.rest import Client

# Cargar las variables de entorno desde el archivo .env
load_dotenv()
# Cargar las variables de entorno desde el archivo .env




# Inicializar el cliente de Twilio
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

print(client)

def enviar_mensaje_whatsapp(mensaje, destinatario):
    print(f"Bot: {mensaje}")
    client.messages.create(
        body=mensaje,
        from_=TWILIO_PHONE_NUMBER,
        to=destinatario
    )


