# menu.py

import re
from unidecode import unidecode

menu = {
    "entradas": {
        "ensalada mixta": 5.00,
        "sopa de tomate": 4.50,
        "gazpacho": 6.00
    },
    "platos principales": {
        "pollo asado": 12.00,
        "paella": 15.00,
        "pasta carbonara": 11.00,
        "bistec a la parrilla": 18.00
    },
    "postres": {
        "flan": 4.00,
        "tarta de queso": 5.00,
        "helado de chocolate": 3.50
    },
    "bebidas": {
        "agua": 1.50,
        "vino tinto": 4.00,
        "cerveza": 3.00,
        "refresco": 2.50,
        "café": 2.00
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
        for item, precio in items.items():
            item_limpio = limpiar_texto(item)
            if item_limpio in pedido_limpio:
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
    resultado = "\nEste es tu pedido hasta ahora:\n"
    for item, precio in carrito:
        resultado += f" - {item}: ${precio:.2f}\n"
    resultado += f"\nTotal a pagar: ${total:.2f}\n"
    
    
    return resultado, total

def mostrar_carrito(carrito):
    resultado, total = mostrar_carrito_sin_mensaje(carrito)
    resultado += "\n¿Quieres sumar algo más? Escribe 'pagar' para proceder al pago."
    return resultado, total
