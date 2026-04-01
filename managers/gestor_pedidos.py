"""
GestorPedidos — Public API.

La implementación se divide por casos de uso en managers/pedidos/.
Este archivo mantiene la API pública estable para blueprints, services y tests.
"""

from managers.pedidos.base import GestorPedidosBase
from managers.pedidos.items_mixin import GestorPedidosItemsMixin
from managers.pedidos.lifecycle_mixin import GestorPedidosLifecycleMixin
from managers.pedidos.workflow_mixin import GestorPedidosWorkflowMixin


class GestorPedidos(
    GestorPedidosItemsMixin,
    GestorPedidosWorkflowMixin,
    GestorPedidosLifecycleMixin,
    GestorPedidosBase,
):
    """Composite order manager assembled from domain mixins."""

    pass
