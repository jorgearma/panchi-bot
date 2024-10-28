from utils.mensajes import enviar_mensaje_whatsapp
from menu import mostrar_menu, procesar_pedido, mostrar_carrito, mostrar_carrito_sin_mensaje
from pago import preguntar_metodo_pago, procesar_pago
from openai_api import obtener_respuesta_openai
from data.usuarios import usuarios_registrados
from data.carrito import carrito
from data.estado_usuarios import estado_usuarios

def manejar_mensajes_registrados(numero_cliente, mensaje_cliente):
    if estado_usuarios.get(numero_cliente, {}).get("recien_registrado"):
        del estado_usuarios[numero_cliente]["recien_registrado"]
    else:
        if numero_cliente not in carrito:
            carrito[numero_cliente] = []
            menu_texto = mostrar_menu()
            enviar_mensaje_whatsapp(f"¡Hola {usuarios_registrados[numero_cliente]['nombre']}! Bienvenido de nuevo. {menu_texto}", numero_cliente)
            return "Mensaje enviado", 200

    if mensaje_cliente in ["revisar pedido", "ver carrito", "revisar", "carrito"]:
        contenido_carrito = mostrar_carrito(carrito[numero_cliente])
        enviar_mensaje_whatsapp(contenido_carrito, numero_cliente)
        return "Mensaje enviado", 200

    if mensaje_cliente in ["salir", "nada más", "eso es todo", "pagar"]:
        if not carrito[numero_cliente]:
            enviar_mensaje_whatsapp("No tienes ningún pedido. ¡Gracias y que tenga un buen día!", numero_cliente)
        else:
            total = mostrar_carrito_sin_mensaje(carrito[numero_cliente])
            enviar_mensaje_whatsapp(total, numero_cliente)
            preguntar_metodo_pago(numero_cliente, enviar_mensaje_whatsapp)
        return "Mensaje enviado", 200

    if mensaje_cliente in ["efectivo", "tarjeta"]:
        productos, total = mostrar_carrito(carrito[numero_cliente])
        procesar_pago(total, mensaje_cliente, numero_cliente, enviar_mensaje_whatsapp)
        carrito.pop(numero_cliente, None)
        return "Mensaje enviado", 200

    respuesta_camarero = procesar_pedido(mensaje_cliente, carrito[numero_cliente])
    if "no reconocí ningún ítem" in respuesta_camarero:
        respuesta_openai = obtener_respuesta_openai(mensaje_cliente, carrito[numero_cliente])
        enviar_mensaje_whatsapp(f"Camarero: {respuesta_openai}", numero_cliente)
    else:
        enviar_mensaje_whatsapp(f"Camarero: {respuesta_camarero}", numero_cliente)
        if "Has agregado" in respuesta_camarero:
            contenido_carrito = mostrar_carrito(carrito[numero_cliente])
            enviar_mensaje_whatsapp(contenido_carrito, numero_cliente)

    return "Mensaje recibido", 200
