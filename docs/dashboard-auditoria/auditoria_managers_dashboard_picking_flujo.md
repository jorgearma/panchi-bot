# Auditoría de `managers/dashboard/picking_flujo.py`

> Auditoría técnica estricta. Fecha: 2026-04-08.
> Archivos analizados: `managers/dashboard/picking_flujo.py`, `managers/dashboard/_helpers.py`, `models.py` (referenciado), `states.py`, `config.py`.

---

## 1. Rol del archivo

**Responsabilidad principal:** Operaciones de mutación del flujo de picking — asignar picker, reasignar picker, completar picking, actualizar ítem individual, aceptar pedido en modo restaurante (equipo cocina) y reclamar picking atómicamente.

**Qué debería hacer:** Orquestar transacciones de DB que cambien el estado de `PickingPedido`, `PickingItem`, `Pedido` e `HistorialEstadoPedido`, con rollback ante errores. Crear `Reparto` al completar. Descontar stock.

**Qué no debería hacer:** Lanzar threads de sistema sin mecanismo de supervisión, importar módulos de DB dentro de funciones (lazy imports), tener lógica de negocio mezclada con acceso a datos sin separación clara.

**Dependencias clave:**
- `sqlalchemy.exc` (IntegrityError, SQLAlchemyError)
- `threading.Thread` (para background tasks)
- `managers/dashboard/_helpers.py` (_ESTADOS_LISTOS_PARA_PICKING)
- `models.py` (Empleado, HistorialEstadoPedido, Pedido, PickingItem, PickingPedido, Reparto, Rol)
- `states.py` (EstadoPedido, EstadoPicking, EstadoReparto, transicion_valida_pedido)
- `database.SessionLocal` — importada lazy dentro de closures de Thread

**Nivel de criticidad:** Crítico — este mixin controla las transiciones de estado del flujo operativo central (PAGADO → EN_PREPARACION → PREPARADO). Un bug aquí puede dejar pedidos en estado inconsistente, duplicar registros de Reparto o corromper el stock.

---

## 2. Lo que hace bien

- `reclamar_picking` (líneas 388-450) usa un UPDATE atómico con condición en `WHERE` (`empleado_id == None AND estado == PENDIENTE`) y verifica `rowcount == 0` para detectar race conditions sin locks explícitos. Es la implementación más sólida del archivo.
- Todas las funciones públicas devuelven tuples `(bool, str)` o `(bool, str, extra)` consistentemente, lo que facilita el manejo en blueprints sin excepciones no controladas.
- `asignar_picker` verifica que el empleado esté activo (`activo=True`) antes de asignar (línea 33).
- `completar_picking` captura `pedido_id_para_reparto` antes del commit (línea 157) para evitar lazy-load post-expire — muestra consciencia del ciclo de vida de la sesión SQLAlchemy.
- `reasignar_picker` (líneas 76-140) registra un log de auditoría en el campo `notas` del picking con timestamp y nombres de empleados (líneas 110-112), proporcionando trazabilidad sin tabla adicional.
- `asignar_cocina_equipo` (líneas 295-386) implementa un fallback de dos fases para encontrar cocineros: primero por `rol_activo`, luego por `Rol.nombre` (líneas 310-334), evitando fallos cuando no hay check-in activo.
- `actualizar_item_picking` (líneas 261-293) valida el conjunto de estados válidos antes de tocar DB (líneas 263-265).

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** consistencia / seguridad
**Severidad:** Alta

**Problema:** `completar_picking` lanza dos `Thread` daemon sin mecanismo de supervisión, manejo de errores a nivel del proceso principal ni forma de reintentar si el worker de fondo falla. El thread `_descontar` (líneas 201-226) abre una nueva `SessionLocal()` dentro de un daemon thread; si la app se reinicia o el proceso termina abruptamente, el thread muere sin completar el descuento de stock, dejando el stock inconsistente sin ningún registro de ello más allá de un `logger.error` en un thread que puede haberse ya terminado.

