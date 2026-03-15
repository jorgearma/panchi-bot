import os
import redis
import Monei
from dotenv import load_dotenv

load_dotenv()

from data.order import GestorPedidos
from managers.gestor_usuarios import GestorUsuariosBD
from managers.gestor_productos import ProductoManager

gestor_pedidos = GestorPedidos()
gestor_usuarios = GestorUsuariosBD()
gestor_productos = ProductoManager()

monei = Monei.MoneiClient(api_key=os.environ.get('MONEI_API_KEY'))
cache = redis.Redis(
    host=os.environ.get('REDIS_HOST', 'localhost'),
    port=int(os.environ.get('REDIS_PORT', 6379)),
    db=int(os.environ.get('REDIS_DB', 0)),
)
