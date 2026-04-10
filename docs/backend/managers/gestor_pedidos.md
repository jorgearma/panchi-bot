# `managers/pedidos/` — GestorPedidos

> Documentación de referencia. Fecha: 2026-04-09.
> Archivos cubiertos: `base.py`, `workflow_mixin.py`, `lifecycle_mixin.py`, `items_mixin.py`, `gestor_pedidos.py`.
> Consumidores leídos: `controllers/pago.py`, `controllers/pedido.py`, `controllers/mensajes_registrados.py`, `controllers/registro.py`, `services/inbound_whatsapp.py`, `blueprints/api/cart.py`, `blueprints/api/tracking.py`, `blueprints/dashboard/pedidos.py`.

---

## Responsabilidad

Único punto de acceso a la tabla `Pedido` y sus entidades relacionadas.
Centraliza la máquina de estados del pedido, la creación y modificación de líneas, y la gestión de pagos.

**Lo que NO hace:** no valida inputs de usuario (eso vive en schemas/ y controllers/), no envía mensajes WhatsApp, no notifica al cliente.

---

## Estructura del paquete

```
managers/pedidos/
  base.py           → Constantes compartidas y helpers sin estado
  workflow_mixin.py → Motor de transiciones de estado
  lifecycle_mixin.py → Ciclo de vida temprano del pedido
  items_mixin.py    → Modificaciones manuales de líneas
managers/gestor_pedidos.py → Assembler (API pública)
```

**MRO de composición:**
```python
class GestorPedidos(
    GestorPedidosItemsMixin,     # 1.º
    GestorPedidosWorkflowMixin,  # 2.º
    GestorPedidosLifecycleMixin, # 3.º
    GestorPedidosBase,           # 4.º
)
```

---

## base.py

### Constantes

| Nombre | Valor | Uso |
|--------|-------|-----|
| `_MOTIVOS_CANCELACION` | set de 6 strings | Valida el campo `motivo` en `cancelar_pedido` |
| `_ESTADOS_MODIFICABLES` | `{PAGADO, CONTRA_REEMBOLSO, EN_PREPARACION}` | Guard en `eliminar_item` y `sustituir_item` |

### Helpers

| Método | Devuelve | Notas |
|--------|----------|-------|
| `session` (property) | `Session` de SQLAlchemy | Llama a `get_db()` en cada acceso — sin caché |
| `_to_decimal(value)` | `Decimal` | Normaliza cualquier numérico; trata `None` como `0` |

---

## workflow_mixin.py

Motor de la máquina de estados. **Todo cambio de estado del pedido pasa por `_set_estado`.**

### `_set_estado(pedido, nuevo_estado, notas, empleado_id) → bool`

Método privado, **sin commit**. Valida la transición contra `states.transicion_valida_pedido`, actualiza `pedido.Estado`, inserta en `HistorialEstadoPedido`, y llama a `_asegurar_picking_si_procede` como side-effect. Devuelve `False` si la transición no es válida (no lanza). Los callers atómicos lo usan antes de su propio `commit`.

### `actualizar_estado(pedido_id, nuevo_estado, notas, empleado_id) → bool`

`@retry(3, wait=1s, SQLAlchemyError)`. Wrapper público de `_set_estado` con commit propio. Devuelve `False` si el pedido no existe o la transición es inválida. Relanza `SQLAlchemyError` tras 3 intentos.

**Consumidores:** `blueprints/api/cart.py` (sin try/except — acepta el False silencioso en `volver_al_menu` y `cambiar_estado_a_enlace`).

### `fijar_carrito_confirmado(pedido_id, redis_id, lat, lng) → bool`

`@retry(3, wait=1s, SQLAlchemyError)`. Atómico: guarda `redisID` + coordenadas + transición a `ENLACE2` en un único commit.

**Consumidor:** `controllers/carrito.py` (no leído en detalle, pero referenciado desde `blueprints/api/cart.py`).

### `_asegurar_picking_si_procede(pedido, nuevo_estado) → None`

Side-effect automático al entrar en `PAGADO` o `CONTRA_REEMBOLSO`. Crea un `PickingPedido` si no existe ya. En modo `warehouse` (APP_MODE) crea además un `PickingItem` por cada línea del pedido. En modo `restaurant` no crea items. Idempotente: no actúa si ya existe un picking.

El import de `config` es lazy (`import config as app_config` dentro del método) — esto es un defecto conocido de diseño (ver auditoría), no un patrón a replicar.

### `procesar_pago_confirmado(pedido_id, importe_euros, referencia_externa, datos_raw) → bool`

**Sin `@retry`.** Idempotente por `referencia_externa`: si ya existe un `Pago` con esa referencia, devuelve `True` sin hacer nada. Valida que `importe_euros` coincida con `Pedido.Total` al céntimo; rechaza con `False` si difiere. Atómico: transición a `PAGADO` + insert `Pago` en un único commit. Captura `SQLAlchemyError` internamente y devuelve `False`.