**Evidencia:**
```python
# línea 226
Thread(target=_descontar, daemon=True).start()

# línea 250
Thread(target=_actualizar_disponibilidad_picker, daemon=True).start()
```

El thread `_descontar` descuenta stock y puede marcar productos como `Disponible=False` (líneas 215-219). Si el thread muere a mitad del loop (por ejemplo en el `commit` de la línea 220), el stock queda parcialmente decrementado.

**Impacto real:** En un reinicio de la app (deploy, crash) los threads daemon se matan sin garantías. El stock puede quedar sobredescuentado o parcialmente decrementado. Dado que `p.Stock = max(0, p.Stock - cantidad)` no tiene idempotencia, una ejecución parcial no es recuperable automáticamente.

**Recomendación mínima concreta:** Mover el descuento de stock a una tarea RQ encolada (ya existe `message_queue.py` en el proyecto) o ejecutarla de forma síncrona dentro de la misma transacción de `completar_picking`. Si se mantienen threads, añadir un try/except con `logger.error` más específico que registre los `producto_id` que no se pudieron descontar.

---

### Hallazgo 2

**Tipo:** acoplamiento / testabilidad
**Severidad:** Alta

**Problema:** Los closures de los threads (`_descontar` y `_actualizar_disponibilidad_picker`) contienen imports lazy de módulos (`from database import SessionLocal`, `from models import Producto`, `from sqlalchemy.exc import SQLAlchemyError`) dentro del cuerpo de la función (líneas 203-206, 233-234). Esto impide mockear las dependencias en tests unitarios sin parchear el módulo completo.

Adicionalmente, el closure `_actualizar_disponibilidad_picker` (línea 245) llama a `self._actualizar_estado_operativo(emp_id, 'disponible')` — capturando `self` del mixin en un thread de fondo. Si la sesión de `self` ha expirado o el objeto ha sido recogido por el GC entre el inicio del thread y su ejecución, puede producirse un error de sesión SQLAlchemy.

**Evidencia:**
```python
# línea 203-205
from database import SessionLocal
from models import Producto
from sqlalchemy.exc import SQLAlchemyError
```

```python
# línea 245 — self capturado en closure de thread daemon
self._actualizar_estado_operativo(emp_id, 'disponible')
```

**Impacto real:** En tests, el thread se lanza en background y puede interferir con la transacción de test. En producción, si `self` (el mixin/gestor) es un singleton, el riesgo de referencia stale es bajo pero presente. El import lazy hace que errores de importación se manifiesten solo en runtime dentro del thread, no en el arranque de la aplicación.

**Recomendación mínima concreta:** Pasar `SessionLocal` y `Producto` como argumentos o importarlos en el nivel del módulo. Extraer `_actualizar_estado_operativo` a una función standalone que no capture `self` en el thread.

---

### Hallazgo 3

**Tipo:** consistencia de estado
**Severidad:** Alta

**Problema:** En `asignar_picker` (líneas 23-74), cuando el `PickingPedido` ya existe (líneas 38-41), se actualiza `empleado_id` y `estado` pero NO se recrean los `PickingItem`. Si el picking existente fue creado previamente sin ítems (por ejemplo, por `_asegurar_picking_si_procede` que crea un picking vacío antes de que haya picker), los ítems quedarán ausentes y el picker no verá nada que picar.

**Evidencia:**
```python
# líneas 38-41: si picking ya existe, solo se actualiza el empleado y estado
if picking:
    picking.empleado_id = empleado_id
    picking.estado = EstadoPicking.EN_PROCESO.value
    picking.iniciado_en = datetime.utcnow()
# else: crea picking Y los PickingItems (líneas 42-56)
```

No hay verificación de si `picking.items` está vacío antes de decidir si crear los ítems.

**Impacto real:** Un picker asignado a un picking sin ítems verá una pantalla vacía y no podrá completar el picking sin intervención manual en la DB.

**Recomendación mínima concreta:** Añadir una verificación tras el bloque `if picking`: si `picking.items` está vacío, crear los `PickingItem` desde `pedido.detalles`. La misma lógica aplica a `reasignar_picker` y `asignar_cocina_equipo`.

