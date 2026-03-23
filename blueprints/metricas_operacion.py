import logging
from flask import Blueprint, jsonify

from blueprints.auth import requiere_rol
from managers.gestor_metricas import GestorMetricas

logger = logging.getLogger(__name__)
blueprint_metricas_operacion = Blueprint('metricas_operacion', __name__)
gestor_metricas = GestorMetricas()


def _ok(data):
    return jsonify({'ok': True, 'data': data})


def _err(msg, code=400):
    return jsonify({'ok': False, 'error': msg}), code


@blueprint_metricas_operacion.route('/metricas/operacion/resumen')
@requiere_rol('admin', 'manager')
def resumen():
    return _ok(gestor_metricas.resumen_operacion())


@blueprint_metricas_operacion.route('/metricas/operacion/asistencia')
@requiere_rol('admin', 'manager')
def asistencia():
    return _ok(gestor_metricas.asistencia_hoy())


@blueprint_metricas_operacion.route('/metricas/operacion/colas')
@requiere_rol('admin', 'manager')
def colas():
    return _ok(gestor_metricas.colas_detalle())


@blueprint_metricas_operacion.route('/metricas/operacion/pedidos-estado')
@requiere_rol('admin', 'manager')
def pedidos_estado():
    return _ok(gestor_metricas.pedidos_por_estado())


@blueprint_metricas_operacion.route('/metricas/operacion/alertas')
@requiere_rol('admin', 'manager')
def alertas():
    return _ok(gestor_metricas.alertas_tiempo_real())
