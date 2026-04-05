import logging

from flask import Blueprint, jsonify, redirect, render_template, request, session

from blueprints.auth import requiere_rol
from blueprints import _pwa
from container import gestor_dashboard

logger = logging.getLogger(__name__)

blueprint_picker = Blueprint("picker", __name__)


@blueprint_picker.route("/picker/demo")
def demo_view():
    """Entrada directa al modo demo del picker sin autenticación."""
    return _pwa.setup_demo_session('/picker')


@blueprint_picker.route("/picker", strict_slashes=False)
@requiere_rol('picker', 'manager', 'admin', demo_ok=True)
def index():
    """Renderiza la PWA principal del picker autenticado."""
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
    """Sirve el icono compartido de la PWA de picking."""
    return _pwa.icon_response('picker')


@blueprint_picker.route("/picker/manifest.json")
@requiere_rol('picker', 'manager', 'admin', demo_ok=True)
def manifest():
    """Genera el manifest de la PWA con el contexto del picker actual."""
    return _pwa.manifest_response("picker/manifest.json", picker_id=session.get('empleado_id'))


@blueprint_picker.route("/picker/sw.js")
def service_worker():
    """Entrega el service worker sin caché para forzar versiones frescas."""
    return _pwa.sw_response("picker/sw.js", "/picker")


@blueprint_picker.route("/picker/mis-pedidos")
@requiere_rol('picker', 'manager', 'admin', demo_ok=True)
def mis_pedidos():
    """Lista los pickings asignados al picker actual."""
    if session.get('demo_mode'):
        from services.demo_state import DemoState
        return jsonify(DemoState.get_picker(session.get('demo_session_id', 'default')))
    picker_id = session.get('empleado_id')
    try:
        return jsonify(gestor_dashboard.pickings_del_picker(picker_id))
    except Exception as e:
        logger.error("Error en /picker/mis-pedidos: %s", e)
        return jsonify({"error": "Error interno"}), 500


@blueprint_picker.route("/picker/item/<int:item_id>/estado", methods=["POST"])
@requiere_rol('picker', 'manager', 'admin', demo_ok=True)
def actualizar_item(item_id: int):
    """Actualiza el estado de una línea de picking, incluida su sustitución."""
    if session.get('demo_mode'):
        from services.demo_state import DemoState
        data = request.get_json(silent=True) or {}
        ok = DemoState.update_item(
            session.get('demo_session_id', 'default'),
            item_id,
            data.get('estado', ''),
            data.get('cantidad_encontrada'),
            data.get('notas'),
            data.get('producto_sustituto_id'),
        )
        return jsonify({"ok": ok, "mensaje": "Demo: item actualizado"})
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
@requiere_rol('picker', 'manager', 'admin', demo_ok=True)
def buscar_productos():
    """Busca productos para proponer sustituciones durante el picking."""
    if session.get('demo_mode'):
        return jsonify([])
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    try:
        return jsonify(gestor_dashboard.buscar_productos(q))
    except Exception as e:
        logger.error("Error en /picker/buscar-productos: %s", e)
        return jsonify({"error": "Error interno"}), 500


@blueprint_picker.route("/picker/picking/<int:picking_id>/finalizar", methods=["POST"])
@requiere_rol('picker', 'manager', 'admin', demo_ok=True)
def finalizar_picking(picking_id: int):
    """Marca un picking como completado por el picker actual."""
    if session.get('demo_mode'):
        from services.demo_state import DemoState
        DemoState.finalizar_picking(session.get('demo_session_id', 'default'), picking_id)
        return jsonify({"ok": True, "mensaje": "Demo: picking finalizado"})
    picker_id = session.get('empleado_id')
    ok, msg, _ = gestor_dashboard.completar_picking(picking_id, picker_id=picker_id)
    if not ok:
        return jsonify({"error": msg}), 400
    logger.info("[PICKING] Empleado %s finaliza picking %s", picker_id, picking_id)
    return jsonify({"ok": True, "mensaje": msg})


@blueprint_picker.route("/picker/cola")
@requiere_rol('picker', 'manager', 'admin', demo_ok=True)
def cola():
    """Devuelve la cola de pickings aún sin asignar."""
    if session.get('demo_mode'):
        from services.demo_state import DemoState
        return jsonify(DemoState.get_cola_picker(session.get('demo_session_id', 'default')))
    try:
        lista = gestor_dashboard.pickings_sin_asignar()
        return jsonify({"cola": lista, "total": len(lista)})
    except Exception as e:
        logger.error("Error en /picker/cola: %s", e)
        return jsonify({"error": "Error interno"}), 500


@blueprint_picker.route("/picker/cola/coger/<int:picking_id>", methods=["POST"])
@requiere_rol('picker', 'manager', 'admin', demo_ok=True)
def coger_picking(picking_id: int):
    """Permite al picker reclamar un picking pendiente de la cola."""
    if session.get('demo_mode'):
        from services.demo_state import DemoState
        ok = DemoState.reclamar_picking(session.get('demo_session_id', 'default'), picking_id)
        if ok:
            return jsonify({"ok": True, "picking_id": picking_id})
        return jsonify({"error": "no_encontrado"}), 404
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
