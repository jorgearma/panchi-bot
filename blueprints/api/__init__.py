from flask import Blueprint

blueprint_api = Blueprint('api', __name__)

from blueprints.api import cart, payments, tracking  # noqa: E402

cart.register(blueprint_api)
payments.register(blueprint_api)
tracking.register(blueprint_api)
