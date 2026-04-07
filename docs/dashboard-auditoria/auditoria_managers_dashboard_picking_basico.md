# Auditoría de `managers/dashboard/picking_basico.py`

> Auditoría técnica estricta. Fecha: 2026-04-08.
> Archivos analizados: `managers/dashboard/picking_basico.py`, `managers/dashboard/_helpers.py`, `models.py` (referenciado), `states.py`, `config.py`.

---

## 1. Rol del archivo

**Responsabilidad principal:** Consultas de lectura sobre el estado del picking — listados de pedidos listos para ser picados, pickings activos, búsqueda de productos y pickings por picker.

**Qué debería hacer:** Acceder a la base de datos mediante SQLAlchemy para devolver estructuras de datos serializables que el dashboard puede renderizar. Solo lectura, sin mutaciones de estado.

**Qué no debería hacer:** Modificar estado de DB, tomar decisiones de negocio, importar módulos de configuración para ramificar lógica de modo operativo dentro de una función de consulta.

**Dependencias clave:**
- `sqlalchemy.orm` (joinedload, selectinload)
- `managers/dashboard/_helpers.py` (_iso, _ESTADOS_LISTOS_PARA_PICKING)
- `models.py` (Pedido, PedidoDetalle, PickingItem, PickingPedido, Producto)
- `states.py` (EstadoPicking, EstadoPedido)
- `config.py` (`APP_MODE`) — importación de módulo de configuración dentro de un mixin de datos

**Nivel de criticidad:** Alto — este mixin alimenta la pantalla principal del dashboard operativo. Datos incorrectos o ausentes bloquean operaciones en tiempo real.

---

## 2. Lo que hace bien

- Usa `outerjoin` con `PickingPedido.id == None` en `picking_activo` (línea 26-35) para detectar pedidos sin picking de forma eficiente en una sola query, evitando NOT IN subqueries.
- `selectinload` + `joinedload` bien combinados (líneas 27-29, 64-68) para evitar N+1 al iterar detalles e items.
- `buscar_productos` (línea 187-200) limita resultados a 20 con `.limit(20)` y filtra solo disponibles — buen comportamiento defensivo para auto-complete.
- `pickings_sin_asignar` (líneas 284-316) filtra por `estados_activos` del `Pedido` vía `JOIN` explícito, evitando devolver pickings huérfanos de pedidos ya cerrados.
- La función auxiliar `_iso` centraliza la serialización de fechas UTC con sufijo `Z`, evitando divergencias de zona horaria.
- Los tres bloques de recolección de datos de ítems son defensivos ante `None` en relaciones opcionales (líneas 82-88, 143-150, 222-232).
- `pickings_sin_asignar` captura `segundos_esperando` calculado en Python para exponer tiempos de espera sin añadir lógica SQL compleja.

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** diseño
**Severidad:** Media

**Problema:** El método `pickings_del_picker` (líneas 246-264) contiene lógica de negocio condicional basada en `APP_MODE` para construir la lista de ítems cuando `APP_MODE == 'restaurant'`. Esto rompe la separación entre capa de datos y lógica de modo operativo — el mixin de consulta no debería saber qué modo está activo.

**Evidencia:**
```python
# línea 246
if not items_data and app_config.APP_MODE == 'restaurant' and pk.pedido:
    items_data = [...]
    for d in pk.pedido.detalles
```

**Impacto real:** Si en el futuro se añade un tercer modo, o si APP_MODE cambia en caliente, este código introduce caminos ocultos difíciles de rastrear. La lógica de "qué ítems mostrar según el modo" pertenece al controlador o a un selector de estrategia, no al mixin de datos.

**Recomendación mínima concreta:** Mover la rama `restaurant` a un método separado `pickings_del_picker_restaurant` o delegar la decisión a quien llama. Alternativamente, el blueprint puede llamar a métodos diferentes según `APP_MODE`.

---

### Hallazgo 2

**Tipo:** rendimiento
**Severidad:** Media

**Problema:** `picking_activo` (líneas 18-185) ejecuta tres queries independientes en secuencia sobre tablas relacionadas (`pagados_sin_picking`, `pickings`, `sin_picker_qs`) sin agruparlas. El tercer bloque (`sin_picker_qs`, líneas 131-183) repite íntegramente la lógica de construcción del dict de ítems que ya existe en el bloque de `pickings` (líneas 79-128) — ~50 líneas duplicadas.

