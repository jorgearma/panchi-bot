from dotenv import load_dotenv
load_dotenv()

import logging
import config as app_config
import sentry_sdk
from sentry_sdk import capture_exception
from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from database import conectar_bd1, close_db


def create_app(config: dict = None) -> Flask:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )

    if not (config or {}).get("TESTING"):
        sentry_sdk.init(
            dsn=app_config.SENTRY_DSN,
            send_default_pii=False,
        )

    app = Flask(__name__)
    app.secret_key = app_config.SECRET_KEY
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
    from blueprints.repartidor import blueprint_repartidor
    from blueprints.productos import blueprint_productos

    app.register_blueprint(blueprint_auth)
    app.register_blueprint(blueprint_webhook)
    app.register_blueprint(blueprint_menu)
    app.register_blueprint(blueprint_api)
    app.register_blueprint(blueprint_dashboard)
    app.register_blueprint(blueprint_picker)
    app.register_blueprint(blueprint_repartidor)
    app.register_blueprint(blueprint_productos)

    @app.errorhandler(Exception)
    def manejar_errores_globales(e):
        capture_exception(e)

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


if __name__ == "__main__":
    app = create_app()
    conectar_bd1()
    app.run(debug=True, host='0.0.0.0', port=5000)