**Consumidor:** `services/inbound_whatsapp.py:192` — llama sin comprobar el valor de retorno. Un `False` silencioso (por ejemplo, importe incorrecto o error de BD) no impide que se envíe el mensaje WhatsApp al cliente.

### `registrar_pago(pedido_id, importe_euros, referencia_externa, datos_raw) → bool`

Inserta un `Pago` sin cambiar el estado del pedido. **No usar para confirmar pagos Monei** — para eso existe `procesar_pago_confirmado`. Captura `SQLAlchemyError` internamente y devuelve `False`.

### `guardar_forma_pago / guardar_coordenadas / guardar_redis_id`

Métodos simples de escritura sin `@retry` y sin manejo de errores — cualquier excepción sube al caller. Devuelven `True/False` según si el pedido existe.

---

## lifecycle_mixin.py

Ciclo de vida temprano: creación del pedido, gestión de enlaces, líneas de producto, y consultas de lectura.

### `iniciar_pedido(id, direccion, telefono) → int`

`@retry(3, wait=1s, SQLAlchemyError|OperationalError)`. Crea un `Pedido` en estado `PENDIENTE` y devuelve `PedidoID`. Relanza la excepción tras 3 intentos.

**Consumidor:** `controllers/mensajes_registrados.py:47` captura `(SQLAlchemyError, OperationalError)`.

### `iniciar_enlace(pedido_id, enlace) → bool`

`@retry(3, wait=1s, SQLAlchemyError|OperationalError)`. Atómico: guarda `Pedido.enlace` + transición a `ENLACE` en un commit. Reemplaza el antipatrón de dos commits separados que podía dejar el pedido en `ENLACE` sin enlace almacenado.

**Consumidor:** `controllers/pedido.py:58` captura `(ValueError, SQLAlchemyError, OperationalError)`.

### `hay_pedido_pendiente(cliente_id) → bool`

`@retry(3, wait=1s, SQLAlchemyError)`. Consulta simple. No usado en el flujo principal actual — solo en tests.

### `obtener_pedido_mas_reciente(id_usuario) → Pedido | None`

`@retry(3, wait=1s, SQLAlchemyError)`. Devuelve el pedido activo más reciente del usuario **excluyendo estados terminales** (`ENTREGADO`, `CANCELADO`, `REEMBOLSADO`). Devuelve `None` si no hay pedido activo. Relanza tras 3 intentos.

**Consumidores:** `controllers/mensajes_registrados.py:75` y `controllers/pago.py:77/160` capturan `(SQLAlchemyError, RetryError)`. `blueprints/api/cart.py:80` llama sin try/except.

### `_reemplazar_detalles(pedido, productos) → bool`

Privado, **sin commit**. Borra todas las `PedidoDetalle` existentes del pedido e inserta las nuevas en una sola operación. Idempotente: reintentos del worker RQ no producen líneas duplicadas. Devuelve `False` si no hay ningún producto válido. El caller es responsable del commit.

### `agregar_productos_a_pedido(pedido_id, productos) → bool`

`@retry(3, wait=1s, SQLAlchemyError|OperationalError)`. Llama a `_reemplazar_detalles` y hace commit. Relanza tras 3 intentos.

### `confirmar_pago_online(pedido_id, productos, redirect_url, notas) → bool`

`@retry(3, wait=1s, SQLAlchemyError|OperationalError)`. Atómico: reemplaza líneas + guarda URL Monei + transición a `CONFIRMANDO_PAGO` en un commit. Debe llamarse **después** de crear el pago en Monei para que un fallo de BD no deje un pago comprometido sin estado en DB.

**Consumidor:** `controllers/pago.py:124` captura `(SQLAlchemyError, RetryError)`.

### `confirmar_pago_efectivo(pedido_id, productos, notas) → bool`

`@retry(3, wait=1s, SQLAlchemyError|OperationalError)`. Atómico: reemplaza líneas + `forma_pago = "efectivo"` + transición a `CONTRA_REEMBOLSO` en un commit.

**Consumidor:** `controllers/pago.py:191` captura `(SQLAlchemyError, RetryError)`.

### `obtener_seguimiento(redis_id) → dict | None`

Sin `@retry`. Busca el pedido por `Pedido.redisID` (no por `PedidoID`). Devuelve una proyección pública para la página de tracking: `{estado, forma_pago, reparto}`. `None` si no se encuentra.

**Consumidor:** `blueprints/api/tracking.py:15` sin try/except — un error de BD sube sin capturar.

### `obtener_pedido(pedido_id) → Pedido | None`

Sin `@retry`. Relanza `SQLAlchemyError` si la hay. Devuelve `None` con `logger.warning` si no existe.

