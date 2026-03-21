import logging

from flask import Blueprint, jsonify, render_template, request, session

from blueprints.auth import requiere_rol
from services import gestor_empleado

logger = logging.getLogger(__name__)

blueprint_empleado = Blueprint('empleado', __name__)

_ROLES_HUB = ('picker', 'repartidor', 'manager', 'admin')


@blueprint_empleado.route('/empleado', strict_slashes=False)
@requiere_rol(*_ROLES_HUB)
def index():
    empleado_id = session.get('empleado_id')
    rol         = session.get('rol')
    return render_template('empleado/index.html', empleado_id=empleado_id, rol=rol)


@blueprint_empleado.route('/empleado/perfil')
@requiere_rol(*_ROLES_HUB)
def perfil():
    empleado_id = session.get('empleado_id')
    try:
        datos = gestor_empleado.perfil(empleado_id)
        if not datos:
            return jsonify({'error': 'Empleado no encontrado'}), 404
        return jsonify(datos)
    except Exception as e:
        logger.error("Error en /empleado/perfil: %s", e)
        return jsonify({'error': 'Error interno'}), 500


@blueprint_empleado.route('/empleado/estado', methods=['POST'])
@requiere_rol(*_ROLES_HUB)
def estado():
    data         = request.get_json(silent=True) or {}
    nuevo_estado = (data.get('estado') or '').strip()
    if not nuevo_estado:
        return jsonify({'error': 'Falta campo: estado'}), 400
    empleado_id = session.get('empleado_id')
    ok, msg = gestor_empleado.cambiar_estado(empleado_id, nuevo_estado)
    if not ok:
        return jsonify({'error': msg}), 400
    return jsonify({'ok': True, 'estado': nuevo_estado})


@blueprint_empleado.route('/empleado/turno-hoy')
@requiere_rol(*_ROLES_HUB)
def turno_hoy():
    empleado_id = session.get('empleado_id')
    try:
        turno = gestor_empleado.turno_hoy(empleado_id)
        return jsonify(turno)   # None se serializa como null en JSON
    except Exception as e:
        logger.error("Error en /empleado/turno-hoy: %s", e)
        return jsonify({'error': 'Error interno'}), 500


@blueprint_empleado.route('/empleado/metricas')
@requiere_rol(*_ROLES_HUB)
def metricas():
    empleado_id = session.get('empleado_id')
    rol         = session.get('rol', '')
    try:
        datos = gestor_empleado.metricas_hoy(empleado_id, rol)
        return jsonify(datos)
    except Exception as e:
        logger.error("Error en /empleado/metricas: %s", e)
        return jsonify({'error': 'Error interno'}), 500
