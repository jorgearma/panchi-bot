# archivo: pago.py

def preguntar_metodo_pago():
    """
    Pregunta al cliente si pagará en efectivo o con tarjeta.
    """
    while True:
        metodo_pago = input("¿Te gustaría pagar en efectivo o con tarjeta? (escribe 'efectivo' o 'tarjeta'): ").strip().lower()
        
        if metodo_pago in ['efectivo', 'tarjeta']:
            return metodo_pago
        else:
            print("Opción no válida. Por favor, elige 'efectivo' o 'tarjeta'.")

def procesar_pago(total, metodo_pago):
    """
    Confirma el pago según el método seleccionado por el cliente.
    """
    if metodo_pago == 'efectivo':
        print(f"El total es de ${total:.2f}. El pago se realizará en efectivo al momento de la entrega.")
    elif metodo_pago == 'tarjeta':
        # Simulación de cobro con tarjeta (puedes expandir esto si quisieras agregar más lógica)
        print(f"El total es de ${total:.2f}. El pago se procesará mediante tarjeta en el momento de la entrega.")
    else:
        print("Método de pago no reconocido.")
    
    print("Tu pedido ha sido registrado con éxito. ¡Gracias por tu compra!\n")

# Puedes añadir funciones adicionales para mejorar el proceso de pago, si es necesario.
