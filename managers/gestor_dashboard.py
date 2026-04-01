"""
GestorDashboard — Public API.

All business logic lives in the domain mixins under managers/dashboard/.
This file is intentionally thin: it just assembles the mixins.
"""
from managers.dashboard._base import GestorDashboardBase
from managers.dashboard.gestor_pedidos_mixin import GestorPedidosMixin
from managers.dashboard.picking_basico import GestorPickingBasicoMixin
from managers.dashboard.picking_flujo import GestorPickingFlujoMixin
from managers.dashboard.reparto_asignacion import GestorRepartoAsignacionMixin
from managers.dashboard.reparto_tracking import GestorRepartoTrackingMixin
from managers.dashboard.reparto_cobro import GestorRepartoCobroMixin
from managers.dashboard.gestor_turnos_mixin import GestorTurnosMixin
from managers.dashboard.empleados_lista import GestorEmpleadosListaMixin
from managers.dashboard.empleados_monitor import GestorEmpleadosMonitorMixin
from managers.dashboard.empleados_rendimiento import GestorEmpleadosRendimientoMixin
from managers.dashboard.gestor_estadisticas_mixin import GestorEstadisticasMixin


class GestorDashboard(
    GestorPedidosMixin,
    GestorPickingBasicoMixin,
    GestorPickingFlujoMixin,
    GestorRepartoAsignacionMixin,
    GestorRepartoTrackingMixin,
    GestorRepartoCobroMixin,
    GestorTurnosMixin,
    GestorEmpleadosListaMixin,
    GestorEmpleadosMonitorMixin,
    GestorEmpleadosRendimientoMixin,
    GestorEstadisticasMixin,
    GestorDashboardBase,
):
    """Composite dashboard manager. Business logic lives in each domain mixin."""
    pass
