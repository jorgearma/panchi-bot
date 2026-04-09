# Auditoría de `managers/pedidos/items_mixin.py`

> Auditoría técnica estricta. Fecha: 2026-04-09.
> Archivos analizados: `managers/pedidos/items_mixin.py`, `managers/pedidos/base.py`, `states.py`, `models.py` (parcial), `services/whatsapp_service.py` (parcial — solo para confirmar la firma de `notificar_async`).

---

## 1. Rol del archivo

**Responsabilidad principal:** Modificaciones post-creación sobre un pedido existente: cancelación, eliminación de línea de producto, sustitución de línea de producto.

**Qué debería hacer:** Operaciones atómicas de escritura en DB que alteran el estado o el contenido de un pedido ya iniciado, con registro en `AuditLog` e `HistorialEstadoPedido`.

**Qué no debería hacer:** Importar servicios externos (WhatsApp). Enviar notificaciones directamente desde un manager.

**Dependencias clave:**
- `base.py` → `_MOTIVOS_CANCELACION`, `_ESTADOS_MODIFICABLES`, `self.session` (MRO implícito)
- `workflow_mixin.py` → `transicion_valida_pedido` se usa directamente desde `states` (no desde el mixin)
- `states.py` → `EstadoPedido`, `transicion_valida_pedido`
- `models.py` → `AuditLog`, `HistorialEstadoPedido`, `Pedido`, `PedidoDetalle`, `PickingItem`, `Producto`
- `services/whatsapp_service.py` → `notificar_async` (importado pero **no usado** — comentado)

**Nivel de criticidad:** Alto — `cancelar_pedido` es una operación irreversible en producción que toca estado financiero.

---

## 2. Lo que hace bien

- **Atomicidad en las tres operaciones:** `cancelar_pedido`, `eliminar_item` y `sustituir_item` concentran todos sus cambios en un único `commit`. Rollback explícito en todos los `except`. (l.85, l.131, l.257-282)
- **Validación de motivo de cancelación** (l.36-42): `motivo` se verifica contra `_MOTIVOS_CANCELACION` antes de tocar la DB. Previene valores arbitrarios en el campo `cancel_reason`.
- **Guarda contra eliminar el único item** (l.116-121): evita dejar un pedido sin líneas en lugar de cancelarlo.
- **Sustitución parcial bien implementada** (l.229-254): si `cantidad_a_sustituir < detalle.Cantidad`, divide la línea original en dos de forma correcta, manteniendo la cantidad restante en el detalle original.
- **Doble vía de cancelación** (l.49-58): `PAGADO` → `REEMBOLSADO`, resto de estados cancelables → `CANCELADO`. Respeta la máquina de estados de `states.py`.
- **AuditLog completo** en las tres operaciones con `json.dumps` de valores controlados.

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** errores  
**Severidad:** Alta

**Problema:** `cancelar_pedido` promete devolver una 3-tupla `(ok, msg, telefono_cliente)` según su docstring y sus paths de validación, pero el path de éxito (l.93) y el path de error de DB (l.96) devuelven solo una 2-tupla. Cualquier caller que desempaquete `ok, msg, telefono = gestor.cancelar_pedido(...)` lanzará `ValueError: not enough values to unpack` en el caso de éxito.

**Evidencia:**
```python
# líneas 37-41 — 3-tupla ✓
return (False, f"Motivo inválido...", None)

# línea 47 — 3-tupla ✓
return False, "Pedido no encontrado", None

# línea 53-56 — 3-tupla ✓
return (False, f"No se puede cancelar...", None)

# línea 93 — 2-tupla ✗  ← BUG
return True, f"Pedido #{pedido_id} cancelado ({nuevo_estado.value})"

# líneas 95-96 — 2-tupla ✗  ← BUG
return False, "Error de base de datos"
```

**Impacto real:** El bug está latente hoy porque la notificación al cliente está comentada (l.86-92) y probablemente ningún caller activo desempaqueta el tercer valor. En el momento en que se reactive la notificación o se añada un caller que use `telefono_cliente`, la aplicación crasheará en producción en el path de éxito — exactamente cuando la cancelación SÍ funcionó.

