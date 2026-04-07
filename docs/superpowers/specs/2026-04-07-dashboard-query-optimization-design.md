# Diseño: Optimización de queries — managers/dashboard/

**Fecha:** 2026-04-07
**Alcance:** todos los mixins de `managers/dashboard/`
**Objetivo:** eliminar N+1, full scans y queries redundantes para solidificar el rendimiento antes de escalar.
**Enfoque elegido:** B — fixes aislados + helpers de batch en `_base.py`

---

## Contexto

Las auditorías previas (`docs/auditoria_managers_dashboard_queries.md` y `docs/auditoria_managers_dashboard_empleados_monitor.md`) identificaron 10 problemas. El código funciona bien en el volumen actual pero tiene patrones que degradan linealmente con el crecimiento del equipo y del histórico de pedidos. Este spec cubre la implementación de todos los fixes de queries Python. Los índices de SQL Server son trabajo separado.

---

## Cambios por archivo

### 1. `managers/dashboard/_base.py`

**`_tiempo_medio(desde, estado_inicio, estado_fin)`** — reescribir con self-join.

- Problema actual: N+1 — 1 query por pedido del día (con 30 pedidos entregados → 60 queries extra solo para los dos `_tiempo_medio()` de `metricas()`).
- Solución: self-join entre dos alias de `HistorialEstadoPedido` con `func.datediff(text('minute'), ...)` calculado en SQL Server y `func.avg()`. Una sola query.
- Contrato sin cambios: misma firma, devuelve `float | None`.

**Añadir `_batch_pickings(ids, estados, desde=None)`** — nuevo método privado.
- Ejecuta una sola query `PickingPedido.empleado_id.in_(ids)` con eager load de `items`.
- Devuelve `defaultdict(list)` indexado por `empleado_id`.
- Usado por `monitor_empleados` y, en el futuro, por cualquier mixin que necesite pickings por lote.

**Añadir `_batch_repartos(ids, estados, desde=None)`** — nuevo método privado.
- Misma lógica para `Reparto.repartidor_id.in_(ids)` con eager load de `pedido` y `pedido.cliente`.
- Devuelve `defaultdict(list)` indexado por `repartidor_id`.

---

### 2. `managers/dashboard/gestor_pedidos_mixin.py`

**`metricas()`**
- Consolidar 5 COUNTs de estado sobre `Pedido` en una sola query `GROUP BY Estado` filtrada por `Estado.in_(_ESTADOS_OPERATIVOS + [ENTREGADO])` o `FechaCreacion >= hoy`.
- Los COUNTs de `PickingPedido` (pickers_activos) y `Reparto` (repartidores_activos) permanecen separados (tablas distintas).
- Dict de retorno sin cambios.

**`pedidos_activos()`**
- Añadir eager loading en la query principal:
  - `joinedload(Pedido.cliente)`
  - `selectinload(Pedido.detalles)`
  - `joinedload(Pedido.picking).joinedload(PickingPedido.empleado)`
  - `joinedload(Pedido.reparto).joinedload(Reparto.repartidor)`
- Sin cambios en la lógica de serialización.

**`alertas()`**
- Sustituir el bucle de 5 queries (una por estado en `_UMBRALES_RETRASO`) por una sola query con `Estado.in_(list(_UMBRALES_RETRASO.keys()))` + `load_only(PedidoID, Estado, FechaCreacion, FechaActualizacion)`.
- La lógica de umbral y clasificación de nivel no cambia.

**`historial_pedidos()`**
- Añadir `joinedload(Pedido.cliente)` en la query de datos (la del `offset/limit`), no en el COUNT.
- Elimina hasta `per_page` lazy loads por página (default 25).

---

### 3. `managers/dashboard/gestor_estadisticas_mixin.py`

**`estadisticas()`**
- Añadir `load_only(PedidoID, Estado, Total, FechaCreacion, forma_pago)` a la query de pedidos del período.
- La lógica de agregación en Python no cambia.

