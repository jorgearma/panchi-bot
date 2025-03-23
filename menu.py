import re
from unidecode import unidecode
from utils.es_pregunta import es_pregunta
from utils.crear_token import generar_enlace
from utils.mensajes import enviar_mensaje_whatsapp

menu = {
    "👇*Obciones*👇": {
        "tienda 🏪": {"codigo": 1, "mensaje": "Tienda online"},
        "Ayuda  🆘": {"codigo": 2, "mensaje": "para comunicarse un servicio al cliente, por favor llama al +45 49 99 48 76."},
        "Salir  🚪🚶🏻": {"codigo": 3, "mensaje": "Has elegido *Salir*. Si necesitas algo más, solo envíanos un mensaje."},
    }
}

# Función para limpiar el texto
def limpiar_texto(texto):
    texto_limpio = unidecode(texto)
    texto_limpio = re.sub(r'[^\w\s]', '', texto_limpio)
    return texto_limpio.lower()

# Función para mostrar el menú de obciones
def mostrar_menu():
    resultado = "\n\n"
    for categoria, items in menu.items():
        resultado += f"{categoria.capitalize()}\n\n"
        for item, detalles in items.items():
            codigo = detalles.get("codigo", "N/A")
            resultado += f" ▪️ *{codigo}* : {item.capitalize()}\n"
    return resultado

# Procesar el pedido y devolver una respuesta específica
def procesar_pedido(pedido, numero_cliente,id_usuario):
    """
    Procesa un pedido realizado por un cliente y genera una respuesta adecuada.
    Este método analiza el mensaje del cliente para determinar si contiene un 
    ítem delas opciones o un códi bciongo valida. , se devuelve un mensaje de error o respuesta 
    predeterminada. En caso de que el ítem requiera un enlace, se genera y guarda 
    un enlace único asociado al pedido.
    Args:
        pedido (str): El mensaje enviado por el cliente, que puede contener 
                      texto relacionado con una obcion del menú el codigo numerico.
        numero_cliente (str): El número de teléfono o identificador único del cliente.
    Returns:
        str: Una respuesta adecuada al pedido del cliente. Puede ser un mensaje 
             relacionado con el ítem del menú, un enlace único, o un mensaje de 
             error si no se reconoce la obcion.
    """
    from main import gestor_pedidos

    # # aqui en un futuro se puede agregar la logica de comprobar si el usuario
    # # hizo una pregunta o no, si la hace responder a la pregunta adecuadamente
    if es_pregunta(pedido): #pedido es el emnsaje del cliente 
        return "Lo siento, no reconocí tu pregunta." # de momento solo reponde esto
    
    id_usuario = id_usuario
    pedido_actual = None

    for intento in range(3):
        try:
            pedido_actual = gestor_pedidos.obtener_pedido_mas_reciente(id_usuario)
            break  # Si se ejecuta correctamente, salir del bucle
        except Exception as e:
            if intento < 2:  # Intentar nuevamente si no es el último intento
                continue
            else:
                # Manejar el error después de 3 intentos fallidos
                return f"Error al obtener el pedido más reciente: {str(e)}"

    pedido_limpio = limpiar_texto(pedido)
    id_pedido = pedido_actual.PedidoID

    for categoria, items in menu.items():
        for item, info in items.items():
            item_limpio = limpiar_texto(item)   
            codigo_producto = str(info["codigo"])
            
            if item_limpio in pedido_limpio or codigo_producto in pedido_limpio:
                mensaje_respuesta = info["mensaje"]
                
                # Generar un enlace solo si es una opción que lo requiere
                if mensaje_respuesta  == "Tienda online":
                    enlace = generar_enlace(numero_cliente, item)
                    gestor_pedidos.actualizar_estado(id_pedido, "enlace")
                    gestor_pedidos.guardar_enlace(id_pedido, enlace)
                    return f"❕ {mensaje_respuesta} ❕\n\n🔗 *Enlace único*: {enlace}"
                
                return mensaje_respuesta
    menu_comando_no_reconocido = mostrar_menu()
    return f"❌Comando no reconocido \n▪️ Por favor, elige una *opción*  {menu_comando_no_reconocido}\nEscribe el *Numero* correspondiente para elegir."

# Manejar el flujo de mensajes
def procesar_mensaje_como_pedido(mensaje_cliente, numero_cliente,id_usuario):
    
    respuesta_camarero = procesar_pedido(mensaje_cliente, numero_cliente,id_usuario)

   
    if "Error al obtener el pedido más reciente" in respuesta_camarero:
        enviar_mensaje_whatsapp("error interno intente nuevamente", numero_cliente)
    else:
        enviar_mensaje_whatsapp(f"{respuesta_camarero}", numero_cliente)
    
    return "Mensaje recibido", 200
