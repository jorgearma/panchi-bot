def es_pregunta(frase):
    """
    Determina si una frase es una pregunta.
    
    Parámetros:
    frase (str): La frase a analizar.

    Retorna:
    bool: True si la frase es una pregunta, False en caso contrario.
    """
    # Elimina espacios en blanco alrededor de la frase
    frase = frase.strip()
    
    # Palabras comunes que indican preguntas
    palabras_pregunta = {"qué", "quién", "cómo", "dónde", "cuándo", "por qué", "cuál", "cuánto", "puedo", "debo", "sería"}
    
    # Verifica si termina en signo de interrogación
    if frase.endswith('?'):
        return True

    # Divide la frase en palabras y verifica si la primera palabra es una de las palabras de pregunta
    primeras_palabras = frase.lower().split()[:2]  # Las dos primeras palabras para mayor precisión
    for palabra in primeras_palabras:
        if palabra in palabras_pregunta:
            return True
    
    return False
