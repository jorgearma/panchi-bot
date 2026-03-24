import logging
from datetime import date, datetime

from sqlalchemy.exc import SQLAlchemyError

from models import Empleado, Turno, PickingPedido, Reparto, CheckIn, TramoTurno
from states import EstadoPicking, EstadoReparto

logger = logging.getLogger(__name__)

_ESTADOS_MANUALES = {'en_pausa', 'desconectado'}


class GestorEmpleado:

    @property
    def session(self):
        from database import get_db
        return get_db()

    # -------------------------------------------------------------------------

    def perfil(self, empleado_id: int) -> dict | None:
        """Datos básicos del empleado para el hub."""
        empleado = self.session.query(Empleado).filter_by(
            EmpleadoID=empleado_id, activo=True
        ).first()
        if not empleado:
            return None
        return {
            'id':               empleado.EmpleadoID,
            'nombre':           f'{empleado.Nombre} {empleado.Apellido}',
            'email':            empleado.Email,
            'telefono':         empleado.Telefono,
            'rol':              empleado.rol.nombre if empleado.rol else empleado.Puesto,
            'estado_operativo': empleado.estado_operativo,
        }

    def cambiar_estado(self, empleado_id: int, nuevo_estado: str) -> tuple:
        """El empleado solo puede fijar en_pausa o desconectado manualmente."""
        if nuevo_estado not in _ESTADOS_MANUALES:
            return False, f"Estado '{nuevo_estado}' no permitido — solo en_pausa o desconectado"
        s = self.session
        try:
            empleado = s.query(Empleado).filter_by(EmpleadoID=empleado_id).first()
            if not empleado:
                return False, "Empleado no encontrado"
            empleado.estado_operativo = nuevo_estado
            # Hook fichaje: pausar cierra tramo activo
            if nuevo_estado == 'en_pausa':
                check_in = self._checkin_abierto_hoy(empleado_id)
                if check_in:
                    self._cerrar_tramo_activo(check_in, datetime.utcnow())
            # Hook fichaje: desconectarse cierra tramo y check-in
            elif nuevo_estado == 'desconectado':
                check_in = self._checkin_abierto_hoy(empleado_id)
                if check_in:
                    ahora = datetime.utcnow()
                    self._cerrar_tramo_activo(check_in, ahora)
                    check_in.fin = ahora
            s.commit()
            logger.info("ESTADO_EMPLEADO empleado_id=%s estado=%s", empleado_id, nuevo_estado)
            return True, f"Estado actualizado a '{nuevo_estado}'"
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error actualizando estado empleado %s: %s", empleado_id, e)
            return False, "Error de base de datos"

    def turno_hoy(self, empleado_id: int) -> dict | None:
        """Turno del día actual, o None si no hay."""
        hoy = date.today()
        turno = self.session.query(Turno).filter_by(
            empleado_id=empleado_id, fecha=hoy
        ).first()
        if not turno:
            return None
        return {
            'fecha':       turno.fecha.isoformat(),
            'hora_inicio': str(turno.hora_inicio)[:5],   # "HH:MM"
            'hora_fin':    str(turno.hora_fin)[:5],
            'notas':       turno.notas,
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
                    'id':          t.id,
                    'fecha':       t.fecha.isoformat(),
                    'hora_inicio': str(t.hora_inicio)[:5],
                    'hora_fin':    str(t.hora_fin)[:5],
                    'notas':       t.notas,
                    'estado':      t.estado,
                    'tipo':        t.tipo,
                }
                for t in turnos
            ]
        except SQLAlchemyError as e:
            logger.error('Error obteniendo turnos_proximos empleado %s: %s', empleado_id, e)
            return []

    def capacidades(self, empleado_id: int) -> list[str]:
        """Roles que puede desempeñar el empleado. Ej: ['picker', 'repartidor']"""
        empleado = self.session.query(Empleado).filter_by(
            EmpleadoID=empleado_id, activo=True
        ).first()
        if not empleado:
            return []
        return [c.rol for c in empleado.capacidades]

    def es_polivalente(self, empleado_id: int) -> bool:
        """True si el empleado tiene más de una capacidad operativa."""
        return len(self.capacidades(empleado_id)) > 1

    def tiene_rol_activo(self, empleado_id: int) -> bool:
        """True si empleado.rol_activo no es NULL en BD."""
        empleado = self.session.query(Empleado).filter_by(
            EmpleadoID=empleado_id, activo=True
        ).first()
        return bool(empleado and empleado.rol_activo)

    def cambiar_rol(self, empleado_id: int, nuevo_rol: str) -> tuple[bool, str, list]:
        """
        Intenta cambiar el rol activo del empleado.
        También setea estado_operativo = 'disponible' si venía de 'desconectado' o 'en_pausa'.
        Returns: (ok, mensaje, pedidos_bloqueantes)
        pedidos_bloqueantes: lista de dicts {id, tipo, estado} si hay bloqueo
        """
        import json as _json
        from models import PickingPedido, Reparto, AuditLog
        from states import EstadoPicking, EstadoReparto
        s = self.session

        empleado = s.query(Empleado).filter_by(EmpleadoID=empleado_id, activo=True).first()
        if not empleado:
            return False, 'Empleado no encontrado', []

        caps = [c.rol for c in empleado.capacidades]
        if nuevo_rol not in caps:
            return False, f"El empleado no tiene la capacidad '{nuevo_rol}'", []

        rol_anterior = empleado.rol_activo or ''

        # Verificar tareas activas con el rol actual
        bloqueantes = []
        if rol_anterior == 'picker':
            activos = s.query(PickingPedido).filter(
                PickingPedido.empleado_id == empleado_id,
                PickingPedido.estado == EstadoPicking.EN_PROCESO.value,
            ).all()
            bloqueantes = [{'id': p.id, 'tipo': 'picking', 'estado': p.estado} for p in activos]
        elif rol_anterior == 'repartidor':
            activos = s.query(Reparto).filter(
                Reparto.repartidor_id == empleado_id,
                Reparto.estado.in_([EstadoReparto.ASIGNADO.value, EstadoReparto.EN_CAMINO.value]),
            ).all()
            bloqueantes = [{'id': r.id, 'tipo': 'reparto', 'estado': r.estado} for r in activos]

        if bloqueantes:
            try:
                s.add(AuditLog(
                    pedido_id=None, empleado_id=empleado_id,
                    accion='cambio_rol_bloqueado',
                    detalles=_json.dumps({'rol_destino': nuevo_rol, 'pedidos_activos': bloqueantes}),
                ))
                s.commit()
            except SQLAlchemyError:
                s.rollback()
            return False, f'Tienes tareas activas como {rol_anterior}', bloqueantes

        try:
            empleado.rol_activo = nuevo_rol
            # Setear directamente en ORM (NO usar cambiar_estado — solo acepta en_pausa/desconectado)
            if empleado.estado_operativo in ('desconectado', 'en_pausa'):
                empleado.estado_operativo = 'disponible'
            s.add(AuditLog(
                pedido_id=None, empleado_id=empleado_id,
                accion='cambio_rol',
                detalles=_json.dumps({'de': rol_anterior, 'a': nuevo_rol}),
            ))
            # Hook fichaje: cierra tramo anterior y abre uno nuevo
            check_in = self._checkin_abierto_hoy(empleado_id)
            if check_in:
                ahora = datetime.utcnow()
                self._cerrar_tramo_activo(check_in, ahora)
                self._abrir_tramo(check_in, nuevo_rol, ahora)
            s.commit()
            logger.info("CAMBIO_ROL empleado_id=%s de=%s a=%s", empleado_id, rol_anterior, nuevo_rol)
            return True, f"Rol cambiado a '{nuevo_rol}'", []
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error cambiando rol empleado %s: %s", empleado_id, e)
            return False, 'Error de base de datos', []

    # -------------------------------------------------------------------------
    # Ventana de fichaje
    # -------------------------------------------------------------------------

    _MINUTOS_ANTES = 10
    _MINUTOS_DESPUES = 30

    def puede_iniciar_turno(self, empleado_id: int) -> dict:
        """Comprueba si el empleado está dentro de la ventana de fichaje de su turno de hoy.

        Returns:
            Dict con keys: puede (bool), razon (str|None), turno_id (int|None),
            ventana_desde (str|None), ventana_hasta (str|None).
        """
        from datetime import timedelta
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
            empleado_id=empleado_id, fecha=hoy
        ).first()

        inicio_turno = datetime(
            turno.fecha.year, turno.fecha.month, turno.fecha.day,
            turno.hora_inicio.hour, turno.hora_inicio.minute
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

    # -------------------------------------------------------------------------
    # Fichaje / Check-in
    # -------------------------------------------------------------------------

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

    def iniciar_turno(self, empleado_id: int, turno_id: int | None = None,
                      ahora: datetime | None = None) -> CheckIn:
        """Crea un CheckIn para hoy.

        Args:
            empleado_id: ID del empleado.
            turno_id: ID del turno planificado al que corresponde este fichaje (opcional).
                      Si se proporciona, calcula minutos_tarde respecto a la hora de inicio del turno.
            ahora: Momento del fichaje. Default None → datetime.utcnow(). Inyectable para tests.

        Raises:
            ValueError('ya_abierto'): si ya hay un check-in abierto.
        """
        s = self.session
        ahora = ahora or datetime.utcnow()
        hoy = ahora.date()

        if self._checkin_abierto_hoy(empleado_id):
            raise ValueError('ya_abierto')

        # Calcular minutos de desfase si hay turno asociado
        minutos_tarde = None
        if turno_id is not None:
            turno = s.query(Turno).filter_by(id=turno_id).first()
            if turno and turno.fecha == hoy:
                inicio_planificado = datetime(
                    hoy.year, hoy.month, hoy.day,
                    turno.hora_inicio.hour, turno.hora_inicio.minute
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
        logger.info("CHECKIN empleado_id=%s inicio=%s turno_id=%s minutos_tarde=%s",
                    empleado_id, ahora.isoformat(), turno_id, minutos_tarde)
        return check_in

    def cerrar_turno(self, empleado_id: int) -> dict:
        """Cierra el CheckIn activo de hoy. Lanza ValueError('no_abierto') si no hay ninguno."""
        s = self.session
        ahora = datetime.utcnow()

        check_in = self._checkin_abierto_hoy(empleado_id)
        if not check_in:
            raise ValueError('no_abierto')

        try:
            self._cerrar_tramo_activo(check_in, ahora)
            check_in.fin = ahora
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
        # Primero buscar turno abierto
        check_in = self._checkin_abierto_hoy(empleado_id)
        if not check_in:
            # Si no hay abierto, mostrar el más reciente del día
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
            'activo':            check_in.fin is None,
            'inicio':            check_in.inicio.isoformat(),
            'fin':               check_in.fin.isoformat() if check_in.fin else None,
            'duracion_total_min': total_min,
            'tramos':            tramos_resumen,
        }

    def carga_operativa(self) -> dict:
        """Nº de pedidos en cada cola para la pantalla de check-in."""
        from models import PickingPedido, Reparto
        from states import EstadoPicking, EstadoReparto
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
                'picker':      {'pendientes': pickings_pendientes, 'en_proceso': pickings_en_proceso},
                'repartidor':  {'listos_para_entregar': repartos_listos, 'en_camino': repartos_en_camino},
            }
        except SQLAlchemyError:
            return {'picker': {'pendientes': 0, 'en_proceso': 0},
                    'repartidor': {'listos_para_entregar': 0, 'en_camino': 0}}

    def _colas_globales(self) -> dict:
        s = self.session
        from sqlalchemy import func
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
                from models import PickingItem
                incidencias = s.query(func.count(PickingItem.id)).filter(
                    PickingItem.picking_id.in_(ids),
                    PickingItem.estado.in_(['sin_stock', 'sustituido']),
                ).scalar() or 0

            return {
                'pedidos_completados': len(completados),
                'tiempo_medio_min':    tiempo_medio,
                'incidencias_hoy':     incidencias,
                **self._colas_globales(),
            }

        else:  # repartidor
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
                'tiempo_medio_min':    tiempo_medio,
                'incidencias_hoy':     fallidos,
                **self._colas_globales(),
            }

    # -------------------------------------------------------------------------
    # Puntualidad
    # -------------------------------------------------------------------------

    _MARGEN_PUNTUALIDAD_MIN = 5   # minutos de gracia antes de contar como tarde

    def puntualidad_empleado(self, empleado_id: int, fecha_inicio, fecha_fin) -> dict:
        """Resumen de puntualidad de un empleado en un rango de fechas.

        Solo se analizan check-ins vinculados a un turno planificado (turno_id no nulo).
        Un fichaje es 'puntual' si minutos_tarde <= _MARGEN_PUNTUALIDAD_MIN.

        Returns:
            Dict con total_turnos, puntuales, tarde, tasa_puntualidad_pct, media_minutos_tarde.
        """
        checkins = [
            c for c in (
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
            1 for c in checkins
            if c.minutos_tarde is not None and c.minutos_tarde <= self._MARGEN_PUNTUALIDAD_MIN
        )
        tarde = total - puntuales

        minutos_con_dato = [c.minutos_tarde for c in checkins if c.minutos_tarde is not None]
        media = round(sum(minutos_con_dato) / len(minutos_con_dato)) if minutos_con_dato else None

        return {
            'total_turnos':         total,
            'puntuales':            puntuales,
            'tarde':                tarde,
            'tasa_puntualidad_pct': round(puntuales / total * 100),
            'media_minutos_tarde':  media,
        }

    # -------------------------------------------------------------------------
    # Ausencias
    # -------------------------------------------------------------------------

    _TIPOS_AUSENCIA = {'vacaciones', 'baja_medica', 'personal', 'injustificada'}

    def registrar_ausencia(self, empleado_id: int, fecha, tipo: str,
                           notas: str | None = None):
        """Registra una ausencia para un empleado en una fecha.

        Raises:
            ValueError('tipo_invalido'): Si el tipo no está en los valores permitidos.
        """
        from models import Ausencia
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
        logger.info("AUSENCIA_REGISTRADA empleado_id=%s fecha=%s tipo=%s", empleado_id, fecha, tipo)
        return ausencia

    # -------------------------------------------------------------------------
    # Métricas diarias (caché para dashboard)
    # -------------------------------------------------------------------------

    def calcular_y_guardar_metrica_diaria(self, empleado_id: int, fecha, rol: str) -> None:
        """Calcula y persiste las métricas del día para un empleado en un rol.

        Diseñado para ser llamado al cerrar turno o desde un job nocturno.
        Si ya existe un registro para ese día+rol, lo sobreescribe (delete+insert).
        """
        from models import MetricaDiariaEmpleado
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
            logger.error("Error guardando metrica diaria empleado %s fecha %s: %s",
                         empleado_id, fecha, e)
            raise
        logger.info("METRICA_DIARIA_GUARDADA empleado_id=%s fecha=%s rol=%s",
                    empleado_id, fecha, rol)

    def ausencias_empleado(self, empleado_id: int, fecha_inicio, fecha_fin) -> list:
        """Lista ausencias de un empleado en un rango de fechas."""
        from models import Ausencia
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
                'id':           a.id,
                'fecha':        a.fecha.isoformat(),
                'tipo':         a.tipo,
                'estado':       a.estado,
                'aprobado_por': a.aprobado_por,
                'notas':        a.notas,
            }
            for a in ausencias
        ]
