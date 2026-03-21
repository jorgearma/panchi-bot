import logging
from datetime import date, datetime

from sqlalchemy.exc import SQLAlchemyError

from models import Empleado, Turno, PickingPedido, Reparto
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
            s.commit()
            logger.info("CAMBIO_ROL empleado_id=%s de=%s a=%s", empleado_id, rol_anterior, nuevo_rol)
            return True, f"Rol cambiado a '{nuevo_rol}'", []
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error cambiando rol empleado %s: %s", empleado_id, e)
            return False, 'Error de base de datos', []

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
            }
