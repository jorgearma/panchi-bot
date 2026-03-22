import logging
import statistics
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

# Estados operativos (no terminales)
_ESTADOS_ACTIVOS = ('en_preparacion', 'preparado', 'en_reparto', 'confirmando_pago',
                    'enlace', 'enlace2', 'pendiente')
_ESTADOS_TERMINALES = ('entregado', 'cancelado', 'reembolsado')


class GestorMetricas:

    @property
    def session(self):
        from database import get_db
        return get_db()

    # =========================================================
    # BLOQUE 1 — Tiempo real
    # =========================================================

    def resumen_operacion(self) -> dict:
        from models import Pedido, CheckIn, PickingPedido, Reparto, HistorialEstadoPedido
        s = self.session
        hoy = date.today()

        pedidos_activos = (
            s.query(Pedido)
            .filter(Pedido.Estado.notin_(_ESTADOS_TERMINALES))
            .count()
        )

        empleados_en_turno = (
            s.query(CheckIn)
            .filter(
                CheckIn.fecha == hoy,
                CheckIn.fin.is_(None)
            )
            .count()
        )

        cola_picking_count = (
            s.query(PickingPedido)
            .filter(
                PickingPedido.estado == 'pendiente',
                PickingPedido.empleado_id.is_(None)
            )
            .count()
        )

        cola_reparto_count = (
            s.query(Reparto)
            .filter(Reparto.estado == 'pendiente')
            .count()
        )

        entregados_hoy = (
            s.query(Reparto)
            .filter(
                Reparto.estado == 'entregado',
                Reparto.updated_at >= datetime.combine(hoy, datetime.min.time())
            )
            .count()
        )

        no_entregados_hoy = (
            s.query(Reparto)
            .filter(
                Reparto.estado == 'no_entregado',
                Reparto.updated_at >= datetime.combine(hoy, datetime.min.time())
            )
            .count()
        )

        total_cerrados = entregados_hoy + no_entregados_hoy
        tasa_entrega_hoy_pct = (
            round(entregados_hoy * 100 / total_cerrados) if total_cerrados > 0 else None
        )

        tiempo_medio_ciclo_hoy_min = self._tiempo_medio_ciclo_hoy(hoy)

        return {
            'pedidos_activos': pedidos_activos,
            'empleados_en_turno': empleados_en_turno,
            'cola_picking_count': cola_picking_count,
            'cola_reparto_count': cola_reparto_count,
            'entregados_hoy': entregados_hoy,
            'tasa_entrega_hoy_pct': tasa_entrega_hoy_pct,
            'tiempo_medio_ciclo_hoy_min': tiempo_medio_ciclo_hoy_min,
        }

    def _tiempo_medio_ciclo_hoy(self, hoy: date) -> int | None:
        """Mediana de (ENTREGADO - EN_PREPARACION) para pedidos entregados hoy."""
        from models import HistorialEstadoPedido, Pedido
        s = self.session
        pedidos_entregados_hoy = (
            s.query(HistorialEstadoPedido.pedido_id)
            .filter(
                HistorialEstadoPedido.estado_nuevo == 'entregado',
                HistorialEstadoPedido.cambiado_en >= datetime.combine(hoy, datetime.min.time())
            )
            .all()
        )
        ids = [r.pedido_id for r in pedidos_entregados_hoy]
        if not ids:
            return None
        tiempos = []
        for pid in ids:
            t = self._tiempo_entre_estados(pid, 'en_preparacion', 'entregado')
            if t is not None:
                tiempos.append(t)
        return round(statistics.median(tiempos)) if tiempos else None

    def asistencia_hoy(self) -> list[dict]:
        from models import Turno, CheckIn, Empleado
        s = self.session
        hoy = date.today()
        rows = (
            s.query(Turno, CheckIn, Empleado)
            .join(Empleado, Turno.empleado_id == Empleado.EmpleadoID)
            .outerjoin(
                CheckIn,
                (CheckIn.empleado_id == Turno.empleado_id) & (CheckIn.fecha == hoy)
            )
            .filter(Turno.fecha == hoy)
            .all()
        )
        result = []
        for turno, checkin, empleado in rows:
            result.append({
                'empleado_id': empleado.EmpleadoID,
                'nombre': empleado.Nombre,
                'rol': empleado.rol.nombre if empleado.rol else None,
                'turno_inicio': turno.inicio.strftime('%H:%M') if turno.inicio else None,
                'turno_fin': turno.fin.strftime('%H:%M') if turno.fin else None,
                'hora_fichaje': checkin.inicio.strftime('%H:%M') if checkin else None,
                'minutos_tarde': checkin.minutos_tarde if checkin else None,
                'activo': checkin is not None and checkin.fin is None,
                'ausente': checkin is None,
            })
        return result

    def colas_detalle(self) -> dict:
        from models import PickingPedido, Reparto, HistorialEstadoPedido, PedidoDetalle
        from sqlalchemy import func
        s = self.session

        pickings = (
            s.query(PickingPedido)
            .filter(
                PickingPedido.estado == 'pendiente',
                PickingPedido.empleado_id.is_(None)
            )
            .all()
        )
        cola_picking = []
        for pp in pickings:
            ultimo_hist = (
                s.query(HistorialEstadoPedido)
                .filter(HistorialEstadoPedido.pedido_id == pp.PedidoID)
                .order_by(HistorialEstadoPedido.cambiado_en.desc())
                .first()
            )
            mins = None
            if ultimo_hist:
                delta = datetime.utcnow() - ultimo_hist.cambiado_en
                mins = round(delta.total_seconds() / 60)
            num_items = (
                s.query(func.count(PedidoDetalle.DetalleID))
                .filter(PedidoDetalle.PedidoID == pp.PedidoID)
                .scalar()
            ) or 0
            cola_picking.append({
                'pedido_id': pp.PedidoID,
                'minutos_esperando': mins,
                'num_items': num_items,
            })
        cola_picking.sort(key=lambda x: x['minutos_esperando'] or 0, reverse=True)

        repartos = (
            s.query(Reparto)
            .filter(Reparto.estado == 'pendiente')
            .all()
        )
        cola_reparto = []
        for r in repartos:
            ultimo_hist = (
                s.query(HistorialEstadoPedido)
                .filter(HistorialEstadoPedido.pedido_id == r.pedido_id)
                .order_by(HistorialEstadoPedido.cambiado_en.desc())
                .first()
            )
            mins = None
            if ultimo_hist:
                delta = datetime.utcnow() - ultimo_hist.cambiado_en
                mins = round(delta.total_seconds() / 60)
            num_items = (
                s.query(func.count(PedidoDetalle.DetalleID))
                .filter(PedidoDetalle.PedidoID == r.pedido_id)
                .scalar()
            ) or 0
            cola_reparto.append({
                'pedido_id': r.pedido_id,
                'minutos_esperando': mins,
                'num_items': num_items,
            })
        cola_reparto.sort(key=lambda x: x['minutos_esperando'] or 0, reverse=True)

        return {'cola_picking': cola_picking, 'cola_reparto': cola_reparto}

    def pedidos_por_estado(self) -> dict:
        from models import Pedido
        from sqlalchemy import func
        s = self.session
        rows = (
            s.query(Pedido.Estado, func.count(Pedido.PedidoID))
            .filter(Pedido.Estado.notin_(_ESTADOS_TERMINALES))
            .group_by(Pedido.Estado)
            .all()
        )
        return {estado: count for estado, count in rows}

    def alertas_tiempo_real(self) -> list[dict]:
        alertas = []
        alertas.extend(self._alertas_ausencia())
        alertas.extend(self._alertas_colas())
        alertas.extend(self._alertas_pedidos_bloqueados())
        alertas.extend(self._alertas_repartidores_inactivos())
        orden = {'alta': 0, 'media': 1, 'baja': 2}
        alertas.sort(key=lambda a: orden.get(a['severidad'], 99))
        return alertas

    def _alertas_ausencia(self) -> list[dict]:
        from models import Turno, CheckIn, Empleado
        s = self.session
        hoy = date.today()
        ahora = datetime.utcnow()
        turnos_hoy = (
            s.query(Turno, Empleado)
            .join(Empleado, Turno.empleado_id == Empleado.EmpleadoID)
            .filter(Turno.fecha == hoy)
            .all()
        )
        alertas = []
        for turno, empleado in turnos_hoy:
            if not turno.inicio:
                continue
            inicio_dt = datetime.combine(hoy, turno.inicio.time()) if isinstance(turno.inicio, datetime) else turno.inicio
            mins_desde_inicio = round((ahora - inicio_dt).total_seconds() / 60)
            if mins_desde_inicio < 15:
                continue
            checkin = (
                s.query(CheckIn)
                .filter(CheckIn.empleado_id == empleado.EmpleadoID, CheckIn.fecha == hoy)
                .first()
            )
            if checkin is None:
                alertas.append({
                    'tipo': 'ausencia_no_fichada',
                    'severidad': 'alta',
                    'mensaje': (
                        f'{empleado.Nombre} tiene turno desde las '
                        f'{turno.inicio.strftime("%H:%M") if hasattr(turno.inicio, "strftime") else turno.inicio} '
                        f'y no ha fichado ({mins_desde_inicio} min de retraso)'
                    ),
                    'empleado_id': empleado.EmpleadoID,
                })
        return alertas

    def _alertas_colas(self) -> list[dict]:
        from models import PickingPedido, Reparto
        s = self.session
        umbral = 3
        alertas = []

        ids_picking = [
            r.PedidoID for r in
            s.query(PickingPedido)
            .filter(PickingPedido.estado == 'pendiente', PickingPedido.empleado_id.is_(None))
            .all()
        ]
        if len(ids_picking) >= umbral:
            alertas.append({
                'tipo': 'cola_picking_alta',
                'severidad': 'alta',
                'mensaje': f'{len(ids_picking)} pedidos en cola de picking sin picker asignado',
                'pedidos_afectados': ids_picking,
            })

        ids_reparto = [
            r.pedido_id for r in
            s.query(Reparto).filter(Reparto.estado == 'pendiente').all()
        ]
        if len(ids_reparto) >= umbral:
            alertas.append({
                'tipo': 'cola_reparto_alta',
                'severidad': 'alta',
                'mensaje': f'{len(ids_reparto)} pedidos en cola de reparto sin repartidor asignado',
                'pedidos_afectados': ids_reparto,
            })
        return alertas

    def _alertas_pedidos_bloqueados(self) -> list[dict]:
        from models import HistorialEstadoPedido, Pedido
        s = self.session
        hoy = date.today()
        tiempo_ref = self._tiempo_medio_ciclo_hoy(hoy)
        if tiempo_ref is None:
            desde_7d = hoy - timedelta(days=7)
            tiempo_ref = self._tiempo_medio_ciclo_periodo(desde_7d, hoy - timedelta(days=1))
        if tiempo_ref is None:
            return []

        umbral_min = tiempo_ref * 2
        ahora = datetime.utcnow()
        alertas = []

        pedidos_activos = (
            s.query(Pedido)
            .filter(Pedido.Estado.notin_(_ESTADOS_TERMINALES))
            .all()
        )
        for pedido in pedidos_activos:
            ultimo = (
                s.query(HistorialEstadoPedido)
                .filter(HistorialEstadoPedido.pedido_id == pedido.PedidoID)
                .order_by(HistorialEstadoPedido.cambiado_en.desc())
                .first()
            )
            if ultimo is None:
                continue
            mins_bloqueado = round((ahora - ultimo.cambiado_en).total_seconds() / 60)
            if mins_bloqueado > umbral_min:
                alertas.append({
                    'tipo': 'pedido_bloqueado',
                    'severidad': 'media',
                    'mensaje': (
                        f'Pedido #{pedido.PedidoID} lleva {mins_bloqueado} min '
                        f"en estado '{pedido.Estado}' sin avanzar"
                    ),
                    'pedido_id': pedido.PedidoID,
                })
        return alertas

    def _tiempo_medio_ciclo_periodo(self, desde: date, hasta: date) -> int | None:
        from models import HistorialEstadoPedido
        s = self.session
        entregados = (
            s.query(HistorialEstadoPedido.pedido_id)
            .filter(
                HistorialEstadoPedido.estado_nuevo == 'entregado',
                HistorialEstadoPedido.cambiado_en >= datetime.combine(desde, datetime.min.time()),
                HistorialEstadoPedido.cambiado_en <= datetime.combine(hasta, datetime.max.time()),
            )
            .all()
        )
        ids = [r.pedido_id for r in entregados]
        if not ids:
            return None
        tiempos = [t for t in (self._tiempo_entre_estados(pid, 'en_preparacion', 'entregado') for pid in ids) if t is not None]
        return round(statistics.median(tiempos)) if tiempos else None

    def _alertas_repartidores_inactivos(self) -> list[dict]:
        from models import CheckIn, Reparto, Empleado, Rol
        s = self.session
        hoy = date.today()
        ahora = datetime.utcnow()
        umbral_min = 45

        checkins_abiertos = (
            s.query(CheckIn, Empleado)
            .join(Empleado, CheckIn.empleado_id == Empleado.EmpleadoID)
            .join(Rol, Empleado.rol_id == Rol.id)
            .filter(
                CheckIn.fecha == hoy,
                CheckIn.fin.is_(None),
                Rol.nombre == 'repartidor',
            )
            .all()
        )
        alertas = []
        for checkin, empleado in checkins_abiertos:
            reparto_activo = (
                s.query(Reparto)
                .filter(
                    Reparto.empleado_id == empleado.EmpleadoID,
                    Reparto.estado.in_(['asignado', 'en_camino']),
                )
                .first()
            )
            if reparto_activo:
                continue
            ultimo_reparto = (
                s.query(Reparto)
                .filter(Reparto.empleado_id == empleado.EmpleadoID)
                .order_by(Reparto.updated_at.desc())
                .first()
            )
            ref_time = ultimo_reparto.updated_at if ultimo_reparto else checkin.inicio
            if ref_time is None:
                continue
            mins_inactivo = round((ahora - ref_time).total_seconds() / 60)
            if mins_inactivo > umbral_min:
                alertas.append({
                    'tipo': 'repartidor_inactivo',
                    'severidad': 'media',
                    'mensaje': f'{empleado.Nombre} lleva {mins_inactivo} min sin reparto activo',
                    'empleado_id': empleado.EmpleadoID,
                })
        return alertas

    # =========================================================
    # BLOQUE 2 — Analítica (stubs)
    # =========================================================

    def resumen_periodo(self, desde: date, hasta: date) -> dict:
        from models import Pedido, Reparto
        from sqlalchemy import func
        s = self.session
        desde_dt = datetime.combine(desde, datetime.min.time())
        hasta_dt = datetime.combine(hasta, datetime.max.time())

        completados = (
            s.query(Pedido)
            .filter(
                Pedido.Estado == 'entregado',
                Pedido.FechaCreacion >= desde_dt,
                Pedido.FechaCreacion <= hasta_dt,
            )
            .count()
        )

        cancelados = (
            s.query(Pedido)
            .filter(
                Pedido.Estado == 'cancelado',
                Pedido.FechaCreacion >= desde_dt,
                Pedido.FechaCreacion <= hasta_dt,
            )
            .count()
        )

        total_pedidos = completados + cancelados

        repartos = (
            s.query(Reparto)
            .filter(
                Reparto.updated_at >= desde_dt,
                Reparto.updated_at <= hasta_dt,
                Reparto.estado.in_(['entregado', 'no_entregado']),
            )
            .all()
        )
        entregados_r = sum(1 for r in repartos if r.estado == 'entregado')
        total_r = len(repartos)
        tasa_entrega = round(entregados_r * 100 / total_r) if total_r > 0 else None

        ratio_cancelacion = round(cancelados * 100 / total_pedidos) if total_pedidos > 0 else None

        tiempo_ciclo = self._tiempo_medio_ciclo_periodo(desde, hasta)

        rows_pago = (
            s.query(Pedido.forma_pago, func.count(Pedido.PedidoID))
            .filter(
                Pedido.Estado == 'entregado',
                Pedido.FechaCreacion >= desde_dt,
                Pedido.FechaCreacion <= hasta_dt,
            )
            .group_by(Pedido.forma_pago)
            .all()
        )
        pedidos_por_forma_pago = {fp: cnt for fp, cnt in rows_pago if fp}

        dias = (hasta - desde).days + 1

        return {
            'pedidos_completados': completados,
            'tasa_entrega_pct': tasa_entrega,
            'tiempo_medio_ciclo_min': tiempo_ciclo,
            'ratio_cancelacion_pct': ratio_cancelacion,
            'pedidos_por_forma_pago': pedidos_por_forma_pago,
            'dias_analizados': dias,
        }

    def metricas_pedidos(self, desde: date, hasta: date) -> dict:
        from models import Pedido, HistorialEstadoPedido
        from sqlalchemy import func, cast, Date
        s = self.session
        desde_dt = datetime.combine(desde, datetime.min.time())
        hasta_dt = datetime.combine(hasta, datetime.max.time())

        # Throughput por día
        rows_dia = (
            s.query(
                func.cast(Pedido.FechaCreacion, Date).label('dia'),
                Pedido.Estado,
                func.count(Pedido.PedidoID),
            )
            .filter(
                Pedido.Estado.in_(['entregado', 'cancelado']),
                Pedido.FechaCreacion >= desde_dt,
                Pedido.FechaCreacion <= hasta_dt,
            )
            .group_by(func.cast(Pedido.FechaCreacion, Date), Pedido.Estado)
            .all()
        )
        # Consolidar por día
        dias_dict: dict = {}
        for dia, estado, cnt in rows_dia:
            key = str(dia)
            if key not in dias_dict:
                dias_dict[key] = {'fecha': key, 'completados': 0, 'cancelados': 0}
            if estado == 'entregado':
                dias_dict[key]['completados'] = cnt
            elif estado == 'cancelado':
                dias_dict[key]['cancelados'] = cnt
        throughput = sorted(dias_dict.values(), key=lambda x: x['fecha'])

        # Tiempos por fase: calcular mediana entre pares de estados
        pares_fases = [
            ('confirmacion_a_preparacion', ['pagado', 'contra_reembolso'], 'en_preparacion'),
            ('preparacion', 'en_preparacion', 'preparado'),
            ('espera_repartidor', 'preparado', 'en_reparto'),
            ('reparto', 'en_reparto', 'entregado'),
        ]
        pedidos_entregados = (
            s.query(Pedido.PedidoID)
            .filter(
                Pedido.Estado == 'entregado',
                Pedido.FechaCreacion >= desde_dt,
                Pedido.FechaCreacion <= hasta_dt,
            )
            .all()
        )
        ids = [r.PedidoID for r in pedidos_entregados]

        tiempos_por_fase: dict = {}
        for nombre_fase, estado_a, estado_b in pares_fases:
            tiempos = []
            for pid in ids:
                if isinstance(estado_a, list):
                    registros = (
                        s.query(HistorialEstadoPedido)
                        .filter(
                            HistorialEstadoPedido.pedido_id == pid,
                            HistorialEstadoPedido.estado_nuevo.in_(estado_a + [estado_b])
                        )
                        .order_by(HistorialEstadoPedido.cambiado_en)
                        .all()
                    )
                    mapa = {}
                    for r in registros:
                        if r.estado_nuevo not in mapa:
                            mapa[r.estado_nuevo] = r.cambiado_en
                    t_a = min((mapa[e] for e in estado_a if e in mapa), default=None)
                    t_b = mapa.get(estado_b)
                    if t_a and t_b:
                        tiempos.append(max(0, round((t_b - t_a).total_seconds() / 60)))
                else:
                    t = self._tiempo_entre_estados(pid, estado_a, estado_b)
                    if t is not None:
                        tiempos.append(t)
            tiempos_por_fase[nombre_fase] = round(statistics.median(tiempos)) if tiempos else None

        # Distribución estados finales
        dist_rows = (
            s.query(Pedido.Estado, func.count(Pedido.PedidoID))
            .filter(
                Pedido.Estado.in_(_ESTADOS_TERMINALES),
                Pedido.FechaCreacion >= desde_dt,
                Pedido.FechaCreacion <= hasta_dt,
            )
            .group_by(Pedido.Estado)
            .all()
        )
        distribucion = {e: c for e, c in dist_rows}

        return {
            'throughput_por_dia': throughput,
            'tiempo_medio_por_fase_min': tiempos_por_fase,
            'distribucion_estado_final': distribucion,
        }

    def metricas_picking(self, desde: date, hasta: date) -> dict:
        from models import PickingPedido, PickingItem, Producto
        from sqlalchemy import func
        s = self.session
        desde_dt = datetime.combine(desde, datetime.min.time())
        hasta_dt = datetime.combine(hasta, datetime.max.time())

        # IDs de pickings completados en el rango (via completado_en)
        pp_completados = (
            s.query(PickingPedido)
            .filter(
                PickingPedido.completado_en >= desde_dt,
                PickingPedido.completado_en <= hasta_dt,
                PickingPedido.estado == 'completado',
            )
            .all()
        )
        pp_ids = [pp.id for pp in pp_completados]

        # Items del período
        items = (
            s.query(PickingItem)
            .filter(PickingItem.picking_id.in_(pp_ids))
            .all()
        )
        items_total = len(items)
        if items_total > 0:
            encontrados = sum(1 for i in items if i.estado == 'encontrado')
            sin_stock = sum(1 for i in items if i.estado == 'sin_stock')
            sustituidos = sum(1 for i in items if i.estado == 'sustituido')
            items_encontrados_pct = round(encontrados * 100 / items_total)
            items_sin_stock_pct = round(sin_stock * 100 / items_total)
            items_sustituidos_pct = round(sustituidos * 100 / items_total)
        else:
            items_encontrados_pct = items_sin_stock_pct = items_sustituidos_pct = None

        # Tiempos de picking
        tiempo_medio_picking_min, tiempo_medio_espera_asignacion_min = self._picking_tiempos(desde_dt, hasta_dt)

        # Top productos sin stock
        top_sin_stock_rows = (
            s.query(PickingItem.pedido_detalle_id, Producto.Nombre, func.count(PickingItem.id).label('veces'))
            .join(Producto, PickingItem.producto_sustituto_id == Producto.ProductoID, isouter=True)
            .join(PickingPedido, PickingItem.picking_id == PickingPedido.id)
            .filter(
                PickingItem.estado == 'sin_stock',
                PickingPedido.completado_en >= desde_dt,
                PickingPedido.completado_en <= hasta_dt,
            )
            .group_by(PickingItem.pedido_detalle_id, Producto.Nombre)
            .order_by(func.count(PickingItem.id).desc())
            .limit(10)
            .all()
        )
        top_productos_sin_stock = [
            {'pedido_detalle_id': pid, 'nombre': nombre, 'veces_sin_stock': veces}
            for pid, nombre, veces in top_sin_stock_rows
        ]

        return {
            'tiempo_medio_picking_min': tiempo_medio_picking_min,
            'tiempo_medio_espera_asignacion_min': tiempo_medio_espera_asignacion_min,
            'items_total': items_total,
            'items_encontrados_pct': items_encontrados_pct,
            'items_sin_stock_pct': items_sin_stock_pct,
            'items_sustituidos_pct': items_sustituidos_pct,
            'top_productos_sin_stock': top_productos_sin_stock,
        }

    def _picking_tiempos(self, desde_dt: datetime, hasta_dt: datetime):
        from models import PickingPedido, HistorialEstadoPedido
        s = self.session
        pickings_completados = (
            s.query(PickingPedido)
            .filter(
                PickingPedido.estado == 'completado',
                PickingPedido.completado_en >= desde_dt,
                PickingPedido.completado_en <= hasta_dt,
            )
            .all()
        )
        tiempos_picking = []
        tiempos_espera = []
        for pp in pickings_completados:
            if pp.created_at and pp.completado_en:
                mins = round((pp.completado_en - pp.created_at).total_seconds() / 60)
                tiempos_picking.append(mins)
            t = self._tiempo_entre_estados(pp.pedido_id, 'pagado', 'en_preparacion')
            if t is not None:
                tiempos_espera.append(t)
        tiempo_medio_picking = round(statistics.mean(tiempos_picking)) if tiempos_picking else None
        tiempo_espera_asig = round(statistics.mean(tiempos_espera)) if tiempos_espera else None
        return tiempo_medio_picking, tiempo_espera_asig

    def metricas_reparto(self, desde: date, hasta: date) -> dict:
        from models import Reparto, Empleado
        from sqlalchemy import func
        s = self.session
        desde_dt = datetime.combine(desde, datetime.min.time())
        hasta_dt = datetime.combine(hasta, datetime.max.time())

        repartos = (
            s.query(Reparto)
            .filter(
                Reparto.updated_at >= desde_dt,
                Reparto.updated_at <= hasta_dt,
                Reparto.estado.in_(['entregado', 'no_entregado']),
            )
            .all()
        )

        total = len(repartos)
        entregados = [r for r in repartos if r.estado == 'entregado']
        tasa_exitosa = round(len(entregados) * 100 / total) if total > 0 else None

        # Solo con hora_salida para tiempos
        con_salida = [r for r in entregados if r.hora_salida is not None]
        tiempos_entrega = []
        for r in con_salida:
            if r.hora_entrega_real and r.hora_salida:
                mins = round((r.hora_entrega_real - r.hora_salida).total_seconds() / 60)
                tiempos_entrega.append(mins)
        tiempo_medio_entrega = round(statistics.mean(tiempos_entrega)) if tiempos_entrega else None

        # Espera antes de salida (PREPARADO → en_reparto)
        tiempos_espera_salida = []
        for r in con_salida:
            t = self._tiempo_entre_estados(r.pedido_id, 'preparado', 'en_reparto')
            if t is not None:
                tiempos_espera_salida.append(t)
        tiempo_espera_salida = round(statistics.mean(tiempos_espera_salida)) if tiempos_espera_salida else None

        # Por repartidor
        por_empleado: dict = {}
        for r in repartos:
            eid = r.repartidor_id
            if not eid:
                continue
            if eid not in por_empleado:
                por_empleado[eid] = {'entregas': 0, 'tiempos': [], 'total': 0, 'nombre': None}
            por_empleado[eid]['total'] += 1
            if r.estado == 'entregado':
                por_empleado[eid]['entregas'] += 1
                if r.hora_salida and r.hora_entrega_real:
                    mins = round((r.hora_entrega_real - r.hora_salida).total_seconds() / 60)
                    por_empleado[eid]['tiempos'].append(mins)

        entregas_por_repartidor = []
        for eid, data in por_empleado.items():
            emp = s.query(Empleado).filter(Empleado.EmpleadoID == eid).first()
            nombre = emp.Nombre if emp else f'Empleado {eid}'
            tasa = round(data['entregas'] * 100 / data['total']) if data['total'] > 0 else None
            t_medio = round(statistics.mean(data['tiempos'])) if data['tiempos'] else None
            entregas_por_repartidor.append({
                'empleado_id': eid,
                'nombre': nombre,
                'entregas': data['entregas'],
                'tiempo_medio_min': t_medio,
                'tasa_exito_pct': tasa,
            })
        entregas_por_repartidor.sort(key=lambda x: x['entregas'], reverse=True)

        return {
            'tiempo_medio_entrega_min': tiempo_medio_entrega,
            'tiempo_medio_espera_antes_salida_min': tiempo_espera_salida,
            'tasa_entrega_exitosa_pct': tasa_exitosa,
            'entregas_por_repartidor': entregas_por_repartidor,
        }

    def rendimiento_empleados(self, desde: date, hasta: date, rol: str | None = None) -> list[dict]:
        from models import Empleado, Rol, PickingItem, PickingPedido, Reparto
        s = self.session
        query = s.query(Empleado)
        if rol:
            query = query.join(Rol, Empleado.rol_id == Rol.id).filter(Rol.nombre == rol)
        else:
            query = query.filter(Empleado.activo == True)
        empleados = query.all()

        result = []
        for emp in empleados:
            rol_nombre = emp.rol.nombre if emp.rol else None
            horas = self._horas_trabajadas(emp.EmpleadoID, desde, hasta)
            ops = self._operaciones_empleado(emp.EmpleadoID, rol_nombre, desde, hasta)
            num_ops = len(ops)
            productividad = round(num_ops / horas, 2) if horas > 0 else 0

            # Tiempo medio por operación
            if rol_nombre == 'picker' and ops:
                tiempos = [
                    round((op.completado_en - op.created_at).total_seconds() / 60)
                    for op in ops
                    if op.created_at and op.completado_en
                ]
                tiempo_medio = round(statistics.mean(tiempos)) if tiempos else None
            elif rol_nombre == 'repartidor' and ops:
                tiempos = [
                    round((op.hora_entrega_real - op.hora_salida).total_seconds() / 60)
                    for op in ops
                    if op.hora_salida and op.hora_entrega_real
                ]
                tiempo_medio = round(statistics.mean(tiempos)) if tiempos else None
            else:
                tiempo_medio = None

            # Ratio incidencias
            if rol_nombre == 'picker':
                todos_items = (
                    s.query(PickingItem)
                    .join(PickingPedido, PickingItem.picking_id == PickingPedido.id)
                    .filter(
                        PickingPedido.empleado_id == emp.EmpleadoID,
                        PickingPedido.completado_en >= datetime.combine(desde, datetime.min.time()),
                        PickingPedido.completado_en <= datetime.combine(hasta, datetime.max.time()),
                    )
                    .all()
                )
                total_items = len(todos_items)
                inc = sum(1 for i in todos_items if i.estado in ('sin_stock', 'sustituido'))
                ratio_inc = round(inc * 100 / total_items) if total_items > 0 else 0
            else:
                todos_repartos = (
                    s.query(Reparto)
                    .filter(
                        Reparto.repartidor_id == emp.EmpleadoID,
                        Reparto.estado.in_(['entregado', 'no_entregado']),
                        Reparto.updated_at >= datetime.combine(desde, datetime.min.time()),
                        Reparto.updated_at <= datetime.combine(hasta, datetime.max.time()),
                    )
                    .all()
                )
                total_rep = len(todos_repartos)
                no_ent = sum(1 for r in todos_repartos if r.estado == 'no_entregado')
                ratio_inc = round(no_ent * 100 / total_rep) if total_rep > 0 else 0

            # Puntualidad via GestorEmpleado (puede fallar fuera de contexto Flask)
            puntualidad_media = None
            try:
                from managers.gestor_empleado import GestorEmpleado
                ge = GestorEmpleado()
                punt_data = ge.puntualidad_empleado(emp.EmpleadoID, desde, hasta)
                puntualidad_media = punt_data.get('media_minutos_tarde')
            except Exception:
                pass

            result.append({
                'empleado_id': emp.EmpleadoID,
                'nombre': emp.Nombre,
                'rol': rol_nombre,
                'operaciones_completadas': num_ops,
                'horas_trabajadas': horas,
                'productividad_operaciones_hora': productividad,
                'tiempo_medio_operacion_min': tiempo_medio,
                'ratio_incidencias_pct': ratio_inc,
                'puntualidad_media_min': puntualidad_media,
            })
        return result

    def comparativa_empleados(self, desde: date, hasta: date, rol: str) -> dict:
        empleados_data = self.rendimiento_empleados(desde, hasta, rol=rol)
        ranking = sorted(
            empleados_data,
            key=lambda x: x['productividad_operaciones_hora'],
            reverse=True
        )
        for i, emp in enumerate(ranking):
            emp['posicion'] = i + 1

        con_ops = [e for e in empleados_data if e['operaciones_completadas'] > 0]
        if con_ops:
            media_prod = round(statistics.mean(e['productividad_operaciones_hora'] for e in con_ops), 2)
            tiempos = [e['tiempo_medio_operacion_min'] for e in con_ops if e['tiempo_medio_operacion_min'] is not None]
            media_tiempo = round(statistics.mean(tiempos)) if tiempos else None
            ratios = [e['ratio_incidencias_pct'] for e in con_ops]
            media_ratio = round(statistics.mean(ratios)) if ratios else None
        else:
            media_prod = media_tiempo = media_ratio = None

        return {
            'rol': rol,
            'periodo': {'desde': str(desde), 'hasta': str(hasta)},
            'ranking': ranking,
            'media_equipo': {
                'productividad_operaciones_hora': media_prod,
                'tiempo_medio_operacion_min': media_tiempo,
                'ratio_incidencias_pct': media_ratio,
            },
        }

    def ficha_empleado(self, empleado_id: int, desde: date, hasta: date) -> dict:
        from models import Empleado, Turno, CheckIn, Ausencia
        from managers.gestor_empleado import GestorEmpleado
        s = self.session
        emp = s.query(Empleado).filter(Empleado.EmpleadoID == empleado_id).first()
        if not emp:
            return {}
        rol_nombre = emp.rol.nombre if emp.rol else None

        # Asistencia
        turnos = (
            s.query(Turno)
            .filter(Turno.empleado_id == empleado_id, Turno.fecha >= desde, Turno.fecha <= hasta)
            .all()
        )
        dias_planificados = len(turnos)
        checkins = (
            s.query(CheckIn)
            .filter(CheckIn.empleado_id == empleado_id, CheckIn.fecha >= desde, CheckIn.fecha <= hasta)
            .all()
        )
        dias_trabajados = len(checkins)
        ausencias = (
            s.query(Ausencia)
            .filter(Ausencia.empleado_id == empleado_id, Ausencia.fecha >= desde, Ausencia.fecha <= hasta)
            .count()
        )
        tasa_asistencia = round(dias_trabajados * 100 / dias_planificados) if dias_planificados > 0 else None

        # Puntualidad
        gestor_emp = GestorEmpleado()
        punt_data = gestor_emp.puntualidad_empleado(empleado_id, desde, hasta)

        # Rendimiento
        horas = self._horas_trabajadas(empleado_id, desde, hasta)
        ops = self._operaciones_empleado(empleado_id, rol_nombre, desde, hasta)
        num_ops = len(ops)
        productividad = round(num_ops / horas, 2) if horas > 0 else 0
        if rol_nombre == 'picker' and ops:
            tiempos = [round((op.completado_en - op.created_at).total_seconds() / 60)
                       for op in ops if op.created_at and op.completado_en]
        elif rol_nombre == 'repartidor' and ops:
            tiempos = [round((op.hora_entrega_real - op.hora_salida).total_seconds() / 60)
                       for op in ops if op.hora_salida and op.hora_entrega_real]
        else:
            tiempos = []
        tiempo_medio = round(statistics.mean(tiempos)) if tiempos else None

        # Evolución semanal
        evolucion = self._evolucion_semanal(empleado_id, rol_nombre, desde, hasta)

        return {
            'empleado_id': empleado_id,
            'nombre': emp.Nombre,
            'rol': rol_nombre,
            'asistencia': {
                'dias_planificados': dias_planificados,
                'dias_trabajados': dias_trabajados,
                'ausencias': ausencias,
                'tasa_asistencia_pct': tasa_asistencia,
            },
            'puntualidad': punt_data,
            'rendimiento': {
                'operaciones_completadas': num_ops,
                'horas_trabajadas': horas,
                'productividad_operaciones_hora': productividad,
                'tiempo_medio_operacion_min': tiempo_medio,
            },
            'evolucion_semanal': evolucion,
        }

    def _evolucion_semanal(self, empleado_id: int, rol: str, desde: date, hasta: date) -> list[dict]:
        """Punto por semana natural (lunes-domingo) dentro del rango."""
        semanas = []
        lunes = desde - timedelta(days=desde.weekday())
        while lunes <= hasta:
            fin_semana = lunes + timedelta(days=6)
            ops = self._operaciones_empleado(empleado_id, rol, lunes, fin_semana)
            if ops:
                if rol == 'picker':
                    tiempos = [round((op.completado_en - op.created_at).total_seconds() / 60)
                               for op in ops if op.created_at and op.completado_en]
                else:
                    tiempos = [round((op.hora_entrega_real - op.hora_salida).total_seconds() / 60)
                               for op in ops if op.hora_salida and op.hora_entrega_real]
                tiempo_medio = round(statistics.mean(tiempos)) if tiempos else None
            else:
                tiempo_medio = None
            semanas.append({
                'semana_inicio': str(lunes),
                'operaciones': len(ops),
                'tiempo_medio_min': tiempo_medio,
            })
            lunes += timedelta(weeks=1)
        return semanas

    def asistencia_periodo(self, desde: date, hasta: date) -> dict:
        from models import Turno, CheckIn, Ausencia, Empleado
        s = self.session
        rows = (
            s.query(Turno, CheckIn, Empleado)
            .join(Empleado, Turno.empleado_id == Empleado.EmpleadoID)
            .outerjoin(
                CheckIn,
                (CheckIn.empleado_id == Turno.empleado_id) & (CheckIn.fecha == Turno.fecha)
            )
            .outerjoin(
                Ausencia,
                (Ausencia.empleado_id == Turno.empleado_id) & (Ausencia.fecha == Turno.fecha)
            )
            .filter(Turno.fecha >= desde, Turno.fecha <= hasta)
            .all()
        )

        por_emp: dict = {}
        for turno, checkin, empleado in rows:
            eid = empleado.EmpleadoID
            if eid not in por_emp:
                por_emp[eid] = {
                    'empleado_id': eid,
                    'nombre': empleado.Nombre,
                    'dias_planificados': 0,
                    'dias_trabajados': 0,
                    'ausencias': 0,
                    'minutos_tarde': [],
                    'checkins_con_turno': 0,
                }
            por_emp[eid]['dias_planificados'] += 1
            if checkin:
                por_emp[eid]['dias_trabajados'] += 1
                if checkin.minutos_tarde is not None:
                    por_emp[eid]['minutos_tarde'].append(checkin.minutos_tarde)
                    por_emp[eid]['checkins_con_turno'] += 1
            else:
                por_emp[eid]['ausencias'] += 1

        por_empleado_list = []
        total_planificados = total_trabajados = 0
        total_puntuales = total_check = 0
        for eid, data in por_emp.items():
            total_planificados += data['dias_planificados']
            total_trabajados += data['dias_trabajados']
            min_tarde = data['minutos_tarde']
            tasa_puntualidad = None
            media_tarde = None
            if min_tarde:
                puntuales = sum(1 for m in min_tarde if m <= 5)
                total_puntuales += puntuales
                total_check += len(min_tarde)
                tasa_puntualidad = round(puntuales * 100 / len(min_tarde))
                media_tarde = round(statistics.mean(min_tarde), 1)
            tasa_asistencia = round(data['dias_trabajados'] * 100 / data['dias_planificados']) if data['dias_planificados'] > 0 else None
            por_empleado_list.append({
                'empleado_id': eid,
                'nombre': data['nombre'],
                'dias_planificados': data['dias_planificados'],
                'dias_trabajados': data['dias_trabajados'],
                'ausencias': data['ausencias'],
                'tasa_asistencia_pct': tasa_asistencia,
                'tasa_puntualidad_pct': tasa_puntualidad,
                'media_minutos_tarde': media_tarde,
            })

        tasa_global_asistencia = round(total_trabajados * 100 / total_planificados) if total_planificados > 0 else None
        tasa_global_puntualidad = round(total_puntuales * 100 / total_check) if total_check > 0 else None

        return {
            'tasa_asistencia_global_pct': tasa_global_asistencia,
            'tasa_puntualidad_global_pct': tasa_global_puntualidad,
            'por_empleado': por_empleado_list,
        }

    def metricas_incidencias(self, desde: date, hasta: date) -> dict:
        from models import PickingItem, PickingPedido, Reparto, Empleado, Producto, PedidoDetalle
        from sqlalchemy import func
        s = self.session
        desde_dt = datetime.combine(desde, datetime.min.time())
        hasta_dt = datetime.combine(hasta, datetime.max.time())

        # Picking incidencias
        items_inc = (
            s.query(PickingItem, PickingPedido)
            .join(PickingPedido, PickingItem.picking_id == PickingPedido.id)
            .filter(
                PickingItem.estado.in_(['sin_stock', 'sustituido']),
                PickingPedido.completado_en >= desde_dt,
                PickingPedido.completado_en <= hasta_dt,
            )
            .all()
        )

        # Reparto incidencias
        repartos_fallidos = (
            s.query(Reparto)
            .filter(
                Reparto.estado == 'no_entregado',
                Reparto.updated_at >= desde_dt,
                Reparto.updated_at <= hasta_dt,
            )
            .all()
        )

        sin_stock = sum(1 for item, _ in items_inc if item.estado == 'sin_stock')
        sustitucion = sum(1 for item, _ in items_inc if item.estado == 'sustituido')
        entrega_fallida = len(repartos_fallidos)
        total = sin_stock + sustitucion + entrega_fallida

        # Por empleado
        por_emp_picking: dict = {}
        for item, pp in items_inc:
            if pp.empleado_id is None:
                continue
            eid = pp.empleado_id
            por_emp_picking[eid] = por_emp_picking.get(eid, 0) + 1

        por_emp_reparto: dict = {}
        for r in repartos_fallidos:
            if r.repartidor_id is None:
                continue
            por_emp_reparto[r.repartidor_id] = por_emp_reparto.get(r.repartidor_id, 0) + 1

        todos_eids = set(por_emp_picking) | set(por_emp_reparto)
        por_empleado_list = []
        for eid in todos_eids:
            emp = s.query(Empleado).filter(Empleado.EmpleadoID == eid).first()
            nombre = emp.Nombre if emp else f'Empleado {eid}'
            total_inc_emp = por_emp_picking.get(eid, 0) + por_emp_reparto.get(eid, 0)
            rol_emp = emp.rol.nombre if emp and emp.rol else 'picker'
            ops = self._operaciones_empleado(eid, rol_emp, desde, hasta)
            ratio = round(total_inc_emp * 100 / len(ops)) if ops else None
            por_empleado_list.append({
                'empleado_id': eid,
                'nombre': nombre,
                'total_incidencias': total_inc_emp,
                'ratio_sobre_operaciones_pct': ratio,
            })
        por_empleado_list.sort(key=lambda x: x['total_incidencias'], reverse=True)

        # Top 10 por pedido_detalle_id sin stock
        top_rows = (
            s.query(PickingItem.pedido_detalle_id, func.count(PickingItem.id).label('veces'))
            .join(PickingPedido, PickingItem.picking_id == PickingPedido.id)
            .filter(
                PickingItem.estado == 'sin_stock',
                PickingPedido.completado_en >= desde_dt,
                PickingPedido.completado_en <= hasta_dt,
            )
            .group_by(PickingItem.pedido_detalle_id)
            .order_by(func.count(PickingItem.id).desc())
            .limit(10)
            .all()
        )
        productos_mas_afectados = [
            {'pedido_detalle_id': pid, 'veces_sin_stock': veces}
            for pid, veces in top_rows
        ]

        return {
            'total': total,
            'por_tipo': {
                'sin_stock': sin_stock,
                'entrega_fallida': entrega_fallida,
                'sustitucion': sustitucion,
            },
            'por_empleado': por_empleado_list,
            'productos_mas_afectados': productos_mas_afectados,
        }

    # =========================================================
    # HELPERS PRIVADOS
    # =========================================================

    def _horas_trabajadas(self, empleado_id: int, desde: date, hasta: date) -> float:
        from models import CheckIn
        s = self.session
        checkins = (
            s.query(CheckIn)
            .filter(
                CheckIn.empleado_id == empleado_id,
                CheckIn.fecha >= desde,
                CheckIn.fecha <= hasta,
                CheckIn.fin.isnot(None)
            )
            .all()
        )
        total_min = sum(
            (c.fin - c.inicio).total_seconds() / 60
            for c in checkins
            if c.fin and c.inicio
        )
        return round(total_min / 60, 2)

    def _tiempo_entre_estados(self, pedido_id: int, estado_a: str, estado_b: str) -> int | None:
        from models import HistorialEstadoPedido
        s = self.session
        registros = (
            s.query(HistorialEstadoPedido)
            .filter(
                HistorialEstadoPedido.pedido_id == pedido_id,
                HistorialEstadoPedido.estado_nuevo.in_([estado_a, estado_b])
            )
            .order_by(HistorialEstadoPedido.cambiado_en)
            .all()
        )
        mapa = {r.estado_nuevo: r.cambiado_en for r in registros}
        if estado_a not in mapa or estado_b not in mapa:
            return None
        delta = mapa[estado_b] - mapa[estado_a]
        return max(0, round(delta.total_seconds() / 60))

    def _operaciones_empleado(self, empleado_id: int, rol: str, desde: date, hasta: date) -> list:
        from models import PickingPedido, Reparto
        s = self.session
        if rol == 'picker':
            return (
                s.query(PickingPedido)
                .filter(
                    PickingPedido.empleado_id == empleado_id,
                    PickingPedido.estado == 'completado',
                    PickingPedido.updated_at >= datetime.combine(desde, datetime.min.time()),
                    PickingPedido.updated_at <= datetime.combine(hasta, datetime.max.time()),
                )
                .all()
            )
        else:  # repartidor
            return (
                s.query(Reparto)
                .filter(
                    Reparto.empleado_id == empleado_id,
                    Reparto.estado == 'entregado',
                    Reparto.updated_at >= datetime.combine(desde, datetime.min.time()),
                    Reparto.updated_at <= datetime.combine(hasta, datetime.max.time()),
                )
                .all()
            )
