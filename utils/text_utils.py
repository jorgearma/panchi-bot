import re
from unidecode import unidecode


def limpiar_texto(texto):
    """Normaliza texto: transliteración unicode, elimina puntuación y pasa a minúsculas."""
    texto_limpio = unidecode(texto)
    texto_limpio = re.sub(r'[^\w\s]', '', texto_limpio)
    return texto_limpio.lower()
