import logging
from datetime import date, datetime, timedelta

from models import CheckIn, Turno
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class GestorEmpleadoTurnosMixin:
    def turno_hoy(self, empleado_id: int) -> dict | None:
        """Turno activo ahora o próximo del día actual. Devuelve None si no hay ninguno.

        Prioridad:
        1. Turno cuya ventana de fichaje esté activa AHORA
        2. Si no, el próximo turno futuro del día
        3. Si ninguno, None
        """
        hoy = date.today()
        ahora = datetime.now()

        turnos = self.session.query(Turno).filter(
            Turno.empleado_id == empleado_id,
            Turno.fecha == hoy,
            Turno.estado != 'cancelado',
            Turno.estado != 'completado',
        ).order_by(Turno.hora_inicio).all()

        if not turnos:
            return None

        # Buscar turno en ventana activa ahora
        for turno in turnos:
            inicio_dt = datetime.combine(hoy, turno.hora_inicio)
            fin_dt = datetime.combine(hoy, turno.hora_fin)
            ventana_inicio = inicio_dt - timedelta(minutes=self._MINUTOS_ANTES)
            ventana_fin = fin_dt
            if ventana_inicio <= ahora <= ventana_fin:
                return {
                    'id': turno.id,
                    'fecha': turno.fecha.isoformat(),
                    'hora_inicio': str(turno.hora_inicio)[:5],
                    'hora_fin': str(turno.hora_fin)[:5],
                    'notas': turno.notas,
                    'estado': turno.estado,
                }

        # Si no hay ninguno activo, devolver el primero futuro
        turno = turnos[0]
        return {
            'id': turno.id,
            'fecha': turno.fecha.isoformat(),
            'hora_inicio': str(turno.hora_inicio)[:5],
            'hora_fin': str(turno.hora_fin)[:5],
            'notas': turno.notas,
            'estado': turno.estado,
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
        """Comprueba si el empleado puede abrir turno AHORA.

        Validaciones:
        1. Existe un turno activo para hoy
        2. No está completado
        3. No hay otro CheckIn abierto hoy
        4. Está dentro de la ventana de fichaje (desde -10 min antes hasta hora_fin)
        """
        turno_data = self.turno_hoy(empleado_id)
        if turno_data is None:
            return {
                'puede': False,
                'razon': 'Sin turno hoy',
                'turno_id': None,
                'ventana_desde': None,
                'ventana_hasta': None,
            }

        turno_id = turno_data['id']
        turno = self.session.query(Turno).filter_by(id=turno_id).first()
        if not turno:
            return {
                'puede': False,
                'razon': 'Turno no encontrado',
                'turno_id': None,
                'ventana_desde': None,
                'ventana_hasta': None,
            }

        # Verificar si ya está completado
        if turno.estado == 'completado':
            return {
                'puede': False,
                'razon': 'Turno ya completado',
                'turno_id': turno_id,
                'ventana_desde': None,
                'ventana_hasta': None,
            }

        # Verificar si hay CheckIn abierto para este turno
        checkin_abierto = self.session.query(CheckIn).filter(
            CheckIn.empleado_id == empleado_id,
            CheckIn.turno_id == turno_id,
            CheckIn.fin == None,
        ).first()
        if checkin_abierto:
            return {
                'puede': False,
                'razon': 'Ya tienes un turno en curso',
                'turno_id': turno_id,
                'ventana_desde': None,
                'ventana_hasta': None,
            }

        # Calcular ventana: desde -MINUTOS_ANTES hasta hora_fin
        hoy = date.today()
        inicio_turno = datetime(
            turno.fecha.year,
            turno.fecha.month,
            turno.fecha.day,
            turno.hora_inicio.hour,
            turno.hora_inicio.minute,
        )
        fin_turno = datetime(
            turno.fecha.year,
            turno.fecha.month,
            turno.fecha.day,
            turno.hora_fin.hour,
            turno.hora_fin.minute,
        )

        ventana_desde = inicio_turno - timedelta(minutes=self._MINUTOS_ANTES)
        ventana_hasta = fin_turno  # Permite fichar hasta la hora de fin del turno

        ahora = datetime.now()

        if not (ventana_desde <= ahora <= ventana_hasta):
            return {
                'puede': False,
                'razon': (
                    f"Fuera del horario de fichaje "
                    f"(ventana {ventana_desde.strftime('%H:%M')}-{ventana_hasta.strftime('%H:%M')})"
                ),
                'turno_id': turno_id,
                'ventana_desde': ventana_desde.strftime('%H:%M'),
                'ventana_hasta': ventana_hasta.strftime('%H:%M'),
            }

        return {
            'puede': True,
            'razon': None,
            'turno_id': turno_id,
            'ventana_desde': ventana_desde.strftime('%H:%M'),
            'ventana_hasta': ventana_hasta.strftime('%H:%M'),
        }
