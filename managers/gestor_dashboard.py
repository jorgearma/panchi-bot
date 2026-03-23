"""
GestorDashboard — Public API.

All business logic lives in the domain mixins under managers/dashboard/.
This file is intentionally thin: it just assembles the mixins.
"""
from managers.dashboard._base import GestorDashboardBase
from managers.dashboard.gestor_pedidos_mixin import GestorPedidosMixin
from managers.dashboard.gestor_picking_mixin import GestorPickingMixin
from managers.dashboard.gestor_reparto_mixin import GestorRepartoMixin
from managers.dashboard.gestor_turnos_mixin import GestorTurnosMixin
from managers.dashboard.gestor_empleados_mixin import GestorEmpleadosMixin
from managers.dashboard.gestor_estadisticas_mixin import GestorEstadisticasMixin

class GestorDashboard(
    GestorPedidosMixin,
    GestorPickingMixin,
    GestorRepartoMixin,
    GestorTurnosMixin,
    GestorEmpleadosMixin,
    GestorEstadisticasMixin,
    GestorDashboardBase,
):
    """Composite dashboard manager. Business logic lives in each domain mixin."""
    pass
