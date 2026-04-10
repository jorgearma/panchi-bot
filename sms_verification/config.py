"""Configuración del módulo SMS verification — todo vía variables de entorno."""

import os

# Android SMS Gateway (capcom6/android-sms-gateway)
# Dejar vacío para modo mock (solo loguea, no envía SMS reales)
GATEWAY_URL: str | None = os.environ.get("SMS_GATEWAY_URL")
GATEWAY_USER: str | None = os.environ.get("SMS_GATEWAY_USER")
GATEWAY_PASSWORD: str | None = os.environ.get("SMS_GATEWAY_PASSWORD")

# Importe (EUR) a partir del cual siempre se pide verificación
VERIFICATION_THRESHOLD: float = float(os.environ.get("SMS_VERIFICATION_THRESHOLD", "40.0"))

# TTL del código en Redis (segundos) — 10 min por defecto
CODE_TTL: int = int(os.environ.get("SMS_CODE_TTL", "600"))

# Cooldown entre reenvíos (segundos) — 2 min por defecto
RESEND_COOLDOWN: int = int(os.environ.get("SMS_RESEND_COOLDOWN", "120"))

# Máximo intentos fallidos antes de bloquear
MAX_ATTEMPTS: int = int(os.environ.get("SMS_MAX_ATTEMPTS", "3"))

# TTL del bloqueo por intentos (segundos) — 1 hora por defecto
BLOCK_TTL: int = int(os.environ.get("SMS_BLOCK_TTL", "3600"))
