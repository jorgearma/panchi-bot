"""Mixin: gestión de turnos y asistencia — consultas, creación, edición, cancelación."""
import logging
from datetime import datetime, timedelta, date

from sqlalchemy.exc import SQLAlchemyError

from models import Empleado, Rol
from managers.dashboard._helpers import _iso

logger = logging.getLogger(__name__)


class GestorTurnosMixin:

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

        hoy = date.today()
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
        # Si un empleado tiene múltiples turnos, se guarda el primero (por hora de inicio)
        turnos_hoy_map = {}
        for t in (
            s.query(TurnoModel)
            .filter(TurnoModel.fecha == hoy, TurnoModel.estado != 'cancelado')
            .order_by(TurnoModel.hora_inicio)
            .all()
        ):
            # Solo guardar el primer turno del empleado para este día
            if t.empleado_id not in turnos_hoy_map:
                turnos_hoy_map[t.empleado_id] = t

        resultado = []
        for emp in empleados:
            turno = turnos_hoy_map.get(emp.EmpleadoID)

            # Solo incluir empleados con turno hoy
            if not turno:
                continue

            ci = checkins_hoy.get(emp.EmpleadoID)
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
                'tiene_turno':      True,  # Ya filtramos arriba
                'turno_id':         turno.id if turno else None,
                'turno_hora_inicio': str(turno.hora_inicio)[:5] if turno and turno.hora_inicio else None,
                'turno_hora_fin':    str(turno.hora_fin)[:5] if turno and turno.hora_fin else None,
                'turno_tipo':        turno.tipo if turno else None,
                'turno_empezado':   (
                    datetime.combine(turno.fecha, turno.hora_inicio) <= ahora
                    if turno and turno.hora_inicio else False
                ),
            })

        # Ordenar alfabéticamente por nombre
        resultado.sort(key=lambda e: e['nombre'])

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
        hoy = date.today()
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

    def eliminar_turno(self, turno_id: int) -> dict:
        """Elimina físicamente un turno si no tiene fichajes asociados."""
        from models import CheckIn, Turno as TurnoModel

        s = self.session
        turno = s.query(TurnoModel).filter_by(id=turno_id).first()
        if not turno:
            return {'ok': False, 'error': 'Turno no encontrado'}

        tiene_checkins = s.query(CheckIn).filter_by(turno_id=turno_id).count() > 0
        if tiene_checkins:
            return {'ok': False, 'error': 'No se puede eliminar un turno con fichajes asociados'}

        try:
            s.delete(turno)
            s.commit()
            logger.info('TURNO_ELIMINADO id=%s', turno_id)
            return {'ok': True}
        except Exception as exc:
            s.rollback()
            logger.error('Error eliminando turno %s: %s', turno_id, exc)
            return {'ok': False, 'error': 'Error al eliminar el turno'}
