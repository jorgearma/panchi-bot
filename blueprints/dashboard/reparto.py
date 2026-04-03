import logging

from flask import jsonify, request, session

from blueprints.auth import requiere_rol
from container import gestor_dashboard
from blueprints.dashboard._common import _ok, _err, _notificar

logger = logging.getLogger(__name__)


def register(bp):
    """Registra las rutas de supervisión y gestión del reparto."""
    @bp.route("/dashboard/repartidores")
    @requiere_rol('manager', 'admin', demo_ok=True)
    def repartidores():
        """Devuelve el estado operativo de los repartidores."""
        if session.get('demo_mode'):
            from blueprints.demo_data import get_demo_dashboard_repartidores
            return _ok(get_demo_dashboard_repartidores())
        try:
            return _ok(gestor_dashboard.repartidores())
        except Exception as e:
            logger.error("Error en /dashboard/repartidores: %s", e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/reparto/asignar", methods=["POST"])
    @requiere_rol('manager', 'admin')
    def asignar_repartidor():
        """Asigna un repartidor a un pedido listo para entregar."""
        data = request.get_json(silent=True) or {}
        pedido_id   = data.get("pedido_id")
        empleado_id = data.get("empleado_id")

        if not pedido_id or not empleado_id:
            return _err("Faltan campos: pedido_id, empleado_id")

        ok, msg = gestor_dashboard.asignar_repartidor(int(pedido_id), int(empleado_id))
        if not ok:
            return _err(msg)
        return jsonify({"ok": True, "mensaje": msg})

    @bp.route("/dashboard/reparto/<int:reparto_id>/salida", methods=["POST"])
    @requiere_rol('manager', 'admin')
    def marcar_salida(reparto_id: int):
        """Marca el reparto como salido y avisa al cliente."""
        ok, msg, telefono = gestor_dashboard.marcar_salida_reparto(reparto_id)
        if not ok:
            return _err(msg)
        _notificar(telefono, "🛵 Tu pedido está en camino. ¡El repartidor ya va hacia tu dirección!")
        return jsonify({"ok": True, "mensaje": msg})

    @bp.route("/dashboard/reparto/<int:reparto_id>/entregar", methods=["POST"])
    @requiere_rol('manager', 'admin')
    def marcar_entregado(reparto_id: int):
        """Marca el reparto como entregado y cierra la comunicación con el cliente."""
        ok, msg, telefono = gestor_dashboard.marcar_entregado(reparto_id)
        if not ok:
            return _err(msg)
        _notificar(telefono, "🙌 ¡Tu pedido ha sido entregado! Gracias por tu compra. ¡Hasta la próxima!")
        return jsonify({"ok": True, "mensaje": msg})
