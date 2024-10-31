from twilio.rest import Client

TWILIO_ACCOUNT_SID = 'AC01bddb839117c02af0a1fe2ade2e1d4e'
TWILIO_AUTH_TOKEN = '6817bfa1828c017d726821d6f6934f2a'
TWILIO_PHONE_NUMBER = 'whatsapp:+14155238886'

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

def enviar_mensaje_whatsapp(mensaje, destinatario):
    print(f"Bot: {mensaje}")
    client.messages.create(
        body=mensaje,
        from_=TWILIO_PHONE_NUMBER,
        to=destinatario
    )
