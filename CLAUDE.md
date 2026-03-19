# Panchi-Bot — Guía para Claude

Sistema de pedidos para restaurante vía WhatsApp (Twilio). Los clientes se registran o reciben un enlace de menú, confirman su carrito y pagan online (Monei) o contra reembolso. El personal gestiona preparación (picker), reparto y supervisión desde paneles web internos.

---

## Comandos esenciales

```bash
# Tests (siempre antes de hacer commit)
pytest -v --tb=short

# Servidor de desarrollo
python main.py          # http://0.0.0.0:5000

# Modelo spaCy (solo primera vez tras instalar)
python -m spacy download es_core_news_sm

# Dependencias
pip install -r requirements.txt
```

---

## Arquitectura por capas

```
Twilio webhook → blueprints/ → controllers/ → managers/ → SQL Server / Redis
                                            ↘ services/  → Twilio / Monei / Google Maps
```

| Capa | Directorio | Responsabilidad |
|------|-----------|-----------------|
| Rutas HTTP | `blueprints/` | Validar request, llamar controller o manager, devolver JSON/HTML |
| Lógica de negocio | `controllers/` | Orquestar flujos complejos (registro, pedido, pago) |
| Acceso a datos | `managers/` | Queries SQLAlchemy, operaciones Redis |
| Servicios externos | `services/` | Twilio, Monei, Google Maps, tokens |
| Modelos ORM | `models.py` | Definición de tablas |
| Máquinas de estado | `states.py` | Enums y transiciones válidas |

---

## Blueprints registrados

| Blueprint | Archivo | Rutas principales |
|-----------|---------|-------------------|
| `webhook` | `blueprints/webhook.py` | `POST /webhook` (Twilio), `POST /webhook/monei` |
| `menu` | `blueprints/menu.py` | `GET /menu/<token>` |
| `api` | `blueprints/api.py` | `POST /api/agregar_pedido`, `/api/confirmacion`, `/api/cambiar_estado_a_enlace` |
| `dashboard` | `blueprints/dashboard.py` | `GET /dashboard`, `/dashboard/monitor`, y endpoints de gestión |
| `picker` | `blueprints/picker.py` | `GET /picker`, `/picker/mis-pedidos`, `/picker/item/<id>/estado` |
| `repartidor` | `blueprints/repartidor.py` | `GET /repartidor`, `/repartidor/mis-pedidos`, `/repartidor/cierre` |
| `productos` | `blueprints/productos.py` | `GET /productos`, endpoints admin |

---

## Máquinas de estado (`states.py`)

### EstadoRegistro (Redis, flujo WhatsApp)
```
SALUDO_INICIAL → ESPERANDO_CONFIRMACION → ESPERANDO_NOMBRE → ESPERANDO_DIRECCION → CONFIRMANDO_DIRECCION → (guardado en BD)
```

### EstadoPedido (SQL Server, ciclo de vida completo)
```
PENDIENTE → ENLACE → ENLACE2 → CONFIRMANDO_PAGO → PAGADO ┐
                             ↘ CONTRA_REEMBOLSO           ├→ EN_PREPARACION → PREPARADO → EN_REPARTO → ENTREGADO
                                                          ↓
                                                     CANCELADO / REEMBOLSADO
```
Estados terminales: `ENTREGADO`, `CANCELADO`, `REEMBOLSADO`

### EstadoPicking y EstadoReparto
```
EstadoPicking: PENDIENTE → EN_PROCESO → COMPLETADO | CON_INCIDENCIAS | CANCELADO
EstadoReparto: PENDIENTE → ASIGNADO → EN_CAMINO → ENTREGADO | NO_ENTREGADO | CANCELADO
```

**Nunca cambiar estado directamente en el modelo** — usar `gestor_pedidos.actualizar_estado()` que valida la transición y registra en `HistorialEstadoPedido`.

---

## Managers principales