**Consumidores:** `controllers/pedido.py:50` y `blueprints/api/cart.py:102` sin try/except para la segunda.

---

## items_mixin.py

Modificaciones manuales de pedidos activos (operaciones del dashboard). Todos los métodos capturan `SQLAlchemyError` internamente y devuelven una tupla de resultado — el caller no necesita try/except.

### `cancelar_pedido(pedido_id, motivo, empleado_id) → (bool, str, telefono | None)`

**Firma diferente al resto:** devuelve 3 valores. Valida el motivo contra `_MOTIVOS_CANCELACION`. Detecta automáticamente si el pedido va a `CANCELADO` o a `REEMBOLSADO` (si estaba `PAGADO`) usando `transicion_valida_pedido`. Registra en `HistorialEstadoPedido` y `AuditLog`. La notificación WhatsApp está desactivada (comentada) intencionalmente.

**Consumidor:** `blueprints/dashboard/pedidos.py:82` — solo desempaqueta `(ok, msg)`, ignora el teléfono.

### `eliminar_item(pedido_id, detalle_id, empleado_id) → (bool, str)`

Guard de estado: solo opera en `_ESTADOS_MODIFICABLES`. Impide eliminar el último item (debe cancelarse el pedido en su lugar). Recalcula `Pedido.Total` con `_recalcular_total`. Registra en `AuditLog`.

**Consumidor:** `blueprints/dashboard/pedidos.py:92`.

### `sustituir_item(pedido_id, detalle_id, producto_sustituto_id, cantidad_a_sustituir, empleado_id) → (bool, str)`

Sustitución total o parcial. Si `cantidad_a_sustituir < detalle.Cantidad`, divide la línea: la original conserva las unidades restantes y se crea una nueva `PedidoDetalle` para el sustituto. Si hay un `PickingPedido` activo, actualiza o crea el `PickingItem` correspondiente con estado `'sustituido'`. Recalcula total. Registra en `AuditLog`.

**Consumidor:** `blueprints/dashboard/pedidos.py:109`.

### `_recalcular_total(session, pedido) → None`

Privado, sin commit. Suma los `Subtotal` de todas las `PedidoDetalle` actuales del pedido y actualiza `Pedido.Total`.

---

## Tablas modificadas

| Tabla | Operaciones |
|-------|-------------|
| `Pedido` | Read/write en todos los mixins |
| `PedidoDetalle` | Insert/delete en `lifecycle_mixin`, `items_mixin` |
| `HistorialEstadoPedido` | Insert en `workflow_mixin` (vía `_set_estado`) e `items_mixin` (`cancelar_pedido`) |
| `AuditLog` | Insert en `items_mixin` (`cancelar_pedido`, `eliminar_item`, `sustituir_item`) |
| `Pago` | Read/insert en `workflow_mixin` |
| `Producto` | Read en `lifecycle_mixin`, `items_mixin` |
| `PickingPedido` | Read/insert en `workflow_mixin` (`_asegurar_picking_si_procede`) |
| `PickingItem` | Insert en `workflow_mixin` (modo warehouse), `items_mixin` (`sustituir_item`) |

---

## Contrato de errores

### Métodos con `@retry`

Relanza `SQLAlchemyError` o `OperationalError` tras 3 intentos (lo que `tenacity` convierte en `RetryError`). Los controllers deben capturar `(SQLAlchemyError, RetryError)`.

### Métodos sin `@retry` que relanzna

`obtener_pedido`, `obtener_seguimiento` — el caller recibe la excepción directa.

### Métodos que capturan internamente

`cancelar_pedido`, `eliminar_item`, `sustituir_item`, `procesar_pago_confirmado`, `registrar_pago` — capturan `SQLAlchemyError`, hacen rollback y devuelven `False` o `(False, msg)`. El caller no necesita try/except para estos.

---

## Patrones de diseño clave

1. **Staging sin commit:** `_set_estado` y `_reemplazar_detalles` nunca hacen commit. Los métodos atómicos (`iniciar_enlace`, `confirmar_pago_online`, `confirmar_pago_efectivo`, `fijar_carrito_confirmado`, `procesar_pago_confirmado`) los componen antes de un único `commit` final.

2. **Idempotencia:** `_reemplazar_detalles` (delete-then-insert) es seguro para reintentos del worker RQ. `procesar_pago_confirmado` comprueba `referencia_externa` antes de actuar, haciendo el webhook de Monei idempotente.

3. **Picking como side-effect:** `_asegurar_picking_si_procede` se invoca automáticamente dentro de `_set_estado`. Toda transición a `PAGADO` o `CONTRA_REEMBOLSO` crea el `PickingPedido` sin que el caller deba recordarlo.

4. **`registrar_pago` vs `procesar_pago_confirmado`:** son distintos. El primero solo inserta un `Pago`. El segundo hace la transición de estado + pago en un commit. No intercambiarlos.
