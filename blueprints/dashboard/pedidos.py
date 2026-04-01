import logging

from flask import jsonify, render_template, request, session

from blueprints.auth import requiere_rol
from container import gestor_dashboard, gestor_pedidos
from blueprints.dashboard._common import _ok, _err, _notificar, _MOTIVOS_LABEL

logger = logging.getLogger(__name__)


def register(bp):
    """Registra las rutas de consulta y edición de pedidos desde el dashboard."""
    @bp.route("/dashboard/historial")
    @requiere_rol('manager', 'admin')
    def historial():
        """Renderiza la vista de historial de pedidos."""
        return render_template("dashboard/historial.html")

    @bp.route("/dashboard/historial-pedidos")
    @requiere_rol('manager', 'admin')
    def historial_pedidos():
        """Devuelve el historial paginado de pedidos con filtros."""
        try:
            desde     = request.args.get("desde")
            hasta     = request.args.get("hasta")
            estado    = request.args.get("estado")
            forma_pago = request.args.get("forma_pago")
            q         = request.args.get("q")
            page      = int(request.args.get("page", 1))
            per_page  = int(request.args.get("per_page", 25))
            return _ok(gestor_dashboard.historial_pedidos(
                desde=desde, hasta=hasta, estado=estado,
                forma_pago=forma_pago, q=q, page=page, per_page=per_page,
            ))
        except Exception as e:
            logger.error("Error en /dashboard/historial-pedidos: %s", e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/pedidos-activos")
    @requiere_rol('manager', 'admin')
    def pedidos_activos():
        """Lista los pedidos activos visibles en operación."""
        try:
            estado = request.args.get("estado")
            return _ok(gestor_dashboard.pedidos_activos(estado=estado))
        except Exception as e:
            logger.error("Error en /dashboard/pedidos-activos: %s", e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/pedido/<int:pedido_id>/detalle")
    @requiere_rol('manager', 'admin')
    def detalle_pedido(pedido_id):
        """Devuelve el detalle completo de un pedido."""
        try:
            data = gestor_dashboard.detalle_pedido(pedido_id)
            if data is None:
                return _err("Pedido no encontrado", 404)
            return _ok(data)
        except Exception as e:
            logger.error("Error en /dashboard/pedido/%s/detalle: %s", pedido_id, e)
            return _err("Error interno", 500)

    @bp.route("/dashboard/pedido/<int:pedido_id>/cancelar", methods=["POST"])
    @requiere_rol('manager', 'admin')
    def cancelar_pedido(pedido_id: int):
        """Cancela un pedido, registra el motivo y avisa al cliente."""
        data = request.get_json(silent=True) or {}
        motivo = data.get("motivo")
        empleado_id = session.get('empleado_id')

        if not motivo:
            return _err("Falta el campo: motivo")

        ok, msg, telefono = gestor_pedidos.cancelar_pedido(pedido_id, motivo, empleado_id)
        if not ok:
            return _err(msg)

        motivo_label = _MOTIVOS_LABEL.get(motivo, motivo)
        _notificar(
            telefono,
            f"❌ Tu pedido #{pedido_id} ha sido cancelado ({motivo_label}). "
            "Si tienes alguna duda llámanos. Disculpa las molestias.",
        )
        return jsonify({"ok": True, "mensaje": msg})

    @bp.route("/dashboard/pedido/<int:pedido_id>/item/<int:detalle_id>/eliminar", methods=["POST"])
    @requiere_rol('manager', 'admin')
    def eliminar_item(pedido_id: int, detalle_id: int):
        """Elimina una línea concreta del pedido."""
        empleado_id = session.get('empleado_id')
        ok, msg = gestor_pedidos.eliminar_item(pedido_id, detalle_id, empleado_id)
        if not ok:
            return _err(msg)
        return jsonify({"ok": True, "mensaje": msg})

    @bp.route("/dashboard/pedido/<int:pedido_id>/item/<int:detalle_id>/sustituir", methods=["POST"])
    @requiere_rol('manager', 'admin')
    def sustituir_item(pedido_id: int, detalle_id: int):
        """Sustituye un producto del pedido por otro disponible."""
        data = request.get_json(silent=True) or {}
        producto_sustituto_id = data.get("producto_sustituto_id")
        cantidad_a_sustituir  = data.get("cantidad_a_sustituir")
        empleado_id = session.get('empleado_id')

        if not producto_sustituto_id:
            return _err("Falta el campo: producto_sustituto_id")

        ok, msg = gestor_pedidos.sustituir_item(
            pedido_id,
            detalle_id,
            int(producto_sustituto_id),
            cantidad_a_sustituir=int(cantidad_a_sustituir) if cantidad_a_sustituir is not None else None,
            empleado_id=empleado_id,
        )
        if not ok:
            return _err(msg)
        return jsonify({"ok": True, "mensaje": msg})

    @bp.route("/dashboard/productos")
    @requiere_rol('manager', 'admin')
    def productos_disponibles():
        """Busca productos para sustituciones o ajustes manuales."""
        try:
            q = request.args.get("q", "").strip()
            return _ok(gestor_dashboard.buscar_productos(q))
        except Exception as e:
            logger.error("Error en /dashboard/productos: %s", e)
            return _err("Error interno", 500)