### `GestorPedidos` (`managers/gestor_pedidos.py`)
- `iniciar_pedido(id, direccion, telefono)` — crea el pedido en BD
- `actualizar_estado(pedido_id, nuevo_estado)` — valida transición + audit trail
- `cancelar_pedido(pedido_id, motivo, empleado_id)` — cancela y registra en `AuditLog`
- `eliminar_item` / `sustituir_item` — modificaciones de items con audit log
- Usa `tenacity` con 3 reintentos (1s espera)

### `GestorDashboard` (`managers/gestor_dashboard.py`)
- `metricas()` — pedidos_hoy, ingresos, tiempos medios, cancelaciones_hoy, ingresos_por_metodo
- `alertas()` — pedidos en estado demasiado tiempo, incidencias abiertas
- `pickings_del_picker(picker_id)` — devuelve items_total, items_listos, items_pendientes, picking_completo
- `marcar_entregado(reparto_id)` — tiene guard: si `forma_pago in ('efectivo','tarjeta')` y `metodo_cobro is None` → error
- `monitor_empleados()`, `eventos(limit)`, `mapa()`

### `GestorUsuarios` (`managers/gestor_usuarios.py`)
- `verificar_usuario(numero_cliente)` — devuelve ORM o None
- `guardar_usuario(numero_cliente, nombre, direccion)`

### `GestorProductos` (`managers/gestor_productos.py`)
- `obtener_productos()` — catálogo para el menú
- `descontar_stock_picking(items)` — batch tras completar picking

### `RedisManager` (`managers/gestor_redis.py`)
- Singleton: `redismanager` (importar desde `managers.gestor_redis`)
- `get/set/delete` con reintentos tenacity
- `bloquear_usuario(numero, duracion)` / `esta_bloqueado(numero)` — rate-limiting

---

## Servicios externos (`services/`)

- **`twilio_service.py`** — `enviar_mensaje_whatsapp(mensaje, destinatario)`, cliente singleton cacheado
- **`token_service.py`** — `generar_token_temporal(usuario_datos)` → token 7 chars, TTL 24h en Redis
- **`maps_service.py`** — geocodificación y validación de direcciones (Google Maps)
- **`services/__init__.py`** — exporta singletons: `gestor_pedidos`, `gestor_usuarios`, `gestor_productos`, `gestor_dashboard`, `cache` (alias de `redismanager`), `get_monei()`

---

## Redis — qué almacena

| Clave | Contenido | TTL |
|-------|-----------|-----|
| `<numero_cliente>` | JSON estado de registro `{estado, nombre, direccion}` | Sin TTL |
| `<token>` | JSON datos de usuario para menú | 24h |
| `bloqueo:<numero>` | `"1"` (usuario bloqueado por rate-limit) | 4s |

---

## Base de datos

- **Motor:** SQL Server via `mssql+pyodbc`
- **ORM:** SQLAlchemy 2.x con session por request (`g.db`)
- **Inicialización:** `database.conectar_bd1()` — crea todas las tablas incluida `AuditLog`
- **Session:** acceder via `get_db()` o la propiedad `session` de cada manager
- **No usar `db.session` global** — cada request tiene su propia sesión en `flask.g`

### Modelos clave

| Modelo | Tabla | Notas |
|--------|-------|-------|
| `Pedido` | `pedidos` | `PedidoID` (PK), `forma_pago` en minúsculas (`online`/`efectivo`/`tarjeta`) |
| `Usuario` | `usuarios` | `numero_cliente` es el identificador WhatsApp |
| `Empleado` | `empleados` | `password_hash` (werkzeug), `rol_id` FK a `Rol` |
| `PickingPedido` + `PickingItem` | `picking_*` | Uno por pedido; items reflejan `PedidoDetalle` |
| `Reparto` | `repartos` | `metodo_cobro`, `importe_cobrado`, `hora_entrega_real` |
| `HistorialEstadoPedido` | `historial_estados_pedido` | Timestamps de cada transición — fuente para métricas |
| `AuditLog` | `audit_log` | Acciones de empleados (cancelar, eliminar item, sustituir) |

