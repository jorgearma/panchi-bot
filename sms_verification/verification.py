"""
Lógica de verificación por SMS: generación de códigos, almacenamiento en Redis
y regla de negocio para decidir cuándo pedir verificación.
"""

import logging
import random
import string

from sms_verification import config as sms_config
from sms_verification.gateway_client import enviar_sms

logger = logging.getLogger(__name__)

# Redis key patterns
_KEY_CODE = "sms_verify:{phone}"
_KEY_ATTEMPTS = "sms_attempts:{phone}"
_KEY_COOLDOWN = "sms_cooldown:{phone}"


def _generar_codigo() -> str:
    """Genera un código numérico de 6 dígitos."""
    return "".join(random.choices(string.digits, k=6))


def enviar_codigo(phone: str, redis_client) -> tuple[bool, str]:
    """
    Genera y envía un código de verificación por SMS.

    Returns:
        (True,  "ok")       — SMS enviado correctamente
        (False, "cooldown") — hay que esperar antes de reenviar
        (False, "error")    — fallo en el envío del SMS
    """
    cooldown_key = _KEY_COOLDOWN.format(phone=phone)
    if redis_client.exists(cooldown_key):
        ttl = redis_client.ttl(cooldown_key)
        logger.info("SMS cooldown activo para %s, %ds restantes", phone, ttl)
        return False, "cooldown"

    codigo = _generar_codigo()
    mensaje = f"Tu codigo de verificacion Panchi es: {codigo}. Valido 10 minutos."

    enviado = enviar_sms(phone, mensaje)
    if not enviado:
        return False, "error"

    # Guardar código y activar cooldown
    code_key = _KEY_CODE.format(phone=phone)
    redis_client.setex(code_key, sms_config.CODE_TTL, codigo)
    redis_client.setex(cooldown_key, sms_config.RESEND_COOLDOWN, "1")

    return True, "ok"


def verificar_codigo(phone: str, code: str, redis_client) -> tuple[bool, str]:
    """
    Verifica el código introducido por el usuario.

    Returns:
        (True,  "ok")         — código correcto
        (False, "bloqueado")  — superó el máximo de intentos
        (False, "expirado")   — el código no existe o expiró
        (False, "incorrecto") — código incorrecto
    """
    attempts_key = _KEY_ATTEMPTS.format(phone=phone)
    attempts = redis_client.get(attempts_key)
    if attempts and int(attempts) >= sms_config.MAX_ATTEMPTS:
        return False, "bloqueado"

    code_key = _KEY_CODE.format(phone=phone)
    stored = redis_client.get(code_key)
    if stored is None:
        return False, "expirado"

    # Redis puede devolver bytes o str según el cliente
    stored_code = stored.decode() if isinstance(stored, bytes) else stored

    if stored_code != code.strip():
        redis_client.incr(attempts_key)
        redis_client.expire(attempts_key, sms_config.BLOCK_TTL)
        remaining = sms_config.MAX_ATTEMPTS - int(redis_client.get(attempts_key) or 1)
        logger.warning(
            "Código incorrecto para %s, %d intentos restantes", phone, remaining
        )
        return False, "incorrecto"

    # Código correcto — limpiar todas las claves del flujo
    redis_client.delete(
        code_key,
        attempts_key,
        _KEY_COOLDOWN.format(phone=phone),
    )
    return True, "ok"


def requiere_verificacion(
    phone_verified: bool,
    tiene_pago_online: bool,
    importe: float,
) -> bool:
    """
    Decide si un pedido contra reembolso necesita verificación SMS.

    Reglas:
      1. Importe >= umbral → requiere, salvo que ya esté verificado
      2. Ya verificado → no requiere
      3. Tiene al menos un pago online completado → no requiere
      4. Si no cumple ninguna excepción → requiere
    """
    if importe >= sms_config.VERIFICATION_THRESHOLD:
        return not phone_verified

    if phone_verified:
        return False

    return not tiene_pago_online
