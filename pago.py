# archivo: pago.py

def preguntar_metodo_pago(numero_cliente, enviar_mensaje_whatsapp):
    """
    Pregunta al cliente si pagará en efectivo o con tarjeta a través de WhatsApp.
    
    Esta función no espera respuesta, solo envía el mensaje. 
    La respuesta será manejada en el webhook del archivo principal.
    """
    mensaje = "¿Te gustaría pagar en efectivo o con tarjeta? (responde 'efectivo' o 'tarjeta')"
    enviar_mensaje_whatsapp(mensaje, numero_cliente)

def procesar_pago(total, metodo_pago, numero_cliente, enviar_mensaje_whatsapp):
    """
    Procesa el pago según el método seleccionado y envía la confirmación por WhatsApp.
    
    Este es un procesamiento simulado para el pago en efectivo o tarjeta.
    """
    if metodo_pago == 'efectivo':
        mensaje_pago = f"El total es de ${total:.2f}. El pago se realizará en efectivo al momento de la entrega."
    elif metodo_pago == 'tarjeta':
        # Aquí podrías agregar más lógica si fuera necesario para simular el procesamiento de tarjetas.
        mensaje_pago = f"El total es de ${total:.2f}. El pago se procesará mediante tarjeta en el momento de la entrega."
    else:
        mensaje_pago = "Método de pago no reconocido."

    # Enviar el mensaje con la información del pago al cliente
    enviar_mensaje_whatsapp(mensaje_pago, numero_cliente)

    # Confirmar al cliente que su pedido ha sido registrado correctamente
    enviar_mensaje_whatsapp("Tu pedido ha sido registrado con éxito. ¡Gracias por tu compra!\n", numero_cliente)
