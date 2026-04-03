import logging

from flask import render_template, request, session

import config as app_config
from blueprints.auth import requiere_rol
from container import gestor_dashboard
from blueprints.dashboard._common import _ok, _err

logger = logging.getLogger(__name__)


def register(bp):
    """Registra las páginas generales y paneles resumen del dashboard."""
    @bp.route("/dashboard")
    @requiere_rol('manager', 'admin', demo_ok=True)
    def index():
        """Renderiza la portada principal del dashboard."""
        if app_config.APP_MODE == 'restaurant':
            return render_template("dashboard/index_restaurant.html")
        return render_template("dashboard/index.html")

    @bp.route("/dashboard/monitor")
    @requiere_rol('manager', 'admin', demo_ok=True)
    def monitor():
        """Renderiza la vista de monitor en tiempo real."""
        return render_template("dashboard/monitor.html")

    @bp.route("/dashboard/monitor/datos")
    @requiere_rol('manager', 'admin', demo_ok=True)
    def monitor_datos():
        """Agrupa datos clave para alimentar el monitor operativo."""
        if session.get('demo_mode'):
            from blueprints.demo_data import get_demo_monitor_datos
            return _ok(get_demo_monitor_datos())
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
    @requiere_rol('manager', 'admin', demo_ok=True)
    def metricas():
        """Devuelve las métricas resumidas del dashboard."""
        if session.get('demo_mode'):
            from blueprints.demo_data import get_demo_dashboard_metricas
            return _ok(get_demo_dashboard_metricas())
        try:
            return _ok(gestor_dashboard.metricas())
        except Exception as e:
            logger.error("Error en /dashboard/metricas: %s", e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/alertas")
    @requiere_rol('manager', 'admin', demo_ok=True)
    def alertas():
        """Devuelve las alertas activas para supervisión."""
        if session.get('demo_mode'):
            from blueprints.demo_data import get_demo_dashboard_alertas
            return _ok(get_demo_dashboard_alertas())
        try:
            return _ok(gestor_dashboard.alertas())
        except Exception as e:
            logger.error("Error en /dashboard/alertas: %s", e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/eventos")
    @requiere_rol('manager', 'admin', demo_ok=True)
    def eventos():
        """Lista eventos recientes del sistema con límite configurable."""
        if session.get('demo_mode'):
            from blueprints.demo_data import get_demo_dashboard_eventos
            return _ok(get_demo_dashboard_eventos())
        try:
            limit = min(int(request.args.get("limit", 50)), 200)
            return _ok(gestor_dashboard.eventos(limit=limit))
        except Exception as e:
            logger.error("Error en /dashboard/eventos: %s", e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/mapa")
    @requiere_rol('manager', 'admin', demo_ok=True)
    def mapa():
        """Devuelve la información necesaria para el mapa operativo."""
        if session.get('demo_mode'):
            return _ok({"repartidores": [], "tienda": {"lat": 40.01139, "lng": -3.01102}})
        try:
            return _ok(gestor_dashboard.mapa())
        except Exception as e:
            logger.error("Error en /dashboard/mapa: %s", e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/empleados")
    @requiere_rol('manager', 'admin', demo_ok=True)
    def empleados():
        """Lista empleados disponibles, opcionalmente filtrados por rol.

        Parámetros:
        - rol: filtrar por rol (picker, repartidor, etc.)
        - operacion: si es "true", solo muestra empleados con turno hoy (para asignación operativa)
        """
        if session.get('demo_mode'):
            rol = request.args.get("rol")
            todos = [
                {"id": 11, "nombre": "Luis R.",  "rol": "picker"},
                {"id": 21, "nombre": "Pedro M.", "rol": "repartidor"},
                {"id": 22, "nombre": "Sara V.",  "rol": "repartidor"},
            ]
            return _ok([e for e in todos if rol is None or e['rol'] == rol])
        try:
            rol = request.args.get("rol")
            operacion = request.args.get("operacion", "").lower() == "true"
            resultado = gestor_dashboard.empleados_disponibles(rol=rol, solo_con_turno=operacion)
            return _ok(resultado)
        except Exception as e:
            logger.error("Error en /dashboard/empleados: %s", str(e), exc_info=True)
            return _err(f"Error al cargar empleados: {str(e)}", 500)
