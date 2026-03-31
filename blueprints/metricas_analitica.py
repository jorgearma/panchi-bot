import logging
from datetime import date, timedelta

from flask import Blueprint, jsonify, request

from blueprints.auth import requiere_rol
from managers.gestor_metricas import GestorMetricas

logger = logging.getLogger(__name__)
blueprint_metricas_analitica = Blueprint('metricas_analitica', __name__)
gestor_metricas = GestorMetricas()


def _ok(data):
    """Envuelve la respuesta analítica en un payload estándar de éxito."""
    return jsonify({'ok': True, 'data': data})


def _err(msg, code=400):
    """Devuelve un error uniforme para endpoints analíticos."""
    return jsonify({'ok': False, 'error': msg}), code


def _parse_rango():
    """Lee el rango solicitado y, si falta, usa los últimos siete días."""
    hasta_str = request.args.get('hasta')
    desde_str = request.args.get('desde')
    hasta = date.fromisoformat(hasta_str) if hasta_str else date.today()
    desde = date.fromisoformat(desde_str) if desde_str else hasta - timedelta(days=6)
    return desde, hasta


@blueprint_metricas_analitica.route('/metricas/analitica/resumen')
@requiere_rol('admin', 'manager')
def resumen():
    """Resume el rendimiento global del periodo solicitado."""
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.resumen_periodo(desde, hasta))


@blueprint_metricas_analitica.route('/metricas/analitica/pedidos')
@requiere_rol('admin', 'manager')
def pedidos():
    """Devuelve métricas analíticas centradas en pedidos."""
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.metricas_pedidos(desde, hasta))


@blueprint_metricas_analitica.route('/metricas/analitica/picking')
@requiere_rol('admin', 'manager')
def picking():
    """Devuelve métricas analíticas del proceso de picking."""
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.metricas_picking(desde, hasta))


@blueprint_metricas_analitica.route('/metricas/analitica/reparto')
@requiere_rol('admin', 'manager')
def reparto():
    """Devuelve métricas analíticas del proceso de reparto."""
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.metricas_reparto(desde, hasta))


@blueprint_metricas_analitica.route('/metricas/analitica/empleados')
@requiere_rol('admin', 'manager')
def empleados():
    """Lista el rendimiento de empleados, opcionalmente filtrado por rol."""
    desde, hasta = _parse_rango()
    rol = request.args.get('rol') or None
    return _ok(gestor_metricas.rendimiento_empleados(desde, hasta, rol=rol))


@blueprint_metricas_analitica.route('/metricas/analitica/empleado/<int:empleado_id>')
@requiere_rol('admin', 'manager')
def ficha_empleado(empleado_id: int):
    """Devuelve la ficha analítica detallada de un empleado."""
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.ficha_empleado(empleado_id, desde, hasta))


@blueprint_metricas_analitica.route('/metricas/analitica/comparativa')
@requiere_rol('admin', 'manager')
def comparativa():
    """Compara el rendimiento entre empleados de un mismo rol operativo."""
    rol = request.args.get('rol')
    if not rol or rol not in ('picker', 'repartidor'):
        return _err("Parámetro 'rol' requerido: picker | repartidor")
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.comparativa_empleados(desde, hasta, rol))


@blueprint_metricas_analitica.route('/metricas/analitica/asistencia')
@requiere_rol('admin', 'manager')
def asistencia():
    """Devuelve métricas históricas de asistencia para el periodo."""
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.asistencia_periodo(desde, hasta))


@blueprint_metricas_analitica.route('/metricas/analitica/incidencias')
@requiere_rol('admin', 'manager')
def incidencias():
    """Resume incidencias y anomalías detectadas en el periodo."""
    desde, hasta = _parse_rango()
    return _ok(gestor_metricas.metricas_incidencias(desde, hasta))
