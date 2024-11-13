import re

import re
import unicodedata

def es_pregunta(frase):
    """
    Determina si una frase es una pregunta.
    
    Parámetros:
    frase (str): La frase a analizar.

    Retorna:
    bool: True si la frase es una pregunta, False en caso contrario.
    """
    # Función para eliminar acentos
    def quitar_tildes(texto):
        return ''.join(
            (c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
        )

    # Elimina espacios en blanco, convierte la frase a minúsculas y quita tildes
    frase = quitar_tildes(frase.strip().lower())
    
    # Lista extendida de palabras y estructuras comunes que indican preguntas (sin tildes)
    palabras_pregunta = {
        "que", "quien", "como", "donde", "cuando", "por que", "cual", "cuanto", "puedo", "debo", 
        "podria", "deberia", "seria", "tendria", "habria", "estaria", "hace", "hay", "es", "si"
    }
    
    # Patrón de expresión regular para detectar preguntas comunes (sin tildes)
    patrones_pregunta = re.compile(
        r'^(que|quien|como|donde|cuando|por que|cual|cuanto|podria|deberia|seria|tendria|habria|hay|hace|es)\b'
    )
    
    # Verifica si termina en signo de interrogación
    if frase.endswith('?'):
        return True

    # Verifica si contiene estructuras de pregunta comunes al inicio
    if patrones_pregunta.match(frase):
        return True

    # Verifica si alguna de las primeras palabras es una palabra de pregunta
    palabras_frase = frase.split()[:3]  # Analizamos hasta tres palabras para cubrir más casos
    for palabra in palabras_frase:
        if palabra in palabras_pregunta:
            return True
    
    # Verifica si hay estructuras verbales o gramaticales indicativas de pregunta
    if any(palabra in frase for palabra in ["¿", "no es", "verdad", "cierto", "o no"]):
        return True

    return False


