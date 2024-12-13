import secrets
import redis

cache = redis.Redis(host='localhost', port=6379, db=0)

# Generar token y almacenarlo en Redis
def generar_token_temporal(numero_cliente):
    token = secrets.token_urlsafe(4)
    cache.set(token, numero_cliente, ex=86400)  # Expira en 24 horas
    return token

# Generar enlace único
def generar_enlace(numero_cliente , restaurante_elegido):
    token = generar_token_temporal(numero_cliente)
    return f"http://localhost:5000/menu/{token}"