# Dashboard Query Optimization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminar N+1, full scans y queries redundantes en `managers/dashboard/` sin cambiar ninguna interfaz pública.

**Architecture:** Enfoque B — fixes aislados por archivo + dos helpers de batch en `_base.py` (`_batch_pickings`, `_batch_repartos`) que centralizan el pre-load de datos operativos por empleado. El resto de fixes son puntuales: eager loading, subqueries en SQL, `load_only`, y consolidación de COUNTs en GROUP BY.

**Tech Stack:** Python 3.11, SQLAlchemy 2.x, SQL Server (pyodbc), Flask. Tests con `pytest` + `fakeredis` (sin BD real). Los tests de BD se saltan automáticamente en CI.

---

## Mapa de archivos

| Archivo | Qué cambia |
|---------|-----------|
| `managers/dashboard/_base.py` | Reescribir `_tiempo_medio()` con self-join; añadir `_batch_pickings()` y `_batch_repartos()` |
| `managers/dashboard/empleados_monitor.py` | `_monitor_empleados_impl()`: sustituir bucle N+1 por lectura de batch dicts |
| `managers/dashboard/gestor_pedidos_mixin.py` | Eager loading en `pedidos_activos()`; `alertas()` 5→1 query; `historial_pedidos()` joinedload; `metricas()` GROUP BY |
| `managers/dashboard/picking_basico.py` | `picking_activo()`: full scan → LEFT OUTER JOIN |
| `managers/dashboard/reparto_asignacion.py` | `repartos_con_repartidor_ids` filtro de estado; `repartidores()` N+1 → batch |
| `managers/dashboard/gestor_estadisticas_mixin.py` | `estadisticas()`: añadir `load_only` |

---

## Task 1: `_base.py` — `_tiempo_medio()` self-join + helpers de batch

**Files:**
- Modify: `managers/dashboard/_base.py`

### Contexto

`_tiempo_medio()` actualmente lanza 1 query por cada pedido del día (N+1). Con 30 entregas hoy = 60 queries extra solo en `metricas()` (que la llama dos veces). Se reescribe con un self-join en SQL Server.

`_batch_pickings` y `_batch_repartos` son helpers privados que se usarán en los Tasks 2 y 6 para eliminar otros N+1.

### Implementación

- [ ] **Reemplazar el contenido completo de `managers/dashboard/_base.py`:**

