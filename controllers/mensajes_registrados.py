from utils.mensajes import enviar_mensaje_whatsapp
from menu import mostrar_menu, procesar_pedido, mostrar_carrito, mostrar_carrito_sin_mensaje
from pago import preguntar_metodo_pago, procesar_pago
from openai_api import obtener_respuesta_openai
from data.usuarios import  obtener_usuario_bd
from data.carrito import carrito , guardar_pedido
from data.estado_usuarios import estado_usuarios
from data.pedidos import enviar_comanda_a_cocina , verificar_pedido_activo


import random

# Diccionario para almacenar pedidos activos y sus identificadores
pedidos_activos = {}
def manejar_consulta_carrito(mensaje_cliente, numero_cliente):
    # Normaliza el mensaje para evitar problemas con mayúsculas/minúsculas
    mensaje_cliente = mensaje_cliente.lower()
    
    # Lista de palabras clave para identificar la consulta
    palabras_clave = ["revisar pedido", "ver carrito", "revisar", "carrito"]
    
    # Verifica si el mensaje coincide con las palabras clave
    if mensaje_cliente in palabras_clave:
        # Verifica si el cliente tiene un carrito activo
        if numero_cliente in carrito:
            # Obtiene el contenido del carrito
            contenido_carrito = mostrar_carrito(carrito[numero_cliente])
            # Envía el mensaje al cliente
            enviar_mensaje_whatsapp(contenido_carrito, numero_cliente)
        else:
            # Maneja el caso de un carrito vacío o inexistente
            enviar_mensaje_whatsapp("Tu carrito está vacío.", numero_cliente)
        return True
    
    # Retorna False si el mensaje no está relacionado con el carrito
    return False


def manejar_usuario(numero_cliente):
    if estado_usuarios.get(numero_cliente, {}).get("recien_registrado"):
        del estado_usuarios[numero_cliente]["recien_registrado"]
    else:
        if numero_cliente not in carrito:
            carrito[numero_cliente] = []
            menu_texto = mostrar_menu()
            nombre_usuario = obtener_usuario_bd(numero_cliente)["nombre"]
            enviar_mensaje_whatsapp(
                f"¡Hola {nombre_usuario}! 👋 Bienvenido de nuevo. {menu_texto}                ⬆️ *MENU* ⬆️ \n❗*Para agregar un producto*❗\n\nescribe el *numero* o su *nombre* \n\n      👇 *Ejemplos* 👇 \n\n ▪️ *clasica*    o    *301* \n ▪️ *helado*    o    *503* ", 
                numero_cliente
            )
            return "Mensaje enviado", 200


def manejar_mensajes_registrados(numero_cliente, mensaje_cliente):
    
    respuesta = verificar_pedido_activo(numero_cliente, mensaje_cliente, pedidos_activos)
    if respuesta:
        return respuesta

        
    respuesta_usuario = manejar_usuario(numero_cliente)
    if respuesta_usuario:
        return respuesta_usuario

     # Consultar el carrito
    if manejar_consulta_carrito(mensaje_cliente, numero_cliente):
        return "Mensaje enviado", 200

    # Salir o proceder al pago
    if mensaje_cliente in ["salir", "nada más", "eso es todo", "pagar"]:
        if not carrito[numero_cliente]:
            enviar_mensaje_whatsapp("No tienes ningún pedido. ¡Gracias y que tenga un buen día!", numero_cliente)
        else:
            total = mostrar_carrito_sin_mensaje(carrito[numero_cliente])
            enviar_mensaje_whatsapp(total, numero_cliente)
            preguntar_metodo_pago(numero_cliente, enviar_mensaje_whatsapp)
        return "Mensaje enviado", 200

    # Procesar el método de pago y asignar un identificador al pedido
    if mensaje_cliente in ["efectivo", "tarjeta"]:
        productos, total = mostrar_carrito(carrito[numero_cliente])
        procesar_pago(total, mensaje_cliente, numero_cliente, enviar_mensaje_whatsapp)
        
        # Generar un identificador de pedido de 4 dígitos
        id_pedido = random.randint(1000, 9999)
        
        # Guardar el pedido con el identificador en pedidos_activos
        pedidos_activos[numero_cliente] = {"id_pedido": id_pedido, "contenido": carrito[numero_cliente]}
        guardar_pedido(numero_cliente, carrito , id_pedido)
        contenido_pedido = carrito[numero_cliente]
        print(contenido_pedido)
        enviar_comanda_a_cocina(id_pedido, contenido_pedido)
        # Informar al cliente sobre el identificador del pedido
        enviar_mensaje_whatsapp(f"Su pedido está confirmado y en preparación. Su número de pedido es: {id_pedido}", numero_cliente)
        
        # Vaciar el carrito después de procesar el pedido
        carrito.pop(numero_cliente, None)
        return "Mensaje enviado", 200

    # Verificar si el mensaje es un número de 4 dígitos para el estado del pedido
    

    # Procesar el mensaje como un pedido
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
