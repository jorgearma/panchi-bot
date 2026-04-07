import logging
from functools import wraps

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from container import gestor_empleado
from services import auth_service

logger = logging.getLogger(__name__)

blueprint_auth = Blueprint('auth', __name__)


@blueprint_auth.route('/auth/manifest.json')
def manifest():
    from flask import Response
    return Response(
        render_template('auth/manifest.json'),
        mimetype='application/manifest+json',
    )


@blueprint_auth.route('/auth/login', methods=['GET', 'POST'])
def login():
    """Autentica al empleado y decide su destino inicial según su rol."""
    if request.method == 'GET':
        return render_template('auth/login.html')

    data = request.get_json(silent=True) or request.form
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''

    if not email or not password:
        if request.is_json:
            return jsonify({'error': 'Faltan email y/o contraseña'}), 400
        return render_template('auth/login.html', error='Rellena todos los campos'), 400

    resultado = auth_service.login(email, password, request.remote_addr)

    if not resultado['ok']:
        if request.is_json:
            return jsonify({'error': resultado['error']}), 401
        return render_template('auth/login.html', error=resultado['error']), 401

    session.clear()  # también elimina demo_mode si existía
    session['empleado_id'] = resultado['empleado_id']
    session['empleado_nombre'] = resultado['empleado_nombre']
    session['rol'] = resultado['rol']
    session.permanent = True

    if request.is_json:
        return jsonify({'ok': True, 'redirect': resultado['destino']})
    return redirect(resultado['destino'])


@blueprint_auth.route('/auth/logout', methods=['POST'])
def logout():
    """Cierra la sesión y limpia el rol activo persistido del empleado."""
    empleado_id = session.get('empleado_id')
    if empleado_id and not session.get('demo_mode'):
        gestor_empleado.limpiar_rol_activo(empleado_id)
    session.clear()
    logger.info("AUTH_LOGOUT empleado_id=%s", empleado_id)
    return redirect(url_for('auth.login'))


def requiere_rol(*roles_permitidos, demo_ok=False):
    """Restringe una ruta a empleados autenticados con uno de los roles indicados."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if 'empleado_id' not in session:
                if request.method == 'GET' and not request.is_json:
                    return redirect(url_for('auth.login'))
                return jsonify({'error': 'No autenticado'}), 401
            if session.get('demo_mode') and not demo_ok:
                return jsonify({'error': 'No disponible en demo'}), 403
            if roles_permitidos and session.get('rol') not in roles_permitidos:
                return jsonify({'error': 'Sin permisos para este panel'}), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator


def requiere_autenticacion(f):
    """Exige sesión activa sin validar rol, útil en flujos previos al check-in."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'empleado_id' not in session:
            if request.method == 'GET' and not request.is_json:
                return redirect(url_for('auth.login'))
            return jsonify({'error': 'No autenticado'}), 401
        return f(*args, **kwargs)
    return wrapped
