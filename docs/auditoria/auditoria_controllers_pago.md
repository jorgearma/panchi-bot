# Auditoría de `controllers/pago.py`

> Auditoría técnica estricta. Fecha: 2026-04-07.
> Archivos analizados: `controllers/pago.py`, `controllers/pago_notifier.py`, `services/monei_service.py`, `states.py`.

---

## 1. Rol del archivo

**Responsabilidad principal:** Orquestar la creación de pedidos pagados — validar el carrito contra la DB, llamar a Monei (online) o saltar ese paso (efectivo), y delegar la transición de estado al manager.

**Qué debería hacer:** Coordinar la secuencia validar → pagar externamente → persistir, manteniendo la consistencia de estado ante fallos parciales.

**Qué no debería hacer:** Hablar directamente con Redis, construir mensajes WhatsApp, o contener lógica de routing HTTP.

**Dependencias clave:** `gestor_pedidos`, `gestor_productos`, `monei_service.crear_pago`, `pago_notifier._enviar_confirmacion_efectivo`, `EstadoPedido`.

**Nivel de criticidad:** Crítico — es el punto donde se crea el cobro real o se compromete un pedido contra reembolso.

---

## 2. Lo que hace bien

- **Validación de precio en servidor** (`_validar_carrito`, líneas 13–41): recalcula el total desde precios de BD, no confía en el importe enviado por el cliente.
- **Orden deliberado Monei-antes-de-DB** (líneas 86–88, comentado): si Monei falla, el pedido sigue en `ENLACE2` y el reintento es limpio.
- **Guard de idempotencia en `iniciar_pago`** (líneas 66–68): si el pedido ya está en `CONFIRMANDO_PAGO`, devuelve la URL existente sin crear un segundo pago.
- **Resiliencia en WhatsApp** (líneas 175–182): el fallo de notificación no revierte el pedido; el try/except es intencional y tiene log con `exc_info`.
- **Dependencias inyectadas**: todos los managers, monei y public_url se reciben como parámetros — muy testeable.
- **Tipos de excepción correctos**: captura `SQLAlchemyError` + `RetryError` donde toca, sin capturar `Exception` genérica en paths críticos.
- **Validación defensiva de `cantidad`** (línea 28): rechaza `bool`, enteros negativos y cero antes de llegar a la DB.

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** Rendimiento / diseño
**Severidad:** Media

**Problema:** `_validar_carrito` hace una query de DB por cada producto del carrito (bucle N+1).

**Evidencia:**
```python
# línea 31
producto_db = gestor_productos.obtener_producto_por_codigo(codigo)
```
Llamado dentro del `for item in productos_recibidos` de la línea 25.

**Impacto real:** Para un carrito de 8 ítems distintos se hacen 8 queries secuenciales. Bajo SQL Server con latencia de red, esto acumula tiempo de respuesta visible para el cliente.

**Recomendación mínima concreta:** Recoger todos los `codigo` únicos antes del bucle y hacer una sola consulta batch (`obtener_productos_por_codigos([...])`) si el manager lo soporta o se añade. Si no vale la pena refactorizar el manager ahora, documentarlo como deuda.

---

### Hallazgo 2

**Tipo:** Manejo de errores
**Severidad:** Media

**Problema:** Las llamadas al manager dentro de `_validar_carrito` no están protegidas por try/except. Si `gestor_productos.obtener_producto_por_codigo` lanza `SQLAlchemyError` o `RetryError`, la excepción se propaga sin capturar hacia el blueprint.

**Evidencia:**
```python
# línea 31 — sin try/except
producto_db = gestor_productos.obtener_producto_por_codigo(codigo)
```
Contrasta con las líneas 59–61 y 141–144, donde sí se captura el mismo tipo de error en llamadas al manager.

**Impacto real:** Un error transitorio de SQL Server durante la validación del carrito provoca un 500 no controlado que llega al blueprint. Según el patrón conocido del proyecto, Meta reintentará ante cualquier no-2xx desde el webhook; si el blueprint envuelve en 500, se producirá reintento.

