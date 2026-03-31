import logging
from datetime import datetime

from models import Ausencia, CheckIn, MetricaDiariaEmpleado, PickingItem, PickingPedido, Reparto
from sqlalchemy.exc import SQLAlchemyError
from states import EstadoPicking, EstadoReparto

logger = logging.getLogger(__name__)


class GestorEmpleadoMetricasMixin:
    def carga_operativa(self) -> dict:
        """Nº de pedidos en cada cola para la pantalla de check-in."""
        from sqlalchemy import func

        s = self.session
        try:
            pickings_pendientes = s.query(func.count(PickingPedido.id)).filter(
                PickingPedido.estado == EstadoPicking.PENDIENTE.value
            ).scalar() or 0
            pickings_en_proceso = s.query(func.count(PickingPedido.id)).filter(
                PickingPedido.estado == EstadoPicking.EN_PROCESO.value
            ).scalar() or 0
            repartos_listos = s.query(func.count(Reparto.id)).filter(
                Reparto.estado == EstadoReparto.PENDIENTE.value
            ).scalar() or 0
            repartos_en_camino = s.query(func.count(Reparto.id)).filter(
                Reparto.estado == EstadoReparto.EN_CAMINO.value
            ).scalar() or 0
            return {
                'picker': {
                    'pendientes': pickings_pendientes,
                    'en_proceso': pickings_en_proceso,
                },
                'repartidor': {
                    'listos_para_entregar': repartos_listos,
                    'en_camino': repartos_en_camino,
                },
            }
        except SQLAlchemyError:
            return {
                'picker': {'pendientes': 0, 'en_proceso': 0},
                'repartidor': {'listos_para_entregar': 0, 'en_camino': 0},
            }

    def _colas_globales(self) -> dict:
        from sqlalchemy import func

        s = self.session
        sin_picker = s.query(func.count(PickingPedido.id)).filter(
            PickingPedido.empleado_id == None,
            PickingPedido.estado == EstadoPicking.PENDIENTE.value,
        ).scalar() or 0
        sin_repartidor = s.query(func.count(Reparto.id)).filter(
            Reparto.repartidor_id == None,
            Reparto.estado == EstadoReparto.PENDIENTE.value,
        ).scalar() or 0
        return {'sin_picker': sin_picker, 'sin_repartidor': sin_repartidor}

    def metricas_hoy(self, empleado_id: int, rol: str) -> dict:
        """KPIs personales del día: pedidos_completados, tiempo_medio_min, incidencias_hoy."""
        from sqlalchemy import func

        s = self.session
        hoy = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        if rol == 'picker':
            completados = s.query(PickingPedido).filter(
                PickingPedido.empleado_id == empleado_id,
                PickingPedido.estado == EstadoPicking.COMPLETADO.value,
                PickingPedido.completado_en >= hoy,
            ).all()

            tiempos = [
                (pk.completado_en - pk.iniciado_en).total_seconds() / 60
                for pk in completados
                if pk.iniciado_en and pk.completado_en
            ]
            tiempo_medio = round(sum(tiempos) / len(tiempos)) if tiempos else None

            ids = [pk.id for pk in completados]
            incidencias = 0
            if ids:
                incidencias = s.query(func.count(PickingItem.id)).filter(
                    PickingItem.picking_id.in_(ids),
                    PickingItem.estado.in_(['sin_stock', 'sustituido']),
                ).scalar() or 0

            return {
                'pedidos_completados': len(completados),
                'tiempo_medio_min': tiempo_medio,
                'incidencias_hoy': incidencias,
                **self._colas_globales(),
            }

        entregados = s.query(Reparto).filter(
            Reparto.repartidor_id == empleado_id,
            Reparto.estado == EstadoReparto.ENTREGADO.value,
            Reparto.hora_entrega_real >= hoy,
        ).all()

        tiempos = [
            (r.hora_entrega_real - r.hora_salida).total_seconds() / 60
            for r in entregados
            if r.hora_salida and r.hora_entrega_real
        ]
        tiempo_medio = round(sum(tiempos) / len(tiempos)) if tiempos else None

        fallidos = s.query(func.count(Reparto.id)).filter(
            Reparto.repartidor_id == empleado_id,
            Reparto.estado == EstadoReparto.NO_ENTREGADO.value,
            Reparto.updated_at >= hoy,
        ).scalar() or 0

        return {
            'pedidos_completados': len(entregados),
            'tiempo_medio_min': tiempo_medio,
            'incidencias_hoy': fallidos,
            **self._colas_globales(),
        }

    def puntualidad_empleado(self, empleado_id: int, fecha_inicio, fecha_fin) -> dict:
        """Resumen de puntualidad de un empleado en un rango de fechas."""
        checkins = [
            c
            for c in (
                self.session.query(CheckIn)
                .filter(
                    CheckIn.empleado_id == empleado_id,
                    CheckIn.fecha >= fecha_inicio,
                    CheckIn.fecha <= fecha_fin,
                )
                .all()
            )
            if c.turno_id is not None
        ]

        total = len(checkins)
        if total == 0:
            return {
                'total_turnos': 0,
                'puntuales': 0,
                'tarde': 0,
                'tasa_puntualidad_pct': 100,
                'media_minutos_tarde': None,
            }

        puntuales = sum(
            1
            for c in checkins
            if c.minutos_tarde is not None
            and c.minutos_tarde <= self._MARGEN_PUNTUALIDAD_MIN
        )
        tarde = total - puntuales

        minutos_con_dato = [c.minutos_tarde for c in checkins if c.minutos_tarde is not None]
        media = round(sum(minutos_con_dato) / len(minutos_con_dato)) if minutos_con_dato else None

        return {
            'total_turnos': total,
            'puntuales': puntuales,
            'tarde': tarde,
            'tasa_puntualidad_pct': round(puntuales / total * 100),
            'media_minutos_tarde': media,
        }

    def registrar_ausencia(self, empleado_id: int, fecha, tipo: str, notas: str | None = None):
        """Registra una ausencia para un empleado en una fecha."""
        if tipo not in self._TIPOS_AUSENCIA:
            raise ValueError('tipo_invalido')
        s = self.session
        ausencia = Ausencia(empleado_id=empleado_id, fecha=fecha, tipo=tipo, notas=notas)
        s.add(ausencia)
        try:
            s.commit()
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error registrando ausencia empleado %s: %s", empleado_id, e)
            raise
        logger.info(
            "AUSENCIA_REGISTRADA empleado_id=%s fecha=%s tipo=%s",
            empleado_id,
            fecha,
            tipo,
        )
        return ausencia

    def calcular_y_guardar_metrica_diaria(self, empleado_id: int, fecha, rol: str) -> None:
        """Calcula y persiste las métricas del día para un empleado en un rol."""
        s = self.session

        check_in = s.query(CheckIn).filter(
            CheckIn.empleado_id == empleado_id,
            CheckIn.fecha == fecha,
        ).first()

        horas_min = None
        minutos_tarde_dia = None
        if check_in and check_in.inicio and check_in.fin:
            horas_min = int((check_in.fin - check_in.inicio).total_seconds() / 60)
            minutos_tarde_dia = check_in.minutos_tarde

        kpis = self.metricas_hoy(empleado_id, rol)

        s.query(MetricaDiariaEmpleado).filter(
            MetricaDiariaEmpleado.empleado_id == empleado_id,
            MetricaDiariaEmpleado.fecha == fecha,
            MetricaDiariaEmpleado.rol == rol,
        ).delete()
        s.flush()

        metrica = MetricaDiariaEmpleado(
            empleado_id=empleado_id,
            fecha=fecha,
            rol=rol,
            horas_trabajadas_min=horas_min,
            pedidos_completados=kpis.get('pedidos_completados', 0),
            tiempo_medio_operacion_min=kpis.get('tiempo_medio_min'),
            incidencias=kpis.get('incidencias_hoy', 0),
            minutos_tarde=minutos_tarde_dia,
        )
        s.add(metrica)
        try:
            s.commit()
        except SQLAlchemyError as e:
            s.rollback()
            logger.error(
                "Error guardando metrica diaria empleado %s fecha %s: %s",
                empleado_id,
                fecha,
                e,
            )
            raise
        logger.info(
            "METRICA_DIARIA_GUARDADA empleado_id=%s fecha=%s rol=%s",
            empleado_id,
            fecha,
            rol,
        )

    def ausencias_empleado(self, empleado_id: int, fecha_inicio, fecha_fin) -> list:
        """Lista ausencias de un empleado en un rango de fechas."""
        ausencias = (
            self.session.query(Ausencia)
            .filter(
                Ausencia.empleado_id == empleado_id,
                Ausencia.fecha >= fecha_inicio,
                Ausencia.fecha <= fecha_fin,
            )
            .order_by(Ausencia.fecha)
            .all()
        )
        return [
            {
                'id': a.id,
                'fecha': a.fecha.isoformat(),
                'tipo': a.tipo,
                'estado': a.estado,
                'aprobado_por': a.aprobado_por,
                'notas': a.notas,
            }
            for a in ausencias
        ]
