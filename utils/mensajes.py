from twilio.rest import Client

TWILIO_ACCOUNT_SID = '***REMOVED***'
TWILIO_AUTH_TOKEN = '***REMOVED***'
TWILIO_PHONE_NUMBER = 'whatsapp:+14155238886'

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

def enviar_mensaje_whatsapp(mensaje, destinatario):
    print(f"Bot: {mensaje}")
    client.messages.create(
        body=mensaje,
        from_=TWILIO_PHONE_NUMBER,
        to=destinatario
    )