```python
import logging
from collections import defaultdict
from datetime import datetime
from threading import Thread

from sqlalchemy import and_, or_, text
from sqlalchemy import func
from sqlalchemy.orm import aliased, joinedload

from models import Empleado, HistorialEstadoPedido, PickingPedido, Reparto, Pedido
from states import EstadoPedido, EstadoPicking, EstadoReparto

logger = logging.getLogger(__name__)


class GestorDashboardBase:

    @property
    def session(self):
        """Devuelve la sesión activa de base de datos."""
        from database import get_db
        return get_db()

    _ESTADOS_PROTEGIDOS = frozenset({'en_pausa', 'desconectado'})

    def _actualizar_estado_operativo(self, empleado_id: int, nuevo_estado: str) -> None:
        """Actualiza estado_operativo en background con su propia sesión de BD.

        Los estados en_pausa y desconectado son manuales — el sistema no los sobreescribe.
        Corre en un thread daemon para no bloquear la respuesta HTTP.
        """
        if not empleado_id:
            return
        estados_protegidos = self._ESTADOS_PROTEGIDOS

        def _ejecutar():
            """Aplica el cambio de estado sin bloquear la petición."""
            from database import SessionLocal
            s = SessionLocal()
            try:
                s.query(Empleado).filter(
                    Empleado.EmpleadoID == empleado_id,
                    Empleado.estado_operativo.notin_(estados_protegidos),
                ).update({'estado_operativo': nuevo_estado}, synchronize_session=False)
                s.commit()
            except Exception as e:
                logger.warning("No se pudo actualizar estado_operativo de empleado %s: %s", empleado_id, e)
                s.rollback()
            finally:
                s.close()

        Thread(target=_ejecutar, daemon=True).start()

    def _tiempo_medio(self, desde: datetime, estado_inicio: EstadoPedido, estado_fin: EstadoPedido):
        """Calcula el tiempo medio en minutos entre dos estados usando un self-join en SQL Server.

        Una sola query en lugar de 1 query por pedido (N+1 anterior).
        """
        s = self.session
        h_fin = aliased(HistorialEstadoPedido)
        h_ini = aliased(HistorialEstadoPedido)

        result = (
            s.query(
                func.avg(
                    func.datediff(text('minute'), h_ini.cambiado_en, h_fin.cambiado_en)
                )
            )
            .select_from(h_fin)
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
        return round(float(result), 1) if result is not None else None

    def _batch_pickings(
        self,
        ids: list,
        estados_activos: list,
        desde: datetime,
    ) -> dict:
        """Carga pickings activos + completados hoy para una lista de empleado_ids en una sola query.

        Returns:
            defaultdict con clave empleado_id → {'activos': [...], 'completados': [...]}
            Los 'completados' son los finalizados desde `desde`.
            Los objetos PickingPedido vienen con `items` eager-loaded.
        """
        empty: dict = defaultdict(lambda: {'activos': [], 'completados': []})
        if not ids:
            return empty

        rows = (
            self.session.query(PickingPedido)
            .options(joinedload(PickingPedido.items))
            .filter(
                PickingPedido.empleado_id.in_(ids),
                or_(
                    PickingPedido.estado.in_(estados_activos),
                    and_(
                        PickingPedido.estado == EstadoPicking.COMPLETADO.value,
                        PickingPedido.completado_en >= desde,
                    ),
                ),
            )
            .all()
        )

        result: dict = defaultdict(lambda: {'activos': [], 'completados': []})
        for pk in rows:
            if pk.estado in estados_activos:
                result[pk.empleado_id]['activos'].append(pk)
            else:
                result[pk.empleado_id]['completados'].append(pk)
        return result

    def _batch_repartos(
        self,
        ids: list,
        estados_activos: list,
        desde: datetime,
    ) -> dict:
        """Carga repartos activos + entregados hoy para una lista de repartidor_ids en una sola query.

        Returns:
            defaultdict con clave repartidor_id → {'activos': [...], 'entregados': [...]}
            Los objetos Reparto vienen con pedido y pedido.cliente eager-loaded.
        """
        empty: dict = defaultdict(lambda: {'activos': [], 'entregados': []})
        if not ids:
            return empty

        rows = (
            self.session.query(Reparto)
            .options(
                joinedload(Reparto.pedido).joinedload(Pedido.cliente)
            )
            .filter(
                Reparto.repartidor_id.in_(ids),
                or_(
                    Reparto.estado.in_(estados_activos),
                    and_(
                        Reparto.estado == EstadoReparto.ENTREGADO.value,
                        Reparto.hora_entrega_real >= desde,
                    ),
                ),
            )
            .all()
        )

        result: dict = defaultdict(lambda: {'activos': [], 'entregados': []})
        for r in rows:
            if r.estado in estados_activos:
                result[r.repartidor_id]['activos'].append(r)
            else:
                result[r.repartidor_id]['entregados'].append(r)
        return result
```

- [ ] **Ejecutar tests:**

```bash
cd /home/siemprearmando/test/panchi-bot
pytest -v --tb=short 2>&1 | tail -20
```

Los tests de BD se saltan (no hay SQL Server en CI). Esperado: mismos resultados que antes del cambio.

- [ ] **Commit:**

```bash
git add managers/dashboard/_base.py
git commit -m "perf(dashboard): _tiempo_medio self-join + _batch_pickings/_batch_repartos helpers"
```

---

## Task 2: `empleados_monitor.py` — eliminar N+1 por empleado

**Files:**
- Modify: `managers/dashboard/empleados_monitor.py`

### Contexto

`_monitor_empleados_impl()` lanza 2-3 queries por cada picker y 2 por cada repartidor dentro del bucle principal. Con 5 pickers + 3 repartidores = hasta 21 queries dentro del bucle. Se sustituye por los batch helpers del Task 1.

### Implementación

- [ ] **Sustituir el método `_monitor_empleados_impl()` completo.**

Localiza el método en `managers/dashboard/empleados_monitor.py` (línea 35) y reemplázalo por:

