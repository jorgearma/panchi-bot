# RedisManager

**Archivo:** `managers/gestor_redis.py`  
**Capa:** Manager (acceso a Redis)  
**Singleton:** `redismanager` — importar desde `container.py`

## Responsabilidad

Único punto de acceso a Redis. Expone operaciones seguras con manejo de errores y reintentos. El cliente raw (`self.client`) solo lo usan servicios que necesitan comandos Redis sin abstracción (ver tabla de consumidores).

## Configuración de conexión

| Parámetro | Valor |
|---|---|
| `socket_timeout` | 3s — tiempo máximo esperando respuesta |
| `socket_connect_timeout` | 3s — tiempo máximo conectando |
| `retry_on_timeout` | `True` — reintenta automáticamente en timeout |

Si Redis no está disponible al arrancar, el `__init__` lanza excepción y la app no arranca.

## Métodos

### `get(key) → bytes | None`

Lectura segura. Si Redis falla devuelve `None` sin lanzar excepción — decisión consciente para no bloquear al usuario por un fallo de lectura.

---

### `set(key, value, ex=None) → bool`

Escritura con reintentos: 3 intentos, espera 2s entre ellos. Si agota los intentos lanza excepción. El TTL (`ex`) es opcional.

---

### `delete(key) → int`

Borrado con reintentos: 3 intentos, espera 2s. Si la clave no existe loguea warning pero no lanza excepción.

---

### `esta_bloqueado(numero) → bool`

Comprueba si existe `bloqueo:<numero>` en Redis.  
**Usado por:** `services/inbound_whatsapp.py` — anti-spam antes de procesar cualquier mensaje.

---

### `bloquear_usuario(numero, duracion=None)`

Escribe `bloqueo:<numero>` con TTL opcional.  
**Usado por:** `services/inbound_whatsapp.py` — bloqueo de 4s tras recibir un mensaje (anti-flood).

---

### `desbloquear_usuario(numero)`

Elimina `bloqueo:<numero>`.

---

### `ya_procesado_wamid(wamid, ttl=300) → bool`

Deduplicación de mensajes WhatsApp usando `SET NX` (atómico). Devuelve `True` si el `wamid` ya fue procesado.

- **TTL por defecto:** 300s (5 minutos)
- **Ante error Redis:** devuelve `False` — mejor procesar un duplicado que perder un mensaje
- **Usado por:** `services/inbound_whatsapp.py` — primera comprobación al recibir un webhook de Meta

---

### `adquirir_lock(key, ttl=10) → bool`

Lock atómico con `SET NX`. Devuelve `True` si se adquirió el lock.

- **Ante error Redis:** devuelve `True` (fail-open) — mejor dejar pasar que bloquear al usuario indefinidamente
- **Usado por:**
  - `controllers/mensajes_registrados.py` — evita crear dos pedidos simultáneos para el mismo usuario
  - `controllers/pedido.py` — evita procesar dos opciones de menú a la vez

## Consumidores y qué usan

| Consumidor | Métodos usados |
|---|---|
| `services/inbound_whatsapp.py` | `ya_procesado_wamid`, `esta_bloqueado`, `bloquear_usuario` |
| `controllers/mensajes_registrados.py` | `adquirir_lock` |
| `controllers/pedido.py` | `adquirir_lock` |
| `managers/estado_usuario.py` | `get`, `set`, `delete` (estado de registro en Redis) |
| `services/token_service.py` | `set` (token de menú, TTL 24h) |
| `services/menu_session.py` | `get` (recuperar sesión de carrito) |
| `services/auth_service.py` | `client` directo — `incr`, `expire`, `get`, `delete` (intentos de login por IP) |
| `services/demo_state.py` | `client` directo — estado de sesión demo |

## Claves Redis por responsabilidad

| Patrón de clave | Responsable | TTL |
|---|---|---|
| `bloqueo:<numero>` | `esta_bloqueado` / `bloquear_usuario` | 4s (anti-flood) |
| `wamid:<wamid>` | `ya_procesado_wamid` | 300s |
| `pedido_lock:<numero>` | `adquirir_lock` (desde controllers) | 10s |
| `<numero_cliente>` | `estado_usuario.py` vía `get`/`set` | 3600s |
| `<uuid-token>` | `token_service.py` vía `set` | 86400s |
| `login_intentos:<ip>` | `auth_service.py` vía `client` directo | variable |

## Notas

- `set` y `delete` tienen `@retry` (escrituras críticas). `get` no — devuelve `None` ante fallo para no bloquear flujos de lectura.
- Los métodos atómicos (`ya_procesado_wamid`, `adquirir_lock`) usan `self.client` directamente con `SET NX` — no pasan por `self.set` para evitar reintentos que romperían la atomicidad.
- `auth_service.py` y `demo_state.py` acceden a `client` directamente porque necesitan comandos Redis sin abstracción (`INCR`, `EXPIRE`).
