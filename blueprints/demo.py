import logging
from flask import Blueprint, redirect, render_template, request, session
from database import get_db
from models import Empleado

logger = logging.getLogger(__name__)
blueprint_demo = Blueprint('demo', __name__)

DEMO_EMAIL = 'demo@panchi.com'

@blueprint_demo.route('/demo')
def index():
    return render_template('demo/index.html')

@blueprint_demo.route('/demo/autologin')
def autologin():
    role = request.args.get('role', 'picker')
    if role not in ('picker', 'repartidor'):
        role = 'picker'
    try:
        demo = get_db().query(Empleado).filter_by(Email=DEMO_EMAIL, activo=True).first()
    except Exception:
        demo = None
    if not demo:
        return redirect('/auth/login')
    session.clear()
    session['empleado_id'] = demo.EmpleadoID
    session['empleado_nombre'] = demo.Nombre
    session['rol'] = 'manager'  # manager puede acceder a picker y repartidor
    session.permanent = False
    logger.info("DEMO_LOGIN role=%s empleado_id=%s", role, demo.EmpleadoID)
    return redirect('/picker' if role == 'picker' else '/repartidor')
