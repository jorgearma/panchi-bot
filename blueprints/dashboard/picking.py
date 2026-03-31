import logging

from flask import jsonify, request

from blueprints.auth import requiere_rol
from services import gestor_dashboard
from blueprints.dashboard._common import _ok, _err, _notificar

logger = logging.getLogger(__name__)


def register(bp):
    @bp.route("/dashboard/picking")
    @requiere_rol('manager', 'admin')
    def picking():
        try:
            return _ok(gestor_dashboard.picking_activo())
        except Exception as e:
            logger.error("Error en /dashboard/picking: %s", e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/picking/asignar", methods=["POST"])
    @requiere_rol('manager', 'admin')
    def asignar_picker():
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
        data = request.get_json(silent=True) or {}
        empleado_id_raw   = data.get("empleado_id")
        nuevo_empleado_id = int(empleado_id_raw) if empleado_id_raw is not None else None

        ok, msg = gestor_dashboard.reasignar_picker(picking_id, nuevo_empleado_id)
        if not ok:
            return _err(msg)
        return jsonify({"ok": True, "mensaje": msg})

    @bp.route("/dashboard/picking/<int:picking_id>/completar", methods=["POST"])
    @requiere_rol('manager', 'admin')
    def completar_picking(picking_id: int):
        ok, msg, telefono = gestor_dashboard.completar_picking(picking_id)
        if not ok:
            return _err(msg)
        _notificar(telefono, "✅ Tu pedido está listo y en camino hacia ti. ¡Ya casi está! 📦")
        return jsonify({"ok": True, "mensaje": msg})
