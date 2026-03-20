# Spec: Soporte multi-proveedor WhatsApp (Twilio + Meta Cloud API)

**Fecha:** 2026-03-20
**Ámbito:** `services/whatsapp_service.py`, `blueprints/webhook.py`, `config.py`, 8 ficheros importadores, `tests/test_webhook.py`

---

## Objetivo

Permitir elegir entre Twilio y la Meta WhatsApp Cloud API como proveedor de mensajería mediante la variable de entorno `WHATSAPP_PROVIDER`, sin tocar la lógica de negocio. Un solo proveedor activo a la vez.

---

## Decisiones de diseño

- **Un fichero de servicio único** con routing interno — no módulos separados por proveedor (YAGNI).
- **Env var en arranque** (`WHATSAPP_PROVIDER=twilio|meta`) — no switchable en caliente.
- **Meta Cloud API directa** — sin BSP intermediario.
- **Misma firma pública** `enviar_mensaje_whatsapp(mensaje, destinatario)` — los 8 importadores no cambian.

---

## 1. Capa de envío (outgoing)

### 1.1 Renombrado de fichero

`services/twilio_service.py` → `services/whatsapp_service.py`

Todos los ficheros que importan `from services.twilio_service import enviar_mensaje_whatsapp` deben actualizarse a `from services.whatsapp_service import enviar_mensaje_whatsapp`. Ficheros afectados:

- `blueprints/webhook.py`
- `blueprints/repartidor.py`
- `blueprints/dashboard.py`
- `blueprints/picker.py`
- `controllers/pago.py`
- `controllers/registro.py`
- `controllers/mensajes_registrados.py`
- `controllers/pedido.py`

### 1.2 Estructura interna

```python
# services/whatsapp_service.py

WHATSAPP_PROVIDER = os.getenv("WHATSAPP_PROVIDER", "twilio")

def enviar_mensaje_whatsapp(mensaje: str, destinatario: str) -> None:
    """Envía un mensaje WhatsApp usando el proveedor configurado."""
    if WHATSAPP_PROVIDER == "meta":
        _enviar_meta(mensaje, destinatario)
    else:
        _enviar_twilio(mensaje, destinatario)
```

### 1.3 `_enviar_twilio`

Código actual de `twilio_service.py` sin cambios, decorado con `@retry` (tenacity, 3 intentos, backoff exponencial).

### 1.4 `_enviar_meta`

POST a `https://graph.facebook.com/v19.0/{META_PHONE_NUMBER_ID}/messages` con:

```json
{
  "messaging_product": "whatsapp",
  "to": "<número_normalizado>",
  "type": "text",
  "text": { "body": "<mensaje>" }
}
```

Header: `Authorization: Bearer <META_ACCESS_TOKEN>`

Decorado con el mismo `@retry` de tenacity. Lanza excepción si la respuesta no es 2xx.

### 1.5 Normalización de números

Los callers siempre pasan el número con el prefijo Twilio: `whatsapp:+34600000000`. Este es el formato que llega del webhook de Twilio (`data.From`) y que se almacena en Redis y BD.

- `_enviar_twilio` pasa el número tal cual — la API de Twilio acepta el formato `whatsapp:+XXXXXXXXX` directamente en el campo `to`.
- `_enviar_meta` extrae solo los dígitos: `destinatario.replace("whatsapp:+", "")` → `34600000000`. La Cloud API de Meta espera el número sin prefijo ni `+`.

---

## 2. Webhook entrante (incoming)

### 2.1 Endpoint existente `/webhook` (Twilio)

**No se modifica.** Sigue funcionando igual.

### 2.2 Nuevo `GET /webhook/meta` — verificación de webhook

Meta envía un GET con query params `hub.mode`, `hub.challenge`, `hub.verify_token` cuando registras el webhook en el panel.

Comportamiento:
- Si `hub.mode == "subscribe"` y `hub.verify_token == config.META_VERIFY_TOKEN` → responder con `hub.challenge` en texto plano, 200.
- En cualquier otro caso → 403.

### 2.3 Nuevo `POST /webhook/meta` — mensajes entrantes

**Validación de firma:**

Header `X-Hub-Signature-256: sha256=<hex>`. Se verifica con HMAC-SHA256 usando `config.META_APP_SECRET` sobre el body raw. Si falla → 401.

**Parseo del payload:**

Meta envía JSON. La estructura relevante:

```json
{
  "entry": [{
    "changes": [{
      "value": {
        "messages": [{
          "from": "34600000000",
          "text": { "body": "hola" },
          "type": "text"
        }]
      }
    }]
  }]
}
```

- Si no hay `messages` (p.ej. notificaciones de estado de entrega) → responder 200 sin procesar.
- Si `type != "text"` → responder 200 sin procesar (ignorar audio, imagen, etc.).
- Extraer `from` y `text.body`.

**Normalización del número:**

