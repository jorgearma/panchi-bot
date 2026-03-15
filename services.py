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
cache = redis.Redis(host='localhost', port=6379, db=0)
