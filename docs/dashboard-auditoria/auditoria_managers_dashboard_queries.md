# Auditoría de queries — `managers/dashboard/`

**Fecha:** 2026-04-07  
**Alcance:** todos los mixins de `managers/dashboard/`  
**Objetivo:** identificar queries que saturan SQL Server, patrones N+1 y consultas sin límite histórico.

---

## Resumen ejecutivo

| Severidad | Problema | Archivo |
|-----------|----------|---------|
| 🔴 CRÍTICO | N+1 extremo en `_tiempo_medio()` — 1 query por pedido | `_base.py` |
| 🔴 CRÍTICO | N+1 por empleado en `_monitor_empleados_impl()` | `empleados_monitor.py` |
| 🔴 CRÍTICO | N+1 por empleado en `repartidores()` | `reparto_asignacion.py` |
| 🟠 ALTO | N+1 lazy-load en `pedidos_activos()` | `gestor_pedidos_mixin.py` |
| 🟠 ALTO | Full scan de PickingPedido → lista Python → NOT IN | `picking_basico.py` |
| 🟠 ALTO | `repartos_con_repartidor_ids` sin filtro histórico | `reparto_asignacion.py` |
| 🟡 MEDIO | 5 queries separadas en `alertas()` cargando objetos completos | `gestor_pedidos_mixin.py` |
| 🟡 MEDIO | `estadisticas()` carga todos los Pedido cuando solo necesita agregados | `gestor_estadisticas_mixin.py` |
| 🟡 MEDIO | `historial_pedidos()` — double-query (COUNT + datos) + lazy-load `p.cliente` | `gestor_pedidos_mixin.py` |
| 🟡 MEDIO | `metricas()` dispara 8 COUNT separados en cada refresco del dashboard | `gestor_pedidos_mixin.py` |

---

## Problemas detallados

---

### 🔴 1 — N+1 extremo en `_tiempo_medio()` (`_base.py:51-75`)

**Qué hace:**  
Carga todos los registros de `HistorialEstadoPedido` para el estado final del día y luego, para cada fila, lanza **una query independiente** buscando el estado inicial del mismo pedido.

```python
# _base.py:54-70
finales = s.query(HistorialEstadoPedido).filter(
    HistorialEstadoPedido.estado_nuevo == estado_fin.value,
    HistorialEstadoPedido.cambiado_en >= desde,
).all()

for final in finales:          # ← 1 query por fila
    inicio = s.query(HistorialEstadoPedido).filter(
        HistorialEstadoPedido.pedido_id == final.pedido_id,
        HistorialEstadoPedido.estado_nuevo == estado_inicio.value,
        ...
    ).first()
```

**Por qué duele:**  
`metricas()` llama a `_tiempo_medio()` **dos veces** (líneas 95-100 de `gestor_pedidos_mixin.py`). Con 30 pedidos entregados hoy → 60 queries extra solo para calcular tiempos medios.  
Se ejecuta en cada refresco del dashboard (puede ser cada 10-30 segundos).

**Solución:**  
Una sola self-join o subquery agrupa ambos estados de una vez:

```python
from sqlalchemy import func, case
from sqlalchemy.orm import aliased

h_fin   = aliased(HistorialEstadoPedido)
h_ini   = aliased(HistorialEstadoPedido)

rows = (
    s.query(
        func.avg(
            func.datediff(
                text('minute'),
                h_ini.cambiado_en,
                h_fin.cambiado_en,
            )
        )
    )
    .join(h_ini, and_(
        h_ini.pedido_id == h_fin.pedido_id,
        h_ini.estado_nuevo == estado_inicio.value,
        h_ini.cambiado_en <= h_fin.cambiado_en,
    ))
    .filter(
        h_fin.estado_nuevo == estado_fin.value,
        h_fin.cambiado_en >= desde,
    )
    .scalar()
)
```

Esto convierte N+1 queries en **1 sola query con JOIN** en SQL Server.

---

### 🔴 2 — N+1 por empleado en `_monitor_empleados_impl()` (`empleados_monitor.py:101-232`)

**Qué hace:**  
Para cada picker: 2 queries a `PickingPedido` + 1 COUNT a `PickingItem` = **3 queries por picker**.  
Para cada repartidor: 2 queries a `Reparto` = **2 queries por repartidor**.

