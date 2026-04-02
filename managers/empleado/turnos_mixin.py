import logging
from datetime import date, datetime, timedelta

from models import CheckIn, Turno
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def _iso(dt) -> str | None:
    """Serializes a datetime to ISO 8601 with 'Z' suffix."""
    return dt.isoformat() + 'Z' if dt else None


class GestorEmpleadoTurnosMixin:
    # ── Per-employee helpers (used by check-in flow) ─────────────────────────

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

    # ── Aggregate queries (used by dashboard) ────────────────────────────────

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
        from models import Empleado
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
                checkins_hoy[ci.empleado_id] = ci
            elif ci.fin is None and prev.fin is None:
                if ci.inicio > prev.inicio:
                    checkins_hoy[ci.empleado_id] = ci
            elif prev.fin is not None and ci.fin is not None:
                if ci.inicio > prev.inicio:
                    checkins_hoy[ci.empleado_id] = ci

        # Build dict empleado_id → list of turnos planificados de hoy (no cancelado)
        turnos_hoy_map = {}
        for t in (
            s.query(TurnoModel)
            .filter(TurnoModel.fecha == hoy, TurnoModel.estado != 'cancelado')
            .order_by(TurnoModel.hora_inicio)
            .all()
        ):
            if t.empleado_id not in turnos_hoy_map:
                turnos_hoy_map[t.empleado_id] = []
            turnos_hoy_map[t.empleado_id].append(t)

        resultado = []
        for emp in empleados:
            turnos = turnos_hoy_map.get(emp.EmpleadoID, [])
            turno_activo = None
            if turnos:
                # Buscar el turno cuya ventana de fichaje está activa AHORA
                for t in turnos:
                    inicio_dt = datetime.combine(t.fecha, t.hora_inicio)
                    fin_dt = datetime.combine(t.fecha, t.hora_fin)
                    ventana_inicio = inicio_dt - timedelta(minutes=self._MINUTOS_ANTES)
                    ventana_fin = fin_dt
                    if ventana_inicio <= ahora <= ventana_fin and t.estado != 'completado':
                        turno_activo = t
                        break
                if not turno_activo and turnos:
                    turno_activo = (
                        [t for t in turnos if t.estado != 'completado'][0]
                        if any(t.estado != 'completado' for t in turnos)
                        else None
                    )

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
                'tiene_turno':      len(turnos) > 0,
                'turno_id':         turno_activo.id if turno_activo else None,
                'turno_hora_inicio': str(turno_activo.hora_inicio)[:5] if turno_activo and turno_activo.hora_inicio else None,
                'turno_hora_fin':    str(turno_activo.hora_fin)[:5] if turno_activo and turno_activo.hora_fin else None,
                'turno_tipo':        turno_activo.tipo if turno_activo else None,
                'turno_empezado':   (
                    datetime.combine(turno_activo.fecha, turno_activo.hora_inicio) <= ahora
                    if turno_activo and turno_activo.hora_inicio else False
                ),
                'turnos_dia':       [
                    {
                        'id': t.id,
                        'hora_inicio': str(t.hora_inicio)[:5],
                        'hora_fin': str(t.hora_fin)[:5],
                        'estado': t.estado,
                        'tipo': t.tipo,
                    }
                    for t in turnos
                ]
            })

        resultado.sort(key=lambda e: (0 if e['tiene_turno'] else 1, e['nombre']))

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

        Returns:
            { turnos: list[dict], total: int, page: int, pages: int }
        """
        from math import ceil
        from models import Empleado, Rol as RolModel

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
        from models import Empleado, Rol, Turno as TurnoModel

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

    # ── CRUD (manager-only operations) ───────────────────────────────────────

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
        from models import Empleado, Turno as TurnoModel
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

        # Validar solapamiento (solo contra turnos planificados)
        turnos_ese_dia = s.query(TurnoModel).filter(
            TurnoModel.empleado_id == empleado_id,
            TurnoModel.fecha == fecha_dt,
            TurnoModel.estado == 'planificado',
        ).all()

        for turno_existente in turnos_ese_dia:
            if h_ini < turno_existente.hora_fin and h_fin > turno_existente.hora_inicio:
                hora_str = f"{turno_existente.hora_inicio.strftime('%H:%M')}-{turno_existente.hora_fin.strftime('%H:%M')}"
                return {'ok': False, 'error': f'Turno solapado con uno existente ({hora_str})'}

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
        from models import Turno as TurnoModel

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
