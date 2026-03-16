import logging

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

    producto_sustituto_id = data.get("producto_sustituto_id")
    if producto_sustituto_id is not None:
        try:
            producto_sustituto_id = int(producto_sustituto_id)
        except (TypeError, ValueError):
            return jsonify({"error": "producto_sustituto_id inválido"}), 400

    ok, msg = gestor_dashboard.actualizar_item_picking(
        item_id=item_id,
        estado=estado,
        cantidad_encontrada=data.get("cantidad_encontrada"),
        notas=data.get("notas"),
        producto_sustituto_id=producto_sustituto_id,
    )
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True, "mensaje": msg})


@blueprint_picker.route("/picker/buscar-productos")
def buscar_productos():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    try:
        return jsonify(gestor_dashboard.buscar_productos(q))
    except Exception as e:
        logger.error("Error en /picker/buscar-productos: %s", e)
        return jsonify({"error": "Error interno"}), 500


@blueprint_picker.route("/picker/picking/<int:picking_id>/finalizar", methods=["POST"])
def finalizar_picking(picking_id: int):
    ok, msg, telefono = gestor_dashboard.completar_picking(picking_id)
    if not ok:
        return jsonify({"error": msg}), 400
    _notificar(telefono, "✅ Tu pedido está listo y en camino hacia ti. ¡Ya casi está! 📦")
    return jsonify({"ok": True, "mensaje": msg})
