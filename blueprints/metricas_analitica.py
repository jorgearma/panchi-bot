import logging
from datetime import date, timedelta

from flask import Blueprint, jsonify, request

from blueprints.auth import requiere_rol
from managers.gestor_metricas import GestorMetricas

logger = logging.getLogger(__name__)
blueprint_metricas_analitica = Blueprint('metricas_analitica', __name__)
gestor_metricas = GestorMetricas()


def _ok(data):
    return jsonify({'ok': True, 'data': data})


def _err(msg, code=400):
    return jsonify({'ok': False, 'error': msg}), code


def _parse_rango():
    """Parse ?desde=&hasta= query params. Default: last 7 days."""
    hasta_str = request.args.get('hasta')
    desde_str = request.args.get('desde')
    hasta = date.fromisoformat(hasta_str) if hasta_str else date.today()
    desde = date.fromisoformat(desde_str) if desde_str else hasta - timedelta(days=6)
    return desde, hasta


@blueprint_metricas_analitica.route('/metricas/analitica/resumen')
@requiere_rol('admin', 'manager')
def resumen():
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.resumen_periodo(desde, hasta))


@blueprint_metricas_analitica.route('/metricas/analitica/pedidos')
@requiere_rol('admin', 'manager')
def pedidos():
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.metricas_pedidos(desde, hasta))


@blueprint_metricas_analitica.route('/metricas/analitica/picking')
@requiere_rol('admin', 'manager')
def picking():
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.metricas_picking(desde, hasta))


@blueprint_metricas_analitica.route('/metricas/analitica/reparto')
@requiere_rol('admin', 'manager')
def reparto():
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.metricas_reparto(desde, hasta))


@blueprint_metricas_analitica.route('/metricas/analitica/empleados')
@requiere_rol('admin', 'manager')
def empleados():
    desde, hasta = _parse_rango()
    rol = request.args.get('rol') or None
    return _ok(gestor_metricas.rendimiento_empleados(desde, hasta, rol=rol))


@blueprint_metricas_analitica.route('/metricas/analitica/empleado/<int:empleado_id>')
@requiere_rol('admin', 'manager')
def ficha_empleado(empleado_id: int):
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.ficha_empleado(empleado_id, desde, hasta))


@blueprint_metricas_analitica.route('/metricas/analitica/comparativa')
@requiere_rol('admin', 'manager')
def comparativa():
    rol = request.args.get('rol')
    if not rol or rol not in ('picker', 'repartidor'):
        return _err("Parámetro 'rol' requerido: picker | repartidor")
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.comparativa_empleados(desde, hasta, rol))


@blueprint_metricas_analitica.route('/metricas/analitica/asistencia')
@requiere_rol('admin', 'manager')
def asistencia():
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.asistencia_periodo(desde, hasta))


@blueprint_metricas_analitica.route('/metricas/analitica/incidencias')
@requiere_rol('admin', 'manager')
def incidencias():
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.metricas_incidencias(desde, hasta))
