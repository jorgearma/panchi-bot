import logging
from flask import Blueprint, jsonify

from blueprints.auth import requiere_rol
from managers.gestor_metricas import GestorMetricas

logger = logging.getLogger(__name__)
blueprint_metricas_operacion = Blueprint('metricas_operacion', __name__)
gestor_metricas = GestorMetricas()


def _ok(data):
    """Envuelve la respuesta operativa en un payload estándar de éxito."""
    return jsonify({'ok': True, 'data': data})


def _err(msg, code=400):
    """Devuelve un error uniforme para endpoints operativos."""
    return jsonify({'ok': False, 'error': msg}), code


@blueprint_metricas_operacion.route('/metricas/operacion/resumen')
@requiere_rol('admin', 'manager')
def resumen():
    """Resume la foto operativa actual del negocio."""
    return _ok(gestor_metricas.resumen_operacion())


@blueprint_metricas_operacion.route('/metricas/operacion/asistencia')
@requiere_rol('admin', 'manager')
def asistencia():
    """Devuelve la asistencia del día en curso."""
    return _ok(gestor_metricas.asistencia_hoy())


@blueprint_metricas_operacion.route('/metricas/operacion/colas')
@requiere_rol('admin', 'manager')
def colas():
    """Muestra el estado actual de las colas de trabajo."""
    return _ok(gestor_metricas.colas_detalle())


@blueprint_metricas_operacion.route('/metricas/operacion/pedidos-estado')
@requiere_rol('admin', 'manager')
def pedidos_estado():
    """Agrupa los pedidos según su estado operativo actual."""
    return _ok(gestor_metricas.pedidos_por_estado())


@blueprint_metricas_operacion.route('/metricas/operacion/alertas')
@requiere_rol('admin', 'manager')
def alertas():
    """Devuelve alertas en tiempo real para supervisión."""
    return _ok(gestor_metricas.alertas_tiempo_real())
