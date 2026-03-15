import os
from dotenv import load_dotenv
from twilio.rest import Client

from managers.gestor_redis import redismanager

load_dotenv()

TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER')




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


