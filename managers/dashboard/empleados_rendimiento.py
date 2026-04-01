"""Empleados — rendimiento individual y ranking de equipo."""
import logging
from datetime import datetime, timedelta

from managers.dashboard._helpers import _iso
from models import Empleado, PickingPedido, Reparto

logger = logging.getLogger(__name__)


class GestorEmpleadosRendimientoMixin:

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
            pedidos     = data['pedidos']
            incidencias = data['incidencias']
            tiempos     = data['tiempos']
            tasa        = round(pedidos / (pedidos + incidencias) * 100) if (pedidos + incidencias) > 0 else None
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
