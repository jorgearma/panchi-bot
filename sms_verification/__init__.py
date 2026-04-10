"""
sms_verification — módulo de verificación de teléfono por SMS.

API pública:
    enviar_codigo(phone, redis_client) -> (bool, str)
    verificar_codigo(phone, code, redis_client) -> (bool, str)
    requiere_verificacion(phone_verified, tiene_pago_online, importe) -> bool

Diseñado para ser independiente del resto de la aplicación:
    - Sin imports de models, managers, controllers ni blueprints.
    - Requiere Redis para almacenar los códigos temporales.
    - En modo desarrollo (sin SMS_GATEWAY_URL), los códigos se loguean en vez de enviarse.
    - En producción, usa capcom6/android-sms-gateway como backend de envío.
"""
from sms_verification.verification import (
    enviar_codigo,
    verificar_codigo,
    requiere_verificacion,
)

__all__ = [
    "enviar_codigo",
    "verificar_codigo",
    "requiere_verificacion",
]
