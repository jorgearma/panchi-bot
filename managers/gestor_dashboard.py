import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from threading import Thread

from sqlalchemy import func, or_, and_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload, selectinload

from models import (
    Empleado, HistorialEstadoPedido, Incidencia, Pedido, PedidoDetalle,
    PickingItem, PickingPedido, Producto, Reparto, Rol,
)
from states import (
    ESTADOS_TERMINALES_PEDIDO, EstadoPedido, EstadoPicking, EstadoReparto,
    transicion_valida_pedido,
)
from managers.dashboard._base import GestorDashboardBase
from managers.dashboard.gestor_pedidos_mixin import GestorPedidosMixin
from managers.dashboard.gestor_picking_mixin import GestorPickingMixin
from managers.dashboard.gestor_reparto_mixin import GestorRepartoMixin
from managers.dashboard._helpers import (
    _iso,
    _TARANCON_LAT,
    _TARANCON_LNG,
    _COLORES_ESTADO,
    _UMBRALES_RETRASO,
    _ESTADOS_OPERATIVOS,
    _ESTADOS_LISTOS_PARA_PICKING,
)

logger = logging.getLogger(__name__)


class GestorDashboard(GestorPedidosMixin, GestorPickingMixin, GestorRepartoMixin, GestorDashboardBase):

    # -------------------------------------------------------------------------
    # Read methods
    # -------------------------------------------------------------------------

    def empleados_disponibles(self, rol: str = None) -> list:
        query = self.session.query(Empleado).filter(Empleado.activo == True)
        if rol:
            query = query.join(Rol, Empleado.rol_id == Rol.id).filter(Rol.nombre == rol)
        return [
            {
                "id": e.EmpleadoID,
                "nombre": f"{e.Nombre} {e.Apellido}",
                "telefono": e.Telefono,
                "rol": e.rol.nombre if e.rol else e.Puesto,
            }
            for e in query.order_by(Empleado.Nombre).all()
        ]

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

        # Orders waiting for a picker — estado PAGADO/CONTRA_REEMBOLSO es fuente de verdad:
        # cuando un picker lo toma, reclamar_picking() transiciona el pedido a EN_PREPARACION.
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

    def turnos_hoy(self) -> dict:
        """Estado de asistencia del día actual.

        Devuelve todos los empleados activos con su check-in de hoy (si lo hay),
        el turno planificado del día, el tiempo acumulado, y el estado operativo.

        Returns:
            {
                empleados: [{
                    id, nombre, rol, rol_activo, estado_operativo,
                    check_in_inicio, check_in_fin, minutos_activo,
                    activo (bool), minutos_tarde,
                    tiene_turno (bool), turno_id, turno_hora_inicio, turno_hora_fin, turno_tipo,
                }],
                resumen: { con_checkin, en_pausa, desconectados, con_turno, ausentes, total }
            }
        """
        from models import CheckIn
        from models import Turno as TurnoModel

        hoy = datetime.utcnow().date()
        ahora = datetime.utcnow()
        s = self.session

        empleados = (
            s.query(Empleado)
            .filter_by(activo=True)
            .order_by(Empleado.Nombre)
            .all()
        )

        # Build dict empleado_id → best check-in of the day
        # Prefer open check-ins; among same type, prefer the most recent
        checkins_hoy = {}
        for ci in s.query(CheckIn).filter(CheckIn.fecha == hoy).all():
            prev = checkins_hoy.get(ci.empleado_id)
            if prev is None:
                checkins_hoy[ci.empleado_id] = ci
            elif ci.fin is None and prev.fin is not None:
                # Open beats closed
                checkins_hoy[ci.empleado_id] = ci
            elif ci.fin is None and prev.fin is None:
                # Both open — keep later
                if ci.inicio > prev.inicio:
                    checkins_hoy[ci.empleado_id] = ci
            elif prev.fin is not None and ci.fin is not None:
                # Both closed — keep later
                if ci.inicio > prev.inicio:
                    checkins_hoy[ci.empleado_id] = ci

        # Build dict empleado_id → turno planificado de hoy (no cancelado)
        turnos_hoy_map = {}
        for t in (
            s.query(TurnoModel)
            .filter(TurnoModel.fecha == hoy, TurnoModel.estado != 'cancelado')
            .all()
        ):
            turnos_hoy_map[t.empleado_id] = t

        resultado = []
        for emp in empleados:
            ci = checkins_hoy.get(emp.EmpleadoID)
            turno = turnos_hoy_map.get(emp.EmpleadoID)
            minutos_activo = None
            if ci:
                fin_efectivo = ci.fin or ahora
                minutos_activo = int((fin_efectivo - ci.inicio).total_seconds() / 60)

            resultado.append({
                'id':               emp.EmpleadoID,
                'nombre':           f'{emp.Nombre} {emp.Apellido}',
                'rol':              emp.rol.nombre if emp.rol else None,
                'rol_activo':       emp.rol_activo,
                'estado_operativo': emp.estado_operativo,
                'check_in_inicio':  _iso(ci.inicio) if ci else None,
                'check_in_fin':     _iso(ci.fin) if ci else None,
                'minutos_activo':   minutos_activo,
                'activo':           ci is not None and ci.fin is None,
                'minutos_tarde':    ci.minutos_tarde if ci else None,
                # Turno planificado
                'tiene_turno':      turno is not None,
                'turno_id':         turno.id if turno else None,
                'turno_hora_inicio': str(turno.hora_inicio)[:5] if turno and turno.hora_inicio else None,
                'turno_hora_fin':    str(turno.hora_fin)[:5] if turno and turno.hora_fin else None,
                'turno_tipo':        turno.tipo if turno else None,
                'turno_empezado':   (
                    datetime.combine(turno.fecha, turno.hora_inicio) <= ahora
                    if turno and turno.hora_inicio else False
                ),
            })

        n_con_checkin   = sum(1 for e in resultado if e['activo'])
        n_pausa         = sum(1 for e in resultado if e['estado_operativo'] == 'en_pausa')
        n_desconectados = sum(1 for e in resultado if e['estado_operativo'] == 'desconectado')
        n_con_turno     = sum(1 for e in resultado if e['tiene_turno'])
        n_ausentes      = sum(1 for e in resultado if e['tiene_turno'] and e['turno_empezado'] and not e['check_in_inicio'])

        return {
            'empleados': resultado,
            'resumen': {
                'con_checkin':   n_con_checkin,
                'en_pausa':      n_pausa,
                'desconectados': n_desconectados,
                'con_turno':     n_con_turno,
                'ausentes':      n_ausentes,
                'total':         len(resultado),
            },
        }

    def turnos_historial(
        self,
        desde: str = None,
        hasta: str = None,
        empleado_id: int = None,
        rol: str = None,
        page: int = 1,
        per_page: int = 25,
    ) -> dict:
        """Historial paginado de check-ins con filtros.

        Args:
            desde:       fecha ISO 'YYYY-MM-DD' (inclusive)
            hasta:       fecha ISO 'YYYY-MM-DD' (inclusive)
            empleado_id: filtrar por empleado concreto
            rol:         filtrar por nombre de rol (Rol.nombre)
            page:        página 1-based
            per_page:    resultados por página (máx 100)

        Returns:
            { turnos: list[dict], total: int, page: int, pages: int }
        """
        from math import ceil
        from models import CheckIn, Rol as RolModel

        per_page = min(per_page, 100)
        s = self.session

        query = (
            s.query(CheckIn)
            .join(Empleado, CheckIn.empleado_id == Empleado.EmpleadoID)
        )

        if desde:
            try:
                query = query.filter(CheckIn.fecha >= datetime.strptime(desde, '%Y-%m-%d').date())
            except ValueError:
                pass

        if hasta:
            try:
                query = query.filter(CheckIn.fecha <= datetime.strptime(hasta, '%Y-%m-%d').date())
            except ValueError:
                pass

        if empleado_id:
            query = query.filter(CheckIn.empleado_id == empleado_id)

        if rol:
            query = (
                query
                .join(RolModel, Empleado.rol_id == RolModel.id)
                .filter(RolModel.nombre == rol)
            )

        total = query.count()
        pages = ceil(total / per_page) if total else 1

        checkins = (
            query
            .order_by(CheckIn.fecha.desc(), CheckIn.inicio.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        resultado = []
        for ci in checkins:
            emp = ci.empleado
            horas_trabajadas = None
            if ci.inicio and ci.fin:
                horas_trabajadas = round((ci.fin - ci.inicio).total_seconds() / 3600, 1)

            resultado.append({
                'check_in_id':      ci.id,
                'empleado_id':      emp.EmpleadoID,
                'empleado_nombre':  f'{emp.Nombre} {emp.Apellido}',
                'rol':              emp.rol.nombre if emp.rol else None,
                'fecha':            ci.fecha.isoformat() if ci.fecha else None,
                'inicio':           _iso(ci.inicio),
                'fin':              _iso(ci.fin),
                'horas_trabajadas': horas_trabajadas,
                'minutos_tarde':    ci.minutos_tarde,
                'activo':           ci.fin is None,
            })

        return {'turnos': resultado, 'total': total, 'page': page, 'pages': pages}

    def rendimiento_resumen(self, periodo: str = 'hoy', rol: str = None) -> dict:
        """Ranking de rendimiento de empleados para el período dado.

        Consulta directamente PickingPedido y Reparto, sin depender de la caché
        MetricaDiariaEmpleado.

        Args:
            periodo: 'hoy' | 'semana' | 'mes'
            rol:     'picker' | 'repartidor' | None (todos)

        Returns:
            { empleados: [{ id, nombre, rol_sistema, rol_operativo,
                            pedidos, tiempo_medio_min, incidencias, tasa_pct }] }
        """
        hoy = datetime.utcnow().date()
        if periodo == 'semana':
            desde = hoy - timedelta(days=6)
        elif periodo == 'mes':
            desde = hoy - timedelta(days=29)
        else:
            desde = hoy

        desde_dt = datetime(desde.year, desde.month, desde.day)
        s = self.session

        # {(empleado_id, rol_op): {pedidos, incidencias, tiempos}}
        agg = {}

        if not rol or rol == 'picker':
            pickings = (
                s.query(PickingPedido)
                .filter(
                    PickingPedido.empleado_id.isnot(None),
                    PickingPedido.estado.in_(['completado', 'con_incidencias']),
                    PickingPedido.completado_en >= desde_dt,
                )
                .all()
            )
            for pk in pickings:
                key = (pk.empleado_id, 'picker')
                if key not in agg:
                    agg[key] = {'pedidos': 0, 'incidencias': 0, 'tiempos': []}
                if pk.estado == 'completado':
                    agg[key]['pedidos'] += 1
                    if pk.iniciado_en and pk.completado_en:
                        agg[key]['tiempos'].append(
                            (pk.completado_en - pk.iniciado_en).total_seconds() / 60
                        )
                else:
                    agg[key]['incidencias'] += 1

        if not rol or rol == 'repartidor':
            repartos = (
                s.query(Reparto)
                .filter(
                    Reparto.repartidor_id.isnot(None),
                    Reparto.estado.in_(['entregado', 'no_entregado']),
                    Reparto.hora_entrega_real >= desde_dt,
                )
                .all()
            )
            for rp in repartos:
                key = (rp.repartidor_id, 'repartidor')
                if key not in agg:
                    agg[key] = {'pedidos': 0, 'incidencias': 0, 'tiempos': []}
                if rp.estado == 'entregado':
                    agg[key]['pedidos'] += 1
                    if rp.hora_salida and rp.hora_entrega_real:
                        agg[key]['tiempos'].append(
                            (rp.hora_entrega_real - rp.hora_salida).total_seconds() / 60
                        )
                else:
                    agg[key]['incidencias'] += 1

        ids = list({k[0] for k in agg})
        empleados_map = {}
        if ids:
            for emp in s.query(Empleado).filter(Empleado.EmpleadoID.in_(ids)).all():
                empleados_map[emp.EmpleadoID] = emp

        resultado = []
        for (emp_id, rol_op), data in agg.items():
            pedidos    = data['pedidos']
            incidencias = data['incidencias']
            tiempos    = data['tiempos']
            tasa       = round(pedidos / (pedidos + incidencias) * 100) if (pedidos + incidencias) > 0 else None
            tiempo_medio = round(sum(tiempos) / len(tiempos)) if tiempos else None
            emp = empleados_map.get(emp_id)
            resultado.append({
                'id':               emp_id,
                'nombre':           f'{emp.Nombre} {emp.Apellido}' if emp else f'#{emp_id}',
                'rol_sistema':      emp.rol.nombre if emp and emp.rol else None,
                'rol_operativo':    rol_op,
                'pedidos':          pedidos,
                'tiempo_medio_min': tiempo_medio,
                'incidencias':      incidencias,
                'tasa_pct':         tasa,
            })

        resultado.sort(key=lambda e: e['pedidos'], reverse=True)
        return {'empleados': resultado}

    def rendimiento_empleado(self, empleado_id: int, periodo: str = 'semana') -> dict | None:
        """Detalle de rendimiento individual.

        Args:
            empleado_id: ID del empleado.
            periodo:     'hoy' | 'semana' | 'mes'

        Returns None si el empleado no existe.

        Returns:
            {
                nombre, rol_sistema,
                kpis: { pedidos, tiempo_medio_min, mejor_tiempo_min, incidencias },
                pedidos_por_dia: [{ fecha, pedidos }],
                turnos_recientes: [{ fecha, inicio, fin, horas }],
                ultimos_pedidos: [{ tipo, pedido_id, fecha, duracion_min }],
            }
        """
        from models import CheckIn

        s = self.session
        emp = s.query(Empleado).filter_by(EmpleadoID=empleado_id).first()
        if not emp:
            return None

        hoy = datetime.utcnow().date()
        if periodo == 'semana':
            desde = hoy - timedelta(days=6)
        elif periodo == 'mes':
            desde = hoy - timedelta(days=29)
        else:
            desde = hoy

        desde_dt = datetime(desde.year, desde.month, desde.day)

        # ── KPIs — from PickingPedido + Reparto ──
        pickings_periodo = (
            s.query(PickingPedido)
            .filter(
                PickingPedido.empleado_id == empleado_id,
                PickingPedido.estado.in_(['completado', 'con_incidencias']),
                PickingPedido.completado_en >= desde_dt,
            )
            .all()
        )
        repartos_periodo = (
            s.query(Reparto)
            .filter(
                Reparto.repartidor_id == empleado_id,
                Reparto.estado.in_(['entregado', 'no_entregado']),
                Reparto.hora_entrega_real >= desde_dt,
            )
            .all()
        )

        tiempos = []
        pedidos_total = 0
        incidencias_total = 0
        for pk in pickings_periodo:
            if pk.estado == 'completado':
                pedidos_total += 1
                if pk.iniciado_en and pk.completado_en:
                    tiempos.append((pk.completado_en - pk.iniciado_en).total_seconds() / 60)
            else:
                incidencias_total += 1
        for rp in repartos_periodo:
            if rp.estado == 'entregado':
                pedidos_total += 1
                if rp.hora_salida and rp.hora_entrega_real:
                    tiempos.append((rp.hora_entrega_real - rp.hora_salida).total_seconds() / 60)
            else:
                incidencias_total += 1

        tiempo_medio_avg = round(sum(tiempos) / len(tiempos)) if tiempos else None
        mejor_tiempo     = round(min(tiempos)) if tiempos else None

        # ── pedidos_por_dia — last 7 days for the chart ──
        siete_dias = hoy - timedelta(days=6)
        siete_dias_dt = datetime(siete_dias.year, siete_dias.month, siete_dias.day)
        conteo_por_dia = {}
        for pk in pickings_periodo:
            if pk.estado == 'completado' and pk.completado_en and pk.completado_en >= siete_dias_dt:
                dia = pk.completado_en.date()
                conteo_por_dia[dia] = conteo_por_dia.get(dia, 0) + 1
        for rp in repartos_periodo:
            if rp.estado == 'entregado' and rp.hora_entrega_real and rp.hora_entrega_real >= siete_dias_dt:
                dia = rp.hora_entrega_real.date()
                conteo_por_dia[dia] = conteo_por_dia.get(dia, 0) + 1
        pedidos_por_dia = []
        for i in range(7):
            dia = siete_dias + timedelta(days=i)
            pedidos_por_dia.append({
                'fecha':   dia.isoformat(),
                'pedidos': conteo_por_dia.get(dia, 0),
            })

        # ── turnos_recientes — last 5 check-ins ──
        checkins = (
            s.query(CheckIn)
            .filter_by(empleado_id=empleado_id)
            .order_by(CheckIn.fecha.desc(), CheckIn.inicio.desc())
            .limit(5)
            .all()
        )
        turnos_recientes = []
        for ci in checkins:
            horas = None
            if ci.inicio and ci.fin:
                horas = round((ci.fin - ci.inicio).total_seconds() / 3600, 1)
            turnos_recientes.append({
                'fecha':  ci.fecha.isoformat() if ci.fecha else None,
                'inicio': _iso(ci.inicio),
                'fin':    _iso(ci.fin),
                'horas':  horas,
            })

        # ── ultimos_pedidos — last 10 completed pickings + entregas in period ──
        pickings = (
            s.query(PickingPedido)
            .filter(
                PickingPedido.empleado_id == empleado_id,
                PickingPedido.estado == 'completado',
                PickingPedido.completado_en >= desde_dt,
            )
            .order_by(PickingPedido.completado_en.desc())
            .limit(10)
            .all()
        )
        repartos = (
            s.query(Reparto)
            .filter(
                Reparto.repartidor_id == empleado_id,
                Reparto.estado == 'entregado',
                Reparto.hora_entrega_real >= desde_dt,
            )
            .order_by(Reparto.hora_entrega_real.desc())
            .limit(10)
            .all()
        )

        ultimos_pedidos = []
        for pk in pickings:
            dur = None
            if pk.iniciado_en and pk.completado_en:
                dur = int((pk.completado_en - pk.iniciado_en).total_seconds() / 60)
            ultimos_pedidos.append({
                'tipo': 'picking',
                'pedido_id': pk.pedido_id,
                'fecha': _iso(pk.completado_en),
                'duracion_min': dur,
            })
        for rp in repartos:
            dur = None
            if rp.hora_salida and rp.hora_entrega_real:
                dur = int((rp.hora_entrega_real - rp.hora_salida).total_seconds() / 60)
            ultimos_pedidos.append({
                'tipo': 'reparto',
                'pedido_id': rp.pedido_id,
                'fecha': _iso(rp.hora_entrega_real),
                'duracion_min': dur,
            })

        ultimos_pedidos.sort(key=lambda x: x['fecha'] or '', reverse=True)
        ultimos_pedidos = ultimos_pedidos[:10]

        return {
            'nombre':      f'{emp.Nombre} {emp.Apellido}',
            'rol_sistema': emp.rol.nombre if emp.rol else None,
            'kpis': {
                'pedidos':          pedidos_total,
                'tiempo_medio_min': tiempo_medio_avg,
                'mejor_tiempo_min': mejor_tiempo,
                'incidencias':      incidencias_total,
            },
            'pedidos_por_dia':  pedidos_por_dia,
            'turnos_recientes': turnos_recientes,
            'ultimos_pedidos':  ultimos_pedidos,
        }

    def estadisticas(self, desde: str = None, hasta: str = None, granularidad: str = 'dia') -> dict:
        """Estadísticas de ventas y operación para el período dado.

        Args:
            desde:        Fecha ISO YYYY-MM-DD (default: hace 6 días)
            hasta:        Fecha ISO YYYY-MM-DD (default: hoy)
            granularidad: 'dia' | 'semana'

        Returns:
            {
              kpis: {ingresos, pedidos, entregados, cancelados,
                     tasa_cancelacion_pct, t_prep_min, t_entrega_min},
              serie_pedidos_ingresos: [{fecha, pedidos, ingresos}],
              distribucion_estados:   {estado: count, ...},
              forma_pago:             {online, efectivo, tarjeta},
              serie_tiempos:          [{fecha, t_prep, t_entrega}],
            }
        """
        hoy = datetime.utcnow().date()
        fecha_desde = datetime.strptime(desde, '%Y-%m-%d').date() if desde else hoy - timedelta(days=6)
        fecha_hasta = datetime.strptime(hasta, '%Y-%m-%d').date() if hasta else hoy

        if granularidad not in ('dia', 'semana'):
            granularidad = 'dia'

        dt_desde = datetime.combine(fecha_desde, datetime.min.time())
        dt_hasta = datetime.combine(fecha_hasta, datetime.max.time())

        s = self.session
        pedidos = (
            s.query(Pedido)
            .filter(Pedido.FechaCreacion >= dt_desde, Pedido.FechaCreacion <= dt_hasta)
            .all()
        )

        # ── KPIs ─────────────────────────────────────────────────────────────
        total_pedidos = len(pedidos)
        entregados   = [p for p in pedidos if p.Estado == EstadoPedido.ENTREGADO.value]
        cancelados   = [p for p in pedidos if p.Estado in (
            EstadoPedido.CANCELADO.value, EstadoPedido.REEMBOLSADO.value
        )]
        ingresos      = sum(float(p.Total or 0) for p in entregados)
        tasa_cancelacion = (
            round(len(cancelados) / total_pedidos * 100, 1) if total_pedidos > 0 else None
        )

        # ── Tiempos via HistorialEstadoPedido ─────────────────────────────────
        pedido_ids = [p.PedidoID for p in pedidos]
        t_prep_sum = t_prep_cnt = t_entrega_sum = t_entrega_cnt = 0
        tiempos_por_dia: dict[str, dict] = {}

        if pedido_ids:
            historial = (
                s.query(HistorialEstadoPedido)
                .filter(
                    HistorialEstadoPedido.pedido_id.in_(pedido_ids),
                    HistorialEstadoPedido.estado_nuevo.in_([
                        EstadoPedido.EN_PREPARACION.value,
                        EstadoPedido.PREPARADO.value,
                        EstadoPedido.EN_REPARTO.value,
                        EstadoPedido.ENTREGADO.value,
                    ])
                )
                .all()
            )
            hist_by_pedido: dict[int, dict] = {}
            for h in sorted(historial, key=lambda x: x.cambiado_en):
                ts = hist_by_pedido.setdefault(h.pedido_id, {})
                ts.setdefault(h.estado_nuevo, h.cambiado_en)

            EN_PREP = EstadoPedido.EN_PREPARACION.value
            PREP    = EstadoPedido.PREPARADO.value
            EN_REP  = EstadoPedido.EN_REPARTO.value
            ENTR    = EstadoPedido.ENTREGADO.value

            for ts in hist_by_pedido.values():
                if EN_PREP in ts and PREP in ts:
                    mins = (ts[PREP] - ts[EN_PREP]).total_seconds() / 60
                    if mins >= 0:
                        t_prep_sum += mins
                        t_prep_cnt += 1
                        dk = ts[PREP].date().isoformat()
                        b = tiempos_por_dia.setdefault(dk, {'ps': 0, 'pc': 0, 'es': 0, 'ec': 0})
                        b['ps'] += mins
                        b['pc'] += 1
                if EN_REP in ts and ENTR in ts:
                    mins = (ts[ENTR] - ts[EN_REP]).total_seconds() / 60
                    if mins >= 0:
                        t_entrega_sum += mins
                        t_entrega_cnt += 1
                        dk = ts[ENTR].date().isoformat()
                        b = tiempos_por_dia.setdefault(dk, {'ps': 0, 'pc': 0, 'es': 0, 'ec': 0})
                        b['es'] += mins
                        b['ec'] += 1

        t_prep_min    = round(t_prep_sum    / t_prep_cnt,    1) if t_prep_cnt    > 0 else None
        t_entrega_min = round(t_entrega_sum / t_entrega_cnt, 1) if t_entrega_cnt > 0 else None

        # ── Distribución estados ──────────────────────────────────────────────
        _ESTADOS_DIST = [
            EstadoPedido.EN_PREPARACION.value, EstadoPedido.PREPARADO.value,
            EstadoPedido.EN_REPARTO.value,     EstadoPedido.ENTREGADO.value,
            EstadoPedido.CANCELADO.value,      EstadoPedido.REEMBOLSADO.value,
        ]
        distribucion_estados = {e: 0 for e in _ESTADOS_DIST}
        for p in pedidos:
            if p.Estado in distribucion_estados:
                distribucion_estados[p.Estado] += 1

        # ── Forma de pago ─────────────────────────────────────────────────────
        forma_pago = {'online': 0, 'efectivo': 0, 'tarjeta': 0}
        for p in pedidos:
            if p.forma_pago in forma_pago:
                forma_pago[p.forma_pago] += 1

        # ── Pedidos por fecha para series (day-level) ─────────────────────────
        pedidos_por_dia: dict[str, dict] = {}
        for p in pedidos:
            if p.FechaCreacion:
                dk = p.FechaCreacion.date().isoformat()
                b = pedidos_por_dia.setdefault(dk, {'pedidos': 0, 'ingresos': 0.0})
                b['pedidos'] += 1
                if p.Estado == EstadoPedido.ENTREGADO.value:
                    b['ingresos'] += float(p.Total or 0)

        # ── Build output series (apply granularidad) ──────────────────────────
        def _gen_keys():
            """Generate ordered unique series keys (always advances by 1 day)."""
            seen: set = set()
            d = fecha_desde
            while d <= fecha_hasta:
                if granularidad == 'semana':
                    iso = d.isocalendar()
                    key = f"{iso[0]}-W{iso[1]:02d}"
                    if key not in seen:
                        seen.add(key)
                        yield key
                else:
                    yield d.isoformat()
                d += timedelta(days=1)

        def _dias_in_key(key: str):
            """Return day ISOs that belong to a series key."""
            result = []
            d = fecha_desde
            while d <= fecha_hasta:
                if granularidad == 'semana':
                    iso = d.isocalendar()
                    if f"{iso[0]}-W{iso[1]:02d}" == key:
                        result.append(d.isoformat())
                else:
                    if d.isoformat() == key:
                        result.append(d.isoformat())
                d += timedelta(days=1)
            return result

        serie_pedidos_ingresos = []
        serie_tiempos = []
        for key in _gen_keys():
            dias = _dias_in_key(key)
            p_total = sum(pedidos_por_dia.get(dk, {}).get('pedidos',  0)   for dk in dias)
            i_total = sum(pedidos_por_dia.get(dk, {}).get('ingresos', 0.0) for dk in dias)
            ps = sum(tiempos_por_dia.get(dk, {}).get('ps', 0) for dk in dias)
            pc = sum(tiempos_por_dia.get(dk, {}).get('pc', 0) for dk in dias)
            es = sum(tiempos_por_dia.get(dk, {}).get('es', 0) for dk in dias)
            ec = sum(tiempos_por_dia.get(dk, {}).get('ec', 0) for dk in dias)
            serie_pedidos_ingresos.append({
                'fecha':    key,
                'pedidos':  p_total,
                'ingresos': round(i_total, 2),
            })
            serie_tiempos.append({
                'fecha':     key,
                't_prep':    round(ps / pc, 1) if pc > 0 else None,
                't_entrega': round(es / ec, 1) if ec > 0 else None,
            })

        return {
            'kpis': {
                'ingresos':             round(ingresos, 2),
                'pedidos':              total_pedidos,
                'entregados':           len(entregados),
                'cancelados':           len(cancelados),
                'tasa_cancelacion_pct': tasa_cancelacion,
                't_prep_min':           t_prep_min,
                't_entrega_min':        t_entrega_min,
            },
            'serie_pedidos_ingresos': serie_pedidos_ingresos,
            'distribucion_estados':   distribucion_estados,
            'forma_pago':             forma_pago,
            'serie_tiempos':          serie_tiempos,
        }

    def turnos_planificacion(
        self,
        desde: str = None,
        hasta: str = None,
        empleado_id: int = None,
        rol: str = None,
        page: int = 1,
        per_page: int = 25,
    ) -> dict:
        """Lista de turnos planificados (pasados y futuros), paginada."""
        from models import Turno as TurnoModel
        hoy = datetime.utcnow().date()
        fecha_desde = datetime.strptime(desde, '%Y-%m-%d').date() if desde else hoy
        fecha_hasta = datetime.strptime(hasta, '%Y-%m-%d').date() if hasta else hoy + timedelta(days=13)
        page = max(page, 1)

        s = self.session
        query = (
            s.query(TurnoModel)
            .join(Empleado, TurnoModel.empleado_id == Empleado.EmpleadoID)
            .filter(TurnoModel.fecha >= fecha_desde, TurnoModel.fecha <= fecha_hasta)
        )

        if empleado_id:
            query = query.filter(TurnoModel.empleado_id == empleado_id)
        if rol:
            query = query.join(Rol, Empleado.rol_id == Rol.id).filter(Rol.nombre == rol)

        total = query.count()
        pages = max((total + per_page - 1) // per_page, 1)
        turnos = (
            query
            .order_by(TurnoModel.fecha.asc(), TurnoModel.hora_inicio.asc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        resultado = []
        for t in turnos:
            emp = t.empleado
            resultado.append({
                'id':          t.id,
                'empleado_id': t.empleado_id,
                'empleado':    f'{emp.Nombre} {emp.Apellido}' if emp else f'#{t.empleado_id}',
                'rol':         emp.rol.nombre if emp and emp.rol else None,
                'fecha':       t.fecha.isoformat() if t.fecha else None,
                'hora_inicio': t.hora_inicio.strftime('%H:%M') if t.hora_inicio else None,
                'hora_fin':    t.hora_fin.strftime('%H:%M') if t.hora_fin else None,
                'tipo':        t.tipo,
                'estado':      t.estado,
                'notas':       t.notas,
            })

        return {'turnos': resultado, 'total': total, 'page': page, 'pages': pages}

    def crear_turno(
        self,
        empleado_id: int,
        fecha: str,
        hora_inicio: str,
        hora_fin: str,
        tipo: str = None,
        notas: str = None,
    ) -> dict:
        """Crea un nuevo turno para un empleado."""
        from models import Turno as TurnoModel
        from datetime import time as dtime

        s = self.session
        emp = s.query(Empleado).filter_by(EmpleadoID=empleado_id).first()
        if not emp:
            return {'ok': False, 'error': 'Empleado no encontrado'}

        try:
            fecha_dt = datetime.strptime(fecha, '%Y-%m-%d').date()
            h_ini = dtime(*[int(x) for x in hora_inicio.split(':')])
            h_fin = dtime(*[int(x) for x in hora_fin.split(':')])
        except (ValueError, AttributeError) as exc:
            return {'ok': False, 'error': 'Formato de fecha/hora inválido: %s' % exc}

        turno = TurnoModel(
            empleado_id=empleado_id,
            fecha=fecha_dt,
            hora_inicio=h_ini,
            hora_fin=h_fin,
            tipo=tipo or None,
            notas=notas or None,
            estado='planificado',
        )
        try:
            s.add(turno)
            s.flush()
            turno_id = turno.id
            s.commit()
            logger.info('TURNO_CREADO empleado=%s fecha=%s', empleado_id, fecha)
            return {'ok': True, 'turno_id': turno_id}
        except Exception as exc:
            s.rollback()
            logger.error('Error creando turno para empleado %s: %s', empleado_id, exc)
            return {'ok': False, 'error': 'Error al guardar el turno'}

    def editar_turno(
        self,
        turno_id: int,
        hora_inicio: str = None,
        hora_fin: str = None,
        tipo: str = None,
        notas: str = None,
    ) -> dict:
        """Edita hora_inicio, hora_fin, tipo y/o notas de un turno planificado."""
        from models import Turno as TurnoModel
        from datetime import time as dtime

        s = self.session
        turno = s.query(TurnoModel).filter_by(id=turno_id).first()
        if not turno:
            return {'ok': False, 'error': 'Turno no encontrado'}
        if turno.estado == 'cancelado':
            return {'ok': False, 'error': 'No se puede editar un turno cancelado'}

        try:
            if hora_inicio:
                turno.hora_inicio = dtime(*[int(x) for x in hora_inicio.split(':')])
            if hora_fin:
                turno.hora_fin = dtime(*[int(x) for x in hora_fin.split(':')])
            if tipo is not None and tipo != '__no_change__':
                turno.tipo = tipo or None
            if notas is not None and notas != '__no_change__':
                turno.notas = notas or None
            s.commit()
            logger.info('TURNO_EDITADO id=%s', turno_id)
            return {'ok': True}
        except Exception as exc:
            s.rollback()
            logger.error('Error editando turno %s: %s', turno_id, exc)
            return {'ok': False, 'error': 'Error al guardar los cambios'}

    def cancelar_turno(self, turno_id: int) -> dict:
        """Marca un turno como cancelado."""
        from models import Turno as TurnoModel

        s = self.session
        turno = s.query(TurnoModel).filter_by(id=turno_id).first()
        if not turno:
            return {'ok': False, 'error': 'Turno no encontrado'}
        if turno.estado == 'cancelado':
            return {'ok': False, 'error': 'El turno ya está cancelado'}

        try:
            turno.estado = 'cancelado'
            s.commit()
            logger.info('TURNO_CANCELADO id=%s', turno_id)
            return {'ok': True}
        except Exception as exc:
            s.rollback()
            logger.error('Error cancelando turno %s: %s', turno_id, exc)
            return {'ok': False, 'error': 'Error al cancelar el turno'}