---

### Hallazgo 4

**Tipo:** consistencia de estado
**Severidad:** Media

**Problema:** `reasignar_picker` (líneas 76-140) hace dos queries al mismo empleado nuevo: una para validar (línea 93: `.filter_by(EmpleadoID=nuevo_empleado_id, activo=True)`) y otra para obtener el nombre (línea 105: `.filter_by(EmpleadoID=nuevo_empleado_id)`). La segunda query no verifica `activo=True`, lo que es inconsistente. Más grave: entre las dos queries podría teóricamente cambiar el estado del empleado (race condition extremadamente improbable pero indicativo de design smell).

**Evidencia:**
```python
# línea 93 — verifica activo=True
empleado = s.query(Empleado).filter_by(EmpleadoID=nuevo_empleado_id, activo=True).first()
if not empleado:
    return False, "Empleado no válido o inactivo"

# línea 105 — misma query SIN activo=True para obtener el nombre
nuevo_empleado = s.query(Empleado).filter_by(EmpleadoID=nuevo_empleado_id).first()
nuevo_nombre = f"{nuevo_empleado.Nombre} {nuevo_empleado.Apellido}"
```

**Impacto real:** Query redundante que puede ser eliminada reutilizando el objeto `empleado` de la línea 93.

**Recomendación mínima concreta:** Reutilizar el objeto `empleado` de la validación: `nuevo_nombre = f"{empleado.Nombre} {empleado.Apellido}"`. Eliminar la segunda query.

---

### Hallazgo 5

**Tipo:** seguridad / validación de inputs
**Severidad:** Media

**Problema:** `actualizar_item_picking` (líneas 261-293) acepta `notas: str = None` sin sanitización ni límite de longitud. El valor se escribe directamente al campo `item.notas` (línea 279). Si hay un campo de formulario en el frontend con este input, un operador puede insertar strings arbitrariamente largos.

**Evidencia:**
```python
# línea 279
if notas is not None:
    item.notas = notas
```

No hay `len(notas) > MAX` ni strip de caracteres de control.

**Impacto real:** En SQL Server, si la columna tiene longitud definida, SQLAlchemy lanzará un error de truncamiento. Si la columna es `TEXT`/`NVARCHAR(MAX)`, el valor se escribe sin restricción. Un actor interno malicioso podría inyectar datos en el campo de notas.

**Recomendación mínima concreta:** Añadir `notas = notas.strip()[:500]` antes de asignar, o definir una constante `MAX_NOTAS_LENGTH = 500` y validar.

---

### Hallazgo 6

**Tipo:** diseño / acoplamiento
**Severidad:** Media

**Problema:** `asignar_cocina_equipo` (líneas 295-386) tiene un import lazy de `Rol` dentro del método (línea 311: `from models import Rol`). `Rol` ya está disponible en `models.py` que es importado en el nivel del módulo (línea 10), por lo que este import es innecesario y redundante.

**Evidencia:**
```python
# línea 10 — importación de nivel de módulo
from models import (
    Empleado, HistorialEstadoPedido, Pedido,
    PickingItem, PickingPedido, Reparto,
)

# línea 311 — import lazy dentro del método
from models import Rol
```

**Impacto real:** Sin impacto en runtime (Python cachea los módulos), pero es un code smell que dificulta la lectura de dependencias y puede confundir a herramientas de análisis estático.

**Recomendación mínima concreta:** Añadir `Rol` al import de nivel de módulo en línea 10 y eliminar el import lazy.

---

### Hallazgo 7

**Tipo:** observabilidad
**Severidad:** Media

**Problema:** `completar_picking` registra `logger.info("REPARTO_CREADO pedido=%s", ...)` (línea 181) pero no registra el éxito de la transición de estado del pedido (PREPARADO), ni el inicio del picking en `asignar_picker`, ni la reasignación de picker. Los eventos de negocio más críticos (cambio de estado de pedido) no tienen `logger.info`.