**Recomendación mínima concreta:**
```python
try:
    producto_db = gestor_productos.obtener_producto_por_codigo(codigo)
except (SQLAlchemyError, RetryError) as e:
    logger.error("_validar_carrito: DB error producto=%s: %s", codigo, e)
    return None, None, "Error de base de datos al validar el carrito"
```

---

### Hallazgo 3

**Tipo:** Observabilidad
**Severidad:** Baja

**Problema:** El path `not ok` de `iniciar_pago_efectivo` (línea 171–172) no tiene log. Es una falla silenciosa.

**Evidencia:**
```python
# líneas 171–172
if not ok:
    return False, "Error al registrar el pedido contra reembolso"
```
Contrasta con el mismo path en `iniciar_pago` (líneas 114–119), que sí registra `CONFIRMAR_PAGO_ONLINE_FALLIDO` con `pedido_id` e importe.

**Impacto real:** Si `confirmar_pago_efectivo` devuelve `False` por razón interna (transición de estado rechazada, constraint de DB), no queda rastro en los logs. Imposible distinguir en producción de una excepción silenciosa.

**Recomendación mínima concreta:**
```python
if not ok:
    logger.error(
        "CONFIRMAR_PAGO_EFECTIVO_FALLIDO pedido=%s",
        pedido_id,
    )
    return False, "Error al registrar el pedido contra reembolso"
```

---

### Hallazgo 4

**Tipo:** Consistencia de estado
**Severidad:** Media

**Problema:** `iniciar_pago_efectivo` no tiene guard de idempotencia equivalente al de `iniciar_pago`. Si se llama dos veces concurrentemente mientras el pedido está en `ENLACE2`, ambas llamadas pasan el check de línea 149 y ambas intentan escribir.

**Evidencia:**
```python
# línea 149 — única protección
if pedido_activo.Estado != EstadoPedido.ENLACE2:
    return False, "El pedido no está listo para confirmar"
```
No existe el equivalente a las líneas 66–68 de `iniciar_pago` que maneja `CONTRA_REEMBOLSO` ya creado.

**Impacto real:** La segunda escritura fallará probablemente por la transición de estado en el manager (ENLACE2 → CONTRA_REEMBOLSO ya consumida), pero no hay log ni respuesta diferenciada. En un escenario de doble clic o reintento del cliente, el usuario ve un error en la segunda llamada sin saber si el pedido quedó confirmado.

**Recomendación mínima concreta:**
```python
if pedido_activo.Estado == EstadoPedido.CONTRA_REEMBOLSO:
    logger.info("EFECTIVO_YA_CONFIRMADO pedido=%s usuario=%s", pedido_activo.PedidoID, user_id)
    return True, f"{public_url}/pago_confirmado?pedido_id={pedido_activo.redisID}"

if pedido_activo.Estado != EstadoPedido.ENLACE2:
    ...
```

---

### Hallazgo 5

**Tipo:** Consistencia de estado (posible riesgo no confirmado)
**Severidad:** Media

**Problema:** Si `confirmar_pago_online` falla en DB después de que Monei creó el pago con éxito (líneas 104–113), el pago de Monei queda huérfano. El comment en línea 102 dice "idempotente: re-running won't duplicate lines", pero si el manager falla antes de persistir el estado, el reintento del usuario creará un **segundo pago en Monei** para el mismo `pedido_id`.

**Evidencia:**
- El guard de idempotencia de líneas 66–68 solo actúa si el estado ya llegó a `CONFIRMANDO_PAGO`.
- Si la DB falla entre la llamada a Monei (línea 88) y el commit del estado (línea 105), el pedido sigue en `ENLACE2` y el reintento pasa el guard y crea un nuevo pago Monei.

**Impacto real:** Monei puede recibir dos pagos para el mismo `order_id`. El comportamiento de Monei ante `order_id` duplicado no está confirmado desde este archivo — podría rechazarlo o crear dos cobros.

