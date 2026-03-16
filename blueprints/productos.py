import logging
from flask import Blueprint, jsonify, render_template, request
from services import gestor_productos

logger = logging.getLogger(__name__)

blueprint_productos = Blueprint("productos_admin", __name__)


@blueprint_productos.route("/productos-admin")
def index():
    return render_template("productos/index.html")


@blueprint_productos.route("/productos-admin/lista")
def lista():
    try:
        return jsonify(gestor_productos.productos_admin())
    except Exception as e:
        logger.error("Error en /productos-admin/lista: %s", e)
        return jsonify({"error": "Error interno"}), 500


@blueprint_productos.route("/productos-admin/<int:producto_id>/stock", methods=["PATCH"])
def actualizar_stock(producto_id: int):
    data = request.get_json(silent=True) or {}

    # Accepts absolute value {"stock": 10} or delta {"delta": -1}
    if "stock" in data:
        ok, result = gestor_productos.actualizar_stock(producto_id, int(data["stock"]))
    elif "delta" in data:
        ok, result = gestor_productos.ajustar_stock(producto_id, int(data["delta"]))
    else:
        return jsonify({"error": "Falta campo: stock o delta"}), 400

    if not ok:
        return jsonify({"error": result}), 400
    return jsonify({"ok": True, "stock": result})


@blueprint_productos.route("/productos-admin/<int:producto_id>/disponible", methods=["PATCH"])
def toggle_disponible(producto_id: int):
    data = request.get_json(silent=True) or {}
    if "disponible" not in data:
        return jsonify({"error": "Falta campo: disponible"}), 400
    ok, result = gestor_productos.toggle_disponible(producto_id, bool(data["disponible"]))
    if not ok:
        return jsonify({"error": result}), 400
    return jsonify({"ok": True, "disponible": result})


@blueprint_productos.route("/productos-admin/<int:producto_id>/precio", methods=["PATCH"])
def actualizar_precio(producto_id: int):
    data = request.get_json(silent=True) or {}
    if "precio" not in data:
        return jsonify({"error": "Falta campo: precio"}), 400
    try:
        precio = float(data["precio"])
    except (ValueError, TypeError):
        return jsonify({"error": "Precio inválido"}), 400
    ok, result = gestor_productos.actualizar_precio(producto_id, precio)
    if not ok:
        return jsonify({"error": result}), 400
    return jsonify({"ok": True, "precio": result})
