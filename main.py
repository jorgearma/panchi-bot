import os
import sentry_sdk
from sentry_sdk import capture_exception
from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from database import conectar_bd1, close_db

sentry_sdk.init(
    dsn="https://1d28c716e34691862059ab2ee7cbb20b@o4509045878620160.ingest.de.sentry.io/4509045889892432",
    send_default_pii=True,
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')
app.teardown_appcontext(close_db)
CORS(app, resources={r"/api/*": {"origins": "*"}})

from blueprints.webhook import blueprint_webhook
from blueprints.menu import blueprint_menu
from blueprints.api import blueprint_api

app.register_blueprint(blueprint_webhook)
app.register_blueprint(blueprint_menu)
app.register_blueprint(blueprint_api)


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


if __name__ == "__main__":
    conectar_bd1()
    app.run(debug=True, host='0.0.0.0', port=5000)