```python
def _monitor_empleados_impl(self) -> dict:
    s = self.session
    ahora = datetime.utcnow()
    hoy = ahora.replace(hour=0, minute=0, second=0, microsecond=0)

    estados_activos_picking = [
        EstadoPicking.PENDIENTE.value,
        EstadoPicking.EN_PROCESO.value,
        EstadoPicking.CON_INCIDENCIAS.value,
    ]
    estados_activos_reparto = [EstadoReparto.ASIGNADO.value, EstadoReparto.EN_CAMINO.value]

    hoy_date = ahora.date()
    empleados = (
        s.query(Empleado)
        .join(Turno, and_(
            Turno.empleado_id == Empleado.EmpleadoID,
            Turno.fecha == hoy_date,
            Turno.estado != 'cancelado',
        ))
        .filter(Empleado.activo == True)
        .order_by(Empleado.Nombre)
        .all()
    )

    ids = [e.EmpleadoID for e in empleados]
    checked_in_ids = set()
    if ids:
        checked_in_ids = {
            ci.empleado_id
            for ci in s.query(CheckIn.empleado_id).filter(
                CheckIn.empleado_id.in_(ids),
                CheckIn.fecha == hoy_date,
                CheckIn.fin == None,
            ).all()
        }

    # Pre-compute role inference sets — avoids 2 queries per employee with ambiguous role
    ids_con_picking = set()
    ids_con_reparto = set()
    if ids:
        ids_con_picking = {
            row[0] for row in s.query(PickingPedido.empleado_id)
            .filter(PickingPedido.empleado_id.in_(ids))
            .distinct().all()
        }
        ids_con_reparto = {
            row[0] for row in s.query(Reparto.repartidor_id)
            .filter(Reparto.repartidor_id.in_(ids))
            .distinct().all()
        }

    # Batch pre-load — 2 queries replace N×3 queries inside the loop
    pickings_batch = self._batch_pickings(ids, estados_activos_picking, hoy)
    repartos_batch = self._batch_repartos(ids, estados_activos_reparto, hoy)

    pickers_data = []
    repartidores_data = []

    for e in empleados:
        nombre_rol = (e.rol.nombre.lower() if e.rol else (e.Puesto or "").lower())
        es_picker = "picker" in nombre_rol
        es_repartidor = "repartidor" in nombre_rol or "reparto" in nombre_rol

        if not es_picker and not es_repartidor:
            es_picker = e.EmpleadoID in ids_con_picking
            es_repartidor = e.EmpleadoID in ids_con_reparto

        # ── PICKER ────────────────────────────────────────────────────────
        if es_picker:
            emp_pickings = pickings_batch[e.EmpleadoID]
            pickings_activos = sorted(
                emp_pickings['activos'], key=lambda pk: pk.created_at or ahora
            )
            completados_hoy = emp_pickings['completados']

            # Avg picking time (min)
            tiempos = [
                (pk.completado_en - pk.iniciado_en).total_seconds() / 60
                for pk in completados_hoy
                if pk.iniciado_en and pk.completado_en
            ]
            tiempo_medio = round(sum(tiempos) / len(tiempos)) if tiempos else None

            # Incidents today — items ya eager-loaded en _batch_pickings
            ids_picking_hoy = (
                [pk.id for pk in completados_hoy] + [pk.id for pk in pickings_activos]
            )
            incidencias_hoy = sum(
                1
                for pk in completados_hoy + pickings_activos
                for item in pk.items
                if item.estado in ("sin_stock", "sustituido")
            )

            # Current picking detail
            pickings_activos_data = []
            for pk in pickings_activos:
                items = pk.items  # already eager-loaded
                total_items = len(items)
                completados_items = sum(
                    1 for i in items if i.estado in ("encontrado", "sustituido")
                )
                sin_stock_items = sum(1 for i in items if i.estado == "sin_stock")
                minutos_activo = (
                    int((ahora - pk.iniciado_en).total_seconds() / 60)
                    if pk.iniciado_en else None
                )
                pickings_activos_data.append({
                    "picking_id": pk.id,
                    "pedido_id": pk.pedido_id,
                    "estado": pk.estado,
                    "iniciado_en": _iso(pk.iniciado_en),
                    "minutos_activo": minutos_activo,
                    "items_total": total_items,
                    "items_completados": completados_items,
                    "items_sin_stock": sin_stock_items,
                    "progreso_pct": (
                        round(completados_items / total_items * 100) if total_items else 0
                    ),
                })

            n_activos = len(pickings_activos)
            if n_activos >= 3:
                estado = "sobrecargado"
            elif n_activos >= 1:
                estado = "activo"
            elif completados_hoy:
                estado = "inactivo"
            else:
                estado = "sin_carga"

            todos_pk = pickings_activos + completados_hoy
            ultima_actividad = None
            if todos_pk:
                ts_vals = [
                    pk.completado_en or pk.iniciado_en or pk.created_at
                    for pk in todos_pk
                    if pk.completado_en or pk.iniciado_en or pk.created_at
                ]
                ultima_actividad = max(ts_vals) if ts_vals else None

            rendimiento = None
            if tiempo_medio is not None:
                rendimiento = "rapido" if tiempo_medio < 15 else ("lento" if tiempo_medio > 30 else "normal")

            historial_picker = []
            for pk in sorted(completados_hoy, key=lambda x: x.completado_en or x.created_at, reverse=True):
                dur = None
                if pk.iniciado_en and pk.completado_en:
                    dur = int((pk.completado_en - pk.iniciado_en).total_seconds() / 60)
                historial_picker.append({
                    "pedido_id": pk.pedido_id,
                    "completado_en": _iso(pk.completado_en),
                    "duracion_min": dur,
                })

            pickers_data.append({
                "empleado_id": e.EmpleadoID,
                "nombre": f"{e.Nombre} {e.Apellido}",
                "telefono": e.Telefono,
                "estado": estado,
                "estado_operativo": e.estado_operativo,
                "has_checked_in": e.EmpleadoID in checked_in_ids,
                "pedidos_activos": n_activos,
                "completados_hoy": len(completados_hoy),
                "pickings_activos": pickings_activos_data,
                "historial_hoy": historial_picker,
                "tiempo_medio_min": tiempo_medio,
                "ultima_actividad": _iso(ultima_actividad),
                "incidencias_hoy": incidencias_hoy,
                "rendimiento": rendimiento,
            })

        # ── REPARTIDOR ────────────────────────────────────────────────────
        if es_repartidor:
            emp_repartos = repartos_batch[e.EmpleadoID]
            repartos_activos = emp_repartos['activos']
            entregados_hoy = emp_repartos['entregados']

            # Avg delivery time
            tiempos = [
                (r.hora_entrega_real - r.hora_salida).total_seconds() / 60
                for r in entregados_hoy
                if r.hora_salida and r.hora_entrega_real
            ]
            tiempo_medio = round(sum(tiempos) / len(tiempos)) if tiempos else None

            entregas_activas = []
            for r in sorted(repartos_activos, key=lambda x: x.hora_salida or x.created_at or ahora, reverse=True):
                minutos_en_ruta = (
                    int((ahora - r.hora_salida).total_seconds() / 60)
                    if r.hora_salida else None
                )
                entregas_activas.append({
                    "reparto_id": r.id,
                    "pedido_id": r.pedido_id,
                    "estado": r.estado,
                    "hora_salida": _iso(r.hora_salida),
                    "minutos_en_ruta": minutos_en_ruta,
                    "direccion": r.pedido.DireccionEntrega if r.pedido else "—",
                    "total": float(r.pedido.Total) if r.pedido and r.pedido.Total else 0.0,
                    "forma_pago": r.pedido.forma_pago if r.pedido else None,
                })

            tiempo_inactivo_min = None
            if not repartos_activos and entregados_hoy:
                ultimo = max(entregados_hoy, key=lambda r: r.hora_entrega_real or r.created_at)
                ref = ultimo.hora_entrega_real or ultimo.created_at
                if ref:
                    tiempo_inactivo_min = int((ahora - ref).total_seconds() / 60)

            n_activos = len(repartos_activos)
            if n_activos >= 3:
                estado = "sobrecargado"
            elif n_activos >= 1:
                estado = "activo"
            elif entregados_hoy:
                estado = "inactivo"
            else:
                estado = "sin_carga"

            todos_r = repartos_activos + entregados_hoy
            ultima_actividad = None
            if todos_r:
                ts_vals = [
                    r.hora_entrega_real or r.hora_salida or r.created_at
                    for r in todos_r
                    if r.hora_entrega_real or r.hora_salida or r.created_at
                ]
                ultima_actividad = max(ts_vals) if ts_vals else None

            rendimiento = None
            if tiempo_medio is not None:
                rendimiento = "rapido" if tiempo_medio < 20 else ("lento" if tiempo_medio > 40 else "normal")

            carga = "alta" if n_activos >= 3 else ("media" if n_activos == 2 else "ligera")

            historial_repartidor = []
            for r in sorted(entregados_hoy, key=lambda x: x.hora_entrega_real or x.created_at, reverse=True):
                dur = None
                if r.hora_salida and r.hora_entrega_real:
                    dur = int((r.hora_entrega_real - r.hora_salida).total_seconds() / 60)
                historial_repartidor.append({
                    "pedido_id": r.pedido_id,
                    "entregado_en": _iso(r.hora_entrega_real),
                    "duracion_min": dur,
                    "total": float(r.pedido.Total) if r.pedido and r.pedido.Total else 0.0,
                    "forma_pago": r.pedido.forma_pago if r.pedido else None,
                })

            repartidores_data.append({
                "empleado_id": e.EmpleadoID,
                "nombre": f"{e.Nombre} {e.Apellido}",
                "telefono": e.Telefono,
                "estado": estado,
                "estado_operativo": e.estado_operativo,
                "has_checked_in": e.EmpleadoID in checked_in_ids,
                "pedidos_activos": n_activos,
                "entregados_hoy": len(entregados_hoy),
                "entregas_activas": entregas_activas,
                "historial_hoy": historial_repartidor,
                "tiempo_medio_min": tiempo_medio,
                "tiempo_inactivo_min": tiempo_inactivo_min,
                "ultima_actividad": _iso(ultima_actividad),
                "rendimiento": rendimiento,
                "carga": carga,
            })

    # Pipeline counts — single GROUP BY query
    estados_pipeline = [
        EstadoPedido.PAGADO.value,
        EstadoPedido.CONTRA_REEMBOLSO.value,
        EstadoPedido.EN_PREPARACION.value,
        EstadoPedido.PREPARADO.value,
        EstadoPedido.EN_REPARTO.value,
    ]
    pipeline = {estado_val: 0 for estado_val in estados_pipeline}
    for estado_val, count in (
        s.query(Pedido.Estado, func.count(Pedido.PedidoID))
        .filter(Pedido.Estado.in_(estados_pipeline))
        .group_by(Pedido.Estado)
        .all()
    ):
        pipeline[estado_val] = count
    pipeline[EstadoPedido.ENTREGADO.value] = s.query(func.count(Pedido.PedidoID)).filter(
        Pedido.Estado == EstadoPedido.ENTREGADO.value,
        Pedido.FechaActualizacion >= hoy,
    ).scalar() or 0

    incidencias_abiertas = s.query(func.count(Incidencia.id)).filter(
        Incidencia.estado.in_(["abierta", "en_proceso"])
    ).scalar() or 0

    sin_picker = s.query(Pedido).options(
        joinedload(Pedido.cliente),
        joinedload(Pedido.detalles),
    ).filter(
        Pedido.Estado.in_(_ESTADOS_LISTOS_PARA_PICKING),
    ).order_by(Pedido.FechaCreacion.asc()).all()

    pedidos_sin_picker = [
        {
            "pedido_id": p.PedidoID,
            "cliente_nombre": p.cliente.nombre if p.cliente else "—",
            "total": float(p.Total) if p.Total else 0.0,
            "forma_pago": p.forma_pago or "online",
            "fecha_creacion": _iso(p.FechaCreacion),
            "minutos_espera": int((ahora - p.FechaCreacion).total_seconds() / 60) if p.FechaCreacion else None,
            "n_items": len(p.detalles),
        }
        for p in sin_picker
    ]

    repartos_pendientes = (
        s.query(Reparto).options(
            joinedload(Reparto.pedido).joinedload(Pedido.cliente)
        )
        .filter(
            Reparto.repartidor_id == None,
            Reparto.estado == EstadoReparto.PENDIENTE.value,
        )
        .join(Pedido, Pedido.PedidoID == Reparto.pedido_id)
        .filter(Pedido.Estado == EstadoPedido.PREPARADO.value)
        .order_by(Reparto.created_at.asc())
        .all()
    )

    pedidos_sin_repartidor = [
        {
            "pedido_id": r.pedido.PedidoID,
            "reparto_id": r.id,
            "cliente_nombre": r.pedido.cliente.nombre if r.pedido.cliente else "—",
            "direccion": r.pedido.DireccionEntrega,
            "total": float(r.pedido.Total) if r.pedido.Total else 0.0,
            "forma_pago": r.pedido.forma_pago or "online",
            "fecha_creacion": _iso(r.pedido.FechaCreacion),
            "minutos_espera": int((ahora - r.pedido.FechaCreacion).total_seconds() / 60) if r.pedido.FechaCreacion else None,
        }
        for r in repartos_pendientes
    ]

    return {
        "pickers": pickers_data,
        "repartidores": repartidores_data,
        "pipeline": pipeline,
        "pedidos_sin_picker": pedidos_sin_picker,
        "pedidos_sin_repartidor": pedidos_sin_repartidor,
        "incidencias_abiertas": incidencias_abiertas,
        "ts": _iso(ahora),
    }
```