---

## Tests

```bash
pytest -v --tb=short          # Suite completa
pytest tests/test_webhook.py  # Archivo específico
pytest -k "test_metricas"     # Por nombre
```

**Cómo funcionan:**
- `tests/conftest.py` parchea `redis.Redis` con `fakeredis.FakeRedis` **antes** de cualquier import
- App fixture con `TESTING=True` — desactiva Sentry y validación de firma Twilio
- No hay SQL Server en CI: tests que necesitan BD usan `inspect.getsource()` o capturan `OperationalError` con `pass`
- Tests de managers con BD se mockean via `patch.object(type(manager), 'session', new_callable=PropertyMock)`

**Archivos de test:**
`test_webhook.py`, `test_menu.py`, `test_api_pedido.py`, `test_registro.py`, `test_mensajes_registrados.py`, `test_gestor_pedidos.py`, `test_gestor_usuarios.py`, `test_gestor_dashboard.py`, `test_repartidor.py`, `test_picker.py`, `test_token_service.py`, `test_states.py`, `test_database.py`

**3 tests pre-existentes fallan** (`TestWebhookMonei`) — son conocidos y no bloquean.

---

## Variables de entorno requeridas

```bash
# Twilio (WhatsApp)
TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN
TWILIO_WHATSAPP_NUMBER

# Monei (pagos)
MONEI_API_KEY
MONEI_WEBHOOK_SECRET

# Google Maps
GOOGLE_MAPS_API_KEY

# Flask
SECRET_KEY
PUBLIC_URL            # URL pública (ngrok en dev, dominio real en prod)

# SQL Server
SQL_SERVER            # default: localhost,1433
SQL_DATABASE          # default: pruebabot
SQL_UID
SQL_PWD

# Redis
REDIS_HOST            # default: localhost
REDIS_PORT            # default: 6379
REDIS_DB              # default: 0

# Sentry
SENTRY_DSN

# Otros
INTERNAL_API_TOKEN    # Token para endpoints internos de cambio de estado
CUSTOMER_SUPPORT_PHONE
```

---

## Convenciones de código

- **Logging:** `logger = logging.getLogger(__name__)` al nivel de módulo, siempre. Usar `%`-formatting: `logger.info("msg %s", var)` — nunca f-strings en logger.
- **Eventos de negocio** se loguean con prefijos: `REGISTRO_COMPLETADO`, `PEDIDO_INICIADO`, `CARRITO_CONFIRMADO`, `PAGO_INICIADO`
- **Transiciones de estado** solo via `gestor_pedidos.actualizar_estado()` — nunca escribir `pedido.Estado = ...` directamente
- **Sentry SDK v2:** usar `sentry_sdk.get_current_scope()` — `push_scope()` fue eliminado en v2
- **`forma_pago`** en `Pedido` es minúsculas: `'online'`, `'efectivo'`, `'tarjeta'` — no usar mayúsculas ni enum
- **Guard cobro:** `marcar_entregado` en `GestorDashboard` rechaza si `forma_pago in ('efectivo','tarjeta')` y `reparto.metodo_cobro is None`

---

## Estado del proyecto

**Rama activa:** `refactorizar-estructura`
**Plan en curso:** `docs/superpowers/plans/2026-03-19-produccion-panchi-bot.md`

Fases completadas: 1 (base), 2 (logs/métricas), 3 (pulido de interfaces)
Pendiente: Fase 4 — Hardening (Tasks 11-15: auth PIN, tenacity Twilio, env vars validation, docker-compose/health, observabilidad)

### LEGACY-1 (acción pendiente externa)
Una vez que el dashboard de Monei esté configurado para apuntar a `/webhook/monei`, eliminar la ruta legacy `/webhoo/monei` de `blueprints/webhook.py:90`. Trigger: confirmación del proveedor de que la URL está actualizada.
