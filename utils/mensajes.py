from twilio.rest import Client

TWILIO_ACCOUNT_SID = 'AC35793b91ca234f34f3daaac4be84995a'
TWILIO_AUTH_TOKEN = '8048ecfc0534ea05c137aed2a7d72a47'
TWILIO_PHONE_NUMBER = 'whatsapp:+14155238886'

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

def enviar_mensaje_whatsapp(mensaje, destinatario):
    print(f"Bot: {mensaje}")
    client.messages.create(
        body=mensaje,
        from_=TWILIO_PHONE_NUMBER,
        to=destinatario
    )
