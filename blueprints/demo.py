import logging
from flask import Blueprint, redirect, render_template, request, session

logger = logging.getLogger(__name__)
blueprint_demo = Blueprint('demo', __name__)


@blueprint_demo.route('/demo')
def index():
    return render_template('demo/index.html')


@blueprint_demo.route('/demo/autologin')
def autologin():
    role = request.args.get('role', 'picker')
    if role not in ('picker', 'repartidor'):
        role = 'picker'

    session.clear()
    session['empleado_id'] = 0
    session['empleado_nombre'] = 'Demo'
    session['rol'] = 'manager'
    session.permanent = False

    logger.info("DEMO_AUTOLOGIN role=%s", role)
    return redirect('/picker' if role == 'picker' else '/repartidor')