**Evidencia:** Las líneas 58-66 (transición a EN_PREPARACION) y 158-167 (transición a PREPARADO) no tienen logging. El único `logger.info` de éxito está en la línea 181 (creación de Reparto).

**Impacto real:** En producción es imposible auditar cuándo un pedido entró en preparación o cuándo fue marcado como preparado mirando solo los logs. Se necesita consultar la tabla `historial_estados_pedido` directamente.

**Recomendación mínima concreta:** Añadir `logger.info("PICKING_ASIGNADO pedido=%s picker=%s", pedido_id, empleado_id)` en `asignar_picker`, `logger.info("PICKING_COMPLETADO picking=%s pedido=%s", picking_id, pedido_id_para_reparto)` en `completar_picking`.

---

### Hallazgo 8

**Tipo:** idempotencia / duplicados
**Severidad:** Baja

**Problema:** `completar_picking` ya maneja la creación idempotente de `Reparto` con `filter_by(pedido_id=...).first()` (línea 173) y captura `IntegrityError` (líneas 182-185). Sin embargo, el descuento de stock en el thread `_descontar` NO es idempotente: si `completar_picking` se llama dos veces por error (por ejemplo, doble submit desde el frontend), el stock se descontará dos veces porque no hay guard previo a la actualización de `p.Stock`.

**Evidencia:**
```python
# línea 214 — sin verificación de si ya fue descontado
if item["estado"] == "encontrado":
    cantidad = item["cantidad_encontrada"] or item["cantidad_pedida"]
    p.Stock = max(0, p.Stock - cantidad)
```

No hay comprobación de si `picking.estado` ya era `COMPLETADO` al inicio de la función.

**Impacto real:** Un doble submit (bug de frontend o retry) puede descontar stock dos veces. Con `max(0, ...)` el mínimo es 0, pero productos podrían marcarse `Disponible=False` prematuramente.

**Recomendación mínima concreta:** Al inicio de `completar_picking`, añadir un guard:
```python
if picking.estado == EstadoPicking.COMPLETADO.value:
    return False, "Picking ya completado", None
```

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|--------|-------------------|
| Stock inconsistente tras reinicio de app | Un deploy en producción mientras hay pickings completándose mata los threads daemon de descuento de stock a mitad del loop; el stock queda sobredescuentado o parcialmente decrementado sin trazabilidad |
| Picking sin ítems bloqueado | Un pedido con `PickingPedido` preexistente (sin ítems) se asigna con `asignar_picker`; el picker ve pantalla vacía, no puede completar el picking y el pedido queda bloqueado en EN_PREPARACION |
| Doble descuento de stock | Un doble click en el botón "Completar picking" del frontend envía dos requests; el stock se descuenta dos veces para los mismos ítems |
| Error silencioso en thread de disponibilidad | El closure de `_actualizar_disponibilidad_picker` captura `self`; si la sesión del mixin expira, se lanza una excepción en el thread que solo aparece en logs como warning genérico |
| Query redundante de empleado | En alta concurrencia, dos queries al mismo empleado en `reasignar_picker` pueden devolver resultados distintos si el empleado se desactiva entre las dos llamadas |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)

1. **Guard de idempotencia en `completar_picking`** — añadir verificación de `picking.estado == COMPLETADO` al inicio. Cambio de 2-3 líneas, elimina riesgo de doble descuento.

2. **Verificación de ítems vacíos en `asignar_picker`** — tras el bloque `if picking:`, verificar si `picking.items` está vacío y crearlos si procede. Elimina el riesgo de pickings sin ítems.

3. **Mover import de `Rol` al nivel de módulo** — añadir `Rol` en el import de línea 10. Cambio trivial.

4. **Eliminar query redundante en `reasignar_picker`** — reutilizar el objeto `empleado` validado en la línea 93 en lugar de hacer una segunda query en la línea 105.

