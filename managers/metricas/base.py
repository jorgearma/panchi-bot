from datetime import date, datetime

from database import get_db


class GestorMetricasBase:
    _ESTADOS_ACTIVOS = (
        'en_preparacion',
        'preparado',
        'en_reparto',
        'confirmando_pago',
        'enlace',
        'enlace2',
        'pendiente',
    )
    _ESTADOS_TERMINALES = ('entregado', 'cancelado', 'reembolsado')

    @property
    def session(self):
        return get_db()

    def _horas_trabajadas(self, empleado_id: int, desde: date, hasta: date) -> float:
        from models import CheckIn

        s = self.session
        checkins = (
            s.query(CheckIn)
            .filter(
                CheckIn.empleado_id == empleado_id,
                CheckIn.fecha >= desde,
                CheckIn.fecha <= hasta,
                CheckIn.fin.isnot(None),
            )
            .all()
        )
        total_min = sum(
            (c.fin - c.inicio).total_seconds() / 60 for c in checkins if c.fin and c.inicio
        )
        return round(total_min / 60, 2)

    def _tiempo_entre_estados(self, pedido_id: int, estado_a: str, estado_b: str) -> int | None:
        from models import HistorialEstadoPedido

        s = self.session
        registros = (
            s.query(HistorialEstadoPedido)
            .filter(
                HistorialEstadoPedido.pedido_id == pedido_id,
                HistorialEstadoPedido.estado_nuevo.in_([estado_a, estado_b]),
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