**Evidencia:**
```python
# líneas 79-128: loop para "activo"
for pk in pickings:
    items_data = []
    for item in pk.items:
        nombre = (item.pedido_detalle.NombreProducto if ...)
        ...

# líneas 141-183: loop para "sin_picker" — código idéntico
for pk in sin_picker_qs:
    items_data = []
    for item in pk.items:
        nombre = (item.pedido_detalle.NombreProducto if ...)
        ...
```

**Impacto real:** Duplicación de código que diverge silenciosamente. Una corrección aplicada en un bloque no se aplica al otro. Además, si el dashboard se carga frecuentemente, tres queries separadas por llamada aumentan la latencia acumulada.

**Recomendación mínima concreta:** Extraer la construcción del dict de ítems a un helper privado `_items_data_from_picking(pk)` y reutilizarlo en ambos bloques. Evaluar si `sin_picker_qs` puede unirse al query de `pickings` con un filtro más amplio en `empleado_id`.

---

### Hallazgo 3

**Tipo:** diseño / acoplamiento
**Severidad:** Baja

**Problema:** `pickings_sin_asignar` (línea 288) tiene un import lazy de `datetime` dentro del método (`from datetime import datetime`). El resto del módulo no importa `datetime` en el nivel de módulo, lo que es inconsistente con el patrón del proyecto.

**Evidencia:**
```python
# línea 288
from datetime import datetime
```

**Impacto real:** Ninguno en runtime, pero es inconsistente y dificulta búsquedas de dependencias a nivel de archivo (tooling, linters, auditoría de imports).

**Recomendación mínima concreta:** Mover `from datetime import datetime` al bloque de imports del módulo (línea 2-3).

---

### Hallazgo 4

**Tipo:** observabilidad
**Severidad:** Baja

**Problema:** Ninguno de los métodos de lectura registra métricas de volumetría ni advertencias cuando las colecciones devueltas están vacías o cuando se producen fallbacks (por ejemplo, cuando `d.NombreProducto` es None y se usa `d.producto.Nombre`). No hay un solo `logger.debug` o `logger.warning` en el mixin completo.

**Evidencia:** Las líneas 1-316 no contienen ninguna llamada a `logger`. El logger está declarado en línea 13 pero nunca se usa.

**Impacto real:** En un fallo silencioso (por ejemplo, relación `producto` rota para algunos ítems) todos los productos aparecerán como `"—"` en el dashboard sin ningún rastro en logs. Diagnosticar este tipo de problema requeriría inspección directa de la DB.

**Recomendación mínima concreta:** Añadir al menos `logger.warning` cuando `d.producto` es None y `d.NombreProducto` también es None, dado que el nombre fallará a `"—"`. Añadir `logger.debug("picking_activo: %d pedidos, %d activos, %d sin_picker", ...)` para volumetría.

---

### Hallazgo 5

**Tipo:** consistencia de estado
**Severidad:** Baja

**Problema:** `picking_activo` puede devolver el mismo pedido tanto en el bloque `pagados_sin_picking` (líneas 37-60) como potencialmente en `sin_picker_qs` (líneas 141-183) si existe un `PickingPedido` en estado PENDIENTE sin `empleado_id`. La lógica de `picking_activo` asume que la distinción entre "sin PickingPedido" y "con PickingPedido sin picker" es exhaustiva, pero si hay un bug en creación, un pedido podría aparecer en ambos bloques.

**Evidencia:**
- Líneas 24-35: filtra pedidos cuyo `PickingPedido.id == None`
- Líneas 131-139: filtra pickings con `empleado_id == None` y `estado == PENDIENTE`

Ambas rutas son mutuamente excluyentes en teoría, pero no hay un assert o log que detecte solapamientos.

**Impacto real:** Un pedido duplicado en el dashboard podría ser reclamado dos veces o causar confusión al operador.

**Recomendación mínima concreta:** Añadir una validación de sanity check con `logger.warning` si un `pedido_id` aparece en ambos conjuntos, o unificar la consulta con una condición `CASE` en SQL para garantizar exclusividad en la fuente.

---

### Hallazgo 6

**Tipo:** testabilidad
**Severidad:** Baja

**Problema:** `pickings_del_picker` accede a `app_config.APP_MODE` (módulo global de configuración) en tiempo de ejecución del método (líneas 246, 264, 269, 279, 280). No hay parámetro inyectable para override en tests.

**Evidencia:**
```python
# línea 246
if not items_data and app_config.APP_MODE == 'restaurant' and pk.pedido:
# línea 264
es_restaurant = app_config.APP_MODE == 'restaurant'
# línea 269
"modo": app_config.APP_MODE,
```

**Impacto real:** Para testear el comportamiento en modo `restaurant` hay que hacer monkeypatching de `config.APP_MODE` o del módulo `app_config`, lo que acopla los tests al módulo de configuración global. En un proyecto con múltiples tests paralelos esto puede generar interferencias.

