"""Empleados — monitorización en tiempo real del equipo operativo."""
import logging
from datetime import datetime

from sqlalchemy import and_, func
from sqlalchemy.exc import SQLAlchemyError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from managers.dashboard._helpers import _iso, _ESTADOS_LISTOS_PARA_PICKING
from models import (
    CheckIn, Empleado, Incidencia, PedidoDetalle, PickingPedido,
    Reparto, Pedido, Turno, Usuario,
)
from states import EstadoPedido, EstadoPicking, EstadoReparto

logger = logging.getLogger(__name__)


class GestorEmpleadosMonitorMixin:

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        retry=retry_if_exception_type(SQLAlchemyError),
        reraise=True,
    )
    def monitor_empleados(self) -> dict:
        """Aggregated real-time data for the operations monitoring dashboard."""
        try:
            return self._monitor_empleados_impl()
        except Exception:
            logger.exception("monitor_empleados falló")
            raise

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

                # Incidents today — items already eager-loaded in _batch_pickings
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

        # Pipeline counts — single GROUP BY query instead of one COUNT per state
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

        # Orders waiting for a picker — estado PAGADO/CONTRA_REEMBOLSO es fuente de verdad
        n_items_sub = (
            s.query(func.count(PedidoDetalle.DetalleID))
            .filter(PedidoDetalle.PedidoID == Pedido.PedidoID)
            .correlate(Pedido)
            .scalar_subquery()
        )
        sin_picker_rows = (
            s.query(
                Pedido.PedidoID,
                Pedido.Total,
                Pedido.forma_pago,
                Pedido.FechaCreacion,
                Usuario.nombre.label('cliente_nombre'),
                n_items_sub.label('n_items'),
            )
            .outerjoin(Usuario, Usuario.id == Pedido.ClienteID)
            .filter(Pedido.Estado.in_(_ESTADOS_LISTOS_PARA_PICKING))
            .order_by(Pedido.FechaCreacion.asc())
            .all()
        )

        pedidos_sin_picker = [
            {
                "pedido_id": row.PedidoID,
                "cliente_nombre": row.cliente_nombre or "—",
                "total": float(row.Total) if row.Total else 0.0,
                "forma_pago": row.forma_pago or "online",
                "fecha_creacion": _iso(row.FechaCreacion),
                "minutos_espera": int((ahora - row.FechaCreacion).total_seconds() / 60) if row.FechaCreacion else None,
                "n_items": row.n_items or 0,
            }
            for row in sin_picker_rows
        ]

        # Orders ready (preparado) with no rider assigned yet (Reparto PENDIENTE sin repartidor_id)
        repartos_pendientes_rows = (
            s.query(
                Reparto.id.label('reparto_id'),
                Pedido.PedidoID,
                Pedido.DireccionEntrega,
                Pedido.Total,
                Pedido.forma_pago,
                Pedido.FechaCreacion,
                Usuario.nombre.label('cliente_nombre'),
            )
            .join(Pedido, Pedido.PedidoID == Reparto.pedido_id)
            .outerjoin(Usuario, Usuario.id == Pedido.ClienteID)
            .filter(
                Reparto.repartidor_id == None,
                Reparto.estado == EstadoReparto.PENDIENTE.value,
                Pedido.Estado == EstadoPedido.PREPARADO.value,
            )
            .order_by(Reparto.created_at.asc())
            .all()
        )

        pedidos_sin_repartidor = [
            {
                "pedido_id": row.PedidoID,
                "reparto_id": row.reparto_id,
                "cliente_nombre": row.cliente_nombre or "—",
                "direccion": row.DireccionEntrega,
                "total": float(row.Total) if row.Total else 0.0,
                "forma_pago": row.forma_pago or "online",
                "fecha_creacion": _iso(row.FechaCreacion),
                "minutos_espera": int((ahora - row.FechaCreacion).total_seconds() / 60) if row.FechaCreacion else None,
            }
            for row in repartos_pendientes_rows
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