- [ ] **Verificar que los imports en la cabecera del archivo son correctos.** El archivo ya importa `joinedload`, `func`, `Incidencia`, `PickingItem`, `PickingPedido`, `Reparto`, `Pedido`, `Turno`, `CheckIn`, `Empleado`. Comprueba que siguen todos presentes — no añadas imports duplicados.

- [ ] **Ejecutar tests:**

```bash
pytest -v --tb=short 2>&1 | tail -20
```

- [ ] **Commit:**

```bash
git add managers/dashboard/empleados_monitor.py
git commit -m "perf(dashboard): monitor_empleados usa batch pre-load, elimina N+1 por empleado"
```

---

## Task 3: `gestor_pedidos_mixin.py` — 4 fixes

**Files:**
- Modify: `managers/dashboard/gestor_pedidos_mixin.py`

### 3a — `pedidos_activos()`: eager loading

- [ ] **Localiza la query de pedidos en `pedidos_activos()` (línea ~112):**

```python
# ANTES
query = s.query(Pedido).filter(Pedido.Estado.in_(_ESTADOS_OPERATIVOS))
if estado:
    query = query.filter(Pedido.Estado == estado)
pedidos = query.order_by(Pedido.FechaCreacion.asc()).all()
```

Reemplaza por:

```python
from sqlalchemy.orm import joinedload, selectinload

query = s.query(Pedido).filter(Pedido.Estado.in_(_ESTADOS_OPERATIVOS))
if estado:
    query = query.filter(Pedido.Estado == estado)
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

Asegúrate de que `PickingPedido` y `Reparto` están importados en la cabecera del archivo (ya lo están).

### 3b — `alertas()`: 5 queries → 1

- [ ] **Localiza el bucle en `alertas()` (línea ~193):**

```python
# ANTES
for estado, (umbral, nivel, desc) in _UMBRALES_RETRASO.items():
    pedidos = s.query(Pedido).filter(Pedido.Estado == estado).all()
    for p in pedidos:
        ref = p.FechaActualizacion or p.FechaCreacion
        if ref:
            minutos = (ahora - ref).total_seconds() / 60
            if minutos > umbral:
                resultado.append({...})
