import os
import Monei
from dotenv import load_dotenv

load_dotenv()

from data.order import GestorPedidos
from managers.gestor_usuarios import GestorUsuariosBD
from managers.gestor_productos import ProductoManager
from managers.gestor_redis import redismanager

gestor_pedidos = GestorPedidos()
gestor_usuarios = GestorUsuariosBD()
gestor_productos = ProductoManager()

monei = Monei.MoneiClient(api_key=os.environ.get('MONEI_API_KEY'))
cache = redismanager.client
