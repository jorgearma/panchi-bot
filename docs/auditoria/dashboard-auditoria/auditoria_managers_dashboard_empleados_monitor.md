# Auditoría de `managers/dashboard/empleados_monitor.py`

> Auditoría técnica estricta. Fecha: 2026-04-07.
> Archivos analizados: `managers/dashboard/empleados_monitor.py`, `managers/dashboard/_helpers.py`, `states.py`.

---

## 1. Rol del archivo

**Responsabilidad principal:** Mixin de lectura que agrega datos en tiempo real del equipo operativo (pickers, repartidores, pipeline de pedidos) para el panel de monitorización.

**Qué debería hacer:** Ejecutar queries de solo lectura y devolver un dict serializable para el dashboard.

**Qué no debería hacer:** Mutar estado, validar input de usuario, contener lógica de negocio.

**Dependencias clave:** `self.session` (SQLAlchemy, inyectado por el assembler), `_helpers._iso`, `_helpers._ESTADOS_LISTOS_PARA_PICKING`, enums de `states.py`, modelos `CheckIn`, `Empleado`, `PickingPedido`, `PickingItem`, `Reparto`, `Pedido`, `Incidencia`, `Turno`.

**Nivel de criticidad:** Alto — es el endpoint de monitorización en tiempo real, probablemente polleado cada pocos segundos desde el dashboard.

---

## 2. Lo que hace bien

- **Estructura de mixin correcta** — un único método público, sin routing ni lógica HTTP, sin efectos secundarios.
- **Pre-fetch de CheckIn en bulk** (líneas 46-54) — consulta única con `IN(ids)` en lugar de un query por empleado. Evita el N+1 más obvio.
- **Sin magic strings en estados** — usa `EstadoPicking.value`, `EstadoReparto.value`, `EstadoPedido.value` consistentemente.
- **Null-guards defensivos** en todos los campos de datetime opcionales (`pk.iniciado_en`, `r.hora_salida`, etc.).
- **`_iso()` usado consistentemente** — serialización UTC correcta con sufijo `Z` para evitar confusión de zona horaria en el frontend.
- **Separación de responsabilidades dentro del mixin** — no toca Redis, no envía mensajes, no cambia estados.

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** rendimiento
**Severidad:** Alta

**Problema:** Acceso a `pk.items` dentro de un bucle provoca N+1 de SQL.

**Evidencia:**
```python
# líneas 109–114
for pk in pickings_activos:
    total_items = len(pk.items)              # lazy load → 1 query por PickingPedido
    completados_items = sum(
        1 for i in pk.items if i.estado in ("encontrado", "sustituido")
    )
    sin_stock_items = sum(1 for i in pk.items if i.estado == "sin_stock")
```
`pk.items` es una relación lazy. Si hay 3 pickers con 2 pickings activos cada uno = 6 queries adicionales solo para cargar ítems. Además, `pk.items` se itera 3 veces por picking (líneas 110, 111, 113).

**Impacto real:** En producción con 5 pickers activos y 2 pickings cada uno → 10 queries extra por llamada al dashboard. Con polling cada 5 s = 120 queries/minuto solo en este tramo.

**Recomendación mínima concreta:** Añadir `joinedload(PickingPedido.items)` en la query de `pickings_activos` (línea 77). También materializar `pk.items` en una variable local para evitar las 3 iteraciones:
```python
pickings_activos = s.query(PickingPedido).options(
    joinedload(PickingPedido.items)
).filter(...).order_by(...).all()
```

---

### Hallazgo 2

**Tipo:** rendimiento
**Severidad:** Alta

**Problema:** Acceso a `r.pedido` (y `r.pedido.cliente`) dentro de bucles provoca N+1 encadenado.

**Evidencia:**
```python
# líneas 221–224 (bucle entregas_activas)
"direccion": r.pedido.DireccionEntrega if r.pedido else "—",
"total":     float(r.pedido.Total) if r.pedido and r.pedido.Total else 0.0,
"forma_pago": r.pedido.forma_pago if r.pedido else None,

# líneas 347, 350–356 (bucle pedidos_sin_repartidor)
r.pedido.PedidoID,
r.pedido.cliente.nombre if r.pedido.cliente else "—",   # doble lazy: pedido → cliente
r.pedido.DireccionEntrega,
```
`repartos_activos` (línea 189) y `repartos_pendientes` (línea 334) no hacen eager load de `pedido` ni de `pedido.cliente`.

**Impacto real:** Con 4 repartidores activos con 2 entregas cada uno = 8 queries extra para `pedido`, más 8 para `pedido.cliente` en `pedidos_sin_repartidor`.

**Recomendación mínima concreta:**
```python
from sqlalchemy.orm import joinedload

repartos_activos = s.query(Reparto).options(
    joinedload(Reparto.pedido).joinedload(Pedido.cliente)
).filter(...).all()
```
Aplicar el mismo patrón a `repartos_pendientes` (línea 334).

