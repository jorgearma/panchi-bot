# Auditoría de `controllers/carrito.py`

> Auditoría técnica estricta. Fecha: 2026-04-07.
> Archivos analizados: `controllers/carrito.py`, `maps_module/__init__.py`, `states.py`.

---

## 1. Rol del archivo

**Responsabilidad principal:** Validar el carrito del cliente contra la BD, geocodificar la dirección, persistir la transición de estado en DB y guardar el carrito en Redis como caché.

**Qué debería hacer:** Coordinar la secuencia validar → geocodificar → escribir DB → escribir Redis, asegurando que la transición de estado quede protegida ante fallos parciales.

**Qué no debería hacer:** Hablar directamente con APIs externas más allá de `maps_module`, contener routing HTTP, ni decidir precios de negocio.

**Dependencias clave:** `gestor_productos.obtener_producto_por_codigo`, `pedidos_manager.fijar_carrito_confirmado`, `maps_module.geocodificar_direccion`, `cache` (Redis), `EstadoPedido`.

**Nivel de criticidad:** Alto — es el paso que fija el carrito y permite al cliente avanzar al pago.

---

## 2. Lo que hace bien

- **Orden DB-antes-de-Redis** (líneas 113–137): la transición de estado en DB es la operación crítica; Redis se escribe después y su fallo no revierte el pedido.
- **Resiliencia de Redis** (líneas 136–137): el fallo de escritura en caché se captura y loguea como `warning` sin propagar el error — correcto, el carrito es recuperable.
- **Protección de estado** (líneas 100–106): comprueba que el pedido esté en `ENLACE` antes de confirmar — evita transiciones inválidas.
- **Validación de cantidad robusta** (línea 29): rechaza `bool`, no-enteros y negativos, igual que `pago.py`.
- **Log de negocio** (línea 138): `CARRITO_CONFIRMADO` con `pedido_id` como evento estructurado.
- **Excepción tipada en DB** (líneas 91, 116): captura `SQLAlchemyError`, `OperationalError` y `RetryError` — consistente con el resto del proyecto.
- **TTL en Redis** (línea 134): `ex=3600` presente — el carrito no queda huérfano indefinidamente.

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** Rendimiento / diseño
**Severidad:** Media

**Problema:** `_validar_productos` llama al manager una vez por producto del carrito (N+1 queries). Mismo patrón que fue corregido en `controllers/pago.py` en la sesión anterior.

**Evidencia:**
```python
# línea 35 — dentro del bucle `for p in productos_recibidos`
producto_db = gestor_productos.obtener_producto_por_codigo(codigo)
```

**Impacto real:** Para un carrito de 8 ítems distintos = 8 queries secuenciales a SQL Server antes de responder al cliente.

**Recomendación mínima concreta:** Añadir `obtener_productos_por_codigos` ya existe en `gestor_productos.py` (añadido en esta sesión). Replicar el mismo patrón de `pago.py`: recoger todos los códigos antes del bucle, una sola query batch, iterar el dict en memoria.

---

### Hallazgo 2

**Tipo:** Manejo de errores
**Severidad:** Media

**Problema:** La llamada al manager dentro de `_validar_productos` (línea 35) no está protegida por try/except. Si `obtener_producto_por_codigo` lanza `SQLAlchemyError` o `RetryError`, la excepción se propaga al blueprint sin capturar.

**Evidencia:**
```python
# línea 35 — sin try/except
producto_db = gestor_productos.obtener_producto_por_codigo(codigo)
```
Contrasta con las líneas 91 y 116 donde sí se protegen las llamadas al manager.

**Impacto real:** Mismo patrón de riesgo que Hallazgo 2 en `pago.py`: 500 no gestionado hacia el blueprint. Si el blueprint devuelve 4xx/5xx, Meta reintentará el webhook y puede producir procesamiento doble. (Si este código es llamado desde el blueprint de API y no desde el webhook de Meta directamente, el riesgo de reintento es menor, pero el 500 sin log útil sigue siendo un problema de observabilidad.)

