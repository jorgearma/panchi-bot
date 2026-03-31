"""
GestorEmpleado — Public API.

La lógica queda separada por perfiles, turnos, fichaje y métricas
en managers/empleado/.
"""

from managers.empleado.base import GestorEmpleadoBase
from managers.empleado.checkin_mixin import GestorEmpleadoCheckinMixin
from managers.empleado.metricas_mixin import GestorEmpleadoMetricasMixin
from managers.empleado.profile_roles_mixin import GestorEmpleadoProfileRolesMixin
from managers.empleado.turnos_mixin import GestorEmpleadoTurnosMixin


class GestorEmpleado(
    GestorEmpleadoMetricasMixin,
    GestorEmpleadoCheckinMixin,
    GestorEmpleadoTurnosMixin,
    GestorEmpleadoProfileRolesMixin,
    GestorEmpleadoBase,
):
    """Composite employee manager assembled from domain mixins."""

    pass
