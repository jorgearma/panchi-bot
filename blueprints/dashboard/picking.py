import logging

from flask import jsonify, request, session

from blueprints.auth import requiere_rol
from container import gestor_dashboard
from blueprints.dashboard._common import _ok, _err, _notificar

logger = logging.getLogger(__name__)


def register(bp):
    """Registra las rutas de supervisión y gestión del picking."""
    @bp.route("/dashboard/picking")
    @requiere_rol('manager', 'admin', demo_ok=True)
    def picking():
        """Devuelve el estado actual del picking en curso."""
        if session.get('demo_mode'):
            from blueprints.demo_data import get_demo_dashboard_picking
            return _ok(get_demo_dashboard_picking())
        try:
            return _ok(gestor_dashboard.picking_activo())
        except Exception as e:
            logger.error("Error en /dashboard/picking: %s", e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/picking/asignar", methods=["POST"])
    @requiere_rol('manager', 'admin')
    def asignar_picker():
        """Asigna un picker a un pedido pendiente."""
        data = request.get_json(silent=True) or {}
        pedido_id   = data.get("pedido_id")
        empleado_id = data.get("empleado_id")

        if not pedido_id or not empleado_id:
            return _err("Faltan campos: pedido_id, empleado_id")

        ok, msg = gestor_dashboard.asignar_picker(int(pedido_id), int(empleado_id))
        if not ok:
            return _err(msg)
        return jsonify({"ok": True, "mensaje": msg})

    @bp.route("/dashboard/picking/<int:picking_id>/reasignar", methods=["POST"])
    @requiere_rol('manager', 'admin')
    def reasignar_picker(picking_id: int):
        """Cambia o libera el picker asignado a un picking."""
        data = request.get_json(silent=True) or {}
        empleado_id_raw   = data.get("empleado_id")
        nuevo_empleado_id = int(empleado_id_raw) if empleado_id_raw is not None else None

        ok, msg = gestor_dashboard.reasignar_picker(picking_id, nuevo_empleado_id)
        if not ok:
            return _err(msg)
        return jsonify({"ok": True, "mensaje": msg})

    @bp.route("/dashboard/picking/asignar-cocina", methods=["POST"])
    @requiere_rol('manager', 'admin')
    def asignar_cocina_equipo():
        """Restaurant mode: acepta el pedido en nombre de todo el equipo de cocina."""
        data = request.get_json(silent=True) or {}
        pedido_id = data.get("pedido_id")
        if not pedido_id:
            return _err("Falta pedido_id")
        ok, msg, equipo = gestor_dashboard.asignar_cocina_equipo(int(pedido_id))
        if not ok:
            return _err(msg)
        return jsonify({"ok": True, "mensaje": msg, "equipo": equipo})

    @bp.route("/dashboard/picking/<int:picking_id>/completar", methods=["POST"])
    @requiere_rol('manager', 'admin')
    def completar_picking(picking_id: int):
        """Cierra el picking y notifica al cliente que el pedido ya va en camino."""
        ok, msg, telefono = gestor_dashboard.completar_picking(picking_id)
        if not ok:
            return _err(msg)
        _notificar(telefono, "✅ Tu pedido está listo y en camino hacia ti. ¡Ya casi está! 📦")
        return jsonify({"ok": True, "mensaje": msg})