**Recomendación mínima concreta:** Este hallazgo se resuelve solo si se adopta la solución del Hallazgo 1 (una sola query batch con try/except envolviendo la llamada).

---

### Hallazgo 3

**Tipo:** Consistencia de estado
**Severidad:** Media

**Problema:** Si `fijar_carrito_confirmado` tiene éxito (DB en estado `ENLACE2`) pero la escritura en Redis falla con una excepción no de tipo `Exception` (e.g. `SystemExit`, `KeyboardInterrupt`) o la excepción capturada es genérica, el pedido queda en `ENLACE2` pero sin carrito en Redis. Cuando el cliente intenta pagar, el blueprint leerá Redis y no encontrará los datos del carrito — el comportamiento en ese caso depende del blueprint (posible riesgo no confirmado: no se ha leído el blueprint).

**Evidencia:**
```python
# líneas 121–137: Redis se escribe DESPUÉS del commit de DB.
# Si falla el set de Redis, el pedido ya está en ENLACE2 en DB pero sin datos de carrito en caché.
```

**Impacto real:** El cliente queda bloqueado en `ENLACE2` sin poder avanzar al pago si el blueprint depende de los datos Redis para construir la pantalla de confirmación. El fallo de Redis está logueado como `warning` pero no hay mecanismo de recuperación.

**Recomendación mínima concreta:** Posible riesgo no confirmado hasta leer el blueprint consumidor. Como mínimo, elevar el log de fallo Redis de `warning` a `error` para que sea visible en alertas de producción.

---

### Hallazgo 4

**Tipo:** Idempotencia / duplicados
**Severidad:** Media

**Problema:** No existe guard de idempotencia para el estado `ENLACE2`. Si `confirmar_carrito` se llama dos veces mientras el pedido está en `ENLACE` (doble clic, reintento de red), ambas llamadas pasan el check de línea 100 antes de que la primera haga commit. La segunda falla en la transición de DB (el manager rechaza `ENLACE → ENLACE2` ya consumida), pero sin log ni respuesta diferenciada.

**Evidencia:**
```python
# línea 100
if pedido_activo.Estado != EstadoPedido.ENLACE:
    return False, "El pedido no se encuentra en el estado correcto..."
```
No existe el equivalente a `iniciar_pago` que comprueba `CONFIRMANDO_PAGO` y devuelve la URL existente (idempotencia positiva).

**Impacto real:** En la ventana de carrera, dos peticiones concurrentes producen una exitosa y una con error genérico. El cliente puede ver un error de "estado incorrecto" aunque el carrito ya se confirmó correctamente. No hay duplicación de datos, pero la UX es confusa y el log no ayuda a diagnosticarlo.

**Recomendación mínima concreta:**
```python
if pedido_activo.Estado == EstadoPedido.ENLACE2:
    logger.info("CARRITO_YA_CONFIRMADO pedido=%s usuario=%s", pedido_id_db, user_id)
    return True, f"{public_url}/confirmacion_pago?pedido_id={pedido_activo.redisID}"
```
Añadir antes del check de `ENLACE`.

---

### Hallazgo 5

**Tipo:** Observabilidad
**Severidad:** Baja

**Problema:** El path de geocodificación fallida (líneas 108–111) logea un `warning` pero la función continúa normalmente con `lat=None, lng=None`. No queda claro en el log si esto es un estado aceptable o un degradado silencioso.

**Evidencia:**
```python
# líneas 108–111
coords = geocodificar_direccion(direccion)
lat, lng = (coords[0], coords[1]) if coords else (None, None)
if not coords:
    logger.warning("confirmar_carrito: no se pudieron geocodificar las coordenadas del pedido %s", pedido_id_db)
```

**Impacto real:** Si la geocodificación falla sistemáticamente (API caída, dirección malformada), el pedido avanza sin coordenadas. Si algún flujo posterior depende de `lat`/`lng` (e.g. cálculo de distancia para reparto), falla silenciosamente en ese punto en lugar de aquí.

