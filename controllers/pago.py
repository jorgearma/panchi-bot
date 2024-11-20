from data.carrito import carrito, mostrar_carrito_sin_mensaje ,mostrar_carrito 
from utils.mensajes import enviar_mensaje_whatsapp
from data.pedidos import  enviar_comanda_a_cocina ,guardar_pedido
import random
from data.pedidos_activos import pedidos_activos

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


def salir_o_proceder_al_pago(mensaje_cliente, numero_cliente):
    if mensaje_cliente in ["salir", "nada más", "eso es todo", "pagar"]:
        if not carrito[numero_cliente]:
            enviar_mensaje_whatsapp("No tienes ningún pedido. ¡Gracias y que tenga un buen día!", numero_cliente)
        else:
            total = mostrar_carrito_sin_mensaje(carrito[numero_cliente])
            enviar_mensaje_whatsapp(total, numero_cliente)
            preguntar_metodo_pago(numero_cliente, enviar_mensaje_whatsapp)
        return True
    return False



def procesar_metodo_pago(mensaje_cliente, numero_cliente):
    
    if mensaje_cliente in ["efectivo", "tarjeta"]:
        productos, total = mostrar_carrito(carrito[numero_cliente])
        procesar_pago(total, mensaje_cliente, numero_cliente, enviar_mensaje_whatsapp)
        
        id_pedido = random.randint(1000, 9999)
        pedidos_activos[numero_cliente] = {"id_pedido": id_pedido, "contenido": carrito[numero_cliente]}
        guardar_pedido(numero_cliente, carrito, id_pedido)
        contenido_pedido = carrito[numero_cliente]
        print(contenido_pedido)
        enviar_comanda_a_cocina(id_pedido, contenido_pedido)
        enviar_mensaje_whatsapp(f"Su pedido está confirmado y en preparación. Su número de pedido es: {id_pedido}", numero_cliente)
        
        carrito.pop(numero_cliente, None)
        return True
    return False    