---

### Hallazgo 3

**Tipo:** rendimiento
**Severidad:** Media

**Problema:** Acceso a `p.cliente` y `p.detalles` dentro del listcomp de `pedidos_sin_picker` provoca N+1.

**Evidencia:**
```python
# líneas 320–331
pedidos_sin_picker = [
    {
        "cliente_nombre": p.cliente.nombre if p.cliente else "—",  # lazy load
        "n_items": len(p.detalles),                                  # lazy load
    }
    for p in sin_picker
]
```
`sin_picker` (línea 316) no incluye `joinedload` de `cliente` ni `detalles`.

**Impacto real:** Con 10 pedidos sin picker = 20 queries adicionales (10 para `cliente`, 10 para `detalles`).

**Recomendación mínima concreta:**
```python
sin_picker = s.query(Pedido).options(
    joinedload(Pedido.cliente),
    joinedload(Pedido.detalles),
).filter(Pedido.Estado.in_(_ESTADOS_LISTOS_PARA_PICKING)).order_by(...).all()
```

---

### Hallazgo 4

**Tipo:** rendimiento
**Severidad:** Media

**Problema:** El pipeline de estados se calcula con un `COUNT` query por estado dentro de un bucle `for`.

**Evidencia:**
```python
# líneas 302–309
for estado_val in estados_pipeline:
    pipeline[estado_val] = s.query(func.count(Pedido.PedidoID)).filter(
        Pedido.Estado == estado_val
    ).scalar() or 0
```
5 queries `COUNT` separadas donde bastaría una sola con `GROUP BY`.

**Impacto real:** 5 round-trips a SQL Server por cada poll del dashboard.

**Recomendación mínima concreta:**
```python
from sqlalchemy import case

rows = (
    s.query(Pedido.Estado, func.count(Pedido.PedidoID))
    .filter(Pedido.Estado.in_(estados_pipeline))
    .group_by(Pedido.Estado)
    .all()
)
pipeline = {estado_val: 0 for estado_val in estados_pipeline}
for estado, count in rows:
    pipeline[estado] = count
# ENTREGADO hoy sigue siendo query separada (necesita filtro de fecha)
```

---

### Hallazgo 5

**Tipo:** rendimiento
**Severidad:** Media

**Problema:** Para empleados con rol ambiguo, se lanzan 2 queries por empleado dentro del bucle principal.

**Evidencia:**
```python
# líneas 65–73
if not es_picker and not es_repartidor:
    tiene_picking = s.query(PickingPedido.id).filter(
        PickingPedido.empleado_id == e.EmpleadoID
    ).first()
    tiene_reparto = s.query(Reparto.id).filter(
        Reparto.repartidor_id == e.EmpleadoID
    ).first()
```
Si hay 5 empleados sin rol definido = 10 queries adicionales.

**Impacto real:** Baja en operación normal (los roles deberían estar asignados), pero puede dispararse en configuraciones incompletas.

**Recomendación mínima concreta:** Pre-calcular fuera del bucle con una sola query agregada por `empleado_id` antes de entrar al loop:
```python
ids_con_picking = {
    row[0] for row in s.query(PickingPedido.empleado_id)
    .filter(PickingPedido.empleado_id.in_(ids)).distinct().all()
}
ids_con_reparto = {
    row[0] for row in s.query(Reparto.repartidor_id)
    .filter(Reparto.repartidor_id.in_(ids)).distinct().all()
}
```

---

### Hallazgo 6

**Tipo:** errores / observabilidad
**Severidad:** Media

**Problema:** El método completo (370 líneas, ~10–40 queries) no tiene ningún `try/except`. El `logger` está importado pero nunca se usa.

**Evidencia:**
- Línea 13: `logger = logging.getLogger(__name__)` — importado.
- No hay ninguna llamada a `logger.*` en todo el archivo.
- No hay `try/except` en ningún punto de `monitor_empleados`.

**Impacto real:** Un error transitorio de SQL Server (timeout de conexión, deadlock) en cualquiera de las ~15 queries propaga una excepción sin log contextual. El caller del blueprint recibe un 500 sin información sobre qué query falló. Con `tenacity` ausente, no hay reintento.

**Recomendación mínima concreta:** Al menos envolver el método entero con logging del error:
```python
def monitor_empleados(self) -> dict:
    try:
        return self._monitor_empleados_impl()
    except Exception:
        logger.exception("monitor_empleados falló")
        raise
```
Idealmente, añadir `@retry` de `tenacity` como en otros managers del proyecto para proteger contra drops transitorios de SQL Server.

---

### Hallazgo 7

**Tipo:** rendimiento
**Severidad:** Baja

**Problema:** `pk.items` se itera 3 veces consecutivas en lugar de materializarse.

