import re
from unidecode import unidecode
from utils.es_pregunta import es_pregunta
from utils.crear_token import generar_enlace
from utils.mensajes import enviar_mensaje_whatsapp
from modelos.validator_twilio import PedidoInput
from pydantic import ValidationError
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



from pydantic import ValidationError

def procesar_pedido(pedido, numero_cliente, id_pedido_actual, usuario_datos):
    """
    Procesa un pedido realizado por un cliente y genera una respuesta adecuada.
    """
    try:
        # Validar los datos de entrada con Pydantic
        datos = PedidoInput(pedido=pedido, numero_cliente=numero_cliente, id_pedido_actual=id_pedido_actual)
        print(f"Datos validados: {datos}")
            
    except ValidationError as e:
        # Retornar errores de validación como respuesta
        return f"❌ Error en los datos de entrada:\n{e}"

    # Si los datos son válidos, continuar con el procesamiento
    from main import gestor_pedidos

    if es_pregunta(datos.pedido):
        return "Lo siento, no reconocí tu pregunta."

    pedido_limpio = limpiar_texto(datos.pedido)

    for categoria, items in menu.items():
        for item, info in items.items():
            item_limpio = limpiar_texto(item)
            codigo_producto = str(info["codigo"])

            if item_limpio in pedido_limpio or codigo_producto in pedido_limpio:
                mensaje_respuesta = info["mensaje"]

                if mensaje_respuesta == "Tienda online":
                    try:
                        enlace = generar_enlace( item , usuario_datos)
                        actualizado = gestor_pedidos.actualizar_estado(datos.id_pedido_actual, "enlace")
                        guardado = gestor_pedidos.guardar_enlace(datos.id_pedido_actual, enlace)

                        if actualizado and guardado:
                            return f"❕ {mensaje_respuesta} ❕\n\n🔗 *Enlace único*: {enlace}"
                        else:
                            gestor_pedidos.actualizar_estado(datos.id_pedido_actual, "Pendiente")
                            return "❌ Ocurrió un error al procesar la opción. Intente nuevamente."

                    except Exception as e:
                        print(f"Error al generar el enlace: {e}")
                        return "❌ Error inesperado. Intente nuevamente."
                return mensaje_respuesta

    menu_comando_no_reconocido = mostrar_menu()
    return f"❌Comando no reconocido \n▪️ Por favor, elige una *opción*  {menu_comando_no_reconocido}\nEscribe el *Número* correspondiente para elegir."