**Recomendación mínima concreta:** Pasar `app_mode: str = None` como parámetro con fallback a `app_config.APP_MODE`, o aceptar que el mixin sea testeado con monkeypatching explícito documentado en conftest.

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|--------|-------------------|
| Duplicación silenciosa de bugs | Se corrige el nombre de producto en el loop "activo" pero no en el loop "sin_picker" — el bug persiste para un subconjunto de pickings en el dashboard |
| Pérdida de diagnóstico en producción | Un fallo en la relación `producto → PedidoDetalle` hace que todos los items aparezcan como "—"; sin logs no hay forma de detectarlo sin consultar la DB directamente |
| Acoplamiento APP_MODE en tests | Al añadir tests del modo `restaurant`, hay que parchear el global `app_config.APP_MODE`; si dos tests corren en paralelo con modos distintos, los resultados son no deterministas |
| Doble aparición de pedido en dashboard | Un bug en la creación de `PickingPedido` hace que un pedido aparezca en dos bloques; el operador lo ve duplicado y recibe error al intentar reclamarlo |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)

1. **Extraer `_items_data_from_picking(pk)`** — eliminar la duplicación entre los bloques "activo" y "sin_picker" en `picking_activo`. Impacto: elimina ~50 líneas duplicadas, reduce superficie de divergencia futura.
2. **Mover `from datetime import datetime`** al nivel del módulo — cambio trivial que mejora legibilidad y coherencia.
3. **Añadir logging** — al menos `logger.warning` cuando `nombre` cae a `"—"` por relaciones rotas, y `logger.debug` de volumetría en `picking_activo`.
4. **Extraer la lógica de APP_MODE de `pickings_del_picker`** — pasar `app_mode` como parámetro o mover la rama a quien llama.

### Qué NO tocar todavía

- La estructura de las tres queries en `picking_activo` — unificarlas en una sola es un cambio de mayor riesgo que requiere verificar el impacto en la paginación y el orden del dashboard.
- La lógica de `buscar_productos` — es correcta y simple.
- Las opciones de eager loading — están bien calibradas para evitar N+1.

---

## 6. Tests que deberían existir

- `test_picking_activo_sin_pedidos` — verifica que devuelve lista vacía cuando no hay pedidos en estados listos.
- `test_picking_activo_pedido_sin_picking_pedido` — un pedido PAGADO sin `PickingPedido` aparece en `tipo=sin_asignar`.
- `test_picking_activo_picking_sin_picker` — un `PickingPedido` con `empleado_id=None` aparece en `tipo=sin_picker`.
- `test_picking_activo_picking_activo` — un `PickingPedido` con picker asignado y estado EN_PROCESO aparece en `tipo=activo`.
- `test_picking_activo_no_duplicados` — un pedido no aparece en dos bloques simultáneamente.
- `test_buscar_productos_filtra_no_disponibles` — productos con `Disponible=False` no aparecen.
- `test_buscar_productos_limite_20` — una BD con 30 productos solo devuelve 20.
- `test_pickings_del_picker_modo_warehouse` — devuelve ítems con `item_id` populated.
- `test_pickings_del_picker_modo_restaurant_sin_items` — cuando no hay `PickingItem`, construye ítems desde detalles del pedido.
- `test_pickings_sin_asignar_filtra_estados_inactivos` — pedidos ENTREGADO/CANCELADO con picking sin picker no aparecen.
- `test_pickings_sin_asignar_segundos_esperando` — el campo `segundos_esperando` es mayor o igual a 0 y coherente con `created_at`.

---

## 7. Veredicto final

**Estado general del archivo:** Funcional y razonablemente bien estructurado para un mixin de lectura. Las queries usan eager loading correcto. El problema principal es la duplicación de código en `picking_activo` y el acoplamiento a `APP_MODE` dentro de un método de consulta.

**¿Bloquea crecimiento?** Parcialmente. La duplicación de la lógica de construcción de ítems es una deuda técnica que crecerá con cada campo nuevo que se añada al dict de ítems.

**¿Bloquea testeo?** Sí, moderadamente. El acceso directo a `app_config.APP_MODE` sin parámetro inyectable requiere monkeypatching global en tests, lo que complica la cobertura del modo `restaurant`.

**¿Tiene riesgo operativo real?** Bajo-medio. La ausencia de logging en paths de datos corruptos (relaciones rotas) puede hacer que un fallo silencioso permanezca invisible hasta que un operador note ítems con nombre `"—"` en el dashboard.
