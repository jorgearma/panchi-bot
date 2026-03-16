import logging
from datetime import date

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

blueprint_repartidor = Blueprint("repartidor", __name__)


@blueprint_repartidor.route("/repartidor")
def index():
    repartidor_id = request.args.get("id", type=int)
    return render_template("repartidor/index.html", repartidor_id=repartidor_id)


@blueprint_repartidor.route("/repartidor/mis-pedidos")
def mis_pedidos():
    repartidor_id = request.args.get("repartidor_id", type=int)
    if not repartidor_id:
        return jsonify({"error": "Falta repartidor_id"}), 400
    try:
        return jsonify(gestor_dashboard.repartos_del_repartidor(repartidor_id))
    except Exception as e:
        logger.error("Error en /repartidor/mis-pedidos: %s", e)
        return jsonify({"error": "Error interno"}), 500


@blueprint_repartidor.route("/repartidor/reparto/<int:reparto_id>/salida", methods=["POST"])
def marcar_salida(reparto_id: int):
    ok, msg, telefono = gestor_dashboard.marcar_salida_reparto(reparto_id)
    if not ok:
        return jsonify({"error": msg}), 400
    _notificar(telefono, "🛵 Tu pedido está en camino. ¡El repartidor ya va hacia tu dirección!")
    return jsonify({"ok": True, "mensaje": msg})


@blueprint_repartidor.route("/repartidor/reparto/<int:reparto_id>/entregar", methods=["POST"])
def marcar_entregado(reparto_id: int):
    ok, msg, telefono = gestor_dashboard.marcar_entregado(reparto_id)
    if not ok:
        return jsonify({"error": msg}), 400
    _notificar(telefono, "🙌 ¡Tu pedido ha sido entregado! Gracias por tu compra. ¡Hasta la próxima!")
    return jsonify({"ok": True, "mensaje": msg})


@blueprint_repartidor.route("/repartidor/reparto/<int:reparto_id>/no-entregar", methods=["POST"])
def marcar_no_entregado(reparto_id: int):
    data = request.get_json(silent=True) or {}
    motivo = data.get("motivo", "").strip()
    if not motivo:
        return jsonify({"error": "Indica el motivo de no entrega"}), 400
    ok, msg, telefono = gestor_dashboard.marcar_no_entregado(reparto_id, motivo)
    if not ok:
        return jsonify({"error": msg}), 400
    _notificar(telefono, "⚠️ Lo sentimos, no hemos podido entregar tu pedido. Nuestro equipo se pondrá en contacto contigo muy pronto.")
    return jsonify({"ok": True, "mensaje": msg})


@blueprint_repartidor.route("/repartidor/reparto/<int:reparto_id>/registrar-cobro", methods=["POST"])
def registrar_cobro(reparto_id: int):
    data = request.get_json(silent=True) or {}
    metodo = data.get("metodo_cobro", "").strip()
    try:
        importe_cobrado  = float(data.get("importe_cobrado") or 0)
        cambio_devuelto  = float(data["cambio_devuelto"])  if data.get("cambio_devuelto")  is not None else None
        importe_efectivo = float(data["importe_efectivo"]) if data.get("importe_efectivo") is not None else None
        importe_tarjeta  = float(data["importe_tarjeta"])  if data.get("importe_tarjeta")  is not None else None
    except (TypeError, ValueError):
        return jsonify({"error": "Importes inválidos"}), 400

    ok, msg = gestor_dashboard.registrar_cobro(
        reparto_id, metodo, importe_cobrado,
        cambio_devuelto, importe_efectivo, importe_tarjeta,
    )
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True})


@blueprint_repartidor.route("/repartidor/cierre")
def cierre():
    repartidor_id = request.args.get("id", type=int)
    if not repartidor_id:
        return "Falta el parámetro id", 400
    return render_template("repartidor/cierre.html", repartidor_id=repartidor_id)


@blueprint_repartidor.route("/repartidor/cierre/datos")
def cierre_datos():
    repartidor_id = request.args.get("repartidor_id", type=int)
    fecha_str = request.args.get("fecha")
    if not repartidor_id:
        return jsonify({"error": "Falta repartidor_id"}), 400
    try:
        fecha = date.fromisoformat(fecha_str) if fecha_str else None
        return jsonify(gestor_dashboard.cierre_caja_repartidor(repartidor_id, fecha))
    except Exception as e:
        logger.error("Error en /repartidor/cierre/datos: %s", e)
        return jsonify({"error": "Error interno"}), 500
