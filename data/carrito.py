from utils.mensajes import enviar_mensaje_whatsapp

# Carrito global
carrito = {}

def inicializar_carrito(numero_cliente):
    carrito[numero_cliente] = []

def calcular_total(carrito_cliente):
    return sum(item[1] for item in carrito_cliente)

def mostrar_carrito_sin_mensaje(carrito):
    if not carrito:
        return "Tu carrito está vacío.\n", 0
    
    total = calcular_total(carrito)
    resultado = "\n _⬇️ *Este es tu pedido* ⬇️_ \n\n"
    for item, precio in carrito:
        resultado += f" ▪️ {item}: *€{precio:.2f}*\n"
    resultado += f"\nTotal a pagar: *€{total:.2f}*\n"
    resultado += f"➖➖➖➖➖➖➖➖➖➖\n"
    
    return resultado, total

def mostrar_carrito(carrito):
    resultado, total = mostrar_carrito_sin_mensaje(carrito)
    resultado += "\n ❗¿Algo más?❗Escribe📝\n👉 el *NUMERO* o su *NOMBRE*\n\n❗¿ya estás list@?❗Escribe📝\n👉 *PAGAR* 👈 para continuar "
    return resultado, total

def verificar_palabras_clave(mensaje_cliente, palabras_clave):
    mensaje_cliente = mensaje_cliente.lower()
    return any(palabra in mensaje_cliente for palabra in palabras_clave)

def verificar_carrito(numero_cliente, carrito):
    return numero_cliente in carrito

def obtener_contenido_carrito(numero_cliente, carrito):
    if verificar_carrito(numero_cliente, carrito):
        return mostrar_carrito(carrito[numero_cliente])
    else:
        return "Tu carrito está vacío."

def enviar_respuesta_carrito(contenido, numero_cliente):
    enviar_mensaje_whatsapp(contenido, numero_cliente)

def es_consulta_carrito(mensaje_cliente):
    palabras_clave = ["revisar pedido", "ver carrito", "revisar", "carrito"]
    return verificar_palabras_clave(mensaje_cliente, palabras_clave)

def procesar_consulta_carrito(numero_cliente, carrito):
    contenido_carrito = obtener_contenido_carrito(numero_cliente, carrito)
    enviar_respuesta_carrito(contenido_carrito, numero_cliente)

def manejar_consulta_carrito(mensaje_cliente, numero_cliente, carrito):
    if es_consulta_carrito(mensaje_cliente):
        procesar_consulta_carrito(numero_cliente, carrito)
        return True
    return False
