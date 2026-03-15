import os
import Monei

from managers.gestor_pedidos import GestorPedidos
from managers.gestor_usuarios import GestorUsuarios
from managers.gestor_productos import ProductoManager
from managers.gestor_redis import redismanager

gestor_pedidos = GestorPedidos()
gestor_usuarios = GestorUsuarios()
gestor_productos = ProductoManager()

monei = Monei.MoneiClient(api_key=os.environ.get('MONEI_API_KEY'))
cache = redismanager.client
