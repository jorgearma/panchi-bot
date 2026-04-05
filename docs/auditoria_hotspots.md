# Puntos críticos a vigilar

Lista de zonas del código donde conviene auditar con más detalle. No incluye soluciones, solo el mapa de qué revisar.

- **Webhooks y proveedores externos**
  - `blueprints/webhook.py:12-86`: Validación de firmas Twilio/Meta/Monei depende de `PUBLIC_URL`, `TWILIO_AUTH_TOKEN`, `META_APP_SECRET` y `MONEI_WEBHOOK_SECRET`. Hay ruta duplicada `/webhoo/monei` (typo) que sigue activa; revisar superficie de exposición y logs ante firmas inválidas.
  - `services/inbound_whatsapp.py:40-120`: Cálculo de HMAC para Twilio/Meta/Monei; no se valida caducidad del timestamp de Monei ni se limita el tamaño del cuerpo. Confirmar que los secretos están cargados y que el host público coincide con el que firma Twilio.
  - `services/inbound_whatsapp.py:171-236`: Procesado del webhook de Monei marca PAGADO y envía WhatsApp sin comprobar idempotencia ni concordancia de importe/moneda con el pedido; transiciones inválidas devuelven 200 igualmente.

- **Pagos online y carrito**
  - `controllers/pago.py:14-120` + `services/monei_service.py`: El pago se crea en Monei antes de persistir líneas; revisar manejo de reintentos, importes redondeados y consistencia `amount` vs. totales en BD. Confirmar que `completeUrl` no se puede manipular desde el cliente.
  - `managers/pedidos/lifecycle_mixin.py:120-204`: Cambios de estado y escritura de líneas en transacciones únicas; verificar que las transiciones cubren rollbacks y que no se pueden saltar estados vía llamadas internas.
  - `controllers/pedido.py:14-107` / `blueprints/api/cart.py:14-120`: Validación del carrito y cálculo de totales dependen de Redis y del catálogo; auditar qué pasa si Redis cae o el token expira en medio del flujo.

- **Tokens, sesiones y CORS**
  - `services/token_service.py`: Tokens `token_urlsafe(7)` con datos del usuario en claro y TTL 24h en Redis. Revisar entropía, rotación y acceso a Redis.
  - `blueprints/api/cart.py:23-110`: Autorización del menú web solo por token de Redis; confirmar que el token se invalida tras uso y que no puede reutilizarse en otros pedidos.
  - `main.py:43-63`: CORS permite `ALLOWED_ORIGIN` vacío -> `*` para `/api/*`; revisar exposición de endpoints públicos y mezcla con panel interno.
  - `config.py`: `SESSION_COOKIE_SECURE` por defecto `false`; auditar configuración de cookies y secreto de sesión en producción.

- **Rate limiting y colas**
  - `services/inbound_whatsapp.py:86-122`: Bloqueo por número solo 4s en Redis; evaluar si es suficiente frente a spam o ataques de fuerza bruta.
  - `message_queue.py`: Cola RQ sin TLS hacia Redis y sin DLQ; revisar timeouts y visibilidad de fallos.
  - `managers/gestor_redis.py`: Conexión sin autenticación/TLS; validar configuración en entornos expuestos.

- **Geocodificación y territorio**
  - `maps_module/service.py`: Llamadas a Google Maps sin caché y con claves en claro; revisar cuotas, tratamiento de errores y validación de polígonos (`territories.json`).
  - `controllers/registro.py:41-110`: Flujo de validación de dirección y sugerencias; confirmar que los mensajes no filtran datos sensibles y que los rechazos “fuera_de_zona” se gestionan correctamente.

- **Seguridad de base de datos y credenciales**
  - `database.py` / `config.py`: Credenciales de SQL Server por defecto `sa` sin contraseña; asegurarse de que en despliegue siempre se sobreescriben y que se usa TLS si el servidor es remoto.
  - `config.py`: Variables críticas (`INTERNAL_API_TOKEN`, `MONEI_WEBHOOK_SECRET`, claves Meta/Twilio) deben estar presentes; el arranque solo valida algunas (según proveedor), revisar huecos.

- **Observabilidad y datos sensibles**
  - `main.py:27-41` y logs en `controllers/` y `services/`: Se loguean teléfonos, direcciones e importes. Revisar nivel y destino de logs (`panchi-bot.log` con rotación) para cumplir privacidad y evitar filtraciones.

- **Panel interno y control de acceso**
  - `blueprints/auth.py` + `services/auth_service.py`: Autenticación de empleados basada en sesiones Flask; verificar expiración de sesión, enforcement de `session.permanent`, y selección de rol activo cuando un usuario tiene múltiples roles.
  - Rutas internas protegidas por `requiere_rol` y token `X-Internal-Token` (`blueprints/api/cart.py:79-110`); auditar almacenamiento y distribución de ese token y que no se exponga al frontend.