```python
# empleados_monitor.py:102-134 — se repite para cada empleado picker
pickings_activos   = s.query(PickingPedido).filter(empleado_id == e.EmpleadoID, ...).all()
completados_hoy    = s.query(PickingPedido).filter(empleado_id == e.EmpleadoID, ...).all()
incidencias_hoy    = s.query(func.count(PickingItem.id)).filter(...).scalar()

# empleados_monitor.py:219-232 — se repite para cada empleado repartidor
repartos_activos   = s.query(Reparto).filter(repartidor_id == e.EmpleadoID, ...).all()
entregados_hoy     = s.query(Reparto).filter(repartidor_id == e.EmpleadoID, ...).all()
```

**Por qué duele:**  
Con 5 pickers y 3 repartidores → hasta **21 queries en el bucle** + las consultas de empleados/checkins previas. Este método es llamado en tiempo real.

**Solución:**  
Cargar todos los datos del día en batch antes del bucle, indexar por `empleado_id`:

```python
# Una sola query para todos los pickings del día
todos_pickings_hoy = (
    s.query(PickingPedido)
    .options(joinedload(PickingPedido.items))
    .filter(
        PickingPedido.empleado_id.in_(ids),
        or_(
            PickingPedido.estado.in_(estados_activos_picking),
            and_(
                PickingPedido.estado == EstadoPicking.COMPLETADO.value,
                PickingPedido.completado_en >= hoy,
            )
        )
    )
    .all()
)
pickings_por_emp = defaultdict(lambda: {'activos': [], 'completados': []})
for pk in todos_pickings_hoy:
    if pk.estado in estados_activos_picking:
        pickings_por_emp[pk.empleado_id]['activos'].append(pk)
    elif pk.estado == EstadoPicking.COMPLETADO.value:
        pickings_por_emp[pk.empleado_id]['completados'].append(pk)

# Ídem para Reparto. Luego el bucle solo lee del dict, sin queries.
```

Pasa de 21+ queries a **2 queries batch** (1 para PickingPedido + 1 para Reparto).

---

### 🔴 3 — N+1 por empleado en `repartidores()` (`reparto_asignacion.py:61-70`)

```python
for e in empleados:                    # N empleados
    repartos_activos  = s.query(Reparto).filter(...).all()     # query 1
    entregados_hoy    = s.query(func.count(...)).filter(...).scalar()  # query 2
```

Mismo patrón que el punto anterior. Con 6 repartidores = 12 queries adicionales.

**Solución:** batch pre-load de Reparto para todos los `ids` antes del bucle, agrupar en Python con `defaultdict`.

---

### 🟠 4 — N+1 lazy-load en `pedidos_activos()` (`gestor_pedidos_mixin.py:106-185`)

**Qué hace:**  
Carga los pedidos sin eager loading, luego accede en el bucle a:
- `p.picking.empleado` (lazy → query picking → query empleado)
- `p.reparto.repartidor` (lazy → query reparto → query repartidor)  
- `p.detalles` (lazy → query detalles)
- `p.cliente` (lazy → query usuario)

Con 20 pedidos activos esto puede generar **80+ queries**.

```python
# gestor_pedidos_mixin.py:112 — sin eager loading
pedidos = query.order_by(Pedido.FechaCreacion.asc()).all()

for p in pedidos:
    p.picking.empleado  # lazy load
    p.reparto.repartidor  # lazy load
    p.detalles           # lazy load
    p.cliente            # lazy load
```

**Solución:**

```python
from sqlalchemy.orm import joinedload, selectinload

pedidos = (
    query
    .options(
        joinedload(Pedido.cliente),
        selectinload(Pedido.detalles),
        joinedload(Pedido.picking).joinedload(PickingPedido.empleado),
        joinedload(Pedido.reparto).joinedload(Reparto.repartidor),
    )
    .order_by(Pedido.FechaCreacion.asc())
    .all()
)
```

Pasa de 80+ queries a **5 queries** independientemente del número de pedidos.

---

### 🟠 5 — Full scan de PickingPedido + NOT IN en Python (`picking_basico.py:23-26`)

```python
# picking_basico.py:23-24
pickings_existentes_ids = [pk.pedido_id for pk in s.query(PickingPedido.pedido_id).all()]
pagados_sin_picking = s.query(Pedido).filter(
    ~Pedido.PedidoID.in_(pickings_existentes_ids) if pickings_existentes_ids else True,
).all()
```

