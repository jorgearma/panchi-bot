from flask import Blueprint

blueprint_menu = Blueprint('menu', __name__)

from blueprints.menu import navegacion, sesion  # noqa: E402

navegacion.register(blueprint_menu)
sesion.register(blueprint_menu)
