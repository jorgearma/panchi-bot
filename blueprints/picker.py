import logging

from flask import Blueprint, jsonify, render_template, request

from services import gestor_dashboard

logger = logging.getLogger(__name__)

blueprint_picker = Blueprint("picker", __name__)


@blueprint_picker.route("/picker")
def index():
    picker_id = request.args.get("id", type=int)
    return render_template("picker/index.html", picker_id=picker_id)


@blueprint_picker.route("/picker/mis-pedidos")
def mis_pedidos():
    picker_id = request.args.get("picker_id", type=int)
    if not picker_id:
        return jsonify({"error": "Falta picker_id"}), 400
    try:
        return jsonify(gestor_dashboard.pickings_del_picker(picker_id))
    except Exception as e:
        logger.error("Error en /picker/mis-pedidos: %s", e)
        return jsonify({"error": "Error interno"}), 500


@blueprint_picker.route("/picker/item/<int:item_id>/estado", methods=["POST"])
def actualizar_item(item_id: int):
    data = request.get_json(silent=True) or {}
    estado = data.get("estado")
    if not estado:
        return jsonify({"error": "Falta campo: estado"}), 400

    ok, msg = gestor_dashboard.actualizar_item_picking(
        item_id=item_id,
        estado=estado,
        cantidad_encontrada=data.get("cantidad_encontrada"),
        notas=data.get("notas"),
    )
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True, "mensaje": msg})


@blueprint_picker.route("/picker/picking/<int:picking_id>/finalizar", methods=["POST"])
def finalizar_picking(picking_id: int):
    ok, msg = gestor_dashboard.completar_picking(picking_id)
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True, "mensaje": msg})
