# menu.py

import re
from unidecode import unidecode
from utils.es_pregunta import es_pregunta

menu = {
    "🍔 *HAMBURGuESAS*": {
        "clasica": {"precio": 5.00, "codigo": 301},
        "ranchera": {"precio": 5.50, "codigo": 302},
        "crispy": {"precio": 6.00, "codigo": 303}
    },
    "🌭 *PERRITOS*": {
        "clasico": {"precio": 4.00, "codigo": 401},
        "picanton": {"precio": 4.00, "codigo": 402},
        "texano": {"precio": 4.00, "codigo": 403},
        "bbq": {"precio": 4.00, "codigo": 404}
    },
    "🍨 *POSTRES*": {
        "flan": {"precio": 4.00, "codigo": 501},
        "tarta": {"precio": 5.00, "codigo": 502},
        "helado": {"precio": 3.50, "codigo": 503}
    },
    "🥤 *BEBIDAS*": {
        "agua": {"precio": 1.50, "codigo": 601},
        "vino": {"precio": 4.00, "codigo": 602},
        "cerveza": {"precio": 3.00, "codigo": 603},
        "refresco": {"precio": 2.50, "codigo": 604},
        "café": {"precio": 2.00, "codigo": 605}
    }
}

# Función para limpiar el texto
def limpiar_texto(texto):
    texto_limpio = unidecode(texto)
    texto_limpio = re.sub(r'[^\w\s]', '', texto_limpio)
    return texto_limpio.lower()

# Función para mostrar el menú con precios
def mostrar_menu():
    resultado = " Aquí tienes el menú del restaurante:\n\n"
    for categoria, items in menu.items():
        resultado += f"{categoria.capitalize()}:\n"
        for item, detalles in items.items():
            item_limpio = limpiar_texto(item)
            
            # Poner el nombre del producto en negrita
            item_negrita = f"*{item_limpio.capitalize()}*"
            
            # Obtener el código y el precio desde el diccionario de detalles
            codigo = detalles.get("codigo", "N/A")
            precio = detalles.get("precio", 0.0)
            
            
            resultado += f" ▪️ *{codigo}* : {item_negrita} - €{precio:.2f}\n"
            
            
        resultado += "\n"
    return resultado



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
            precio = info["precio"]
            
            # Verifica si el nombre o el código están en el pedido
            if item_limpio in pedido_limpio or codigo_producto in pedido_limpio:
                carrito.append((item, precio))
                items_agregados.append(f"{item} por €{precio:.2f}")
    
    if items_agregados:
        return f"📌 Has agregado 📌 *{', '.join(items_agregados)}*"
    else:
        return "Lo siento, no reconocí ningún ítem de nuestro menú en tu pedido. Por favor elige algo de lo que ofrecemos."

# Función para mostrar el carrito y calcular el total

