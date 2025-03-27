import os
from dotenv import load_dotenv
from twilio.rest import Client

from managers.gestor_redis import redismanager

# Cargar las variables de entorno desde el archivo .env
load_dotenv()
# Cargar las variables de entorno desde el archivo .env
TWILIO_ACCOUNT_SID="AC9b625f02fcadb3c93f7845811210bc55"
TWILIO_AUTH_TOKEN="cafdac3315be16080bb236071d3309d8"
TWILIO_PHONE_NUMBER="whatsapp:+14155238886" 




# Inicializar el cliente de Twilio
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


print(client)

def enviar_mensaje_whatsapp(mensaje, destinatario):
    
    client.messages.create(
        body=mensaje,
        from_=TWILIO_PHONE_NUMBER,
        to=destinatario
    )
    
    #redismanager.desbloquear_usuario(destinatario)
    redismanager.desbloquear_usuario(destinatario)
    print(f"Mensaje enviado a {destinatario}: {mensaje}")


