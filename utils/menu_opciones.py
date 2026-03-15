import re
from unidecode import unidecode

menu = {
    "👇*Obciones*👇": {
        "tienda 🏪": {"codigo": 1, "mensaje": "Tienda online"},
        "Ayuda  🆘": {"codigo": 2, "mensaje": "para comunicarse un servicio al cliente, por favor llama al +45 49 99 48 76."},
        "Salir  🚪🚶🏻": {"codigo": 3, "mensaje": "Has elegido *Salir*. Si necesitas algo más, solo envíanos un mensaje."},
    }
}


def limpiar_texto(texto):
    texto_limpio = unidecode(texto)
    texto_limpio = re.sub(r'[^\w\s]', '', texto_limpio)
    return texto_limpio.lower()


def mostrar_menu():
    resultado = "\n\n"
    for categoria, items in menu.items():
        resultado += f"{categoria.capitalize()}\n\n"
        for item, detalles in items.items():
            codigo = detalles.get("codigo", "N/A")
            resultado += f" ▪️ *{codigo}* : {item.capitalize()}\n"
    return resultado
