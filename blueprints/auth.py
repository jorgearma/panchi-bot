import logging
from functools import wraps

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database import get_db
from models import Empleado

logger = logging.getLogger(__name__)

blueprint_auth = Blueprint('auth', __name__)

_ROLES_VALIDOS = {'manager', 'picker', 'repartidor', 'admin'}


def _get_empleado_by_email(email: str):
    return get_db().query(Empleado).filter_by(Email=email, activo=True).first()


@blueprint_auth.route('/auth/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('auth/login.html')

    data = request.get_json(silent=True) or request.form
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''

    if not email or not password:
        if request.is_json:
            return jsonify({'error': 'Faltan email y/o contraseña'}), 400
        return render_template('auth/login.html', error='Rellena todos los campos'), 400

    try:
        empleado = _get_empleado_by_email(email)
    except Exception:
        empleado = None

    if not empleado or not empleado.password_hash:
        logger.warning("AUTH_FAIL email=%s — empleado no encontrado o sin contraseña", email)
        if request.is_json:
            return jsonify({'error': 'Credenciales incorrectas'}), 401
        return render_template('auth/login.html', error='Credenciales incorrectas'), 401

    if not check_password_hash(empleado.password_hash, password):
        logger.warning("AUTH_FAIL email=%s — contraseña incorrecta", email)
        if request.is_json:
            return jsonify({'error': 'Credenciales incorrectas'}), 401
        return render_template('auth/login.html', error='Credenciales incorrectas'), 401

    # Leer capacidades operativas del empleado
    capacidades = [c.rol for c in empleado.capacidades] if hasattr(empleado, 'capacidades') else []

    # Determinar session['rol'] — nunca None para empleados operativos
    if not capacidades:
        # Manager/admin o empleado sin capacidades asignadas — usar rol_id como antes
        rol_nombre = empleado.rol.nombre if empleado.rol else None
    elif len(capacidades) == 1:
        rol_nombre = capacidades[0]
    elif empleado.rol_activo and empleado.rol_activo in capacidades:
        rol_nombre = empleado.rol_activo  # restaurar último usado
    else:
        rol_nombre = capacidades[0]  # primer rol disponible; redirigir a checkin

    session.clear()
    session['empleado_id'] = empleado.EmpleadoID
    session['empleado_nombre'] = empleado.Nombre
    session['rol'] = rol_nombre
    session.permanent = True

    logger.info("AUTH_OK empleado_id=%s rol=%s", empleado.EmpleadoID, rol_nombre)

    destinos = {
        'manager':    '/dashboard',
        'admin':      '/dashboard',
        'picker':     '/empleado',
        'repartidor': '/empleado',
    }
    destino = destinos.get(rol_nombre, '/empleado')

    # Polivalente sin rol_activo previo → check-in
    if len(capacidades) > 1 and not empleado.rol_activo:
        destino = '/empleado/checkin'

    if request.is_json:
        return jsonify({'ok': True, 'redirect': destino})
    return redirect(destino)


@blueprint_auth.route('/auth/logout', methods=['POST'])
def logout():
    empleado_id = session.get('empleado_id')
    # Nular rol_activo en BD para forzar check-in en el próximo turno
    if empleado_id:
        try:
            from database import get_db
            from models import Empleado as _Empleado
            emp = get_db().query(_Empleado).filter_by(EmpleadoID=empleado_id).first()
            if emp:
                emp.rol_activo = None
                get_db().commit()
        except Exception:
            pass  # No bloquear el logout por un error de BD
    session.clear()
    logger.info("AUTH_LOGOUT empleado_id=%s", empleado_id)
    return redirect(url_for('auth.login'))


def requiere_rol(*roles_permitidos):
    """Decorator that requires an active session with one of the given roles."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if 'empleado_id' not in session:
                if request.method == 'GET' and not request.is_json:
                    return redirect(url_for('auth.login'))
                return jsonify({'error': 'No autenticado'}), 401
            if roles_permitidos and session.get('rol') not in roles_permitidos:
                return jsonify({'error': 'Sin permisos para este panel'}), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator


def requiere_autenticacion(f):
    """Decorator que solo verifica que hay sesión activa, sin chequear rol.
    Usar en rutas como /empleado/checkin donde el empleado puede tener
    rol temporal o estar en proceso de selección.
    """
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'empleado_id' not in session:
            if request.method == 'GET' and not request.is_json:
                return redirect(url_for('auth.login'))
            return jsonify({'error': 'No autenticado'}), 401
        return f(*args, **kwargs)
    return wrapped
