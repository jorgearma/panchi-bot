import logging
import os
from threading import Thread

from flask import Blueprint, Response, current_app, jsonify, render_template, request, send_from_directory, session

from blueprints.auth import requiere_rol
from services import gestor_dashboard
from services.whatsapp_service import enviar_mensaje_whatsapp

logger = logging.getLogger(__name__)


def _notificar(telefono: str, mensaje: str) -> None:
    if not telefono:
        return
    def _enviar():
        try:
            enviar_mensaje_whatsapp(mensaje, telefono)
        except Exception as exc:
            logger.error("Error enviando WhatsApp a %s: %s", telefono, exc)
    Thread(target=_enviar, daemon=True).start()

blueprint_picker = Blueprint("picker", __name__)


@blueprint_picker.route("/picker", strict_slashes=False)
@requiere_rol('picker', 'manager', 'admin')
def index():
    picker_id = session.get('empleado_id')
    return render_template("picker/index.html", picker_id=picker_id)


@blueprint_picker.route("/apple-touch-icon.png")
@blueprint_picker.route("/apple-touch-icon-precomposed.png")
@blueprint_picker.route("/apple-touch-icon-120x120.png")
@blueprint_picker.route("/apple-touch-icon-120x120-precomposed.png")
@blueprint_picker.route("/apple-touch-icon-152x152.png")
@blueprint_picker.route("/apple-touch-icon-180x180.png")
@blueprint_picker.route("/favicon.ico")
def apple_touch_icon():
    return send_from_directory(
        os.path.join(current_app.root_path, "static", "picker"),
        "icon-180.png",
        mimetype="image/png",
    )


@blueprint_picker.route("/picker/manifest.json")
@requiere_rol('picker', 'manager', 'admin')
def manifest():
    picker_id = session.get('empleado_id')
    return Response(
        render_template("picker/manifest.json", picker_id=picker_id),
        mimetype="application/manifest+json",
    )


@blueprint_picker.route("/picker/sw.js")
def service_worker():
    response = Response(
        render_template("picker/sw.js"),
        mimetype="application/javascript",
    )
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Service-Worker-Allowed"] = "/picker"
    return response


@blueprint_picker.route("/picker/mis-pedidos")
@requiere_rol('picker', 'manager', 'admin')
def mis_pedidos():
    picker_id = session.get('empleado_id')
    try:
        return jsonify(gestor_dashboard.pickings_del_picker(picker_id))
    except Exception as e:
        logger.error("Error en /picker/mis-pedidos: %s", e)
        return jsonify({"error": "Error interno"}), 500


@blueprint_picker.route("/picker/item/<int:item_id>/estado", methods=["POST"])
@requiere_rol('picker', 'manager', 'admin')
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

    picker_id = session.get('empleado_id')
    ok, msg = gestor_dashboard.actualizar_item_picking(
        item_id=item_id,
        estado=estado,
        cantidad_encontrada=data.get("cantidad_encontrada"),
        notas=data.get("notas"),
        producto_sustituto_id=producto_sustituto_id,
        picker_id=picker_id,
    )
    if not ok:
        return jsonify({"error": msg}), 400
    return jsonify({"ok": True, "mensaje": msg})


@blueprint_picker.route("/picker/buscar-productos")
@requiere_rol('picker', 'manager', 'admin')
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
@requiere_rol('picker', 'manager', 'admin')
def finalizar_picking(picking_id: int):
    picker_id = session.get('empleado_id')
    ok, msg, _ = gestor_dashboard.completar_picking(picking_id, picker_id=picker_id)
    if not ok:
        return jsonify({"error": msg}), 400
    logger.info("[PICKING] Empleado %s finaliza picking %s", picker_id, picking_id)
    return jsonify({"ok": True, "mensaje": msg})


@blueprint_picker.route("/picker/cola")
@requiere_rol('picker', 'manager', 'admin')
def cola():
    try:
        lista = gestor_dashboard.pickings_sin_asignar()
        return jsonify({"cola": lista, "total": len(lista)})
    except Exception as e:
        logger.error("Error en /picker/cola: %s", e)
        return jsonify({"error": "Error interno"}), 500


@blueprint_picker.route("/picker/cola/coger/<int:picking_id>", methods=["POST"])
@requiere_rol('picker', 'manager', 'admin')
def coger_picking(picking_id: int):
    empleado_id = session.get('empleado_id')
    try:
        ok, motivo = gestor_dashboard.reclamar_picking(picking_id, empleado_id)
    except Exception as e:
        logger.error("Error en /picker/cola/coger/%s: %s", picking_id, e)
        return jsonify({"error": "Error interno"}), 500
    if ok:
        logger.info("[PICKING] Empleado %s coge picking %s", empleado_id, picking_id)
        return jsonify({"ok": True, "picking_id": picking_id})
    if motivo == 'no_encontrado':
        return jsonify({"error": motivo}), 404
    if motivo == 'ya_cogido':
        return jsonify({"error": motivo}), 409
    return jsonify({"error": motivo}), 400
