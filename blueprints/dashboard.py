import logging
from datetime import datetime
from decimal import Decimal

from flask import Blueprint, jsonify, render_template, request

from services import gestor_dashboard
from services.twilio_service import enviar_mensaje_whatsapp

logger = logging.getLogger(__name__)


def _notificar(telefono: str, mensaje: str) -> None:
    if not telefono:
        return
    try:
        enviar_mensaje_whatsapp(mensaje, telefono)
    except Exception as exc:
        logger.error("Error enviando WhatsApp a %s: %s", telefono, exc)

blueprint_dashboard = Blueprint("dashboard", __name__)


def _serial(obj):
    """JSON serializer for datetime and Decimal objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def _ok(data):
    from flask import current_app
    import json
    return current_app.response_class(
        json.dumps(data, default=_serial),
        mimetype="application/json",
    )


def _err(msg, code=400):
    return jsonify({"error": msg}), code


# ---------------------------------------------------------------------------
# HTML page
# ---------------------------------------------------------------------------

@blueprint_dashboard.route("/dashboard")
def index():
    return render_template("dashboard/index.html")


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------

@blueprint_dashboard.route("/dashboard/metricas")
def metricas():
    try:
        return _ok(gestor_dashboard.metricas())
    except Exception as e:
        logger.error("Error en /dashboard/metricas: %s", e)
        return _err("Error interno", 500)


@blueprint_dashboard.route("/dashboard/pedidos-activos")
def pedidos_activos():
    try:
        estado = request.args.get("estado")
        return _ok(gestor_dashboard.pedidos_activos(estado=estado))
    except Exception as e:
        logger.error("Error en /dashboard/pedidos-activos: %s", e)
        return _err("Error interno", 500)


@blueprint_dashboard.route("/dashboard/picking")
def picking():
    try:
        return _ok(gestor_dashboard.picking_activo())
    except Exception as e:
        logger.error("Error en /dashboard/picking: %s", e)
        return _err("Error interno", 500)


@blueprint_dashboard.route("/dashboard/repartidores")
def repartidores():
    try:
        return _ok(gestor_dashboard.repartidores())
    except Exception as e:
        logger.error("Error en /dashboard/repartidores: %s", e)
        return _err("Error interno", 500)


@blueprint_dashboard.route("/dashboard/alertas")
def alertas():
    try:
        return _ok(gestor_dashboard.alertas())
    except Exception as e:
        logger.error("Error en /dashboard/alertas: %s", e)
        return _err("Error interno", 500)


@blueprint_dashboard.route("/dashboard/eventos")
def eventos():
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
        return _ok(gestor_dashboard.eventos(limit=limit))
    except Exception as e:
        logger.error("Error en /dashboard/eventos: %s", e)
        return _err("Error interno", 500)


@blueprint_dashboard.route("/dashboard/mapa")
def mapa():
    try:
        return _ok(gestor_dashboard.mapa())
    except Exception as e:
        logger.error("Error en /dashboard/mapa: %s", e)
        return _err("Error interno", 500)


@blueprint_dashboard.route("/dashboard/empleados")
def empleados():
    try:
        rol = request.args.get("rol")
        return _ok(gestor_dashboard.empleados_disponibles(rol=rol))
    except Exception as e:
        logger.error("Error en /dashboard/empleados: %s", e)
        return _err("Error interno", 500)


# ---------------------------------------------------------------------------
# Write endpoints
# ---------------------------------------------------------------------------

@blueprint_dashboard.route("/dashboard/picking/asignar", methods=["POST"])
def asignar_picker():
    data = request.get_json(silent=True) or {}
    pedido_id = data.get("pedido_id")
    empleado_id = data.get("empleado_id")

    if not pedido_id or not empleado_id:
        return _err("Faltan campos: pedido_id, empleado_id")

    ok, msg = gestor_dashboard.asignar_picker(int(pedido_id), int(empleado_id))
    if not ok:
        return _err(msg)
    return jsonify({"ok": True, "mensaje": msg})


@blueprint_dashboard.route("/dashboard/picking/<int:picking_id>/completar", methods=["POST"])
def completar_picking(picking_id: int):
    ok, msg, telefono = gestor_dashboard.completar_picking(picking_id)
    if not ok:
        return _err(msg)
    _notificar(telefono, "✅ Tu pedido está listo y en camino hacia ti. ¡Ya casi está! 📦")
    return jsonify({"ok": True, "mensaje": msg})


@blueprint_dashboard.route("/dashboard/reparto/asignar", methods=["POST"])
def asignar_repartidor():
    data = request.get_json(silent=True) or {}
    pedido_id = data.get("pedido_id")
    empleado_id = data.get("empleado_id")

    if not pedido_id or not empleado_id:
        return _err("Faltan campos: pedido_id, empleado_id")

    ok, msg = gestor_dashboard.asignar_repartidor(int(pedido_id), int(empleado_id))
    if not ok:
        return _err(msg)
    return jsonify({"ok": True, "mensaje": msg})


@blueprint_dashboard.route("/dashboard/reparto/<int:reparto_id>/salida", methods=["POST"])
def marcar_salida(reparto_id: int):
    ok, msg, telefono = gestor_dashboard.marcar_salida_reparto(reparto_id)
    if not ok:
        return _err(msg)
    _notificar(telefono, "🛵 Tu pedido está en camino. ¡El repartidor ya va hacia tu dirección!")
    return jsonify({"ok": True, "mensaje": msg})


@blueprint_dashboard.route("/dashboard/reparto/<int:reparto_id>/entregar", methods=["POST"])
def marcar_entregado(reparto_id: int):
    ok, msg, telefono = gestor_dashboard.marcar_entregado(reparto_id)
    if not ok:
        return _err(msg)
    _notificar(telefono, "🙌 ¡Tu pedido ha sido entregado! Gracias por tu compra. ¡Hasta la próxima!")
    return jsonify({"ok": True, "mensaje": msg})
