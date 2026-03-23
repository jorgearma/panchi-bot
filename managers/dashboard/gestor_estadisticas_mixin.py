"""Mixin: analítica histórica de ventas y operaciones."""
from datetime import datetime, timedelta

from models import Pedido, HistorialEstadoPedido
from states import EstadoPedido


class GestorEstadisticasMixin:

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
