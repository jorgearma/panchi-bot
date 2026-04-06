import logging
import uuid

from flask import Blueprint, jsonify, redirect, render_template, request, session

from services.demo_state import DemoState

logger = logging.getLogger(__name__)
blueprint_demo = Blueprint('demo', __name__)


@blueprint_demo.route('/demo')
def index():
    """Renderiza la página demo y prepara la sesión compartida."""
    # Crear demo_session_id una sola vez para picker y repartidor compartido
    if 'demo_session_id' not in session:
        session['demo_session_id'] = str(uuid.uuid4())
        # Inicializar datos en Redis
        try:
            DemoState.init_session(session['demo_session_id'])
        except Exception as e:
            logger.warning("DEMO: no se pudo inicializar Redis: %s", e)
    return render_template('demo/index.html')


@blueprint_demo.route('/demo/autologin')
def autologin():
    role = request.args.get('role', 'picker')
    if role not in ('picker', 'repartidor'):
        role = 'picker'

    # Limpiar cualquier sesión real antes de crear la demo
    session.clear()
    session['demo_session_id'] = str(uuid.uuid4())
    demo_sid = session['demo_session_id']

    session['empleado_id'] = 0
    session['empleado_nombre'] = 'Demo'
    session['rol'] = 'manager'
    session['demo_mode'] = True
    session.permanent = False

    # Inicializar datos demo en Redis
    try:
        DemoState.init_session(demo_sid)
    except Exception as e:
        logger.warning("DEMO: no se pudo inicializar Redis: %s", e)

    logger.info("DEMO_AUTOLOGIN role=%s sid=%s", role, demo_sid)
    return redirect('/picker' if role == 'picker' else '/repartidor')


@blueprint_demo.route('/dashboard/demo')
def dashboard_demo():
    """Entrada directa al modo demo del dashboard sin autenticación."""
    import config as app_config
    if 'demo_session_id' not in session:
        session['demo_session_id'] = str(uuid.uuid4())
        try:
            DemoState.init_session(session['demo_session_id'])
        except Exception as e:
            logger.warning("DEMO: no se pudo inicializar Redis: %s", e)

    session['empleado_id'] = 0
    session['empleado_nombre'] = 'Admin Demo'
    session['rol'] = 'admin'
    session['demo_mode'] = True
    session.permanent = False

    if app_config.APP_MODE == 'restaurant':
        return render_template("dashboard/index_restaurant.html")
    return render_template("dashboard/index.html")


@blueprint_demo.route('/demo/exit')
def exit_demo():
    """Limpia la sesión demo y redirige al login."""
    session.clear()
    return redirect('/auth/login')


@blueprint_demo.route('/demo/reset', methods=['POST'])
def reset():
    """Regenera los datos demo para esta sesión."""
    sid = session.get('demo_session_id')
    if not sid:
        return jsonify({"error": "No hay sesión demo activa"}), 400
    try:
        DemoState.reset(sid)
        logger.info("DEMO_RESET sid=%s", sid)
        return jsonify({"ok": True, "mensaje": "Datos regenerados"})
    except Exception as e:
        logger.error("Error en /demo/reset: %s", e)
        return jsonify({"error": "Error interno"}), 500
