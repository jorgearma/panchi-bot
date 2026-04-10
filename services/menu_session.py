"""Resolución de sesiones de menú web.

Encapsula la obtención de datos desde Redis, su validación con Pydantic,
la consulta del pedido activo y la decisión de qué pantalla mostrar.
Las blueprints solo renderizan el resultado.
"""
import json
import logging
from urllib.parse import unquote

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from tenacity import RetryError

from managers.gestor_redis import redismanager
from container import gestor_pedidos, cache
from schemas.usuario import UsuarioDatos
from states import EstadoPedido

logger = logging.getLogger(__name__)


def resolver_sesion_menu(token: str, ip: str = "-") -> dict:
    """Obtiene y valida los datos de sesión asociados al token del menú.

    Retorna un dict con clave 'tipo':
    - {'tipo': 'error', 'titulo': str, 'mensaje': str, 'status': int}
    - {'tipo': 'quiniela', 'usuario': UsuarioDatos}
    - {'tipo': 'enlace2', 'pedido_id': str}
    """
    # get() devuelve None tanto si la clave no existe como si Redis falla (fail-safe).
    # En ambos casos el usuario ve "caducado" — comportamiento aceptado para esta ruta.
    raw = redismanager.get(token)
    if not raw:
        logger.warning("MENU_TOKEN_INVALIDO  token=%.6s  ip=%s", token, ip)
        return {
            'tipo': 'error',
            'titulo': 'Enlace caducado',
            'mensaje': 'Tu enlace ha caducado. Vuelve a WhatsApp y escribe 1 para obtener uno nuevo.',
            'status': 403,
        }

    try:
        datos = json.loads(unquote(raw))
    except Exception:
        return {'tipo': 'error', 'titulo': 'Error interno', 'mensaje': 'Error al cargar los datos.', 'status': 400}

    try:
        usuario = UsuarioDatos(**datos)
    except ValidationError as e:
        logger.error("Error de validación usuario token=%s: %s", token, e)
        return {'tipo': 'error', 'titulo': 'Datos inválidos', 'mensaje': 'Datos de usuario inválidos.', 'status': 400}

    usuario.token = token
    logger.debug("Sesión de menú validada: user_id=%s", usuario.id)

    try:
        pedido = gestor_pedidos.obtener_pedido_mas_reciente(usuario.id)
    except (SQLAlchemyError, RetryError) as e:
        logger.error("Error al obtener pedido para token=%s: %s", token, e)
        return {
            'tipo': 'error',
            'titulo': 'Error de base de datos',
            'mensaje': 'Error en la base de datos. Intente más tarde.',
            'status': 500,
        }

    if pedido is None:
        return {'tipo': 'error', 'titulo': 'Sin pedido activo', 'mensaje': 'No tienes ningún pedido activo.', 'status': 404}

    logger.debug("Estado del pedido: %s, user_id=%s", pedido.Estado, usuario.id)

    if pedido.Estado == EstadoPedido.ENLACE:
        logger.info("MENU_ACCESO  token=%.6s  user_id=%s  ip=%s  resultado=ok", token, usuario.id, ip)
        return {'tipo': 'quiniela', 'usuario': usuario}
    if pedido.Estado == EstadoPedido.ENLACE2:
        logger.info("MENU_ACCESO  token=%.6s  user_id=%s  ip=%s  resultado=enlace2", token, usuario.id, ip)
        return {'tipo': 'enlace2', 'pedido_id': pedido.redisID}

    logger.warning("MENU_ACCESO  token=%.6s  user_id=%s  ip=%s  resultado=estado_invalido  estado=%s", token, usuario.id, ip, pedido.Estado)
    return {'tipo': 'error', 'titulo': 'Estado no reconocido', 'mensaje': 'Estado del pedido no reconocido.', 'status': 400}


def leer_sesion_confirmacion(pedido_id: str) -> dict | None:
    """Lee los datos del carrito guardados en caché. Retorna None si expiró."""
    raw = cache.get(pedido_id)
    if not raw:
        return None
    return json.loads(raw)
