import logging

from flask import render_template, request, session

from blueprints.auth import requiere_rol
from container import gestor_dashboard, gestor_empleado
from blueprints.dashboard._common import _ok, _err

logger = logging.getLogger(__name__)


def register(bp):
    """Registra las vistas y acciones relacionadas con turnos y rendimiento."""
    @bp.route("/dashboard/turnos")
    @requiere_rol('manager', 'admin', demo_ok=True)
    def turnos():
        """Renderiza la vista de gestión de turnos."""
        return render_template("dashboard/turnos.html")

    @bp.route("/dashboard/turnos/hoy")
    @requiere_rol('manager', 'admin', demo_ok=True)
    def turnos_hoy():
        """Devuelve los turnos programados para hoy."""
        if session.get('demo_mode'):
            from blueprints.demo_data import get_demo_turnos_hoy
            return _ok(get_demo_turnos_hoy())
        try:
            return _ok(gestor_empleado.turnos_hoy())
        except Exception as e:
            logger.error("Error en /dashboard/turnos/hoy: %s", e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/turnos/historial")
    @requiere_rol('manager', 'admin', demo_ok=True)
    def turnos_historial():
        """Devuelve el historial paginado de turnos ejecutados."""
        if session.get('demo_mode'):
            from blueprints.demo_data import get_demo_turnos_historial
            return _ok(get_demo_turnos_historial())
        try:
            desde       = request.args.get("desde")
            hasta       = request.args.get("hasta")
            empleado_id = request.args.get("empleado_id", type=int)
            rol         = request.args.get("rol")
            page        = max(int(request.args.get("page", 1)), 1)
            per_page    = int(request.args.get("per_page", 25))
            return _ok(gestor_empleado.turnos_historial(
                desde=desde, hasta=hasta, empleado_id=empleado_id,
                rol=rol, page=page, per_page=per_page,
            ))
        except Exception as e:
            logger.error("Error en /dashboard/turnos/historial: %s", e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/turnos/planificacion")
    @requiere_rol('manager', 'admin', demo_ok=True)
    def turnos_planificacion():
        """Devuelve la planificación futura de turnos con filtros."""
        if session.get('demo_mode'):
            from blueprints.demo_data import get_demo_turnos_planificacion
            return _ok(get_demo_turnos_planificacion())
        try:
            desde       = request.args.get('desde') or None
            hasta       = request.args.get('hasta') or None
            empleado_id = int(request.args.get('empleado_id')) if request.args.get('empleado_id') else None
            rol         = request.args.get('rol') or None
            page        = max(int(request.args.get('page', 1)), 1)
            per_page    = min(int(request.args.get('per_page', 25)), 200)
            return _ok(gestor_empleado.turnos_planificacion(
                desde=desde, hasta=hasta, empleado_id=empleado_id,
                rol=rol, page=page, per_page=per_page,
            ))
        except Exception as e:
            logger.error("Error en /dashboard/turnos/planificacion: %s", e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/turnos/crear", methods=["POST"])
    @requiere_rol('manager', 'admin')
    def crear_turno():
        """Crea un turno nuevo para un empleado."""
        data = request.get_json(silent=True) or {}
        empleado_id = data.get('empleado_id')
        fecha       = data.get('fecha')
        hora_inicio = data.get('hora_inicio')
        hora_fin    = data.get('hora_fin')
        if not all([empleado_id, fecha, hora_inicio, hora_fin]):
            return _err("Faltan campos: empleado_id, fecha, hora_inicio, hora_fin")
        try:
            result = gestor_empleado.crear_turno(
                empleado_id=int(empleado_id),
                fecha=fecha,
                hora_inicio=hora_inicio,
                hora_fin=hora_fin,
                tipo=data.get('tipo') or None,
                notas=data.get('notas') or None,
            )
            if not result['ok']:
                return _err(result['error'])
            return _ok(result)
        except Exception as e:
            logger.error("Error en /dashboard/turnos/crear: %s", e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/turnos/<int:turno_id>/editar", methods=["POST"])
    @requiere_rol('manager', 'admin')
    def editar_turno(turno_id):
        """Edita los campos permitidos de un turno existente."""
        data = request.get_json(silent=True) or {}
        try:
            result = gestor_empleado.editar_turno(
                turno_id=turno_id,
                hora_inicio=data.get('hora_inicio') or None,
                hora_fin=data.get('hora_fin') or None,
                tipo=data.get('tipo', '__no_change__'),
                notas=data.get('notas', '__no_change__'),
            )
            if not result['ok']:
                return _err(result['error'])
            return _ok(result)
        except Exception as e:
            logger.error("Error en /dashboard/turnos/%s/editar: %s", turno_id, e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/turnos/<int:turno_id>/cancelar", methods=["POST"])
    @requiere_rol('manager', 'admin')
    def cancelar_turno_route(turno_id):
        """Cancela un turno manteniendo su rastro histórico."""
        try:
            result = gestor_empleado.cancelar_turno(turno_id=turno_id)
            if not result['ok']:
                return _err(result['error'])
            return _ok(result)
        except Exception as e:
            logger.error("Error en /dashboard/turnos/%s/cancelar: %s", turno_id, e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/turnos/<int:turno_id>/eliminar", methods=["POST"])
    @requiere_rol('manager', 'admin')
    def eliminar_turno_route(turno_id):
        """Elimina un turno cuando ya no debe conservarse en planificación."""
        try:
            result = gestor_empleado.eliminar_turno(turno_id=turno_id)
            if not result['ok']:
                return _err(result['error'])
            return _ok(result)
        except Exception as e:
            logger.error("Error en /dashboard/turnos/%s/eliminar: %s", turno_id, e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/rendimiento")
    @requiere_rol('manager', 'admin', demo_ok=True)
    def rendimiento():
        """Renderiza la vista de rendimiento por empleado."""
        return render_template("dashboard/rendimiento.html")

    @bp.route("/dashboard/rendimiento-datos")
    @requiere_rol('manager', 'admin', demo_ok=True)
    def rendimiento_datos():
        """Resume el rendimiento de la plantilla para el periodo elegido."""
        if session.get('demo_mode'):
            from blueprints.demo_data import get_demo_rendimiento_resumen
            return _ok(get_demo_rendimiento_resumen())
        try:
            periodo = request.args.get("periodo", "hoy")
            rol     = request.args.get("rol") or None
            return _ok(gestor_dashboard.rendimiento_resumen(periodo=periodo, rol=rol))
        except Exception as e:
            logger.error("Error en /dashboard/rendimiento-datos: %s", e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/rendimiento/<int:empleado_id>")
    @requiere_rol('manager', 'admin', demo_ok=True)
    def rendimiento_empleado(empleado_id):
        """Devuelve el detalle de rendimiento de un empleado concreto."""
        if session.get('demo_mode'):
            from blueprints.demo_data import get_demo_rendimiento_empleado
            return _ok(get_demo_rendimiento_empleado(empleado_id))
        try:
            periodo = request.args.get("periodo", "semana")
            data = gestor_dashboard.rendimiento_empleado(empleado_id, periodo=periodo)
            if data is None:
                return _err("Empleado no encontrado", 404)
            return _ok(data)
        except Exception as e:
            logger.error("Error en /dashboard/rendimiento/%s: %s", empleado_id, e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/estadisticas")
    @requiere_rol('manager', 'admin', demo_ok=True)
    def estadisticas():
        """Renderiza la vista de estadísticas agregadas."""
        return render_template("dashboard/estadisticas.html")

    @bp.route("/dashboard/estadisticas-datos")
    @requiere_rol('manager', 'admin', demo_ok=True)
    def estadisticas_datos():
        """Devuelve series agregadas para la vista de estadísticas."""
        if session.get('demo_mode'):
            from blueprints.demo_data import get_demo_estadisticas
            return _ok(get_demo_estadisticas())
        desde        = request.args.get('desde') or None
        hasta        = request.args.get('hasta') or None
        granularidad = request.args.get('granularidad', 'dia')
        try:
            return _ok(gestor_dashboard.estadisticas(desde=desde, hasta=hasta, granularidad=granularidad))
        except Exception as e:
            logger.error("Error en /dashboard/estadisticas-datos: %s", e)
            return _err("Error interno", 500)
