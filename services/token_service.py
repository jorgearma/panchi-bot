import logging
import secrets
import json
import config
from managers.gestor_redis import redismanager
from schemas.usuario import UsuarioDatos
from pydantic import ValidationError

logger = logging.getLogger(__name__)

# Generar token y almacenarlo en Redis
def generar_token_temporal(usuario_datos):
    """Valida los datos del usuario y crea un token temporal en Redis."""
    # Validar los datos de usuario usando Pydantic
    try:
        usuario_validado = UsuarioDatos(**usuario_datos)
    except ValidationError as e:
        logger.error("Error de validación en usuario_datos: %s", e)
        raise ValueError(f"Datos de usuario inválidos: {e}") from e

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
    """Genera el enlace temporal que abre el menu web."""
    token = generar_token_temporal(usuario_datos)
    return f"{config.PUBLIC_URL}/menu/{token}"
