import os
import Monei

from managers.gestor_pedidos import GestorPedidos
from managers.gestor_usuarios import GestorUsuarios
from managers.gestor_productos import ProductoManager
from managers.gestor_dashboard import GestorDashboard
from managers.gestor_redis import redismanager

gestor_pedidos = GestorPedidos()
gestor_usuarios = GestorUsuarios()
gestor_productos = ProductoManager()
gestor_dashboard = GestorDashboard()

_monei = None


def get_monei():
    global _monei
    if _monei is None:
        _monei = Monei.MoneiClient(api_key=os.environ.get('MONEI_API_KEY'))
    return _monei


cache = redismanager