5. **Migrar descuento de stock de Thread a RQ** — encolar la tarea `_descontar` en la cola `whatsapp` (o una cola `background`) usando el mismo `message_queue.py`. Elimina el riesgo de pérdida de datos en reinicios.

6. **Añadir logging de eventos de negocio** — `logger.info` en transiciones de estado de pedido (EN_PREPARACION, PREPARADO) para auditabilidad en logs.

### Qué NO tocar todavía

- La lógica de `reclamar_picking` — es la más sólida del archivo y no debe tocarse sin tests exhaustivos.
- La estructura de retorno `(bool, str)` — es consistente en todo el archivo y los blueprints dependen de ella.
- El manejo de `IntegrityError` en creación de Reparto — es correcto para el caso de concurrencia.
- La lógica de fallback de dos fases en `asignar_cocina_equipo` — funcional y bien documentada.

---

## 6. Tests que deberían existir

- `test_asignar_picker_pedido_no_encontrado` — devuelve `(False, "Pedido no encontrado")`.
- `test_asignar_picker_estado_invalido` — pedido en estado ENTREGADO devuelve `(False, ...)`.
- `test_asignar_picker_empleado_inactivo` — devuelve `(False, "Empleado no encontrado o inactivo")`.
- `test_asignar_picker_crea_picking_y_items` — cuando no existe PickingPedido, crea picking con ítems.
- `test_asignar_picker_picking_existente_sin_items_crea_items` — cuando existe PickingPedido sin ítems, los crea.
- `test_reasignar_picker_query_redundante_eliminada` — verifica que el empleado usado para el nombre es el mismo objeto validado.
- `test_completar_picking_idempotente` — llamar dos veces a `completar_picking` con el mismo picking devuelve error en la segunda llamada.
- `test_completar_picking_crea_reparto` — al completar, se crea un Reparto en estado PENDIENTE.
- `test_completar_picking_reparto_ya_existe` — si Reparto ya existe (concurrencia), no falla.
- `test_completar_picking_picker_reasignado` — si `picker_id` no coincide con `empleado_id`, devuelve error.
- `test_actualizar_item_picking_estado_invalido` — estado no reconocido devuelve `(False, ...)`.
- `test_actualizar_item_picking_notas_longitud_maxima` — notas muy largas son truncadas o rechazadas.
- `test_reclamar_picking_atomico_ya_cogido` — si otro picker se adelanta (UPDATE rowcount=0), devuelve `(False, 'ya_cogido')`.
- `test_reclamar_picking_no_encontrado` — picking_id inexistente devuelve `(False, 'no_encontrado')`.
- `test_asignar_cocina_equipo_sin_cocineros` — devuelve `(False, "No hay cocineros disponibles...", [])`.
- `test_asignar_cocina_equipo_fallback_rol` — cuando no hay check-in activo, usa fallback por Rol.nombre.

---

## 7. Veredicto final

**Estado general del archivo:** Funcionalmente completo y con buenas decisiones de diseño en los caminos críticos (atomicidad de `reclamar_picking`, captura de errores SQLAlchemy, retornos consistentes). Sin embargo, acumula deuda técnica significativa en el uso de threads daemon sin supervisión para operaciones que afectan datos críticos (stock), y tiene un bug latente en la gestión de pickings existentes sin ítems.

**¿Bloquea crecimiento?** Sí, moderadamente. Los threads daemon sin mecanismo de cola harán que cualquier operación de fondo (nuevas notificaciones, nuevos descuentos) siga el mismo patrón frágil. La migración a RQ requiere refactorizar el patrón completo.

**¿Bloquea testeo?** Sí. Los imports lazy dentro de closures de threads, la captura de `self` en threads daemon y la ausencia de guards de idempotencia hacen que el comportamiento en tests sea no determinista y difícil de aislar sin infraestructura adicional.

**¿Tiene riesgo operativo real?** Sí, alto. El riesgo de pérdida de descuento de stock en un reinicio de app o crash es real y sin mecanismo de recuperación automática. El riesgo de pickings sin ítems es real y bloquea pedidos completos en el flujo operativo.
