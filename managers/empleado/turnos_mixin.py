import logging
from datetime import date, datetime, timedelta

from models import Turno
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class GestorEmpleadoTurnosMixin:
    def turno_hoy(self, empleado_id: int) -> dict | None:
        """Turno del día actual, o None si no hay."""
        hoy = date.today()
        turno = self.session.query(Turno).filter_by(
            empleado_id=empleado_id,
            fecha=hoy,
        ).first()
        if not turno:
            return None
        return {
            'fecha': turno.fecha.isoformat(),
            'hora_inicio': str(turno.hora_inicio)[:5],
            'hora_fin': str(turno.hora_fin)[:5],
            'notas': turno.notas,
        }

    def turnos_proximos(self, empleado_id: int, desde: date, hasta: date) -> list[dict]:
        """Lista de turnos en el rango [desde, hasta] para el empleado."""
        try:
            turnos = (
                self.session.query(Turno)
                .filter(
                    Turno.empleado_id == empleado_id,
                    Turno.fecha >= desde,
                    Turno.fecha <= hasta,
                )
                .order_by(Turno.fecha, Turno.hora_inicio)
                .all()
            )
            return [
                {
                    'id': t.id,
                    'fecha': t.fecha.isoformat(),
                    'hora_inicio': str(t.hora_inicio)[:5],
                    'hora_fin': str(t.hora_fin)[:5],
                    'notas': t.notas,
                    'estado': t.estado,
                    'tipo': t.tipo,
                }
                for t in turnos
            ]
        except SQLAlchemyError as e:
            logger.error(
                'Error obteniendo turnos_proximos empleado %s: %s',
                empleado_id,
                e,
            )
            return []

    def puede_iniciar_turno(self, empleado_id: int) -> dict:
        """Comprueba si el empleado está dentro de la ventana de fichaje de su turno de hoy."""
        turno_data = self.turno_hoy(empleado_id)
        if turno_data is None:
            return {
                'puede': False,
                'razon': 'Sin turno hoy',
                'turno_id': None,
                'ventana_desde': None,
                'ventana_hasta': None,
            }

        hoy = date.today()
        turno = self.session.query(Turno).filter_by(
            empleado_id=empleado_id,
            fecha=hoy,
        ).first()

        inicio_turno = datetime(
            turno.fecha.year,
            turno.fecha.month,
            turno.fecha.day,
            turno.hora_inicio.hour,
            turno.hora_inicio.minute,
        )
        ventana_desde = inicio_turno - timedelta(minutes=self._MINUTOS_ANTES)
        ventana_hasta = inicio_turno + timedelta(minutes=self._MINUTOS_DESPUES)

        ahora = datetime.now()
        ahora_comparable = datetime(hoy.year, hoy.month, hoy.day, ahora.hour, ahora.minute)

        if not (ventana_desde <= ahora_comparable <= ventana_hasta):
            return {
                'puede': False,
                'razon': (
                    f"Fuera del horario de fichaje "
                    f"(ventana {ventana_desde.strftime('%H:%M')}-{ventana_hasta.strftime('%H:%M')})"
                ),
                'turno_id': turno.id,
                'ventana_desde': ventana_desde.strftime('%H:%M'),
                'ventana_hasta': ventana_hasta.strftime('%H:%M'),
            }

        return {
            'puede': True,
            'razon': None,
            'turno_id': turno.id,
            'ventana_desde': ventana_desde.strftime('%H:%M'),
            'ventana_hasta': ventana_hasta.strftime('%H:%M'),
        }
