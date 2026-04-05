"""Lógica de autenticación y determinación de rol para empleados.

Verifica credenciales, determina el rol activo y calcula el destino de
redirección. La blueprint mantiene la gestión de sesión Flask y el formato
de respuesta HTTP.
"""
import logging

from werkzeug.security import check_password_hash

from database import get_db
from models import Empleado

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


def login(email: str, password: str) -> dict:
    """Verifica credenciales y devuelve los datos de sesión.

    Retorna:
    - {'ok': False, 'error': str}
    - {'ok': True, 'empleado_id': int, 'empleado_nombre': str, 'rol': str, 'destino': str}
    """
    try:
        empleado = _get_empleado_by_email(email)
    except Exception:
        empleado = None

    if not empleado or not empleado.password_hash:
        logger.warning("AUTH_FAIL email=%s — empleado no encontrado o sin contraseña", email)
        return {'ok': False, 'error': 'Credenciales incorrectas'}

    if not check_password_hash(empleado.password_hash, password):
        logger.warning("AUTH_FAIL email=%s — contraseña incorrecta", email)
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

    logger.info("AUTH_OK empleado_id=%s rol=%s", empleado.EmpleadoID, rol_nombre)
    return {
        'ok': True,
        'empleado_id': empleado.EmpleadoID,
        'empleado_nombre': empleado.Nombre,
        'rol': rol_nombre,
        'destino': destino,
    }