**Recomendación mínima concreta:** Verificar en la documentación de Monei si `order_id` duplicado es rechazado (idempotencia del lado de Monei). Si no lo es, añadir un campo `monei_payment_id` en la tabla de pedidos y verificar su presencia antes de llamar a Monei en el reintento.

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|---|---|
| Excepción no capturada en `_validar_carrito` | Caída transitoria de SQL Server durante validación de carrito → 500 al blueprint → Meta reintenta → posible procesamiento doble |
| Pago Monei huérfano | DB falla tras crear pago Monei → pedido vuelve a ENLACE2 → reintento crea segundo pago Monei |
| Fallo silencioso en efectivo | `confirmar_pago_efectivo` devuelve `False` sin log → imposible diagnosticar en producción |
| N+1 queries en carrito grande | Menú de 10+ ítems distintos → latencia acumulada visible al cliente |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)

1. **Hallazgo 2** — añadir try/except en `_validar_carrito` alrededor de la llamada al manager (5 líneas, alto impacto operativo).
2. **Hallazgo 3** — añadir log en el path `not ok` de `iniciar_pago_efectivo` (1 línea).
3. **Hallazgo 4** — añadir guard de idempotencia para `CONTRA_REEMBOLSO` en `iniciar_pago_efectivo` (4 líneas).
4. **Hallazgo 5** — investigar comportamiento de Monei ante `order_id` duplicado; documentar o mitigar.

### Qué NO tocar todavía

- El orden Monei-antes-de-DB: es una decisión de diseño correcta y documentada.
- La separación en `pago_notifier.py`: es correcta, no mezclar de vuelta.
- La validación de `bool` en cantidad: no es redundante, Python trata `True`/`False` como `1`/`0`.
- La estructura de inyección de dependencias: funciona bien para tests.

---

## 6. Tests que deberían existir

- `test_validar_carrito_vacio` — devuelve error cuando la lista de productos está vacía.
- `test_validar_carrito_cantidad_bool` — rechaza `True`/`False` como cantidad.
- `test_validar_carrito_producto_no_encontrado` — devuelve error cuando el manager no encuentra el producto.
- `test_validar_carrito_db_error` — captura `SQLAlchemyError` del manager y devuelve error (actualmente no pasa — Hallazgo 2).
- `test_iniciar_pago_idempotente_confirmando_pago` — si el pedido ya está en `CONFIRMANDO_PAGO`, devuelve la URL existente sin llamar a Monei.
- `test_iniciar_pago_monei_falla_estado_no_cambia` — si Monei devuelve error, el pedido sigue en `ENLACE2`.
- `test_iniciar_pago_db_falla_tras_monei` — si el commit falla, la función devuelve `False` y el error queda en log.
- `test_iniciar_pago_efectivo_idempotente` — si el pedido ya está en `CONTRA_REEMBOLSO`, devuelve `True` sin doble escritura (actualmente no pasa — Hallazgo 4).
- `test_iniciar_pago_efectivo_whatsapp_falla_no_revierta` — si `_enviar_confirmacion_efectivo` lanza, la función sigue devolviendo `True`.
- `test_iniciar_pago_estado_incorrecto` — pedido en estado distinto a `ENLACE2`/`CONFIRMANDO_PAGO` es rechazado.

---

## 7. Veredicto final

**Estado general del archivo:** Sólido en estructura y en los caminos felices. Los problemas conocidos están en los caminos de error (excepción no capturada en validación) y en la idempotencia de efectivo.

**¿Bloquea crecimiento?** No — la arquitectura de inyección de dependencias y la separación de responsabilidades son correctas.

**¿Bloquea testeo?** No — todas las dependencias son inyectables. Sí hay un test que no puede escribirse correctamente hasta resolver el Hallazgo 2.

**¿Tiene riesgo operativo real?** Sí — el Hallazgo 2 (excepción no capturada en `_validar_carrito`) puede producir 500s no gestionados en picos de carga de SQL Server. El Hallazgo 5 (pago Monei huérfano) requiere verificación externa pero podría resultar en cobros duplicados.
