import logging
from datetime import datetime

from models import CheckIn, Empleado, TramoTurno, Turno
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class GestorEmpleadoCheckinMixin:
    def _checkin_abierto_hoy(self, empleado_id: int):
        """Devuelve el CheckIn abierto de hoy o None."""
        hoy = datetime.utcnow().date()
        return self.session.query(CheckIn).filter(
            CheckIn.empleado_id == empleado_id,
            CheckIn.fecha == hoy,
            CheckIn.fin == None,
        ).first()

    def _cerrar_tramo_activo(self, check_in, ahora: datetime):
        """Cierra el TramoTurno sin fin de este check-in. Safe si no hay ninguno."""
        tramo = self.session.query(TramoTurno).filter(
            TramoTurno.check_in_id == check_in.id,
            TramoTurno.fin == None,
        ).first()
        if tramo:
            tramo.fin = ahora

    def _abrir_tramo(self, check_in, rol: str, ahora: datetime):
        """Crea un nuevo TramoTurno abierto."""
        tramo = TramoTurno(check_in_id=check_in.id, rol=rol, inicio=ahora)
        self.session.add(tramo)

    def iniciar_turno(
        self,
        empleado_id: int,
        turno_id: int | None = None,
        ahora: datetime | None = None,
    ) -> CheckIn:
        """Crea un CheckIn para hoy."""
        s = self.session
        ahora = ahora or datetime.utcnow()
        hoy = ahora.date()

        if self._checkin_abierto_hoy(empleado_id):
            raise ValueError('ya_abierto')

        minutos_tarde = None
        if turno_id is not None:
            turno = s.query(Turno).filter_by(id=turno_id).first()
            if turno:
                # Validar que el turno no esté completado
                if turno.estado == 'completado':
                    raise ValueError('turno_ya_completado')

                if turno.fecha == hoy:
                    inicio_planificado = datetime(
                        hoy.year,
                        hoy.month,
                        hoy.day,
                        turno.hora_inicio.hour,
                        turno.hora_inicio.minute,
                    )
                    minutos_tarde = int((ahora - inicio_planificado).total_seconds() / 60)

        empleado = s.query(Empleado).filter_by(EmpleadoID=empleado_id).first()
        check_in = CheckIn(
            empleado_id=empleado_id,
            fecha=hoy,
            inicio=ahora,
            turno_id=turno_id,
            minutos_tarde=minutos_tarde,
        )
        s.add(check_in)
        try:
            s.flush()
            if empleado and empleado.rol_activo:
                self._abrir_tramo(check_in, empleado.rol_activo, ahora)
                if empleado.estado_operativo in ('desconectado', 'en_pausa'):
                    empleado.estado_operativo = 'disponible'
            s.commit()
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error en iniciar_turno empleado %s: %s", empleado_id, e)
            raise
        logger.info(
            "CHECKIN empleado_id=%s inicio=%s turno_id=%s minutos_tarde=%s",
            empleado_id,
            ahora.isoformat(),
            turno_id,
            minutos_tarde,
        )
        return check_in

    def cerrar_turno(self, empleado_id: int) -> dict:
        """Cierra el CheckIn activo de hoy. Lanza ValueError('no_abierto') si no hay ninguno.
        Además marca el turno asociado como 'completado'.
        """
        s = self.session
        ahora = datetime.utcnow()

        check_in = self._checkin_abierto_hoy(empleado_id)
        if not check_in:
            raise ValueError('no_abierto')

        try:
            self._cerrar_tramo_activo(check_in, ahora)
            check_in.fin = ahora

            # Marcar turno asociado como completado
            if check_in.turno_id:
                turno = s.query(Turno).filter_by(id=check_in.turno_id).first()
                if turno and turno.estado == 'planificado':
                    turno.estado = 'completado'

            s.commit()
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error en cerrar_turno empleado %s: %s", empleado_id, e)
            raise
        logger.info("CHECKOUT empleado_id=%s fin=%s", empleado_id, ahora.isoformat())
        return self._resumen_checkin(check_in, ahora)

    def checkin_hoy(self, empleado_id: int) -> dict:
        """Turno activo ahora mismo, o el más reciente de hoy si no hay ninguno abierto."""
        hoy = datetime.utcnow().date()
        check_in = self._checkin_abierto_hoy(empleado_id)
        if not check_in:
            check_in = self.session.query(CheckIn).filter(
                CheckIn.empleado_id == empleado_id,
                CheckIn.fecha == hoy,
            ).order_by(CheckIn.inicio.desc()).first()
        if not check_in:
            return {'activo': False}
        ahora = datetime.utcnow()
        return self._resumen_checkin(check_in, ahora)

    def _resumen_checkin(self, check_in, ahora: datetime) -> dict:
        """Calcula duración total y por rol. Tramos abiertos usan ahora como fin provisional."""
        fin_efectivo = check_in.fin or ahora
        total_min = int((fin_efectivo - check_in.inicio).total_seconds() / 60)

        tramos_resumen = []
        for t in check_in.tramos:
            t_fin = t.fin or ahora
            minutos = int((t_fin - t.inicio).total_seconds() / 60)
            tramos_resumen.append({'rol': t.rol, 'minutos': minutos})

        return {
            'activo': check_in.fin is None,
            'inicio': check_in.inicio.isoformat(),
            'fin': check_in.fin.isoformat() if check_in.fin else None,
            'duracion_total_min': total_min,
            'tramos': tramos_resumen,
        }
