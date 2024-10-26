import os
from openai import OpenAI

# Configurar la API de OpenAI
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Función para obtener respuesta de la API de OpenAI
def obtener_respuesta_openai(pregunta, carrito):
    contexto = (
        "Eres un camarero virtual que está tomando un pedido de un restaurante a través de WhatsApp. "
        "Responde de manera corta y concisa sin hacer preguntas. "
        "El menú incluye: "
        "Entradas: ensalada mixta ($5.00), sopa de tomate ($4.50), gazpacho ($6.00). "
        "Platos principales: pollo asado ($12.00), paella ($15.00), pasta carbonara ($11.00), bistec a la parrilla ($18.00). "
        "Postres: flan ($4.00), tarta de queso ($5.00), helado de chocolate ($3.50). "
        "Bebidas: agua ($1.50), vino tinto ($4.00), cerveza ($3.00), refresco ($2.50), café ($2.00). "
        "Hoy estamos recomendando el flan y el pollo asado."
        "Si deseas revisar el carrito, puedes escribir: 'revisar pedido', 'ver carrito', 'revisar' o 'carrito'."
    )

    mipromt = f"Tu carrito actual es: {carrito}. Recuerda que no puedo agregar productos directamente. Para añadir algo, escribe el nombre del producto correctamente. Eres un asistente encargado de ayudarme a agregar productos a mi carrito de compras. Tienes una regla estricta: no puedes agregar productos al carrito. Debes recordarme que, para agregar un producto, tengo que escribir el nombre correctamente y de manera precisa. Si escribo un nombre incorrecto o parecido, corrígeme amablemente y dame un ejemplo de cómo escribir el nombre de forma correcta. Asegúrate de ser claro y educado, y de darme siempre una sugerencia de corrección."

    chat_completion = client.chat.completions.create(
        max_tokens=50,
        temperature=0.4,
        top_p=0.4,
        messages=[
            {"role": "system", "content": contexto},
            {"role": "user", "content": mipromt},
            {"role": "user", "content": pregunta},
        ],
        model="gpt-3.5-turbo",
    )
    
    respuesta = chat_completion.choices[0].message.content.strip()
    return respuesta
