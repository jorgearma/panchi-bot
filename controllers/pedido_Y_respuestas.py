from openai_api import obtener_respuesta_openai
from menu import mostrar_menu, procesar_pedido
from utils.mensajes import enviar_mensaje_whatsapp
from data.carrito import carrito, mostrar_carrito

def procesar_mensaje_como_pedido(mensaje_cliente, numero_cliente):
    respuesta_camarero = procesar_pedido(mensaje_cliente, carrito[numero_cliente])
    if "no reconocí ningún ítem" in respuesta_camarero:
        respuesta_openai = obtener_respuesta_openai(mensaje_cliente, carrito[numero_cliente])
        enviar_mensaje_whatsapp(f"{respuesta_openai}", numero_cliente)
    else:
        enviar_mensaje_whatsapp(f"{respuesta_camarero}", numero_cliente)
        if "Has agregado" in respuesta_camarero:
            contenido_carrito = mostrar_carrito(carrito[numero_cliente])
            enviar_mensaje_whatsapp(contenido_carrito, numero_cliente)
            print(carrito)
    return "Mensaje recibido", 200   