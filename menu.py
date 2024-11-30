# menu.py

import re
from unidecode import unidecode
from utils.es_pregunta import es_pregunta

menu = {
    "👇 *Restaurantes*👇": {
        "italiano": {"codigo": 1},
        "mexicano": {"codigo": 2},
        "japonés": {"codigo": 3},
       
    }
}

# Función para limpiar el texto
def limpiar_texto(texto):
    texto_limpio = unidecode(texto)
    texto_limpio = re.sub(r'[^\w\s]', '', texto_limpio)
    return texto_limpio.lower()

# Función para mostrar el menú de restaurantes
def mostrar_menu():
    resultado = "\n\n"
    for categoria, items in menu.items():
        resultado += f"{categoria.capitalize()}\n\n"
        for item, detalles in items.items():
            # Obtener el código desde el diccionario de detalles
            codigo = detalles.get("codigo", "N/A")
            
            resultado += f" ▪️ *{codigo}* : {item.capitalize()}\n"
            
    return resultado

# Llamada a la función para mostrar el menú




# Función para procesar el pedido del cliente
def procesar_pedido(pedido, carrito):
    pregunta = es_pregunta(pedido)

    if pregunta:
        return  "Lo siento, no reconocí ningún ítem de nuestro menú en"
    pedido_limpio = limpiar_texto(pedido)
    items_agregados = []
    
    for categoria, items in menu.items():
        for item, info in items.items():
            item_limpio = limpiar_texto(item)
            codigo_producto = str(info["codigo"])
            
            
            # Verifica si el nombre o el código están en el pedido
            if item_limpio in pedido_limpio or codigo_producto in pedido_limpio:
                
                items_agregados.append(f"{item}")
    
    if items_agregados:
        return f" elegiste 📌 *{', '.join(items_agregados)}*📌"
    else:
        return "Lo siento, no reconocí ningún ítem de nuestro menú en tu pedido. Por favor elige algo de lo que ofrecemos."

# Función para mostrar el carrito y calcular el total

