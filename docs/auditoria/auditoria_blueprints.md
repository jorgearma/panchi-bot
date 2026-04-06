# Auditoría de seguridad – Blueprints (2026-04-06)

Hallazgos priorizados de mayor a menor severidad. Incluyen impacto y acciones sugeridas.

## Alta
- Estado de pedidos editable con token estático
  - Evidencia: `blueprints/api/cart.py:89-110` usa solo el header `X-Internal-Token` (configurable pero compartido) para cambiar estados de pedido sin sesión ni trazabilidad.
  - Riesgo: si el token se filtra (logs, frontend, repos), cualquier origen puede forzar estados y reabrir pagos.
  - Acciones: exigir sesión con rol adecuado (`manager/admin`), rotar/eliminar el token estático, registrar audit log y limitar origen (mTLS o red interna).

- Seguimiento público sin control ni protección de identificadores
  - Evidencia: `blueprints/api/tracking.py:12-19` expone `/api/seguimiento/<redis_id>` sin autenticación.
  - Riesgo: redis_id se entrega en links al cliente; si es capturado o adivinado se filtra estado, reparto y datos de contacto. No hay rate limiting ni expiración.
  - Acciones: firmar el identificador (HMAC con timestamp), caducarlo tras entrega, aplicar throttling y ocultar datos personales en la respuesta pública.

## Media
- Tokens de menú/pago cortos y expuestos en URL
  - Evidencia: `services/token_service.py` genera `token_urlsafe(7)` (≈56 bits) con TTL 24h; se consumen en `blueprints/menu/navegacion.py` y `_user_id_del_token` (`blueprints/api/cart.py:15-58`). CORS para `/api/*` permite orígenes arbitrarios.
  - Riesgo: el token viaja en la URL (referrers, logs, analytics) y da acceso total al pedido/checkout durante 24h; la entropía moderada facilita fuerza bruta en entornos con Redis expuesto.
  - Acciones: subir longitud (>=16 bytes), reducir TTL, mover el token a cookie HttpOnly + SameSite, limitar CORS a dominios propios y revocar token al cerrar pedido.

- Rutas de demo abiertas en producción
  - Evidencia: `blueprints/demo.py:12-92` permite `/demo`, `/demo/autologin`, `/dashboard/demo` sin autenticación; crean sesiones con rol `manager/admin` y cargan datos en Redis.
  - Riesgo: abuso para consumo de recursos (Redis), posible acceso a vistas internas si alguna ruta con `demo_ok=True` omite la bifurcación a datos simulados.
  - Acciones: proteger con flag de entorno (desactivar en prod), añadir rate limiting y CAPTCHAs, limpiar sesiones demo al arrancar/cron.

- Logs con datos personales en flujos de pago
  - Evidencia: `blueprints/api/payments.py:18-20` y `63-64` loguean el cuerpo completo del pedido (nombre, teléfono, dirección, carrito) a nivel DEBUG/INFO.
  - Riesgo: filtración de PII en `panchi-bot.log`, backups o sistemas de observabilidad; posible incumplimiento de privacidad.
  - Acciones: eliminar/anonimizar esos logs, bajar a TRACE condicionado por entorno de desarrollo y aplicar redacción de campos sensibles.

## Baja
- Mensajes de error diferenciados en autorización
  - Evidencia: `blueprints/api/cart.py:21-78` devuelve códigos y textos distintos para token ausente, expirado o mismatch de userID.
  - Riesgo: facilita enumeración de tokens/IDs y afinado de ataques de fuerza bruta.
  - Acciones: unificar mensajes genéricos de autenticación/autorización y registrar el detalle solo en logs internos.

