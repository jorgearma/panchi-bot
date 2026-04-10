import logging
from datetime import date

from flask import Blueprint, jsonify, redirect, render_template, request, session

from blueprints.auth import requiere_rol
from blueprints import _pwa
from container import gestor_dashboard

logger = logging.getLogger(__name__)

blueprint_repartidor = Blueprint("repartidor", __name__)


@blueprint_repartidor.route("/repartidor/demo")
def demo_view():
    """Entrada directa al modo demo del repartidor sin autenticación."""
    return _pwa.setup_demo_session('/repartidor')


@blueprint_repartidor.route("/repartidor", strict_slashes=False)
@requiere_rol('repartidor', 'manager', 'admin', demo_ok=True)
def index():
    """Renderiza la PWA principal del repartidor autenticado."""
    repartidor_id = session.get('empleado_id')
    return render_template("repartidor/index.html", repartidor_id=repartidor_id)


@blueprint_repartidor.route("/repartidor/apple-touch-icon.png")
@blueprint_repartidor.route("/repartidor/apple-touch-icon-precomposed.png")
@blueprint_repartidor.route("/repartidor/apple-touch-icon-120x120.png")
@blueprint_repartidor.route("/repartidor/apple-touch-icon-120x120-precomposed.png")
@blueprint_repartidor.route("/repartidor/apple-touch-icon-152x152.png")
@blueprint_repartidor.route("/repartidor/apple-touch-icon-180x180.png")
def apple_touch_icon():
    """Sirve el icono compartido de la PWA de reparto."""
    return _pwa.icon_response('repartidor')


@blueprint_repartidor.route("/repartidor/manifest.json")
@requiere_rol('repartidor', 'manager', 'admin', demo_ok=True)
def manifest():
    """Genera el manifest de la PWA con el contexto del repartidor actual."""
    return _pwa.manifest_response("repartidor/manifest.json", repartidor_id=session.get('empleado_id'))


@blueprint_repartidor.route("/repartidor/sw.js")
def service_worker():
    """Entrega el service worker sin caché para forzar versiones frescas."""
    return _pwa.sw_response("repartidor/sw.js", "/repartidor")


@blueprint_repartidor.route("/repartidor/mis-pedidos")
@requiere_rol('repartidor', 'manager', 'admin', demo_ok=True)
def mis_pedidos():
    """Lista los repartos asignados al repartidor actual."""
    if session.get('demo_mode'):
        from services.demo_state import DemoState
        return jsonify(DemoState.get_repartidor(session.get('demo_session_id', 'default')))
    repartidor_id = session.get('empleado_id')
    try:
        return jsonify(gestor_dashboard.repartos_del_repartidor(repartidor_id))
    except Exception as e:
        logger.error("Error en /repartidor/mis-pedidos: %s", e)
        return jsonify({"error": "Error interno"}), 500


@blueprint_repartidor.route("/repartidor/reparto/<int:reparto_id>/salida", methods=["POST"])
@requiere_rol('repartidor', 'manager', 'admin', demo_ok=True)
def marcar_salida(reparto_id: int):
    """Marca un reparto como salido a entrega."""
    if session.get('demo_mode'):
        from services.demo_state import DemoState
        DemoState.marcar_salida_reparto(session.get('demo_session_id', 'default'), reparto_id)
        return jsonify({"ok": True, "mensaje": "Demo: salida marcada"})
    empleado_id = session.get('empleado_id')
    ok, msg = gestor_dashboard.marcar_salida_reparto(reparto_id, repartidor_id=empleado_id)
    if not ok:
        return jsonify({"error": msg}), 400
    logger.info("[REPARTO] Empleado %s sale a entregar reparto %s", empleado_id, reparto_id)
    return jsonify({"ok": True, "mensaje": msg})


@blueprint_repartidor.route("/repartidor/reparto/<int:reparto_id>/entregar", methods=["POST"])
@requiere_rol('repartidor', 'manager', 'admin', demo_ok=True)
def marcar_entregado(reparto_id: int):
    """Marca un reparto como entregado al cliente."""
    if session.get('demo_mode'):
        from services.demo_state import DemoState
        DemoState.marcar_entregado(session.get('demo_session_id', 'default'), reparto_id)
        return jsonify({"ok": True, "mensaje": "Demo: entregado"})
    empleado_id = session.get('empleado_id')
    ok, msg = gestor_dashboard.marcar_entregado(reparto_id, repartidor_id=empleado_id)
    if not ok:
        return jsonify({"error": msg}), 400
    logger.info("[REPARTO] Empleado %s entrega reparto %s", empleado_id, reparto_id)
    return jsonify({"ok": True, "mensaje": msg})


@blueprint_repartidor.route("/repartidor/reparto/<int:reparto_id>/no-entregar", methods=["POST"])
@requiere_rol('repartidor', 'manager', 'admin', demo_ok=True)
def marcar_no_entregado(reparto_id: int):
    """Registra una incidencia de no entrega y avisa al cliente."""
    if session.get('demo_mode'):
        from services.demo_state import DemoState
        data = request.get_json(silent=True) or {}
        DemoState.marcar_no_entregado(session.get('demo_session_id', 'default'), reparto_id, data.get('motivo', ''))
        return jsonify({"ok": True, "mensaje": "Demo: no entregado registrado"})
    data = request.get_json(silent=True) or {}
    motivo = data.get("motivo", "").strip()
    if not motivo:
        return jsonify({"error": "Indica el motivo de no entrega"}), 400
    empleado_id = session.get('empleado_id')
    ok, msg = gestor_dashboard.marcar_no_entregado(reparto_id, motivo, repartidor_id=empleado_id)
    if not ok:
        return jsonify({"error": msg}), 400
    logger.info("[REPARTO] Empleado %s marca no entregado reparto %s — motivo: %s", empleado_id, reparto_id, motivo)
    return jsonify({"ok": True, "mensaje": msg})