```

Reemplaza el bucle por:

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
    ref = p.FechaActualizacion or p.FechaCreacion
    if ref:
        minutos = (ahora - ref).total_seconds() / 60
        if minutos > umbral:
            resultado.append({
                "tipo": "pedido_retrasado",
                "nivel": nivel,
                "pedido_id": p.PedidoID,
                "mensaje": f"Pedido #{p.PedidoID} lleva {int(minutos)}min {desc}",
                "minutos": int(minutos),
                "creada_en": _iso(ahora),
            })
```

### 3c — `historial_pedidos()`: joinedload cliente

- [ ] **Localiza la query de datos en `historial_pedidos()` (línea ~323):**

```python
# ANTES
pedidos = (
    query
    .order_by(Pedido.FechaCreacion.desc())
    .offset((page - 1) * per_page)
    .limit(per_page)
    .all()
)
```

Reemplaza por:

```python
from sqlalchemy.orm import joinedload

pedidos = (
    query
    .options(joinedload(Pedido.cliente))
    .order_by(Pedido.FechaCreacion.desc())
    .offset((page - 1) * per_page)
    .limit(per_page)
    .all()
)
```

El `query.count()` que está justo antes de esta línea no necesita el joinedload — déjalo tal cual.

### 3d — `metricas()`: consolidar 5 COUNTs en 1 GROUP BY

