"""
GestorMetricas — Public API.

Se separa la lógica entre tiempo real, analítica y desempeño de empleados
para que el dashboard y los endpoints métricos crezcan sin concentrar todo
en un único módulo.
"""

from managers.metricas.analitica_mixin import GestorMetricasAnaliticaMixin
from managers.metricas.base import GestorMetricasBase
from managers.metricas.empleados_mixin import GestorMetricasEmpleadosMixin
from managers.metricas.tiempo_real_mixin import GestorMetricasTiempoRealMixin


class GestorMetricas(
    GestorMetricasEmpleadosMixin,
    GestorMetricasAnaliticaMixin,
    GestorMetricasTiempoRealMixin,
    GestorMetricasBase,
):
    """Composite metrics manager assembled from domain mixins."""

    pass
