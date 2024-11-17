import unicodedata


def limpiar_texto(texto):
    # Convierte a minúsculas y elimina espacios en los extremos
    texto = texto.strip().lower()
    # Elimina acentos y tildes
    texto = ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )
    return texto