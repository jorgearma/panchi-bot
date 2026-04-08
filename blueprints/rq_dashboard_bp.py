# blueprints/rq_dashboard_bp.py
"""Monta rq-dashboard bajo /rq-dashboard con login guard."""
import rq_dashboard
from flask import redirect, request, session, url_for

import config


def register_rq_dashboard(app):
    """Registra rq-dashboard en la app Flask con autenticación."""
    app.config['RQ_DASHBOARD_REDIS_URL'] = (
        f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB}"
    )

    # Guard en app-level para evitar el problema del blueprint singleton
    # (rq_dashboard.blueprint.before_request no puede registrarse dos veces)
    @app.before_request
    def _require_rq_login():
        if request.path.startswith('/rq-dashboard'):
            if 'empleado_id' not in session:
                return redirect(url_for('auth.login'))

    app.register_blueprint(
        rq_dashboard.blueprint,
        url_prefix='/rq-dashboard',
    )
