"""Empleados — listados y consultas básicas."""
import logging
from datetime import date, datetime

from sqlalchemy import and_

from models import CheckIn, Empleado, Rol, Turno

logger = logging.getLogger(__name__)


class GestorEmpleadosListaMixin:

    def empleados_disponibles(self, rol: str = None, solo_con_turno: bool = False) -> list:
        """Lista empleados activos. Si solo_con_turno=True, filtra por turno hoy.

        Args:
            rol: filtrar por rol (picker, repartidor, etc.)
            solo_con_turno: si True, solo muestra empleados con turno hoy (para asignación operativa).
                            Si False, muestra todos los empleados activos (para creación de turnos).
        """
        hoy = date.today()
        query = self.session.query(Empleado).filter(Empleado.activo == True)

        if solo_con_turno:
            query = query.join(Turno, and_(
                Turno.empleado_id == Empleado.EmpleadoID,
                Turno.fecha == hoy,
                Turno.estado != 'cancelado',
            ))

        if rol:
            query = query.join(Rol, Empleado.rol_id == Rol.id).filter(Rol.nombre == rol)

        empleados = query.order_by(Empleado.Nombre).all()
        ids = [e.EmpleadoID for e in empleados]

        checked_in_ids = set()
        if ids and solo_con_turno:
            # CheckIn.fecha se graba en UTC (datetime.utcnow().date()), usar la misma referencia.
            hoy_utc = datetime.utcnow().date()
            checked_in_ids = {
                ci.empleado_id
                for ci in self.session.query(CheckIn.empleado_id).filter(
                    CheckIn.empleado_id.in_(ids),
                    CheckIn.fecha == hoy_utc,
                    CheckIn.fin == None,
                ).all()
            }

        return [
            {
                "id": e.EmpleadoID,
                "nombre": f"{e.Nombre} {e.Apellido}",
                "telefono": e.Telefono,
                "rol": e.rol.nombre if e.rol else e.Puesto,
                "has_checked_in": e.EmpleadoID in checked_in_ids if solo_con_turno else True,
            }
            for e in empleados
        ]