**Recomendación mínima concreta:** Mantener el comportamiento de no-bloqueo (correcto para no detener al cliente por un fallo de Maps), pero añadir `pedido_id` y `direccion` truncada al log para facilitar el diagnóstico: `logger.warning("GEOCODIFICACION_FALLIDA pedido=%s dir='%.50s'", pedido_id_db, direccion)`.

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|---|---|
| Excepción no capturada en `_validar_productos` | Caída transitoria de SQL Server → 500 al blueprint → posible reintento Meta si esta ruta es alcanzable desde el webhook |
| Pedido en ENLACE2 sin carrito en Redis | Fallo de Redis justo después del commit de DB → cliente bloqueado en pantalla de confirmación sin poder avanzar al pago |
| Race condition en doble clic | Dos peticiones simultáneas ambas en ENLACE → una falla con "estado incorrecto" → cliente ve error aunque el carrito se confirmó |
| N+1 queries en carrito grande | Misma latencia acumulada que en `pago.py` antes de la corrección |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)

1. **Hallazgos 1 y 2 juntos** — reemplazar el bucle N+1 por la query batch `obtener_productos_por_codigos` (ya disponible en el manager) y envolver la llamada en try/except. Mismo patrón que se aplicó en `pago.py`.
2. **Hallazgo 4** — añadir guard de idempotencia para `ENLACE2` antes del check de `ENLACE` (4 líneas).
3. **Hallazgo 5** — mejorar el mensaje de log de geocodificación (1 línea).
4. **Hallazgo 3** — investigar si el blueprint consumidor puede operar sin datos en Redis antes de decidir si elevar el log o añadir recuperación.

### Qué NO tocar todavía

- El orden DB-antes-de-Redis: es la decisión correcta.
- La validación de `bool` en cantidad: no es redundante.
- La geocodificación no-bloqueante: correcto no detener el pedido por Maps.
- La estructura de inyección de dependencias: funciona bien para tests.

---

## 6. Tests que deberían existir

- `test_carrito_vacio_retorna_false` — lista vacía de productos rechazada antes de tocar DB.
- `test_producto_sin_codigo_retorna_false` — producto en lista sin campo `Codigo`.
- `test_cantidad_bool_retorna_false` — `True`/`False` como cantidad rechazados.
- `test_producto_no_encontrado_retorna_false` — manager no devuelve el producto.
- `test_db_error_en_validacion_retorna_false` — `SQLAlchemyError` en `_validar_productos` devuelve error, no 500 (actualmente no pasa — Hallazgo 2).
- `test_pedido_no_en_enlace_retorna_false` — pedido en estado distinto a `ENLACE` rechazado.
- `test_carrito_ya_confirmado_idempotente` — pedido en `ENLACE2` devuelve True con URL existente (actualmente no pasa — Hallazgo 4).
- `test_redis_fallo_no_revierte_exito` — si Redis lanza, la función sigue devolviendo `True`.
- `test_geocodificacion_fallida_no_bloquea` — `geocodificar_direccion` devuelve `None` y el carrito se confirma igualmente con `lat=None`.
- `test_happy_path_total_calculado_desde_bd` — el total se calcula con precio de BD, no con precio del cliente.

---

## 7. Veredicto final

**Estado general del archivo:** Estructura correcta y orden de operaciones bien pensado. Los problemas están en `_validar_productos` (N+1 + excepción no capturada) y en la falta de idempotencia para `ENLACE2`.

**¿Bloquea crecimiento?** No — la arquitectura de inyección es limpia.

**¿Bloquea testeo?** No — todas las dependencias son inyectables. Dos tests específicos no se pueden escribir correctamente hasta resolver Hallazgos 2 y 4.

**¿Tiene riesgo operativo real?** Sí — el Hallazgo 2 (excepción no capturada en validación de productos) puede producir 500s en picos de carga de SQL Server. El Hallazgo 3 (ENLACE2 sin Redis) puede dejar clientes bloqueados en un escenario de Redis degradado.
