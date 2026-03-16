import logging

from flask import Blueprint, jsonify, render_template, request

from services import gestor_dashboard

logger = logging.getLogger(__name__)

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
    ok, msg = gestor_dashboard.marcar_salida_reparto(reparto_id)
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True, "mensaje": msg})


@blueprint_repartidor.route("/repartidor/reparto/<int:reparto_id>/entregar", methods=["POST"])
def marcar_entregado(reparto_id: int):
    ok, msg = gestor_dashboard.marcar_entregado(reparto_id)
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True, "mensaje": msg})


@blueprint_repartidor.route("/repartidor/reparto/<int:reparto_id>/no-entregar", methods=["POST"])
def marcar_no_entregado(reparto_id: int):
    data = request.get_json(silent=True) or {}
    motivo = data.get("motivo", "").strip()
    if not motivo:
        return jsonify({"error": "Indica el motivo de no entrega"}), 400
    ok, msg = gestor_dashboard.marcar_no_entregado(reparto_id, motivo)
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True, "mensaje": msg})