Carga **toda la tabla PickingPedido** en Python solo para construir una lista de IDs y pasarla como NOT IN. Conforme crezca el histórico, esta lista crece sin límite.

**Solución:** subquery en SQL en lugar de lista Python:

```python
subq = s.query(PickingPedido.pedido_id).subquery()
pagados_sin_picking = s.query(Pedido).filter(
    Pedido.Estado.in_(_ESTADOS_LISTOS_PARA_PICKING),
    ~Pedido.PedidoID.in_(subq),
).all()
```

O mejor aún, un LEFT OUTER JOIN con filtro IS NULL, que SQL Server ejecuta más eficientemente que NOT IN con subquery grande:

```python
pagados_sin_picking = (
    s.query(Pedido)
    .outerjoin(PickingPedido, PickingPedido.pedido_id == Pedido.PedidoID)
    .filter(
        Pedido.Estado.in_(_ESTADOS_LISTOS_PARA_PICKING),
        PickingPedido.id == None,
    )
    .all()
)
```

---

### 🟠 6 — `repartos_con_repartidor_ids` sin filtro histórico (`reparto_asignacion.py:49-53`)

```python
# reparto_asignacion.py:49-53 — sin filtro de fecha
repartos_con_repartidor_ids = {
    r.pedido_id for r in s.query(Reparto.pedido_id).filter(
        Reparto.repartidor_id != None
    ).all()
}
```

Carga el `pedido_id` de **todos los repartos históricos** con repartidor asignado. Conforme crece el histórico (semanas, meses) esto se vuelve una scan de tabla completa que devuelve miles de IDs.

Solo interesa saber si el pedido PREPARADO actual ya tiene repartidor. Basta filtrar por estado activo:

```python
repartos_con_repartidor_ids = {
    r.pedido_id for r in s.query(Reparto.pedido_id).filter(
        Reparto.repartidor_id != None,
        Reparto.estado.in_([EstadoReparto.ASIGNADO.value, EstadoReparto.EN_CAMINO.value]),
    ).all()
}
```

---

### 🟡 7 — 5 queries completas en `alertas()` (`gestor_pedidos_mixin.py:193-232`)

```python
for estado, (umbral, nivel, desc) in _UMBRALES_RETRASO.items():   # 5 iteraciones
    pedidos = s.query(Pedido).filter(Pedido.Estado == estado).all()  # query por estado
```

Carga objetos completos de Pedido para los 5 estados operativos. Solo necesita `PedidoID`, `FechaCreacion`, `FechaActualizacion`. Una sola query con proyección de columnas:

```python
from sqlalchemy.orm import load_only

pedidos_alerta = (
    s.query(Pedido)
    .options(load_only(
        Pedido.PedidoID, Pedido.Estado,
        Pedido.FechaCreacion, Pedido.FechaActualizacion,
    ))
    .filter(Pedido.Estado.in_(list(_UMBRALES_RETRASO.keys())))
    .all()
)
for p in pedidos_alerta:
    umbral, nivel, desc = _UMBRALES_RETRASO[p.Estado]
    ...
```

Pasa de 5 queries a **1 query** con proyección de columnas.

---

### 🟡 8 — `estadisticas()` carga objetos Pedido completos (`gestor_estadisticas_mixin.py:39-43`)

```python
pedidos = (
    s.query(Pedido)
    .filter(Pedido.FechaCreacion >= dt_desde, Pedido.FechaCreacion <= dt_hasta)
    .all()
)
```

Carga todos los campos de Pedido (incluyendo `Notas`, `DireccionEntrega`, etc.) cuando solo se usan `PedidoID`, `Estado`, `Total`, `FechaCreacion`, `forma_pago`. Para un rango de 7 días con 200 pedidos, se transfieren columnas innecesarias.

```python
from sqlalchemy.orm import load_only

pedidos = (
    s.query(Pedido)
    .options(load_only(
        Pedido.PedidoID, Pedido.Estado, Pedido.Total,
        Pedido.FechaCreacion, Pedido.forma_pago,
    ))
    .filter(Pedido.FechaCreacion >= dt_desde, Pedido.FechaCreacion <= dt_hasta)
    .all()
)
```

---

### 🟡 9 — Double-query + lazy-load `p.cliente` en `historial_pedidos()` (`gestor_pedidos_mixin.py:259-346`)

