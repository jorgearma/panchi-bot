import secrets
import redis

cache = redis.Redis(host='localhost', port=6379, db=0)

# Generar token y almacenarlo en Redis
def generar_token_temporal(numero_cliente):
    token = secrets.token_urlsafe(4)
    cache.set(token, numero_cliente, ex=86400)  # Expira en 24 horas
    return token

# Generar enlace único  mejoras codificar el numero del cliente
def generar_enlace(numero_cliente , restaurante_elegido):
    token = generar_token_temporal(numero_cliente)
    return f"https://9fc0-62-116-223-170.ngrok-free.app/menu/{numero_cliente}/{token}"

def generar_token_y_guardar_cliente(numero_cliente):
    """
    Genera un token único, lo guarda en Redis junto con el número de cliente,
    y lo expira a las 24 horas.
    """
    token = secrets.token_urlsafe(4)
    # Guarda el número del cliente en Redis con expiración de 86400 segundos (24h)
    cache.set(token, numero_cliente, ex=86400)
    return token

def obtener_numero_cliente(token):
    """
    Recupera el número de cliente a partir del token almacenado en Redis.
    Si el token no existe o ha expirado, retorna None.
    """
    numero_cliente = cache.get(token)
    if not numero_cliente:
        return None
    return numero_cliente.decode()