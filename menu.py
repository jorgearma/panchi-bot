# menu.py

import re
from unidecode import unidecode

menu = {
    "entradas": {
        "ensalada mixta": {"precio": 5.00, "codigo": 301},
        "sopa de tomate": {"precio": 4.50, "codigo": 302},
        "gazpacho": {"precio": 6.00, "codigo": 303}
    },
    "platos principales": {
        "pollo asado": {"precio": 12.00, "codigo": 401},
        "paella": {"precio": 15.00, "codigo": 402},
        "pasta carbonara": {"precio": 11.00, "codigo": 403},
        "bistec a la parrilla": {"precio": 18.00, "codigo": 404}
    },
    "postres": {
        "flan": {"precio": 4.00, "codigo": 501},
        "tarta de queso": {"precio": 5.00, "codigo": 502},
        "helado de chocolate": {"precio": 3.50, "codigo": 503}
    },
    "bebidas": {
        "agua": {"precio": 1.50, "codigo": 601},
        "vino tinto": {"precio": 4.00, "codigo": 602},
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
    resultado = "Aquí tienes el menú del restaurante:\n\n"
    for categoria, items in menu.items():
        resultado += f"{categoria.capitalize()}:\n"
        for item, precio in items.items():
            item_limpio = limpiar_texto(item)
            resultado += f" - {item_limpio}: ${precio:.2f}\n"
        resultado += "\n"
    return resultado

# Función para procesar el pedido del cliente
def procesar_pedido(pedido, carrito):
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
                items_agregados.append(f"{item} por ${precio:.2f}")
    
    if items_agregados:
        return f"¡Perfecto! Has agregado: {', '.join(items_agregados)}."
    else:
        return "Lo siento, no reconocí ningún ítem de nuestro menú en tu pedido. Por favor elige algo de lo que ofrecemos."

# Función para mostrar el carrito y calcular el total
def mostrar_carrito_sin_mensaje(carrito):
    if not carrito:
        return "Tu carrito está vacío.\n"
    
    total = sum(precio for _, precio in carrito)
    resultado = "\nEste es tu pedido hasta ahora:\n\n"
    for item, precio in carrito:
        resultado += f" - {item}: ${precio:.2f}\n"
    resultado += f"\nTotal a pagar: ${total:.2f}\n"
    
    
    return resultado, total

def mostrar_carrito(carrito):
    resultado, total = mostrar_carrito_sin_mensaje(carrito)
    resultado += "\n🔺¿Algo más? escribe:\n *el nombre del producto* \n🔺¿ya estás listo? escribe:\n *pagar* para proceder al pago "
    return resultado, total