**Recomendación mínima concreta:** Añadir el `telefono_cliente` a los dos returns inconsistentes:
```python
# línea 93
return True, f"Pedido #{pedido_id} cancelado ({nuevo_estado.value})", pedido.TelefonoEntrega

# líneas 95-96
return False, "Error de base de datos", None
```

---

### Hallazgo 2

**Tipo:** diseño / acoplamiento  
**Severidad:** Media

**Problema:** El archivo importa `notificar_async` de `services/whatsapp_service` (l.9), cruzando la frontera arquitectónica `managers → services` que prohíbe el CLAUDE.md. La importación es viva aunque el uso esté comentado — en cada arranque del worker y del app se inicializa el módulo de Twilio solo por este import.

**Evidencia:**
```python
# línea 9
from services.whatsapp_service import notificar_async as _notificar

# líneas 86-92 — uso comentado
# motivo_label = _MOTIVOS_LABEL.get(motivo, motivo)
# _notificar(
#     pedido.TelefonoEntrega,
#     f"❌ Tu pedido #{pedido_id} ha sido cancelado...
```

**Impacto real:** Acopla este manager a Twilio/Meta en tiempo de importación. Si `whatsapp_service` falla al cargarse (credenciales mal configuradas en un entorno de test), este manager también falla. Bloquea tests unitarios que no quieran necesitar credenciales de WhatsApp.

**Recomendación mínima concreta:** Eliminar el import de la cabecera. Cuando se reactive la notificación, inyectar el servicio como dependencia o hacer el import lazy dentro del bloque que lo use:
```python
# dentro del método, solo si se reactiva
from services.whatsapp_service import notificar_async as _notificar
```

---

### Hallazgo 3

**Tipo:** observabilidad  
**Severidad:** Media

**Problema:** Ninguna de las tres operaciones registra `logger.info` en el path de éxito. Una cancelación, eliminación o sustitución de item son eventos de negocio auditables que deberían ser visibles en los logs de aplicación sin necesidad de consultar la tabla `AuditLog`.

**Evidencia:**
- `cancelar_pedido`: solo logs en `logger.warning` (l.48) y `logger.error` (l.95). Sin `logger.info` en éxito.
- `eliminar_item`: solo `logger.error` en l.153. Sin `logger.info` en éxito.
- `sustituir_item`: solo `logger.error` en l.298. Sin `logger.info` en éxito.

**Impacto real:** Al investigar un incidente no se puede reconstruir la secuencia de eventos desde los logs. Solo `AuditLog` (DB) tiene el rastro completo — si la DB está caída durante el incidente, no hay trazabilidad.

**Recomendación mínima concreta:** Un `logger.info` al final de cada `s.commit()` exitoso, con `pedido_id` y acción:
```python
logger.info("PEDIDO_CANCELADO pedido_id=%s motivo=%s estado=%s", pedido_id, motivo, nuevo_estado.value)
logger.info("ITEM_ELIMINADO pedido_id=%s detalle_id=%s", pedido_id, detalle_id)
logger.info("ITEM_SUSTITUIDO pedido_id=%s detalle_id=%s → producto_id=%s", pedido_id, detalle_id, producto_sustituto_id)
```

---

### Hallazgo 4

**Tipo:** consistencia  
**Severidad:** Baja

**Problema:** `sustituir_item` en modo sustitución parcial (l.229-254) crea un `PickingItem` nuevo con `estado='sustituido'` solo si `pedido.picking` existe y no está en estado terminal (l.244-253). Sin embargo, el `PedidoDetalle` nuevo sí se persiste siempre. Si el picking no existe o está terminado, el nuevo detalle no tiene `PickingItem` asociado, lo que puede dejar la vista del picker desincronizada respecto a los detalles reales del pedido.

**Evidencia:**
```python
# líneas 244-253
if pedido.picking and pedido.picking.estado not in ('completado', 'cancelado'):
    s.add(PickingItem(...))
# ← el nuevo PedidoDetalle existe siempre, PickingItem solo en algunos casos
```