`from` viene como `34600000000` → convertir a `whatsapp:+34600000000` para mantener compatibilidad con Redis y la lógica de negocio.

**Routing a lógica de negocio:**

Mismo flujo que `/webhook` de Twilio (incluyendo el 403 para números bloqueados por rate-limit):
1. Comprobar rate-limit con `redismanager.esta_bloqueado`
2. Aplicar `redismanager.bloquear_usuario`
3. Llamar a `gestor_usuarios.verificar_usuario`
4. Despachar a `manejar_registro` o `ManejadorMensajesRegistrados.manejar_mensajes_registrados`

Los mensajes de error al usuario se envían con `enviar_mensaje_whatsapp` (que ya sabe qué proveedor usar).

---

## 3. Configuración (`config.py`)

### 3.1 Variables nuevas

```python
WHATSAPP_PROVIDER: str = os.environ.get("WHATSAPP_PROVIDER", "twilio")
META_ACCESS_TOKEN: str | None = os.environ.get("META_ACCESS_TOKEN")
META_PHONE_NUMBER_ID: str | None = os.environ.get("META_PHONE_NUMBER_ID")
META_APP_SECRET: str | None = os.environ.get("META_APP_SECRET")
META_VERIFY_TOKEN: str | None = os.environ.get("META_VERIFY_TOKEN")
```

### 3.2 Validación de arranque

La lista `_VARS_OBLIGATORIAS` en `main.py` debe volverse condicional. Si faltan vars obligatorias, la app lanza `EnvironmentError` y no arranca (comportamiento actual, se mantiene).

```python
_VARS_COMUNES = ['SECRET_KEY', 'MONEI_API_KEY', 'MONEI_WEBHOOK_SECRET', 'PUBLIC_URL']
if os.environ.get('WHATSAPP_PROVIDER', 'twilio') == 'meta':
    _VARS_OBLIGATORIAS = _VARS_COMUNES + [
        'META_ACCESS_TOKEN', 'META_PHONE_NUMBER_ID', 'META_APP_SECRET', 'META_VERIFY_TOKEN'
    ]
else:
    _VARS_OBLIGATORIAS = _VARS_COMUNES + [
        'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_WHATSAPP_NUMBER'
    ]
```

Con `WHATSAPP_PROVIDER=meta`, las vars de Twilio son opcionales (no se validan). Con `WHATSAPP_PROVIDER=twilio` (default), las vars de Meta son opcionales.

---

## 4. Tests

### 4.1 Tests existentes

- Actualizar todos los `patch("services.twilio_service.enviar_mensaje_whatsapp")` y `patch("controllers.*.enviar_mensaje_whatsapp")` en los módulos de test para reflejar el nuevo path `services.whatsapp_service`.
- Los tests de lógica de negocio (registro, mensajes registrados, pedido) no cambian su lógica, solo el path del patch.

### 4.2 Tests nuevos para `/webhook/meta`

| Test | Resultado esperado |
|------|--------------------|
| GET con `verify_token` correcto | 200, devuelve `hub.challenge` |
| GET con `verify_token` incorrecto | 403 |
| POST sin header `X-Hub-Signature-256` | 401 |
| POST con firma incorrecta | 401 |
| POST con payload sin `messages` (notificación de estado) | 200, no llama a manejar_registro |
| POST con mensaje de tipo no-texto (imagen, audio) | 200, no llama a manejar_registro |
| POST con mensaje de texto válido, usuario no registrado | llama a `manejar_registro` |
| POST con mensaje de texto válido, usuario registrado | llama a `ManejadorMensajesRegistrados` |
| POST con payload malformado (sin clave `entry`) | 200, no procesa (defensa ante notificaciones inesperadas de Meta) |

---

## 5. Lo que NO cambia

- `controllers/` — ningún controller.
- `managers/` — ningún manager.
- `blueprints/webhook.py` ruta `/webhook` (Twilio).
- `blueprints/webhook.py` ruta `/webhook/monei`.
- `schemas/twilio.py` — no se usa en el endpoint Meta (el parseo es manual en el blueprint).
- La lógica de rate-limiting, registro, pedidos, estado de pedido.
- El formato interno de números (`whatsapp:+XXXXXXXXX`) en Redis y BD.

---

## 6. Criterios de aceptación

1. Con `WHATSAPP_PROVIDER=twilio` (default) — comportamiento idéntico al actual.
2. Con `WHATSAPP_PROVIDER=meta` — los mensajes salen vía Meta Cloud API.
3. `GET /webhook/meta` con token correcto → 200 con challenge.
4. `POST /webhook/meta` con firma válida y mensaje de texto → misma lógica de negocio que Twilio.
5. `POST /webhook/meta` con firma inválida → 401.
6. `POST /webhook/meta` con payload sin messages o tipo no-texto → 200 sin procesar.
7. Con `WHATSAPP_PROVIDER=meta` en arranque sin las 4 vars de Meta → error claro al iniciar.
8. Suite completa de tests: sin regresiones.
