import logging
from datetime import datetime
from decimal import Decimal

from flask import Blueprint, jsonify, render_template, request

from services import gestor_dashboard, gestor_pedidos
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


@blueprint_dashboard.route("/dashboard/monitor")
def monitor():
    return render_template("dashboard/monitor.html")


@blueprint_dashboard.route("/dashboard/monitor/datos")
def monitor_datos():
    try:
        monitor_data = gestor_dashboard.monitor_empleados()
        metricas_data = gestor_dashboard.metricas()
        alertas_data = gestor_dashboard.alertas()
        eventos_data = gestor_dashboard.eventos(limit=25)
        return _ok({
            **monitor_data,
            "metricas": metricas_data,
            "alertas": alertas_data,
            "eventos": eventos_data,
        })
    except Exception as e:
        logger.error("Error en /dashboard/monitor/datos: %s", e)
        return _err("Error interno", 500)


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


@blueprint_dashboard.route("/dashboard/picking/<int:picking_id>/reasignar", methods=["POST"])
def reasignar_picker(picking_id: int):
    data = request.get_json(silent=True) or {}
    empleado_id_raw = data.get("empleado_id")
    nuevo_empleado_id = int(empleado_id_raw) if empleado_id_raw is not None else None

    ok, msg = gestor_dashboard.reasignar_picker(picking_id, nuevo_empleado_id)
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


# ---------------------------------------------------------------------------
# Order management: cancel, remove item, substitute item
# ---------------------------------------------------------------------------

_MOTIVOS_LABEL = {
    'cliente_cancelo':      'El cliente canceló',
    'falta_stock':          'Falta de stock',
    'direccion_incorrecta': 'Dirección incorrecta',
    'cliente_no_responde':  'Cliente no responde',
    'pedido_duplicado':     'Pedido duplicado',
    'otro':                 'Otro',
}


@blueprint_dashboard.route("/dashboard/pedido/<int:pedido_id>/cancelar", methods=["POST"])
def cancelar_pedido(pedido_id: int):
    data = request.get_json(silent=True) or {}
    motivo = data.get("motivo")
    empleado_id = data.get("empleado_id")

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


@blueprint_dashboard.route("/dashboard/pedido/<int:pedido_id>/item/<int:detalle_id>/eliminar", methods=["POST"])
def eliminar_item(pedido_id: int, detalle_id: int):
    data = request.get_json(silent=True) or {}
    empleado_id = data.get("empleado_id")

    ok, msg = gestor_pedidos.eliminar_item(pedido_id, detalle_id, empleado_id)
    if not ok:
        return _err(msg)
    return jsonify({"ok": True, "mensaje": msg})


@blueprint_dashboard.route("/dashboard/pedido/<int:pedido_id>/item/<int:detalle_id>/sustituir", methods=["POST"])
def sustituir_item(pedido_id: int, detalle_id: int):
    data = request.get_json(silent=True) or {}
    producto_sustituto_id = data.get("producto_sustituto_id")
    cantidad_a_sustituir = data.get("cantidad_a_sustituir")
    empleado_id = data.get("empleado_id")

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


@blueprint_dashboard.route("/dashboard/productos")
def productos_disponibles():
    try:
        q = request.args.get("q", "").strip()
        return _ok(gestor_dashboard.buscar_productos(q))
    except Exception as e:
        logger.error("Error en /dashboard/productos: %s", e)
        return _err("Error interno", 500)
