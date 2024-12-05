import os
from openai import OpenAI

# Configurar la API de OpenAI
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Función para obtener respuesta de la API de OpenAI
def obtener_respuesta_openai(pregunta, carrito):
    contexto = (
        "Eres un asistente que ayuda a los clientes a elegir entre varios restaurantes y realizar pedidos. "
        "Muestra las opciones disponibles de restaurantes y proporciona enlaces directos para que los usuarios puedan agregar productos al carrito. "
        "Los restaurantes disponibles son Italiano (código 1), Mexicano (código 2) y Japonés (código 3). "
        "Si el cliente pregunta por un restaurante, ofrece el enlace correspondiente. "
        "Si el cliente escribe 'carrito', muestra el contenido del carrito. "
        "Si escribe 'pagar', proporciona los pasos para proceder al pago. "
        "Si necesitan servicio al cliente, dales este número: 6678514. "
        "Responde de manera breve pero completa y ayúdales a elegir."
    )

    chat_completion = client.chat.completions.create(
        max_tokens=60,  # Reducimos el número de tokens para respuestas más breves
        temperature=0.5,
        top_p=0.4,
        messages=[
            {"role": "system", "content": contexto},
            {"role": "user", "content": pregunta},
        ],
        model="gpt-3.5-turbo",
    )
    
    respuesta = chat_completion.choices[0].message.content.strip()
    return respuesta
