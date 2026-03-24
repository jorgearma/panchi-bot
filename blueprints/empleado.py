import logging
from datetime import date, timedelta

from flask import Blueprint, jsonify, redirect, render_template, request, session

from blueprints.auth import requiere_autenticacion, requiere_rol
from database import get_db
from models import Empleado as _Empleado
from services import gestor_empleado

logger = logging.getLogger(__name__)

blueprint_empleado = Blueprint('empleado', __name__)

_ROLES_HUB = ('picker', 'repartidor', 'manager', 'admin')


@blueprint_empleado.route('/empleado', strict_slashes=False)
@requiere_rol(*_ROLES_HUB)
def index():
    empleado_id = session.get('empleado_id')
    rol = session.get('rol')
    # Redirigir a check-in si polivalente y sin rol_activo en BD
    try:
        if gestor_empleado.es_polivalente(empleado_id) and not gestor_empleado.tiene_rol_activo(empleado_id):
            return redirect('/empleado/checkin')
    except Exception:
        pass  # Si falla la BD, mostrar el hub igualmente
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


@blueprint_empleado.route('/empleado/puede-iniciar')
@requiere_rol(*_ROLES_HUB)
def puede_iniciar():
    empleado_id = session.get('empleado_id')
    try:
        resultado = gestor_empleado.puede_iniciar_turno(empleado_id)
        return jsonify(resultado), 200
    except Exception as e:
        logger.error("Error en /empleado/puede-iniciar: %s", e)
        return jsonify({'puede': False, 'razon': 'Error interno'}), 500


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


@blueprint_empleado.route('/empleado/capacidades')
@requiere_rol(*_ROLES_HUB)
def capacidades():
    empleado_id = session.get('empleado_id')
    try:
        caps = gestor_empleado.capacidades(empleado_id)
        emp = get_db().query(_Empleado).filter_by(EmpleadoID=empleado_id).first()
        rol_activo = emp.rol_activo if emp else None
        return jsonify({'capacidades': caps, 'rol_activo': rol_activo})
    except Exception as e:
        logger.error("Error en /empleado/capacidades: %s", e)
        return jsonify({'capacidades': [], 'rol_activo': None})


@blueprint_empleado.route('/empleado/carga-operativa')
@requiere_rol(*_ROLES_HUB)
def carga_operativa():
    try:
        return jsonify(gestor_empleado.carga_operativa())
    except Exception as e:
        logger.error("Error en /empleado/carga-operativa: %s", e)
        return jsonify({'picker': {'pendientes': 0, 'en_proceso': 0},
                        'repartidor': {'listos_para_entregar': 0, 'en_camino': 0}})


@blueprint_empleado.route('/empleado/cambiar-rol', methods=['POST'])
@requiere_rol(*_ROLES_HUB)
def cambiar_rol():
    data = request.get_json(silent=True) or {}
    nuevo_rol = (data.get('rol') or '').strip()
    if not nuevo_rol:
        return jsonify({'error': 'Falta campo: rol'}), 400

    empleado_id = session.get('empleado_id')
    ok, msg, bloqueantes = gestor_empleado.cambiar_rol(empleado_id, nuevo_rol)

    if not ok:
        if bloqueantes:
            return jsonify({'error': msg, 'pedidos_activos': bloqueantes}), 409
        return jsonify({'error': msg}), 403

    session['rol'] = nuevo_rol
    return jsonify({'ok': True, 'rol': nuevo_rol})


@blueprint_empleado.route('/empleado/checkin')
@requiere_autenticacion
def checkin():
    empleado_id = session.get('empleado_id')
    try:
        caps = gestor_empleado.capacidades(empleado_id)
        if len(caps) == 1:
            return redirect('/empleado')
        carga = gestor_empleado.carga_operativa()
        turno = gestor_empleado.turno_hoy(empleado_id)
        return render_template('empleado/checkin.html',
                                capacidades=caps,
                                carga=carga,
                                turno=turno,
                                empleado_id=empleado_id)
    except Exception as e:
        logger.error("Error en /empleado/checkin: %s", e)
        return redirect('/empleado')


@blueprint_empleado.route('/empleado/fichaje', methods=['POST'])
@requiere_rol(*_ROLES_HUB)
def fichaje_iniciar():
    empleado_id = session.get('empleado_id')
    try:
        puede_result = gestor_empleado.puede_iniciar_turno(empleado_id)
        if not puede_result['puede']:
            return jsonify({'error': puede_result['razon']}), 403
        check_in = gestor_empleado.iniciar_turno(empleado_id, turno_id=puede_result['turno_id'])
        return jsonify({'ok': True, 'check_in_id': check_in.id,
                        'inicio': check_in.inicio.isoformat()})
    except ValueError as e:
        if str(e) == 'ya_abierto':
            return jsonify({'error': 'Ya tienes un turno abierto hoy'}), 409
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error("Error en /empleado/fichaje: %s", e)
        return jsonify({'error': 'Error interno'}), 500


@blueprint_empleado.route('/empleado/fichaje/cerrar', methods=['POST'])
@requiere_rol(*_ROLES_HUB)
def fichaje_cerrar():
    empleado_id = session.get('empleado_id')
    try:
        resumen = gestor_empleado.cerrar_turno(empleado_id)
        return jsonify({'ok': True, **resumen})
    except ValueError as e:
        if str(e) == 'no_abierto':
            return jsonify({'error': 'No tienes un turno abierto'}), 400
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error("Error en /empleado/fichaje/cerrar: %s", e)
        return jsonify({'error': 'Error interno'}), 500


@blueprint_empleado.route('/empleado/fichaje/hoy')
@requiere_rol(*_ROLES_HUB)
def fichaje_hoy():
    empleado_id = session.get('empleado_id')
    try:
        return jsonify(gestor_empleado.checkin_hoy(empleado_id))
    except Exception as e:
        logger.error("Error en /empleado/fichaje/hoy: %s", e)
        return jsonify({'activo': False})


@blueprint_empleado.route('/empleado/turnos')
@requiere_rol(*_ROLES_HUB)
def turnos_page():
    empleado_id = session.get('empleado_id')
    rol = session.get('rol')
    return render_template('empleado/turnos.html', empleado_id=empleado_id, rol=rol)


@blueprint_empleado.route('/empleado/turnos/datos')
@requiere_rol(*_ROLES_HUB)
def turnos_datos():
    empleado_id = session.get('empleado_id')
    hoy = date.today()
    try:
        desde_str = request.args.get('desde')
        hasta_str = request.args.get('hasta')
        desde = date.fromisoformat(desde_str) if desde_str else hoy
        hasta = date.fromisoformat(hasta_str) if hasta_str else hoy + timedelta(days=14)
    except ValueError:
        desde = hoy
        hasta = hoy + timedelta(days=14)
    try:
        lista = gestor_empleado.turnos_proximos(empleado_id, desde, hasta)
        return jsonify({'turnos': lista})
    except Exception as e:
        logger.error('Error en /empleado/turnos/datos: %s', e)
        return jsonify({'error': 'Error interno'}), 500
