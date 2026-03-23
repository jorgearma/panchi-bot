import logging
import os
from datetime import date
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

blueprint_repartidor = Blueprint("repartidor", __name__)


@blueprint_repartidor.route("/repartidor", strict_slashes=False)
@requiere_rol('repartidor', 'manager', 'admin')
def index():
    repartidor_id = session.get('empleado_id')
    return render_template("repartidor/index.html", repartidor_id=repartidor_id)


@blueprint_repartidor.route("/repartidor/apple-touch-icon.png")
@blueprint_repartidor.route("/repartidor/apple-touch-icon-precomposed.png")
@blueprint_repartidor.route("/repartidor/apple-touch-icon-120x120.png")
@blueprint_repartidor.route("/repartidor/apple-touch-icon-120x120-precomposed.png")
@blueprint_repartidor.route("/repartidor/apple-touch-icon-152x152.png")
@blueprint_repartidor.route("/repartidor/apple-touch-icon-180x180.png")
def apple_touch_icon():
    return send_from_directory(
        os.path.join(current_app.root_path, "static", "repartidor"),
        "icon-180.png",
        mimetype="image/png",
    )


@blueprint_repartidor.route("/repartidor/manifest.json")
@requiere_rol('repartidor', 'manager', 'admin')
def manifest():
    repartidor_id = session.get('empleado_id')
    return Response(
        render_template("repartidor/manifest.json", repartidor_id=repartidor_id),
        mimetype="application/manifest+json",
    )


@blueprint_repartidor.route("/repartidor/sw.js")
def service_worker():
    response = Response(
        render_template("repartidor/sw.js"),
        mimetype="application/javascript",
    )
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Service-Worker-Allowed"] = "/repartidor"
    return response


@blueprint_repartidor.route("/repartidor/mis-pedidos")
@requiere_rol('repartidor', 'manager', 'admin')
def mis_pedidos():
    repartidor_id = session.get('empleado_id')
    try:
        return jsonify(gestor_dashboard.repartos_del_repartidor(repartidor_id))
    except Exception as e:
        logger.error("Error en /repartidor/mis-pedidos: %s", e)
        return jsonify({"error": "Error interno"}), 500


@blueprint_repartidor.route("/repartidor/reparto/<int:reparto_id>/salida", methods=["POST"])
@requiere_rol('repartidor', 'manager', 'admin')
def marcar_salida(reparto_id: int):
    ok, msg, telefono = gestor_dashboard.marcar_salida_reparto(reparto_id)
    if not ok:
        return jsonify({"error": msg}), 400
    _notificar(telefono, "🛵 Tu pedido está en camino. ¡El repartidor ya va hacia tu dirección!")
    return jsonify({"ok": True, "mensaje": msg})


@blueprint_repartidor.route("/repartidor/reparto/<int:reparto_id>/entregar", methods=["POST"])
@requiere_rol('repartidor', 'manager', 'admin')
def marcar_entregado(reparto_id: int):
    ok, msg, telefono = gestor_dashboard.marcar_entregado(reparto_id)
    if not ok:
        return jsonify({"error": msg}), 400
    _notificar(telefono, "🙌 ¡Tu pedido ha sido entregado! Gracias por tu compra. ¡Hasta la próxima!")
    return jsonify({"ok": True, "mensaje": msg})


@blueprint_repartidor.route("/repartidor/reparto/<int:reparto_id>/no-entregar", methods=["POST"])
@requiere_rol('repartidor', 'manager', 'admin')
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
@requiere_rol('repartidor', 'manager', 'admin')
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
@requiere_rol('repartidor', 'manager', 'admin')
def cierre():
    repartidor_id = session.get('empleado_id')
    return render_template("repartidor/cierre.html", repartidor_id=repartidor_id)


@blueprint_repartidor.route("/repartidor/cierre/datos")
@requiere_rol('repartidor', 'manager', 'admin')
def cierre_datos():
    repartidor_id = session.get('empleado_id')
    fecha_str = request.args.get("fecha")
    try:
        fecha = date.fromisoformat(fecha_str) if fecha_str else None
        return jsonify(gestor_dashboard.cierre_caja_repartidor(repartidor_id, fecha))
    except Exception as e:
        logger.error("Error en /repartidor/cierre/datos: %s", e)
        return jsonify({"error": "Error interno"}), 500


@blueprint_repartidor.route("/repartidor/cola")
@requiere_rol('repartidor', 'manager', 'admin')
def cola():
    try:
        lista = gestor_dashboard.repartos_sin_asignar()
        return jsonify({"cola": lista, "total": len(lista)})
    except Exception as e:
        logger.error("Error en /repartidor/cola: %s", e)
        return jsonify({"error": "Error interno"}), 500


@blueprint_repartidor.route("/repartidor/cola/coger/<int:pedido_id>", methods=["POST"])
@requiere_rol('repartidor', 'manager', 'admin')
def coger_reparto(pedido_id: int):
    empleado_id = session.get('empleado_id')
    try:
        ok, motivo = gestor_dashboard.reclamar_reparto(pedido_id, empleado_id)
    except Exception as e:
        logger.error("Error en /repartidor/cola/coger/%s: %s", pedido_id, e)
        return jsonify({"error": "Error interno"}), 500
    if ok:
        return jsonify({"ok": True, "pedido_id": pedido_id})
    if motivo == 'no_encontrado':
        return jsonify({"error": motivo}), 404
    if motivo == 'ya_cogido':
        return jsonify({"error": motivo}), 409
    return jsonify({"error": motivo}), 400
