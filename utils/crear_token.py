import secrets
from managers.gestor_redis import redismanager
import json
from modelos.validator_usuario import UsuarioDatos
from pydantic import ValidationError

# Generar token y almacenarlo en Redis
def generar_token_temporal(usuario_datos):
     # Validar los datos de usuario usando Pydantic
        try:
            usuario_validado = UsuarioDatos(**usuario_datos)
        except ValidationError as e:
            print(f"Error de validación en usuario_datos: {e}")
            return "Datos de usuario inválidos.", 400

        datos_usuario = {
        "id": usuario_validado.id,
        "numero": usuario_validado.numero,
        "direccion": usuario_validado.direccion,
        "nombre": usuario_validado.nombre
    }
        print("datos desdeq qu sube a toke " ,datos_usuario)
        token = secrets.token_urlsafe(7)
        redismanager.set(token, json.dumps(datos_usuario))  # Expira en 24 horas
        return token

# Generar enlace único  mejoras codificar el numero del cliente
def generar_enlace( restaurante_elegido , usuario_datos):
    token = generar_token_temporal(usuario_datos)
    return f"https://e7c3-62-116-223-170.ngrok-free.app/menu/{token}"

