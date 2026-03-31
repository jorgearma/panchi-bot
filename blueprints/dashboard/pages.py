import logging

from flask import render_template, request

from blueprints.auth import requiere_rol
from services import gestor_dashboard
from blueprints.dashboard._common import _ok, _err

logger = logging.getLogger(__name__)


def register(bp):
    """Registra las páginas generales y paneles resumen del dashboard."""
    @bp.route("/dashboard")
    @requiere_rol('manager', 'admin')
    def index():
        """Renderiza la portada principal del dashboard."""
        return render_template("dashboard/index.html")

    @bp.route("/dashboard/monitor")
    @requiere_rol('manager', 'admin')
    def monitor():
        """Renderiza la vista de monitor en tiempo real."""
        return render_template("dashboard/monitor.html")

    @bp.route("/dashboard/monitor/datos")
    @requiere_rol('manager', 'admin')
    def monitor_datos():
        """Agrupa datos clave para alimentar el monitor operativo."""
        try:
            monitor_data = gestor_dashboard.monitor_empleados()
            metricas_data = gestor_dashboard.metricas()
            alertas_data = gestor_dashboard.alertas()
            eventos_data = gestor_dashboard.eventos(limit=25)
            return _ok({
                **monitor_data,
                "metricas": metricas_data,
                "alertas":  alertas_data,
                "eventos":  eventos_data,
            })
        except Exception as e:
            logger.error("Error en /dashboard/monitor/datos: %s", e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/metricas")
    @requiere_rol('manager', 'admin')
    def metricas():
        """Devuelve las métricas resumidas del dashboard."""
        try:
            return _ok(gestor_dashboard.metricas())
        except Exception as e:
            logger.error("Error en /dashboard/metricas: %s", e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/alertas")
    @requiere_rol('manager', 'admin')
    def alertas():
        """Devuelve las alertas activas para supervisión."""
        try:
            return _ok(gestor_dashboard.alertas())
        except Exception as e:
            logger.error("Error en /dashboard/alertas: %s", e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/eventos")
    @requiere_rol('manager', 'admin')
    def eventos():
        """Lista eventos recientes del sistema con límite configurable."""
        try:
            limit = min(int(request.args.get("limit", 50)), 200)
            return _ok(gestor_dashboard.eventos(limit=limit))
        except Exception as e:
            logger.error("Error en /dashboard/eventos: %s", e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/mapa")
    @requiere_rol('manager', 'admin')
    def mapa():
        """Devuelve la información necesaria para el mapa operativo."""
        try:
            return _ok(gestor_dashboard.mapa())
        except Exception as e:
            logger.error("Error en /dashboard/mapa: %s", e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/empleados")
    @requiere_rol('manager', 'admin')
    def empleados():
        """Lista empleados disponibles, opcionalmente filtrados por rol."""
        try:
            rol = request.args.get("rol")
            return _ok(gestor_dashboard.empleados_disponibles(rol=rol))
        except Exception as e:
            logger.error("Error en /dashboard/empleados: %s", e)
            return _err("Error interno", 500)
