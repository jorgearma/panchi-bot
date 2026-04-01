"""Empleados — listados y consultas básicas."""
import logging

from models import Empleado, Rol

logger = logging.getLogger(__name__)


class GestorEmpleadosListaMixin:

    def empleados_disponibles(self, rol: str = None) -> list:
        """Lista empleados activos, con filtro opcional por rol."""
        query = self.session.query(Empleado).filter(Empleado.activo == True)
        if rol:
            query = query.join(Rol, Empleado.rol_id == Rol.id).filter(Rol.nombre == rol)
        return [
            {
                "id": e.EmpleadoID,
                "nombre": f"{e.Nombre} {e.Apellido}",
                "telefono": e.Telefono,
                "rol": e.rol.nombre if e.rol else e.Puesto,
            }
            for e in query.order_by(Empleado.Nombre).all()
        ]
