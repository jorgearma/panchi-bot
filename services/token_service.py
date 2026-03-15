import os
import logging
import secrets
from managers.gestor_redis import redismanager
import json
from schemas.usuario import UsuarioDatos
from pydantic import ValidationError

logger = logging.getLogger(__name__)

# Generar token y almacenarlo en Redis
def generar_token_temporal(usuario_datos):
     # Validar los datos de usuario usando Pydantic
        try:
            usuario_validado = UsuarioDatos(**usuario_datos)
        except ValidationError as e:
            logger.error("Error de validación en usuario_datos: %s", e)
            return "Datos de usuario inválidos.", 400

        datos_usuario = {
        "id": usuario_validado.id,
        "numero": usuario_validado.numero,
        "direccion": usuario_validado.direccion,
        "nombre": usuario_validado.nombre
    }
        logger.debug("token payload: user_id=%s", datos_usuario["id"])
        token = secrets.token_urlsafe(7)
        redismanager.set(token, json.dumps(datos_usuario), ex=86400)  # Expira en 24 horas
        return token

# Generar enlace único  mejoras codificar el numero del cliente
def generar_enlace( restaurante_elegido , usuario_datos):
    token = generar_token_temporal(usuario_datos)
    return f"{os.environ.get('PUBLIC_URL')}/menu/{token}"