- [ ] **Localiza los 5 COUNTs de estado en `metricas()` (líneas ~31-46):**

```python
# ANTES — 5 queries separadas
pedidos_activos = s.query(func.count(Pedido.PedidoID)).filter(
    Pedido.Estado.in_(_ESTADOS_OPERATIVOS)
).scalar() or 0

en_preparacion = s.query(func.count(Pedido.PedidoID)).filter(
    Pedido.Estado == EstadoPedido.EN_PREPARACION.value
).scalar() or 0

en_reparto = s.query(func.count(Pedido.PedidoID)).filter(
    Pedido.Estado == EstadoPedido.EN_REPARTO.value
).scalar() or 0

entregados_hoy = s.query(func.count(Pedido.PedidoID)).filter(
    Pedido.Estado == EstadoPedido.ENTREGADO.value,
    Pedido.FechaActualizacion >= hoy,
).scalar() or 0
```

Reemplaza esas 4 queries por:

```python
# 1 GROUP BY para los estados operativos (4 queries → 1)
_counts_estado = dict(
    s.query(Pedido.Estado, func.count(Pedido.PedidoID))
    .filter(Pedido.Estado.in_(_ESTADOS_OPERATIVOS))
    .group_by(Pedido.Estado)
    .all()
)
pedidos_activos = sum(_counts_estado.values())
en_preparacion = _counts_estado.get(EstadoPedido.EN_PREPARACION.value, 0)
en_reparto = _counts_estado.get(EstadoPedido.EN_REPARTO.value, 0)

# entregados_hoy necesita filtro de FechaActualizacion — query separada
entregados_hoy = s.query(func.count(Pedido.PedidoID)).filter(
    Pedido.Estado == EstadoPedido.ENTREGADO.value,
    Pedido.FechaActualizacion >= hoy,
).scalar() or 0
```

