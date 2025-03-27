import secrets
from managers.gestor_redis import redismanager
import json

# Generar token y almacenarlo en Redis
def generar_token_temporal(usuario_datos):
    token = secrets.token_urlsafe(7)
    redismanager.set(token, json.dumps(usuario_datos))  # Expira en 24 horas
    return token

# Generar enlace único  mejoras codificar el numero del cliente
def generar_enlace( restaurante_elegido , usuario_datos):
    token = generar_token_temporal(usuario_datos)
    return f"https://e981-62-116-223-170.ngrok-free.app/menu/{token}"

