import logging
import statistics
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)


class GestorMetricasTiempoRealMixin:
    def resumen_operacion(self) -> dict:
        from models import CheckIn, Pedido, PickingPedido, Reparto

        s = self.session
        hoy = date.today()

        pedidos_activos = (
            s.query(Pedido).filter(Pedido.Estado.notin_(self._ESTADOS_TERMINALES)).count()
        )

        empleados_en_turno = (
            s.query(CheckIn).filter(CheckIn.fecha == hoy, CheckIn.fin.is_(None)).count()
        )

        cola_picking_count = (
            s.query(PickingPedido)
            .filter(
                PickingPedido.estado == 'pendiente',
                PickingPedido.empleado_id.is_(None),
            )
            .count()
        )

        cola_reparto_count = (
            s.query(Reparto).filter(Reparto.estado == 'pendiente').count()
        )

        entregados_hoy = (
            s.query(Reparto)
            .filter(
                Reparto.estado == 'entregado',
                Reparto.updated_at >= datetime.combine(hoy, datetime.min.time()),
            )
            .count()
        )

        no_entregados_hoy = (
            s.query(Reparto)
            .filter(
                Reparto.estado == 'no_entregado',
                Reparto.updated_at >= datetime.combine(hoy, datetime.min.time()),
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
        from models import HistorialEstadoPedido

        s = self.session
        pedidos_entregados_hoy = (
            s.query(HistorialEstadoPedido.pedido_id)
            .filter(
                HistorialEstadoPedido.estado_nuevo == 'entregado',
                HistorialEstadoPedido.cambiado_en >= datetime.combine(
                    hoy,
                    datetime.min.time(),
                ),
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
        from models import CheckIn, Empleado, Turno

        s = self.session
        hoy = date.today()
        rows = (
            s.query(Turno, CheckIn, Empleado)
            .join(Empleado, Turno.empleado_id == Empleado.EmpleadoID)
            .outerjoin(
                CheckIn,
                (CheckIn.empleado_id == Turno.empleado_id) & (CheckIn.fecha == hoy),
            )
            .filter(Turno.fecha == hoy)
            .all()
        )
        result = []
        for turno, checkin, empleado in rows:
            result.append(
                {
                    'empleado_id': empleado.EmpleadoID,
                    'nombre': empleado.Nombre,
                    'rol': empleado.rol.nombre if empleado.rol else None,
                    'turno_inicio': turno.inicio.strftime('%H:%M') if turno.inicio else None,
                    'turno_fin': turno.fin.strftime('%H:%M') if turno.fin else None,
                    'hora_fichaje': checkin.inicio.strftime('%H:%M') if checkin else None,
                    'minutos_tarde': checkin.minutos_tarde if checkin else None,
                    'activo': checkin is not None and checkin.fin is None,
                    'ausente': checkin is None,
                }
            )
        return result

    def colas_detalle(self) -> dict:
        from models import HistorialEstadoPedido, PedidoDetalle, PickingPedido, Reparto
        from sqlalchemy import func

        s = self.session

        pickings = (
            s.query(PickingPedido)
            .filter(
                PickingPedido.estado == 'pendiente',
                PickingPedido.empleado_id.is_(None),
            )
            .all()
        )
        cola_picking = []
        for pp in pickings:
            ultimo_hist = (
                s.query(HistorialEstadoPedido)
                .filter(HistorialEstadoPedido.pedido_id == pp.pedido_id)
                .order_by(HistorialEstadoPedido.cambiado_en.desc())
                .first()
            )
            mins = None
            if ultimo_hist:
                delta = datetime.utcnow() - ultimo_hist.cambiado_en
                mins = round(delta.total_seconds() / 60)
            num_items = (
                s.query(func.count(PedidoDetalle.DetalleID))
                .filter(PedidoDetalle.PedidoID == pp.pedido_id)
                .scalar()
            ) or 0
            cola_picking.append(
                {
                    'pedido_id': pp.pedido_id,
                    'minutos_esperando': mins,
                    'num_items': num_items,
                }
            )
        cola_picking.sort(key=lambda x: x['minutos_esperando'] or 0, reverse=True)

        repartos = s.query(Reparto).filter(Reparto.estado == 'pendiente').all()
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
            cola_reparto.append(
                {
                    'pedido_id': r.pedido_id,
                    'minutos_esperando': mins,
                    'num_items': num_items,
                }
            )
        cola_reparto.sort(key=lambda x: x['minutos_esperando'] or 0, reverse=True)

        return {'cola_picking': cola_picking, 'cola_reparto': cola_reparto}

    def pedidos_por_estado(self) -> dict:
        from models import Pedido
        from sqlalchemy import func

        s = self.session
        rows = (
            s.query(Pedido.Estado, func.count(Pedido.PedidoID))
            .filter(Pedido.Estado.notin_(self._ESTADOS_TERMINALES))
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
        from models import CheckIn, Empleado, Turno

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
            inicio_dt = (
                datetime.combine(hoy, turno.inicio.time())
                if isinstance(turno.inicio, datetime)
                else turno.inicio
            )
            mins_desde_inicio = round((ahora - inicio_dt).total_seconds() / 60)
            if mins_desde_inicio < 15:
                continue
            checkin = (
                s.query(CheckIn)
                .filter(CheckIn.empleado_id == empleado.EmpleadoID, CheckIn.fecha == hoy)
                .first()
            )
            if checkin is None:
                alertas.append(
                    {
                        'tipo': 'ausencia_no_fichada',
                        'severidad': 'alta',
                        'mensaje': (
                            f'{empleado.Nombre} tiene turno desde las '
                            f'{turno.inicio.strftime("%H:%M") if hasattr(turno.inicio, "strftime") else turno.inicio} '
                            f'y no ha fichado ({mins_desde_inicio} min de retraso)'
                        ),
                        'empleado_id': empleado.EmpleadoID,
                    }
                )
        return alertas

    def _alertas_colas(self) -> list[dict]:
        from models import PickingPedido, Reparto

        s = self.session
        umbral = 3
        alertas = []

        ids_picking = [
            r.pedido_id
            for r in s.query(PickingPedido)
            .filter(PickingPedido.estado == 'pendiente', PickingPedido.empleado_id.is_(None))
            .all()
        ]
        if len(ids_picking) >= umbral:
            alertas.append(
                {
                    'tipo': 'cola_picking_alta',
                    'severidad': 'alta',
                    'mensaje': f'{len(ids_picking)} pedidos en cola de picking sin picker asignado',
                    'pedidos_afectados': ids_picking,
                }
            )

        ids_reparto = [
            r.pedido_id for r in s.query(Reparto).filter(Reparto.estado == 'pendiente').all()
        ]
        if len(ids_reparto) >= umbral:
            alertas.append(
                {
                    'tipo': 'cola_reparto_alta',
                    'severidad': 'alta',
                    'mensaje': f'{len(ids_reparto)} pedidos en cola de reparto sin repartidor asignado',
                    'pedidos_afectados': ids_reparto,
                }
            )
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
            s.query(Pedido).filter(Pedido.Estado.notin_(self._ESTADOS_TERMINALES)).all()
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
                alertas.append(
                    {
                        'tipo': 'pedido_bloqueado',
                        'severidad': 'media',
                        'mensaje': (
                            f'Pedido #{pedido.PedidoID} lleva {mins_bloqueado} min '
                            f"en estado '{pedido.Estado}' sin avanzar"
                        ),
                        'pedido_id': pedido.PedidoID,
                    }
                )
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
        tiempos = [
            t
            for t in (
                self._tiempo_entre_estados(pid, 'en_preparacion', 'entregado')
                for pid in ids
            )
            if t is not None
        ]
        return round(statistics.median(tiempos)) if tiempos else None

    def _alertas_repartidores_inactivos(self) -> list[dict]:
        from models import CheckIn, Empleado, Reparto, Rol

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
                    Reparto.repartidor_id == empleado.EmpleadoID,
                    Reparto.estado.in_(['asignado', 'en_camino']),
                )
                .first()
            )
            if reparto_activo:
                continue
            ultimo_reparto = (
                s.query(Reparto)
                .filter(Reparto.repartidor_id == empleado.EmpleadoID)
                .order_by(Reparto.updated_at.desc())
                .first()
            )
            ref_time = ultimo_reparto.updated_at if ultimo_reparto else checkin.inicio
            if ref_time is None:
                continue
            mins_inactivo = round((ahora - ref_time).total_seconds() / 60)
            if mins_inactivo > umbral_min:
                alertas.append(
                    {
                        'tipo': 'repartidor_inactivo',
                        'severidad': 'media',
                        'mensaje': f'{empleado.Nombre} lleva {mins_inactivo} min sin reparto activo',
                        'empleado_id': empleado.EmpleadoID,
                    }
                )
        return alertas