El resto de `metricas()` (pedidos_hoy, pickers_activos, repartidores_activos, ingresos_hoy, cancelados_hoy, ingresos_metodo, y las dos llamadas a `_tiempo_medio`) permanece sin cambios.

- [ ] **Ejecutar tests:**

```bash
pytest -v --tb=short 2>&1 | tail -20
```

- [ ] **Commit:**

```bash
git add managers/dashboard/gestor_pedidos_mixin.py
git commit -m "perf(dashboard): eager loading pedidos_activos, alertas 1 query, historial joinedload, metricas GROUP BY"
```

---

## Task 4: `picking_basico.py` — LEFT JOIN elimina full scan

**Files:**
- Modify: `managers/dashboard/picking_basico.py`

### Contexto

`picking_activo()` carga **toda** la tabla `picking_pedido` en Python para construir una lista de IDs y luego hace un NOT IN. Conforme crece el histórico esta lista crece sin límite. Un LEFT OUTER JOIN hace la misma cosa en SQL.

- [ ] **Localiza las líneas 23-27 en `picking_activo()`:**

```python
# ANTES
pickings_existentes_ids = [pk.pedido_id for pk in s.query(PickingPedido.pedido_id).all()]
pagados_sin_picking = s.query(Pedido).filter(
    Pedido.Estado.in_(_ESTADOS_LISTOS_PARA_PICKING),
    ~Pedido.PedidoID.in_(pickings_existentes_ids) if pickings_existentes_ids else True,
).all()
```

Reemplaza por:

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

- [ ] **Ejecutar tests:**

```bash
pytest -v --tb=short 2>&1 | tail -20
```

- [ ] **Commit:**

```bash
git add managers/dashboard/picking_basico.py
git commit -m "perf(dashboard): picking_activo usa LEFT JOIN en vez de full scan + NOT IN"
```

---

## Task 5: `reparto_asignacion.py` — filtro histórico + batch en `repartidores()`

**Files:**
- Modify: `managers/dashboard/reparto_asignacion.py`

### 5a — Filtro de estado en `repartos_con_repartidor_ids`

- [ ] **Localiza las líneas 49-53:**

```python
# ANTES — sin filtro de estado, crece con todo el histórico
repartos_con_repartidor_ids = {
    r.pedido_id for r in s.query(Reparto.pedido_id).filter(
        Reparto.repartidor_id != None
    ).all()
}
```

Reemplaza por:

```python
# Solo repartos activos — no carga histórico completo
repartos_con_repartidor_ids = {
    r.pedido_id for r in s.query(Reparto.pedido_id).filter(
        Reparto.repartidor_id != None,
        Reparto.estado.in_([EstadoReparto.ASIGNADO.value, EstadoReparto.EN_CAMINO.value]),
    ).all()
}
```

### 5b — `repartidores()`: N+1 → batch pre-load

- [ ] **Localiza el bucle de empleados en `repartidores()` (línea ~60):**

```python
# ANTES — 2 queries por empleado dentro del bucle
lista_empleados = []
for e in empleados:
    repartos_activos = s.query(Reparto).filter(
        Reparto.repartidor_id == e.EmpleadoID,
        Reparto.estado.in_([EstadoReparto.ASIGNADO.value, EstadoReparto.EN_CAMINO.value]),
    ).all()

    entregados_hoy = s.query(func.count(Reparto.id)).filter(
        Reparto.repartidor_id == e.EmpleadoID,
        Reparto.estado == EstadoReparto.ENTREGADO.value,
        Reparto.hora_entrega_real >= hoy_dt,
    ).scalar() or 0
    ...
```

