"""Blueprint para el modo restaurant: PWA de cocina en /cocina."""
import logging

from flask import Blueprint, Response, jsonify, render_template, request, session

from blueprints.auth import requiere_rol
from container import gestor_dashboard

logger = logging.getLogger(__name__)

blueprint_cocina = Blueprint("cocina", __name__)


@blueprint_cocina.route("/cocina", strict_slashes=False)
@requiere_rol('picker', 'manager', 'admin')
def index():
    """Renderiza la PWA de cocina para el empleado autenticado."""
    cocinero_id = session.get('empleado_id')
    return render_template("cocina/index.html", cocinero_id=cocinero_id)


@blueprint_cocina.route("/cocina/manifest.json")
@requiere_rol('picker', 'manager', 'admin')
def manifest():
    cocinero_id = session.get('empleado_id')
    return Response(
        render_template("cocina/manifest.json", cocinero_id=cocinero_id),
        mimetype="application/manifest+json",
    )


@blueprint_cocina.route("/cocina/sw.js")
def service_worker():
    response = Response(
        render_template("cocina/sw.js"),
        mimetype="application/javascript",
    )
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Service-Worker-Allowed"] = "/cocina"
    return response


@blueprint_cocina.route("/cocina/mis-pedidos")
@requiere_rol('picker', 'manager', 'admin')
def mis_pedidos():
    """Lista las preparaciones asignadas al cocinero actual."""
    cocinero_id = session.get('empleado_id')
    try:
        return jsonify(gestor_dashboard.pickings_del_picker(cocinero_id))
    except Exception as e:
        logger.error("Error en /cocina/mis-pedidos: %s", e)
        return jsonify({"error": "Error interno"}), 500


@blueprint_cocina.route("/cocina/cola")
@requiere_rol('picker', 'manager', 'admin')
def cola():
    """Devuelve la cola de preparaciones sin asignar."""
    try:
        lista = gestor_dashboard.pickings_sin_asignar()
        return jsonify({"cola": lista, "total": len(lista)})
    except Exception as e:
        logger.error("Error en /cocina/cola: %s", e)
        return jsonify({"error": "Error interno"}), 500


@blueprint_cocina.route("/cocina/cola/coger/<int:picking_id>", methods=["POST"])
@requiere_rol('picker', 'manager', 'admin')
def coger_preparacion(picking_id: int):
    """Permite al cocinero reclamar una preparación pendiente de la cola."""
    cocinero_id = session.get('empleado_id')
    try:
        ok, motivo = gestor_dashboard.reclamar_picking(picking_id, cocinero_id)
    except Exception as e:
        logger.error("Error en /cocina/cola/coger/%s: %s", picking_id, e)
        return jsonify({"error": "Error interno"}), 500
    if ok:
        logger.info("[COCINA] Empleado %s coge preparación %s", cocinero_id, picking_id)
        return jsonify({"ok": True, "picking_id": picking_id})
    if motivo == 'no_encontrado':
        return jsonify({"error": motivo}), 404
    if motivo == 'ya_cogido':
        return jsonify({"error": motivo}), 409
    return jsonify({"error": motivo}), 400


@blueprint_cocina.route("/cocina/preparacion/<int:picking_id>/finalizar", methods=["POST"])
@requiere_rol('picker', 'manager', 'admin')
def finalizar_preparacion(picking_id: int):
    """Marca una preparación como lista (sin validación de items en restaurant mode)."""
    cocinero_id = session.get('empleado_id')
    ok, msg, _ = gestor_dashboard.completar_picking(picking_id, picker_id=cocinero_id)
    if not ok:
        return jsonify({"error": msg}), 400
    logger.info("[COCINA] Empleado %s finaliza preparación %s", cocinero_id, picking_id)
    return jsonify({"ok": True, "mensaje": msg})
