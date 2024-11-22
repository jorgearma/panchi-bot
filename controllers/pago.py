from data.carrito import carrito_instancia, mostrar_carrito_sin_mensaje, mostrar_carrito 
from utils.mensajes import enviar_mensaje_whatsapp
from data.pedidos import  enviar_comanda_a_cocina ,guardar_pedido , pedido 
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
        
        if not carrito_instancia.verificar_carrito(numero_cliente):
            enviar_mensaje_whatsapp("No tienes ningún pedido. ¡Gracias y que tenga un buen día!", numero_cliente)
        else:
            carrito_cliente1 = carrito_instancia.obtener_carrito_cliente(numero_cliente)
            total = mostrar_carrito_sin_mensaje(carrito_cliente1)
            enviar_mensaje_whatsapp(total, numero_cliente)
            preguntar_metodo_pago(numero_cliente, enviar_mensaje_whatsapp)
        return True
    return False



def procesar_metodo_pago(mensaje_cliente, numero_cliente ):
    if mensaje_cliente in ["efectivo", "tarjeta"]:
        # Crear una instancia de Pedido
        pedido1 = pedido(numero_cliente, mensaje_cliente)

        # Mostrar el carrito y calcular el total
        productos, total = mostrar_carrito(pedido1.contenido_pedido)

        # Realizar operaciones relacionadas con el pago (por ejemplo, generar mensaje de confirmación)
        procesar_pago(total, mensaje_cliente, numero_cliente, enviar_mensaje_whatsapp)

        # Guardar el pedido en pedidos activos
        pedidos_activos[numero_cliente] = {
            "id_pedido": pedido1.id_pedido,
            "contenido": pedido1.contenido_pedido
        }

        # Guardar el pedido en la base de datos
        guardar_pedido(numero_cliente, pedido1.contenido_pedido, pedido1.id_pedido)

        # Enviar la comanda a la cocina
        pedido1.enviar_comanda_a_cocina()

        # Confirmar el pedido al cliente
        enviar_mensaje_whatsapp(
            f"Su pedido está confirmado y en preparación. Su número de pedido es: {pedido1.id_pedido}",
            numero_cliente
        )

        # Eliminar el carrito del cliente
        carrito_instancia.eliminar_carrito(numero_cliente)

        return True

    return False
    