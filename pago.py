# archivo: pago.py

def preguntar_metodo_pago(numero_cliente, enviar_mensaje_whatsapp):
    
    mensaje = "🔷¿como te gustaria pagar?🔷\n           👇 Escribe 👇 \n\n▪️ *Efectivo*  O   *Tarjeta* ▪️"
    enviar_mensaje_whatsapp(mensaje, numero_cliente)

def procesar_pago(total, metodo_pago, numero_cliente, enviar_mensaje_whatsapp):
   
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