---

### 4. `managers/dashboard/picking_basico.py`

**`picking_activo()`**
- Sustituir:
  ```python
  pickings_existentes_ids = [pk.pedido_id for pk in s.query(PickingPedido.pedido_id).all()]
  pagados_sin_picking = s.query(Pedido).filter(~Pedido.PedidoID.in_(pickings_existentes_ids) ...).all()
  ```
  por LEFT OUTER JOIN con filtro `PickingPedido.id == None`:
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
- Elimina el full scan de toda la tabla histórica de `picking_pedido`.

---

### 5. `managers/dashboard/reparto_asignacion.py`

**`repartidores()`**
- Extraer la carga de `repartos_activos` y `entregados_hoy` del bucle usando `_batch_repartos()` de `_base.py`.
- El bucle sobre empleados solo lee del dict, sin queries.

**`repartos_con_repartidor_ids`**
- Añadir filtro `Reparto.estado.in_([ASIGNADO, EN_CAMINO])` para evitar que la lista crezca con todo el histórico.

---

### 6. `managers/dashboard/empleados_monitor.py`

**`_monitor_empleados_impl()`**
- Pre-cargar antes del bucle usando `_batch_pickings()` y `_batch_repartos()` de `_base.py`.
- El bucle sobre empleados lee de los dicts en memoria — cero queries dentro del bucle.
- Los `joinedload(PickingPedido.items)` ya están incluidos en `_batch_pickings`.

---

## Flujo y contratos

- **Sin cambios de interfaz pública.** Todas las firmas y estructuras de retorno se mantienen exactas.
- `_batch_pickings` y `_batch_repartos` son métodos privados, no forman parte de la API del mixin.
- `_tiempo_medio()` mantiene `(desde, estado_inicio, estado_fin) → float | None`.
- `metricas()` mantiene el mismo dict de retorno — solo cambia la obtención interna.
- No se añaden nuevas dependencias — se usa SQLAlchemy existente + `sqlalchemy.text` (ya en uso en el proyecto).
- No se añade error handling nuevo — el wrapper `monitor_empleados` con `@retry` de tenacity ya cubre ese escenario.

---

## Testing

- Sin tests nuevos en esta tarea.
- Los 3 tests pre-existentes que ya fallaban antes de estos cambios no son regresiones.
- Verificación manual por método: que el dict de retorno de cada función es idéntico al anterior y que no se producen lazy loads adicionales.

---

## Prioridad de implementación

| # | Fix | Archivo | Impacto |
|---|-----|---------|---------|
| 1 | `_tiempo_medio()` self-join | `_base.py` | Elimina 30-100 queries/refresco |
| 2 | `_batch_pickings` + `_batch_repartos` helpers | `_base.py` | Base para fixes 3 y 6 |
| 3 | Batch pre-load en `_monitor_empleados_impl()` | `empleados_monitor.py` | Elimina N×3 queries |
| 4 | Eager loading en `pedidos_activos()` | `gestor_pedidos_mixin.py` | Elimina N×4 lazy loads |
| 5 | LEFT JOIN en `picking_activo()` | `picking_basico.py` | Evita full scan histórico |
| 6 | Filtro estado activo en `repartos_con_repartidor_ids` | `reparto_asignacion.py` | Evita crecer con histórico |
| 7 | Batch pre-load en `repartidores()` | `reparto_asignacion.py` | Elimina N×2 queries |
| 8 | `alertas()` 5 queries → 1 | `gestor_pedidos_mixin.py` | Menos round-trips |
| 9 | `joinedload(cliente)` en `historial_pedidos()` | `gestor_pedidos_mixin.py` | Elimina lazy loads paginación |
| 10 | `metricas()` GROUP BY | `gestor_pedidos_mixin.py` | Menos round-trips dashboard |
| 11 | `load_only` en `estadisticas()` | `gestor_estadisticas_mixin.py` | Menos datos transferidos |