**Impacto real:** Posible riesgo no confirmado — depende de si la vista del picker consulta `PedidoDetalle` directamente o solo vía `PickingItem`. Si consulta por `PickingItem`, el ítem sustituido en un pedido con picking completado no aparecerá en ninguna vista operativa.

**Recomendación mínima concreta:** Verificar en `blueprints/picker.py` o `managers/dashboard/` qué tabla consulta la vista del picker para los detalles del pedido. Si usa `PedidoDetalle` directamente, el comportamiento actual es correcto. Si usa `PickingItem`, añadir un `logger.warning` cuando se crea el detalle sin picking item correspondiente.

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|---|---|
| Crash al reactivar notificación de cancelación | Un developer descomenta el bloque de `_notificar` y el caller existente que desempaqueta 3 valores empieza a crashear en el path de éxito |
| Tests bloqueados por import de Twilio | En un entorno CI sin `TWILIO_ACCOUNT_SID`, el import de `whatsapp_service` puede fallar, rompiendo todos los tests que importen este mixin |
| Pérdida de trazabilidad en incidente | Una cancelación masiva por script o bug no deja rastro en logs de aplicación — solo en AuditLog DB |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)

1. **Hallazgo 1 (bug arity):** Dos líneas — añadir `pedido.TelefonoEntrega` y `None` a los returns inconsistentes. Riesgo cero, corrige un bug latente.
2. **Hallazgo 2 (import service):** Eliminar `from services.whatsapp_service import notificar_async as _notificar` de la cabecera. Si se reactiva la notificación, hacerlo lazy.
3. **Hallazgo 3 (observabilidad):** Añadir tres `logger.info` en los paths de éxito.

### Qué NO tocar todavía

- La lógica de sustitución parcial (Hallazgo 4): requiere verificar la vista del picker antes de cambiar el comportamiento.
- La ausencia de `@retry`: estas son acciones de operador desde el dashboard, no flujos de webhook. El operador puede reintentar manualmente. No es prioritario.
- La estructura de mixins: funciona correctamente.

---

## 6. Tests que deberían existir

- `test_cancelar_pedido_retorna_3_tupla_en_exito` — verifica que el path de éxito devuelve exactamente 3 valores con `telefono_cliente` no None.
- `test_cancelar_pedido_retorna_3_tupla_en_error_db` — mockea `session.commit` para lanzar `SQLAlchemyError` y verifica que la 3-tupla se mantiene.
- `test_cancelar_pedido_pagado_transiciona_a_reembolsado` — pedido en estado PAGADO debe quedar REEMBOLSADO, no CANCELADO.
- `test_cancelar_pedido_motivo_invalido_rechazado` — motivo fuera de `_MOTIVOS_CANCELACION` devuelve `(False, ..., None)` sin tocar la DB.
- `test_eliminar_item_unico_rechazado` — no permite eliminar el único item del pedido.
- `test_eliminar_item_recalcula_total` — verifica que `Total` se reduce correctamente tras eliminar una línea.
- `test_sustituir_item_parcial_divide_linea` — sustitución de `qty < detalle.Cantidad` crea dos `PedidoDetalle` con cantidades correctas.
- `test_sustituir_item_total_es_correcto_tras_sustitucion` — `Pedido.Total` tras sustitución coincide con la suma de `PedidoDetalle.Subtotal`.
- `test_import_no_requiere_credenciales_whatsapp` — importar el mixin en entorno de test sin `TWILIO_ACCOUNT_SID` no lanza excepción (valida que el import de service está eliminado).

---

## 7. Veredicto final

**Estado general del archivo:** Sólido en lógica de negocio y atomicidad. Un bug latente concreto (arity de la 3-tupla) y un import arquitectónicamente incorrecto que además bloquea tests.

**¿Bloquea crecimiento?** No directamente, pero el bug de arity bloqueará la reactivación de notificaciones al cliente.

**¿Bloquea testeo?** Sí — el import de `services/whatsapp_service` en la cabecera puede romper tests unitarios en entornos sin credenciales de WhatsApp configuradas.

**¿Tiene riesgo operativo real?** El bug de arity es latente (no activo hoy) pero está a una línea descomentada de causar un crash en producción en el flujo de cancelación.