**Evidencia:**
```python
# líneas 110–114
total_items = len(pk.items)
completados_items = sum(1 for i in pk.items if i.estado in ("encontrado", "sustituido"))
sin_stock_items   = sum(1 for i in pk.items if i.estado == "sin_stock")
```
Después del lazy load, la relación está en memoria, pero el código la itera 3 veces. No es un query extra, pero sí trabajo innecesario.

**Impacto real:** Despreciable en volúmenes normales. Merece corrección al tocar el archivo por los hallazgos 1 y 2.

**Recomendación mínima concreta:**
```python
items = pk.items  # una sola vez
total_items       = len(items)
completados_items = sum(1 for i in items if i.estado in ("encontrado", "sustituido"))
sin_stock_items   = sum(1 for i in items if i.estado == "sin_stock")
```

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|--------|-------------------|
| Degradación progresiva del dashboard | A medida que crece el equipo (más empleados, más pickings activos), el tiempo de respuesta crece linealmente por los N+1. Con polling cada 5 s, el SQL Server puede saturarse. |
| 500 silencioso sin contexto | Un timeout de SQL Server en cualquiera de las 15+ queries devuelve un 500 sin log útil. El operador ve el dashboard en blanco sin saber por qué. |
| Doble lazy load `r.pedido.cliente` | En `pedidos_sin_repartidor` (línea 350), si `r.pedido` ya fue lazy-loaded, acceder a `.cliente` dispara otro query. Con 20 repartos pendientes = 40 queries extra. |
| N+1 en rol ambiguo | Si se onboardean empleados sin rol asignado (frecuente durante pruebas), cada uno dispara 2 queries adicionales por poll. |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)

1. **Hallazgo 1** — Añadir `joinedload(PickingPedido.items)` en la query de `pickings_activos` (línea 77). Mayor ROI: elimina N+1 en el hot path del bucle picker.
2. **Hallazgo 2** — Añadir `joinedload` de `Reparto.pedido` y `Pedido.cliente` en `repartos_activos` (línea 189) y `repartos_pendientes` (línea 334).
3. **Hallazgo 3** — Añadir `joinedload` de `Pedido.cliente` y `Pedido.detalles` en `sin_picker` (línea 316).
4. **Hallazgo 5** — Pre-calcular ids con actividad fuera del bucle para eliminar 2 queries por empleado ambiguo.
5. **Hallazgo 4** — Consolidar el bucle de pipeline en una sola query `GROUP BY`.
6. **Hallazgo 6** — Añadir `logger.exception` y considerar `@retry` de tenacity.

### Qué NO tocar todavía

- La estructura del método único — es legible y refleja el modelo mental del dashboard.
- Los null-guards (`if pk.iniciado_en`, etc.) — están correctos y son necesarios.
- La lógica de inferencia de rol por actividad (líneas 65-73) — aunque ineficiente, es la fuente de verdad cuando el rol no está asignado.
- La separación `pickers_data` / `repartidores_data` — el frontend probablemente depende de esta estructura.

---

## 6. Tests que deberían existir

- `test_monitor_empleados_picker_activo` — verifica que un picker con 1 picking activo aparece con `estado="activo"` y `pedidos_activos=1`.
- `test_monitor_empleados_picker_sobrecargado` — verifica que ≥3 pickings activos produce `estado="sobrecargado"`.
- `test_monitor_empleados_sin_items_lazy` — verifica que el dict de picking activo calcula `progreso_pct` correctamente sin depender de lazy load (requiere fixture con `items` precargados).
- `test_monitor_empleados_repartidor_inactivo` — repartidor con solo entregas completadas hoy → `estado="inactivo"`, `tiempo_inactivo_min` calculado.
- `test_monitor_empleados_rol_ambiguo` — empleado sin rol definido en DB pero con historial de picking → aparece en `pickers_data`.
- `test_monitor_empleados_pipeline_counts` — verifica que los conteos de pipeline suman correctamente con pedidos en distintos estados.
- `test_monitor_empleados_sin_empleados_turno` — sin empleados con turno hoy → `pickers=[]`, `repartidores=[]`, `pipeline` con valores a 0.
- `test_monitor_empleados_db_error_logueado` — si `self.session.query` lanza, la excepción se loguea antes de propagarse.

---

## 7. Veredicto final

**Estado general del archivo:** Correcto en estructura y responsabilidad; deficiente en rendimiento de queries.

**¿Bloquea crecimiento?** Sí. Cada empleado adicional con pickings activos añade queries de forma lineal. En un equipo de 8-10 personas con polling frecuente, el SQL Server notará la carga.

**¿Bloquea testeo?** Parcialmente. El acceso a relaciones lazy (`pk.items`, `r.pedido`) hace que los tests unitarios fallen si los fixtures no precargan estas relaciones explícitamente. Con `joinedload` en las queries, el comportamiento es predecible y mockeable.

**¿Tiene riesgo operativo real?** Sí: la ausencia de `try/except` y logging significa que cualquier fallo de DB durante el polling del dashboard produce un 500 opaco, y el operador ve el panel en blanco sin diagnóstico disponible.