```python
total = query.count()          # query 1 — COUNT(*)
pedidos = query.order_by(...).offset(...).limit(...).all()  # query 2 — datos

# luego en el bucle:
p.cliente.nombre  # lazy-load por cada pedido de la página
```

El doble query (COUNT + datos) es el patrón estándar de paginación, pero el lazy-load del cliente en el bucle añade hasta `per_page` queries extra (default 25).

```python
# Añadir eager loading del cliente al query de paginación
pedidos = (
    query
    .options(joinedload(Pedido.cliente))
    .order_by(Pedido.FechaCreacion.desc())
    .offset((page - 1) * per_page)
    .limit(per_page)
    .all()
)
```

---

### 🟡 10 — 8 COUNT separados en `metricas()` (`gestor_pedidos_mixin.py:22-103`)

Cada refresco del dashboard dispara:
1. `pedidos_hoy` — COUNT
2. `pedidos_activos` — COUNT
3. `en_preparacion` — COUNT
4. `en_reparto` — COUNT
5. `entregados_hoy` — COUNT
6. `pickers_activos` — COUNT
7. `repartidores_activos` — COUNT
8. `ingresos_hoy` — SUM
9. `cancelados_hoy` — GROUP BY
10. `ingresos_metodo` — GROUP BY

Los 7 COUNTs sobre `Pedido` pueden consolidarse en un GROUP BY:

```python
from sqlalchemy import case

counts = (
    s.query(
        Pedido.Estado,
        func.count(Pedido.PedidoID),
        func.sum(Pedido.Total),
    )
    .filter(
        or_(
            Pedido.FechaCreacion >= hoy,
            Pedido.Estado.in_(_ESTADOS_OPERATIVOS + [EstadoPedido.ENTREGADO.value]),
        )
    )
    .group_by(Pedido.Estado)
    .all()
)
```

Esto no elimina todas las queries, pero reduce el número de roundtrips a SQL Server en cada refresco.

---

## Índices recomendados

Las queries más frecuentes filtran por estas columnas. Si no tienen índice ya, son candidatas inmediatas:

```sql
-- Pedidos
CREATE INDEX IX_Pedido_Estado          ON pedidos (Estado)          INCLUDE (FechaCreacion, Total);
CREATE INDEX IX_Pedido_FechaCreacion   ON pedidos (FechaCreacion)   INCLUDE (Estado, Total, forma_pago);
CREATE INDEX IX_Pedido_Estado_FechaAct ON pedidos (Estado, FechaActualizacion);

-- HistorialEstadoPedido
CREATE INDEX IX_Historial_EstadoNuevo  ON historial_estados_pedido (estado_nuevo, cambiado_en) INCLUDE (pedido_id);
CREATE INDEX IX_Historial_PedidoEstado ON historial_estados_pedido (pedido_id, estado_nuevo, cambiado_en);

-- PickingPedido
CREATE INDEX IX_Picking_EmpleadoEstado ON picking_pedidos (empleado_id, estado, completado_en);

-- Reparto
CREATE INDEX IX_Reparto_RepartidorEstado ON repartos (repartidor_id, estado, hora_entrega_real);

-- Turno
CREATE INDEX IX_Turno_EmpleadoFecha ON turnos (empleado_id, fecha, estado);

-- CheckIn
CREATE INDEX IX_CheckIn_EmpleadoFecha ON checkins (empleado_id, fecha, fin);
```

---

## Priorización de trabajo

| Prioridad | Acción | Impacto estimado |
|-----------|--------|-----------------|
| 1 | Reescribir `_tiempo_medio()` con self-join | Elimina 30-100 queries por refresco |
| 2 | Batch pre-load en `_monitor_empleados_impl()` | Elimina N×3 queries por llamada |
| 3 | Añadir eager loading en `pedidos_activos()` | Elimina N×4 lazy loads |
| 4 | Subquery en `picking_activo()` | Evita scan de tabla histórica |
| 5 | Filtrar por estado activo en `repartos_con_repartidor_ids` | Evita crecer con el histórico |
| 6 | Batch pre-load en `repartidores()` | Elimina N×2 queries |
| 7 | `load_only` en `alertas()` + query única | Reduce 5 queries a 1 |
| 8 | `joinedload(Pedido.cliente)` en `historial_pedidos()` | Elimina lazy loads en paginación |
| 9 | Índices de SQL Server | Impacto en todas las queries anteriores |
