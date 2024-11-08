import os
from openai import OpenAI

# Configurar la API de OpenAI
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Función para obtener respuesta de la API de OpenAI
def obtener_respuesta_openai(pregunta, carrito):
    contexto = (
        "Eres un asistente que ayuda a los clientes a agregar productos al carrito de compras. "
        "Nuestra cocina, Urban Kitchen, es un servicio de reparto a domicilio ubicado en Avenida Miguel de Cervantes 79. "
        "Si el cliente quiere ver el carrito, indícale que escriba 'carrito'. "
        "Si quiere proceder con el pago, indícale que escriba 'pagar'. "
        "si el cliente pregunta por el servicio al cliente dala este numero 6678514 para que pueda llamar"
        "Responde de manera breve pero completa."
        
    )

    chat_completion = client.chat.completions.create(
        max_tokens=60,  # Reducimos el número de tokens para respuestas más breves
        temperature=0.5,
        top_p=0.4,
        messages=[
            {"role": "system", "content": contexto},
            {"role": "user", "content": "Aquí tienes el menú en formato JSON:\n\nmenu = {\n\"🍔 *HAMBURGuESAS*\": {\n \"clasica\": {\"precio\": 5.00, \"codigo\": 301},\n \"ranchera\": {\"precio\": 5.50, \"codigo\": 302},\n \"crispy\": {\"precio\": 6.00, \"codigo\": 303}\n },\n\"🌭 *PERRITOS*\": {\n \"clasico\": {\"precio\": 4.00, \"codigo\": 401},\n \"picanton\": {\"precio\": 4.00, \"codigo\": 402},\n \"texano\": {\"precio\": 4.00, \"codigo\": 403},\n \"bbq\": {\"precio\": 4.00, \"codigo\": 404}\n },\n\"🍨 *POSTRES*\": {\n \"flan\": {\"precio\": 4.00, \"codigo\": 501},\n \"tarta\": {\"precio\": 5.00, \"codigo\": 502},\n \"helado\": {\"precio\": 3.50, \"codigo\": 503}\n },\n\"🥤 *BEBIDAS*\": {\n \"agua\": {\"precio\": 1.50, \"codigo\": 601},\n \"vino\": {\"precio\": 4.00, \"codigo\": 602},\n \"cerveza\": {\"precio\": 3.00, \"codigo\": 603},\n \"refresco\": {\"precio\": 2.50, \"codigo\": 604},\n \"café\": {\"precio\": 2.00, \"codigo\": 605}\n }\n}\n\nQuiero que ChatGPT responda a las preguntas de los usuarios sobre el menú usando este JSON. Si un usuario escribe un código o nombre incorrecto, dile que verifique y escriba el nombre o código correcto. Indica los pasos que debe seguir el usuario para agregar un producto al carrito, ver el carrito escribiendo 'carrito', o proceder al pago escribiendo 'pagar'."},
            {"role": "user", "content": pregunta},
        ],
        model="gpt-3.5-turbo",
    )
    
    respuesta = chat_completion.choices[0].message.content.strip()
    return respuesta

