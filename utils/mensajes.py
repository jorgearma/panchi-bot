import os
from dotenv import load_dotenv
from twilio.rest import Client

# Cargar las variables de entorno desde el archivo .env
load_dotenv()
# Cargar las variables de entorno desde el archivo .env
TWILIO_ACCOUNT_SID="ACcf3a4c00f07e58a807637992f3d825d5"
TWILIO_AUTH_TOKEN="46e9f9eed87abb29c4eaeeef0851e108"
TWILIO_PHONE_NUMBER="whatsapp:+14155238886" 



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