@blueprint_repartidor.route("/repartidor/reparto/<int:reparto_id>/registrar-cobro", methods=["POST"])
@requiere_rol('repartidor', 'manager', 'admin', demo_ok=True)
def registrar_cobro(reparto_id: int):
    """Guarda el desglose del cobro realizado durante la entrega."""
    if session.get('demo_mode'):
        return jsonify({"ok": True})
    data = request.get_json(silent=True) or {}
    metodo = data.get("metodo_cobro", "").strip()
    try:
        importe_cobrado  = float(data.get("importe_cobrado") or 0)
        cambio_devuelto  = float(data["cambio_devuelto"])  if data.get("cambio_devuelto")  is not None else None
        importe_efectivo = float(data["importe_efectivo"]) if data.get("importe_efectivo") is not None else None
        importe_tarjeta  = float(data["importe_tarjeta"])  if data.get("importe_tarjeta")  is not None else None
    except (TypeError, ValueError):
        return jsonify({"error": "Importes inválidos"}), 400

    empleado_id = session.get('empleado_id')
    ok, msg = gestor_dashboard.registrar_cobro(
        reparto_id, metodo, importe_cobrado,
        cambio_devuelto, importe_efectivo, importe_tarjeta,
        repartidor_id=empleado_id,
    )
    if not ok:
        return jsonify({"error": msg}), 400
    logger.info("[COBRO] Empleado %s registra cobro reparto %s — método: %s, importe: %.2f", empleado_id, reparto_id, metodo, importe_cobrado)
    return jsonify({"ok": True})


@blueprint_repartidor.route("/repartidor/cierre")
@requiere_rol('repartidor', 'manager', 'admin', demo_ok=True)
def cierre():
    """Renderiza la pantalla de cierre de caja del repartidor."""
    repartidor_id = session.get('empleado_id')
    return render_template("repartidor/cierre.html", repartidor_id=repartidor_id)


@blueprint_repartidor.route("/repartidor/cierre/datos")
@requiere_rol('repartidor', 'manager', 'admin', demo_ok=True)
def cierre_datos():
    """Devuelve el resumen de caja del repartidor para una fecha dada."""
    if session.get('demo_mode'):
        return jsonify({"ok": True, "datos": []})
    repartidor_id = session.get('empleado_id')
    fecha_str = request.args.get("fecha")
    try:
        fecha = date.fromisoformat(fecha_str) if fecha_str else None
        return jsonify(gestor_dashboard.cierre_caja_repartidor(repartidor_id, fecha))
    except Exception as e:
        logger.error("Error en /repartidor/cierre/datos: %s", e)
        return jsonify({"error": "Error interno"}), 500


@blueprint_repartidor.route("/repartidor/cola")
@requiere_rol('repartidor', 'manager', 'admin', demo_ok=True)
def cola():
    """Devuelve la cola de repartos todavía sin asignar."""
    if session.get('demo_mode'):
        from services.demo_state import DemoState
        return jsonify(DemoState.get_cola_repartidor(session.get('demo_session_id', 'default')))
    try:
        lista = gestor_dashboard.repartos_sin_asignar()
        return jsonify({"cola": lista, "total": len(lista)})
    except Exception as e:
        logger.error("Error en /repartidor/cola: %s", e)
        return jsonify({"error": "Error interno"}), 500


@blueprint_repartidor.route("/repartidor/cola/coger/<int:pedido_id>", methods=["POST"])
@requiere_rol('repartidor', 'manager', 'admin', demo_ok=True)
def coger_reparto(pedido_id: int):
    """Permite al repartidor reclamar un pedido pendiente de reparto."""
    if session.get('demo_mode'):
        from services.demo_state import DemoState
        ok = DemoState.reclamar_reparto_by_pedido(session.get('demo_session_id', 'default'), pedido_id)
        if ok:
            return jsonify({"ok": True, "pedido_id": pedido_id})
        return jsonify({"error": "no_encontrado"}), 404
    empleado_id = session.get('empleado_id')
    try:
        ok, motivo = gestor_dashboard.reclamar_reparto(pedido_id, empleado_id)
    except Exception as e:
        logger.error("Error en /repartidor/cola/coger/%s: %s", pedido_id, e)
        return jsonify({"error": "Error interno"}), 500
    if ok:
        logger.info("[REPARTO] Empleado %s coge reparto pedido %s", empleado_id, pedido_id)
        return jsonify({"ok": True, "pedido_id": pedido_id})
    if motivo == 'no_encontrado':
        return jsonify({"error": motivo}), 404
    if motivo == 'ya_cogido':
        return jsonify({"error": motivo}), 409
    return jsonify({"error": motivo}), 400
