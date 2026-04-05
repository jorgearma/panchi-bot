from dotenv import load_dotenv
load_dotenv()

import logging
import logging.handlers as _log_handlers
import os
import config as app_config
import sentry_sdk
from sentry_sdk import capture_exception
from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from database import conectar_bd1, close_db


def create_app(config: dict = None) -> Flask:
    _VARS_COMUNES = ['SECRET_KEY', 'MONEI_API_KEY', 'MONEI_WEBHOOK_SECRET', 'PUBLIC_URL']
    _provider = app_config.WHATSAPP_PROVIDER
    if _provider not in ('twilio', 'meta'):
        raise EnvironmentError(
            f"WHATSAPP_PROVIDER '{_provider}' no es válido. Valores aceptados: 'twilio', 'meta'"
        )
    _app_mode = app_config.APP_MODE
    if _app_mode not in ('warehouse', 'restaurant'):
        raise EnvironmentError(
            f"APP_MODE '{_app_mode}' no es válido. Valores aceptados: 'warehouse', 'restaurant'"
        )
    if _provider == 'meta':
        _VARS_OBLIGATORIAS = _VARS_COMUNES + [
            'META_ACCESS_TOKEN', 'META_PHONE_NUMBER_ID', 'META_APP_SECRET', 'META_VERIFY_TOKEN',
        ]
    else:
        _VARS_OBLIGATORIAS = _VARS_COMUNES + [
            'TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_WHATSAPP_NUMBER',
        ]
    if not (config or {}).get('TESTING'):
        faltantes = [v for v in _VARS_OBLIGATORIAS if not os.environ.get(v)]
        if faltantes:
            raise EnvironmentError(
                f"Variables de entorno obligatorias no definidas: {', '.join(faltantes)}\n"
                "Comprueba tu archivo .env"
            )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )

    if not (config or {}).get("TESTING"):
        log_file = os.environ.get('LOG_FILE', 'panchi-bot.log')
        file_handler = _log_handlers.RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8',
        )
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
        logging.getLogger().addHandler(file_handler)

    if not (config or {}).get("TESTING"):
        sentry_sdk.init(
            dsn=app_config.SENTRY_DSN,
            send_default_pii=False,
        )

    app = Flask(__name__)
    app.secret_key = app_config.SECRET_KEY
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = app_config.SESSION_COOKIE_SECURE
    app.teardown_appcontext(close_db)
    CORS(app, resources={r"/api/*": {"origins": app_config.ALLOWED_ORIGIN or "*"}})

    if config:
        app.config.update(config)

    from blueprints.auth import blueprint_auth
    from blueprints.webhook import blueprint_webhook
    from blueprints.menu import blueprint_menu
    from blueprints.api import blueprint_api
    from blueprints.dashboard import blueprint_dashboard
    from blueprints.picker import blueprint_picker
    from blueprints.cocina import blueprint_cocina
    from blueprints.repartidor import blueprint_repartidor
    from blueprints.productos import blueprint_productos
    from blueprints.empleado import blueprint_empleado
    from blueprints.metricas_operacion import blueprint_metricas_operacion
    from blueprints.metricas_analitica import blueprint_metricas_analitica
    from blueprints.demo import blueprint_demo
    from blueprints.landing import blueprint_landing
    from maps_module.blueprint import blueprint_maps

    app.register_blueprint(blueprint_auth)
    app.register_blueprint(blueprint_webhook)
    app.register_blueprint(blueprint_menu)
    app.register_blueprint(blueprint_api)
    app.register_blueprint(blueprint_dashboard)
    app.register_blueprint(blueprint_picker)
    app.register_blueprint(blueprint_cocina)
    app.register_blueprint(blueprint_repartidor)
    app.register_blueprint(blueprint_productos)
    app.register_blueprint(blueprint_empleado)
    app.register_blueprint(blueprint_metricas_operacion)
    app.register_blueprint(blueprint_metricas_analitica)
    app.register_blueprint(blueprint_demo)
    app.register_blueprint(blueprint_landing)
    app.register_blueprint(blueprint_maps)

    @app.context_processor
    def inject_app_mode():
        return {'app_mode': app_config.APP_MODE}

    @app.route('/health')
    def health():
        import json
        checks = {}
        try:
            from managers.gestor_redis import redismanager
            redismanager.client.ping()
            checks['redis'] = 'ok'
        except Exception as e:
            checks['redis'] = f'error: {e}'
        try:
            from database import get_db
            from sqlalchemy import text
            get_db().execute(text('SELECT 1'))
            checks['database'] = 'ok'
        except Exception as e:
            checks['database'] = f'error: {e}'
        status = 'ok' if all(v == 'ok' for v in checks.values()) else 'degraded'
        code = 200 if status == 'ok' else 503
        return app.response_class(
            json.dumps({'status': status, **checks}),
            status=code, mimetype='application/json',
        )

    @app.errorhandler(Exception)
    def manejar_errores_globales(e):
        scope = sentry_sdk.get_current_scope()
        scope.set_tag('blueprint', request.blueprints[-1] if request.blueprints else 'unknown')
        scope.set_extra('url', request.url)
        sentry_sdk.capture_exception(e)

        if isinstance(e, HTTPException):
            return jsonify({
                "error": e.name,
                "detail": e.description
            }), e.code

        return jsonify({
            "error": "Error interno del servidor",
            "detail": "Se ha producido un error inesperado. Ya lo estamos revisando."
        }), 500

    return app


app = create_app()

if __name__ == "__main__":
    conectar_bd1()
    app.run(debug=True, host='0.0.0.0', port=5000)