Reemplaza el bucle por (añade el batch pre-load antes del bucle y actualiza el cuerpo del bucle):

```python
# Batch pre-load — 1 query en lugar de N×2
ids_empleados = [e.EmpleadoID for e in empleados]
estados_activos_rep = [EstadoReparto.ASIGNADO.value, EstadoReparto.EN_CAMINO.value]
repartos_batch = self._batch_repartos(ids_empleados, estados_activos_rep, hoy_dt)

lista_empleados = []
for e in empleados:
    emp_repartos = repartos_batch[e.EmpleadoID]
    repartos_activos = emp_repartos['activos']
    entregados_hoy_count = len(emp_repartos['entregados'])

    pedidos_activos_data = [
        {
            "reparto_id": r.id,
            "pedido_id": r.pedido_id,
            "estado_reparto": r.estado,
            "direccion": r.pedido.DireccionEntrega if r.pedido else "—",
            "hora_salida": _iso(r.hora_salida),
            "hora_estimada_entrega": _iso(r.hora_estimada_entrega),
            "total": float(r.pedido.Total) if r.pedido and r.pedido.Total else 0.0,
        }
        for r in repartos_activos
    ]

    lista_empleados.append({
        "empleado_id": e.EmpleadoID,
        "nombre": f"{e.Nombre} {e.Apellido}",
        "telefono": e.Telefono,
        "activo": e.activo,
        "rol": e.rol.nombre if e.rol else e.Puesto,
        "pedidos_activos": pedidos_activos_data,
        "entregados_hoy": entregados_hoy_count,
        "tiene_checkin": e.EmpleadoID in checkins_abiertos,
    })
```

- [ ] **Ejecutar tests:**

```bash
pytest -v --tb=short 2>&1 | tail -20
```

- [ ] **Commit:**

```bash
git add managers/dashboard/reparto_asignacion.py
git commit -m "perf(dashboard): repartidores batch pre-load + filtro estado activo en repartos_con_repartidor_ids"
```

---

## Task 6: `gestor_estadisticas_mixin.py` — `load_only` en `estadisticas()`

**Files:**
- Modify: `managers/dashboard/gestor_estadisticas_mixin.py`

### Contexto

`estadisticas()` carga todos los campos de `Pedido` cuando solo usa `PedidoID`, `Estado`, `Total`, `FechaCreacion`, `forma_pago`. Para un rango de 7 días con 200 pedidos se transfieren columnas innecesarias (direcciones, notas, tokens, etc.).

- [ ] **Localiza la query en `estadisticas()` (línea ~39):**

```python
# ANTES
pedidos = (
    s.query(Pedido)
    .filter(Pedido.FechaCreacion >= dt_desde, Pedido.FechaCreacion <= dt_hasta)
    .all()
)
```

Reemplaza por:

```python
from sqlalchemy.orm import load_only

pedidos = (
    s.query(Pedido)
    .options(load_only(
        Pedido.PedidoID,
        Pedido.Estado,
        Pedido.Total,
        Pedido.FechaCreacion,
        Pedido.forma_pago,
    ))
    .filter(Pedido.FechaCreacion >= dt_desde, Pedido.FechaCreacion <= dt_hasta)
    .all()
)
```

- [ ] **Ejecutar tests:**

```bash
pytest -v --tb=short 2>&1 | tail -20
```

- [ ] **Commit:**

```bash
git add managers/dashboard/gestor_estadisticas_mixin.py
git commit -m "perf(dashboard): estadisticas load_only — carga solo columnas necesarias de Pedido"
```

---

## Task 7: Verificación final

- [ ] **Ejecutar suite completa:**

```bash
pytest -v --tb=short 2>&1 | tail -30
```

Esperado: mismos resultados que antes de empezar (los 3 tests pre-existentes que fallaban siguen fallando — no son regresiones nuestras).

- [ ] **Verificar que no hay imports rotos:**

```bash
python -c "from managers.gestor_dashboard import GestorDashboard; print('OK')"
```

Esperado: `OK`

- [ ] **Revisar diff global para detectar cualquier cambio no intencionado:**

```bash
git diff HEAD~6
```

Esperado: solo los 6 archivos del plan, sin modificaciones en blueprints, controllers ni tests.
