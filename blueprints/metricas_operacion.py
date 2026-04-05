import logging

from flask import Blueprint

from blueprints.auth import requiere_rol
from blueprints._metricas_common import _ok, _err
from container import gestor_metricas

logger = logging.getLogger(__name__)
blueprint_metricas_operacion = Blueprint('metricas_operacion', __name__)


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
