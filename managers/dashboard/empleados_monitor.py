"""Empleados — monitorización en tiempo real del equipo operativo."""
import logging
from datetime import datetime

from sqlalchemy import func

from managers.dashboard._helpers import _iso, _ESTADOS_LISTOS_PARA_PICKING
from models import (
    Empleado, Incidencia, PickingItem, PickingPedido, Reparto, Pedido,
)
from states import EstadoPedido, EstadoPicking, EstadoReparto

logger = logging.getLogger(__name__)


class GestorEmpleadosMonitorMixin:

    def monitor_empleados(self) -> dict:
        """Aggregated real-time data for the operations monitoring dashboard."""
        s = self.session
        ahora = datetime.utcnow()
        hoy = ahora.replace(hour=0, minute=0, second=0, microsecond=0)

        estados_activos_picking = [
            EstadoPicking.PENDIENTE.value,
            EstadoPicking.EN_PROCESO.value,
            EstadoPicking.CON_INCIDENCIAS.value,
        ]
        estados_activos_reparto = [EstadoReparto.ASIGNADO.value, EstadoReparto.EN_CAMINO.value]

        empleados = s.query(Empleado).filter(Empleado.activo == True).order_by(Empleado.Nombre).all()

        pickers_data = []
        repartidores_data = []

        for e in empleados:
            nombre_rol = (e.rol.nombre.lower() if e.rol else (e.Puesto or "").lower())
            es_picker = "picker" in nombre_rol
            es_repartidor = "repartidor" in nombre_rol or "reparto" in nombre_rol

            # If rol doesn't say clearly, infer from activity
            if not es_picker and not es_repartidor:
                tiene_picking = s.query(PickingPedido.id).filter(
                    PickingPedido.empleado_id == e.EmpleadoID
                ).first()
                tiene_reparto = s.query(Reparto.id).filter(
                    Reparto.repartidor_id == e.EmpleadoID
                ).first()
                es_picker = bool(tiene_picking)
                es_repartidor = bool(tiene_reparto)

            # ── PICKER ────────────────────────────────────────────────────────
            if es_picker:
                pickings_activos = s.query(PickingPedido).filter(
                    PickingPedido.empleado_id == e.EmpleadoID,
                    PickingPedido.estado.in_(estados_activos_picking),
                ).order_by(PickingPedido.created_at.asc()).all()

                completados_hoy = s.query(PickingPedido).filter(
                    PickingPedido.empleado_id == e.EmpleadoID,
                    PickingPedido.estado == EstadoPicking.COMPLETADO.value,
                    PickingPedido.completado_en >= hoy,
                ).all()

                # Avg picking time (min)
                tiempos = [
                    (pk.completado_en - pk.iniciado_en).total_seconds() / 60
                    for pk in completados_hoy
                    if pk.iniciado_en and pk.completado_en
                ]
                tiempo_medio = round(sum(tiempos) / len(tiempos)) if tiempos else None

                # Incidents today (sin_stock + sustituido items)
                ids_picking_hoy = (
                    [pk.id for pk in completados_hoy] + [pk.id for pk in pickings_activos]
                )
                incidencias_hoy = 0
                if ids_picking_hoy:
                    incidencias_hoy = s.query(func.count(PickingItem.id)).filter(
                        PickingItem.picking_id.in_(ids_picking_hoy),
                        PickingItem.estado.in_(["sin_stock", "sustituido"]),
                    ).scalar() or 0

                # Current picking detail
                pickings_activos_data = []
                for pk in pickings_activos:
                    total_items = len(pk.items)
                    completados_items = sum(
                        1 for i in pk.items if i.estado in ("encontrado", "sustituido")
                    )
                    sin_stock_items = sum(1 for i in pk.items if i.estado == "sin_stock")
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

                # Status
                n_activos = len(pickings_activos)
                if n_activos >= 3:
                    estado = "sobrecargado"
                elif n_activos >= 1:
                    estado = "activo"
                elif completados_hoy:
                    estado = "inactivo"
                else:
                    estado = "sin_carga"

                # Last activity
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
                repartos_activos = s.query(Reparto).filter(
                    Reparto.repartidor_id == e.EmpleadoID,
                    Reparto.estado.in_(estados_activos_reparto),
                ).all()

                entregados_hoy = s.query(Reparto).filter(
                    Reparto.repartidor_id == e.EmpleadoID,
                    Reparto.estado == EstadoReparto.ENTREGADO.value,
                    Reparto.hora_entrega_real >= hoy,
                ).all()

                # Avg delivery time
                tiempos = [
                    (r.hora_entrega_real - r.hora_salida).total_seconds() / 60
                    for r in entregados_hoy
                    if r.hora_salida and r.hora_entrega_real
                ]
                tiempo_medio = round(sum(tiempos) / len(tiempos)) if tiempos else None

                # All active deliveries
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

                # Idle time
                tiempo_inactivo_min = None
                if not repartos_activos and entregados_hoy:
                    ultimo = max(entregados_hoy, key=lambda r: r.hora_entrega_real or r.created_at)
                    ref = ultimo.hora_entrega_real or ultimo.created_at
                    if ref:
                        tiempo_inactivo_min = int((ahora - ref).total_seconds() / 60)

                # Status
                n_activos = len(repartos_activos)
                if n_activos >= 3:
                    estado = "sobrecargado"
                elif n_activos >= 1:
                    estado = "activo"
                elif entregados_hoy:
                    estado = "inactivo"
                else:
                    estado = "sin_carga"

                # Last activity
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

        # Pipeline counts
        pipeline = {}
        estados_pipeline = [
            EstadoPedido.PAGADO.value,
            EstadoPedido.CONTRA_REEMBOLSO.value,
            EstadoPedido.EN_PREPARACION.value,
            EstadoPedido.PREPARADO.value,
            EstadoPedido.EN_REPARTO.value,
        ]
        for estado_val in estados_pipeline:
            pipeline[estado_val] = s.query(func.count(Pedido.PedidoID)).filter(
                Pedido.Estado == estado_val
            ).scalar() or 0
        pipeline[EstadoPedido.ENTREGADO.value] = s.query(func.count(Pedido.PedidoID)).filter(
            Pedido.Estado == EstadoPedido.ENTREGADO.value,
            Pedido.FechaActualizacion >= hoy,
        ).scalar() or 0

        incidencias_abiertas = s.query(func.count(Incidencia.id)).filter(
            Incidencia.estado.in_(["abierta", "en_proceso"])
        ).scalar() or 0

        # Orders waiting for a picker — estado PAGADO/CONTRA_REEMBOLSO es fuente de verdad
        sin_picker = s.query(Pedido).filter(
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

        # Orders ready (preparado) with no rider assigned yet (Reparto PENDIENTE sin repartidor_id)
        repartos_pendientes = (
            s.query(Reparto)
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
