# Panchi-Bot — Guía para Claude

Sistema de pedidos para restaurante vía WhatsApp (Twilio). Los clientes se registran o reciben un enlace de menú, confirman su carrito y pagan online (Monei) o contra reembolso. El personal gestiona preparación (picker), reparto y supervisión desde paneles web internos.

---

## Comandos esenciales

```bash
pytest -v --tb=short        # Tests (siempre antes de commit)
python main.py              # Servidor dev — http://0.0.0.0:5000
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
| `auth` | `blueprints/auth.py` | `GET/POST /auth/login`, `POST /auth/logout` |
| `dashboard` | `blueprints/dashboard.py` | `GET /dashboard`, `/dashboard/monitor`, endpoints de gestión |
| `picker` | `blueprints/picker.py` | `GET /picker`, `/picker/mis-pedidos`, `/picker/cola`, `/picker/item/<id>/estado` |
| `repartidor` | `blueprints/repartidor.py` | `GET /repartidor`, `/repartidor/mis-pedidos`, `/repartidor/cierre` |
| `empleado` | `blueprints/empleado.py` | `GET /empleado`, `/empleado/perfil`, `/empleado/estado`, `/empleado/turno-hoy`, `/empleado/checkin` |
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

| Manager | Archivo | Responsabilidad |
|---------|---------|-----------------|
| `GestorPedidos` | `managers/gestor_pedidos.py` | CRUD pedidos, transiciones de estado, cancelaciones, audit log. Usa tenacity (3 reintentos). |
| `GestorDashboard` | `managers/gestor_dashboard.py` | Métricas, alertas, monitor de empleados, mapa, pickings, repartos sin asignar. |
| `GestorEmpleado` | `managers/gestor_empleado.py` | Perfil, estado operativo, turno, métricas individuales, capacidades, check-in. |
| `GestorUsuarios` | `managers/gestor_usuarios.py` | Verificar y guardar clientes WhatsApp. |
| `GestorProductos` | `managers/gestor_productos.py` | Catálogo para el menú, descuento de stock tras picking. |
| `RedisManager` | `managers/gestor_redis.py` | get/set/delete con reintentos, rate-limiting por número de cliente. Singleton: `redismanager`. |

---

## Base de datos — lógica y relaciones

### Sesión por request
`get_db()` crea (o reutiliza) una sesión SQLAlchemy en `flask.g` para cada request y la cierra en `teardown_appcontext`. **No usar `db.session` global.** En managers, acceder siempre via `self.session` (property que llama a `get_db()`).

### Flujo de datos de un pedido
```
Usuario ──< Pedido ──< PedidoDetalle >── Producto
                 │
                 ├──< PickingPedido ──< PickingItem >── PedidoDetalle
                 │         └── Empleado (picker)
                 │
                 └──  Reparto
                           └── Empleado (repartidor)
```

1. **Pedido + PedidoDetalle** — se crean cuando el cliente confirma el carrito. `PedidoID` arranca en 2000 (IDENTITY).
2. **PickingPedido / PickingItem** — se crean automáticamente al pasar a `EN_PREPARACION`. Cada `PickingItem` espeja un `PedidoDetalle`. El picker los marca: `pendiente → encontrado | sin_stock | sustituido`.
3. **Reparto** — se crea con estado `PENDIENTE` al completar el picking. El repartidor lo reclama (`ASIGNADO`), sale (`EN_CAMINO`) y cierra la entrega (`ENTREGADO`).
4. **Pago** — registro de cada intento Monei. Un pedido puede tener varios intentos (reintentos de pago).

### Trazabilidad y auditoría
- `HistorialEstadoPedido` — un registro por cada transición de estado. Es la fuente de métricas de tiempos.
- `AuditLog` — acciones de empleados: `cancelar_pedido`, `eliminar_item`, `sustituir_item`.

### Cobro presencial (repartidor)
`Reparto` tiene `metodo_cobro`, `importe_cobrado`, `cambio_devuelto`, `importe_efectivo`, `importe_tarjeta`. Solo se rellenan si `forma_pago` es `efectivo` o `tarjeta`. **Guard:** `marcar_entregado` falla si `forma_pago in ('efectivo','tarjeta')` y `metodo_cobro is None`.

### Campos legacy a evitar en código nuevo
- `Producto.Categoria` (String) → usar `Producto.categoria_id` (FK)
- `Empleado.Puesto` (String) → usar `Empleado.rol_id` (FK a `Rol`)

---

## Convenciones de código

- **Logging:** `logger = logging.getLogger(__name__)` al nivel de módulo. Usar `%`-formatting — nunca f-strings en logger.
- **Eventos de negocio** con prefijos: `REGISTRO_COMPLETADO`, `PEDIDO_INICIADO`, `CARRITO_CONFIRMADO`, `PAGO_INICIADO`
- **Transiciones de estado** solo via `gestor_pedidos.actualizar_estado()` — nunca `pedido.Estado = ...` directamente.
- **Sentry SDK v2:** `sentry_sdk.get_current_scope()` — `push_scope()` fue eliminado en v2.
- **`forma_pago`** en minúsculas: `'online'`, `'efectivo'`, `'tarjeta'`.

---

## Tests

```bash
pytest -v --tb=short          # Suite completa
pytest tests/test_webhook.py  # Archivo específico
pytest -k "test_metricas"     # Por nombre
```

- `conftest.py` parchea Redis con `fakeredis.FakeRedis` antes de cualquier import.
- App fixture con `TESTING=True` — desactiva Sentry y validación de firma Twilio.
- Managers con BD se mockean via `patch.object(type(manager), 'session', new_callable=PropertyMock)`.
- **3 tests pre-existentes fallan** (`TestWebhookMonei`) — conocidos, no bloquean.

---

## Estado del proyecto

**Rama activa:** `refactorizar-estructura`

Plan de producción `docs/superpowers/plans/2026-03-19-produccion-panchi-bot.md` completado al 100%. Features posteriores al plan: cola de pickers, cola de repartidores, gestión de empleados (`/empleado`), quinela.

### LEGACY-1 (acción pendiente externa)
Una vez que el dashboard de Monei esté configurado para apuntar a `/webhook/monei`, eliminar la ruta legacy `/webhoo/monei` de `blueprints/webhook.py:90`. Trigger: confirmación del proveedor de que la URL está actualizada.
