import logging
from datetime import datetime

from models import AuditLog, Empleado, PickingPedido, Reparto
from sqlalchemy.exc import SQLAlchemyError
from states import EstadoPicking, EstadoReparto

logger = logging.getLogger(__name__)


class GestorEmpleadoProfileRolesMixin:
    def perfil(self, empleado_id: int) -> dict | None:
        """Datos básicos del empleado para el hub."""
        empleado = self.session.query(Empleado).filter_by(
            EmpleadoID=empleado_id,
            activo=True,
        ).first()
        if not empleado:
            return None
        return {
            'id': empleado.EmpleadoID,
            'nombre': f'{empleado.Nombre} {empleado.Apellido}',
            'email': empleado.Email,
            'telefono': empleado.Telefono,
            'rol': empleado.rol.nombre if empleado.rol else empleado.Puesto,
            'estado_operativo': empleado.estado_operativo,
        }

    def cambiar_estado(self, empleado_id: int, nuevo_estado: str) -> tuple:
        """El empleado solo puede fijar en_pausa o desconectado manualmente."""
        if nuevo_estado not in self._ESTADOS_MANUALES:
            return (
                False,
                f"Estado '{nuevo_estado}' no permitido — solo en_pausa o desconectado",
            )
        s = self.session
        try:
            empleado = s.query(Empleado).filter_by(EmpleadoID=empleado_id).first()
            if not empleado:
                return False, "Empleado no encontrado"
            empleado.estado_operativo = nuevo_estado
            if nuevo_estado == 'en_pausa':
                check_in = self._checkin_abierto_hoy(empleado_id)
                if check_in:
                    self._cerrar_tramo_activo(check_in, datetime.utcnow())
            elif nuevo_estado == 'desconectado':
                check_in = self._checkin_abierto_hoy(empleado_id)
                if check_in:
                    ahora = datetime.utcnow()
                    self._cerrar_tramo_activo(check_in, ahora)
                    check_in.fin = ahora
            s.commit()
            logger.info(
                "ESTADO_EMPLEADO empleado_id=%s estado=%s",
                empleado_id,
                nuevo_estado,
            )
            return True, f"Estado actualizado a '{nuevo_estado}'"
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error actualizando estado empleado %s: %s", empleado_id, e)
            return False, "Error de base de datos"

    def capacidades(self, empleado_id: int) -> list[str]:
        """Roles que puede desempeñar el empleado. Ej: ['picker', 'repartidor']"""
        empleado = self.session.query(Empleado).filter_by(
            EmpleadoID=empleado_id,
            activo=True,
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
            EmpleadoID=empleado_id,
            activo=True,
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

        s = self.session

        empleado = s.query(Empleado).filter_by(EmpleadoID=empleado_id, activo=True).first()
        if not empleado:
            return False, 'Empleado no encontrado', []

        caps = [c.rol for c in empleado.capacidades]
        if nuevo_rol not in caps:
            return False, f"El empleado no tiene la capacidad '{nuevo_rol}'", []

        rol_anterior = empleado.rol_activo or ''

        bloqueantes = []
        if rol_anterior == 'picker':
            activos = s.query(PickingPedido).filter(
                PickingPedido.empleado_id == empleado_id,
                PickingPedido.estado == EstadoPicking.EN_PROCESO.value,
            ).all()
            bloqueantes = [
                {'id': p.id, 'tipo': 'picking', 'estado': p.estado}
                for p in activos
            ]
        elif rol_anterior == 'repartidor':
            activos = s.query(Reparto).filter(
                Reparto.repartidor_id == empleado_id,
                Reparto.estado.in_(
                    [EstadoReparto.ASIGNADO.value, EstadoReparto.EN_CAMINO.value]
                ),
            ).all()
            bloqueantes = [
                {'id': r.id, 'tipo': 'reparto', 'estado': r.estado}
                for r in activos
            ]

        if bloqueantes:
            try:
                s.add(
                    AuditLog(
                        pedido_id=None,
                        empleado_id=empleado_id,
                        accion='cambio_rol_bloqueado',
                        detalles=_json.dumps(
                            {'rol_destino': nuevo_rol, 'pedidos_activos': bloqueantes}
                        ),
                    )
                )
                s.commit()
            except SQLAlchemyError:
                s.rollback()
            return False, f'Tienes tareas activas como {rol_anterior}', bloqueantes

        try:
            empleado.rol_activo = nuevo_rol
            if empleado.estado_operativo in ('desconectado', 'en_pausa'):
                empleado.estado_operativo = 'disponible'
            s.add(
                AuditLog(
                    pedido_id=None,
                    empleado_id=empleado_id,
                    accion='cambio_rol',
                    detalles=_json.dumps({'de': rol_anterior, 'a': nuevo_rol}),
                )
            )
            check_in = self._checkin_abierto_hoy(empleado_id)
            if check_in:
                ahora = datetime.utcnow()
                self._cerrar_tramo_activo(check_in, ahora)
                self._abrir_tramo(check_in, nuevo_rol, ahora)
            s.commit()
            logger.info(
                "CAMBIO_ROL empleado_id=%s de=%s a=%s",
                empleado_id,
                rol_anterior,
                nuevo_rol,
            )
            return True, f"Rol cambiado a '{nuevo_rol}'", []
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error cambiando rol empleado %s: %s", empleado_id, e)
            return False, 'Error de base de datos', []
