from openai_api import obtener_respuesta_openai
from menu import mostrar_menu, procesar_pedido
from utils.mensajes import enviar_mensaje_whatsapp
from data.carrito import  mostrar_carrito , carrito_instancia

def procesar_mensaje_como_pedido(mensaje_cliente, numero_cliente):
    carrito_cliente = carrito_instancia.carrito[numero_cliente]

    respuesta_camarero = procesar_pedido(mensaje_cliente, carrito_cliente , numero_cliente)
    
    if "no reconocí ningún ítem" in respuesta_camarero:
        respuesta_openai = "comando no reconosido"  #obtener_respuesta_openai(mensaje_cliente, carrito_cliente)
        enviar_mensaje_whatsapp(f"{respuesta_openai}", numero_cliente)
    else:
        enviar_mensaje_whatsapp(f"{respuesta_camarero}", numero_cliente)
        if "Has agregado" in respuesta_camarero:
            contenido_carrito = mostrar_carrito(carrito_cliente)
            enviar_mensaje_whatsapp(contenido_carrito, numero_cliente)
            
    return "Mensaje recibido", 200   