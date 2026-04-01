from flask import Blueprint

blueprint_dashboard = Blueprint("dashboard", __name__)

from blueprints.dashboard import pages, turnos, pedidos, picking, reparto  # noqa: E402

pages.register(blueprint_dashboard)
turnos.register(blueprint_dashboard)
pedidos.register(blueprint_dashboard)
picking.register(blueprint_dashboard)
reparto.register(blueprint_dashboard)
