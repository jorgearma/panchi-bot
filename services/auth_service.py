"""Lógica de autenticación y determinación de rol para empleados.

Verifica credenciales, determina el rol activo y calcula el destino de
redirección. La blueprint mantiene la gestión de sesión Flask y el formato
de respuesta HTTP.
"""
import logging

from werkzeug.security import check_password_hash

from database import get_db
from managers.gestor_redis import redismanager
from models import Empleado

_MAX_INTENTOS = 5
_BLOQUEO_SEGUNDOS = 300  # 5 minutos

logger = logging.getLogger(__name__)

_DESTINOS = {
    'manager':    '/dashboard',
    'admin':      '/dashboard',
    'picker':     '/empleado',
    'repartidor': '/empleado',
}


def _get_empleado_by_email(email: str):
    """Busca un empleado activo por email."""
    return get_db().query(Empleado).filter_by(Email=email, activo=True).first()


def _clave_intentos(ip: str) -> str:
    return f"login_fail:{ip}"


def _registrar_fallo(ip: str, email: str) -> int:
    """Incrementa el contador de fallos por IP y devuelve el total acumulado."""
    key = _clave_intentos(ip)
    try:
        intentos = redismanager.client.incr(key)
        redismanager.client.expire(key, _BLOQUEO_SEGUNDOS)
        return intentos
    except Exception as e:
        logger.error("AUTH_REDIS_ERROR al registrar fallo ip=%s email=%s: %s", ip, email, e)
        return 0


def _esta_bloqueado(ip: str) -> bool:
    key = _clave_intentos(ip)
    try:
        intentos = redismanager.client.get(key)
        return intentos is not None and int(intentos) >= _MAX_INTENTOS
    except Exception as e:
        logger.error("AUTH_REDIS_ERROR al comprobar bloqueo ip=%s: %s", ip, e)
        return False


def _limpiar_fallos(ip: str) -> None:
    key = _clave_intentos(ip)
    try:
        redismanager.client.delete(key)
    except Exception as e:
        logger.error("AUTH_REDIS_ERROR al limpiar fallos ip=%s: %s", ip, e)


def login(email: str, password: str, ip: str) -> dict:
    """Verifica credenciales y devuelve los datos de sesión.

    Retorna:
    - {'ok': False, 'error': str}
    - {'ok': True, 'empleado_id': int, 'empleado_nombre': str, 'rol': str, 'destino': str}
    """
    if _esta_bloqueado(ip):
        logger.warning("AUTH_BLOCKED ip=%s email=%s", ip, email)
        return {'ok': False, 'error': 'Demasiados intentos fallidos. Inténtalo en 5 minutos.'}

    try:
        empleado = _get_empleado_by_email(email)
    except Exception as e:
        logger.error("AUTH_DB_ERROR email=%s: %s", email, e)
        return {'ok': False, 'error': 'Error interno, inténtalo de nuevo'}

    if not empleado or not empleado.password_hash:
        logger.warning("AUTH_FAIL ip=%s email=%s — empleado no encontrado o sin contraseña", ip, email)
        _registrar_fallo(ip, email)
        return {'ok': False, 'error': 'Credenciales incorrectas'}

    if not check_password_hash(empleado.password_hash, password):
        intentos = _registrar_fallo(ip, email)
        logger.warning("AUTH_FAIL ip=%s email=%s — contraseña incorrecta (%s/%s)", ip, email, intentos, _MAX_INTENTOS)
        return {'ok': False, 'error': 'Credenciales incorrectas'}

    capacidades = [c.rol for c in empleado.capacidades] if hasattr(empleado, 'capacidades') else []

    if not capacidades:
        rol_nombre = empleado.rol.nombre if empleado.rol else None
    elif len(capacidades) == 1:
        rol_nombre = capacidades[0]
    elif empleado.rol_activo and empleado.rol_activo in capacidades:
        rol_nombre = empleado.rol_activo
    else:
        rol_nombre = capacidades[0]

    destino = _DESTINOS.get(rol_nombre, '/empleado')
    if len(capacidades) > 1 and not empleado.rol_activo:
        destino = '/empleado/checkin'

    _limpiar_fallos(ip)
    logger.info("AUTH_OK ip=%s empleado_id=%s rol=%s", ip, empleado.EmpleadoID, rol_nombre)
    return {
        'ok': True,
        'empleado_id': empleado.EmpleadoID,
        'empleado_nombre': empleado.Nombre,
        'rol': rol_nombre,
        'destino': destino,
    }
