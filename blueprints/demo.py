import json
import logging
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, redirect, render_template, request, session

logger = logging.getLogger(__name__)
blueprint_demo = Blueprint('demo', __name__)

DEMO_TTL = 1800  # 30 minutos


def _get_redis():
    """Obtiene el cliente Redis del gestor global."""
    from managers.gestor_redis import redismanager
    return redismanager.client


class DemoState:
    """Gestiona el estado de la sesión demo en Redis."""

    @staticmethod
    def _key_picker(session_id: str) -> str:
        return f"demo:picker:{session_id}"

    @staticmethod
    def _key_rep(session_id: str) -> str:
        return f"demo:repartidor:{session_id}"

    @staticmethod
    def _key_cola_picker(session_id: str) -> str:
        return f"demo:cola:picker:{session_id}"

    @staticmethod
    def _key_cola_rep(session_id: str) -> str:
        return f"demo:cola:repartidor:{session_id}"

    @classmethod
    def init_session(cls, session_id: str):
        """Inicializa los datos demo en Redis para esta sesión."""
        from blueprints.demo_data import get_demo_picker_data, get_demo_repartidor_data, get_demo_cola_picker, get_demo_cola_repartidor
        r = _get_redis()
        key_p = cls._key_picker(session_id)
        key_r = cls._key_rep(session_id)
        key_cp = cls._key_cola_picker(session_id)
        key_cr = cls._key_cola_rep(session_id)

        r.setex(key_p, DEMO_TTL, json.dumps(get_demo_picker_data()))
        r.setex(key_r, DEMO_TTL, json.dumps(get_demo_repartidor_data()))
        r.setex(key_cp, DEMO_TTL, json.dumps(get_demo_cola_picker()))
        r.setex(key_cr, DEMO_TTL, json.dumps(get_demo_cola_repartidor()))

    @classmethod
    def get_picker(cls, session_id: str):
        r = _get_redis()
        raw = r.get(cls._key_picker(session_id))
        if raw:
            return json.loads(raw)
        from blueprints.demo_data import get_demo_picker_data
        return get_demo_picker_data()

    @classmethod
    def get_repartidor(cls, session_id: str):
        r = _get_redis()
        raw = r.get(cls._key_rep(session_id))
        if raw:
            return json.loads(raw)
        from blueprints.demo_data import get_demo_repartidor_data
        return get_demo_repartidor_data()

    @classmethod
    def get_cola_picker(cls, session_id: str):
        r = _get_redis()
        raw = r.get(cls._key_cola_picker(session_id))
        if raw:
            return json.loads(raw)
        from blueprints.demo_data import get_demo_cola_picker
        return get_demo_cola_picker()

    @classmethod
    def get_cola_repartidor(cls, session_id: str):
        r = _get_redis()
        raw = r.get(cls._key_cola_rep(session_id))
        if raw:
            return json.loads(raw)
        from blueprints.demo_data import get_demo_cola_repartidor
        return get_demo_cola_repartidor()

    @classmethod
    def reclamar_picking(cls, session_id: str, picking_id: int):
        """Reclamar un picking de la cola y agregarlo a mis pedidos."""
        r = _get_redis()
        cola_raw = r.get(cls._key_cola_picker(session_id))
        if not cola_raw:
            return False
        cola = json.loads(cola_raw)

        # Buscar en la cola
        picking_obj = None
        for i, item in enumerate(cola["cola"]):
            if item["picking_id"] == picking_id:
                picking_obj = cola["cola"].pop(i)
                break

        if not picking_obj:
            return False

        # Actualizar cola
        cola["total"] = len(cola["cola"])
        r.setex(cls._key_cola_picker(session_id), DEMO_TTL, json.dumps(cola))

        # Agregar a mis pedidos
        pickings_raw = r.get(cls._key_picker(session_id))
        pickings = json.loads(pickings_raw) if pickings_raw else []
        pickings.append(picking_obj)
        r.setex(cls._key_picker(session_id), DEMO_TTL, json.dumps(pickings))

        return True

    @classmethod
    def reclamar_reparto(cls, session_id: str, reparto_id: int):
        """Reclamar un reparto de la cola y agregarlo a mis pedidos."""
        r = _get_redis()
        cola_raw = r.get(cls._key_cola_rep(session_id))
        if not cola_raw:
            return False
        cola = json.loads(cola_raw)

        # Buscar en la cola
        reparto_obj = None
        for i, item in enumerate(cola["cola"]):
            if item["reparto_id"] == reparto_id:
                reparto_obj = cola["cola"].pop(i)
                break

        if not reparto_obj:
            return False

        # Actualizar cola
        cola["total"] = len(cola["cola"])
        r.setex(cls._key_cola_rep(session_id), DEMO_TTL, json.dumps(cola))

        # Agregar a mis pedidos
        repartos_raw = r.get(cls._key_rep(session_id))
        repartos = json.loads(repartos_raw) if repartos_raw else []
        repartos.append(reparto_obj)
        r.setex(cls._key_rep(session_id), DEMO_TTL, json.dumps(repartos))

        return True

    @classmethod
    def save_picker(cls, session_id: str, data):
        r = _get_redis()
        r.setex(cls._key_picker(session_id), DEMO_TTL, json.dumps(data))

    @classmethod
    def save_repartidor(cls, session_id: str, data):
        r = _get_redis()
        r.setex(cls._key_rep(session_id), DEMO_TTL, json.dumps(data))

    @classmethod
    def update_item(cls, session_id: str, item_id: int, estado: str, cantidad_encontrada=None, notas=None, producto_sustituto_id=None):
        """Actualiza el estado de un item del picking demo."""
        pickings = cls.get_picker(session_id)
        for picking in pickings:
            for item in picking.get('items', []):
                if item['item_id'] == item_id:
                    item['estado'] = estado
                    if cantidad_encontrada is not None:
                        item['cantidad_encontrada'] = cantidad_encontrada
                    if notas is not None:
                        item['notas'] = notas
                    # Recalcular contadores
                    total = len(picking['items'])
                    listos = sum(1 for i in picking['items'] if i['estado'] != 'pendiente')
                    pendientes = total - listos
                    picking['items_listos'] = listos
                    picking['items_pendientes'] = pendientes
                    picking['picking_completo'] = pendientes == 0
                    picking['listo_para_finalizar'] = pendientes == 0
                    cls.save_picker(session_id, pickings)
                    return True
        return False

    @classmethod
    def finalizar_picking(cls, session_id: str, picking_id: int):
        """Marca un picking como completado."""
        pickings = cls.get_picker(session_id)
        for picking in pickings:
            if picking['picking_id'] == picking_id:
                picking['estado'] = 'COMPLETADO'
                cls.save_picker(session_id, pickings)
                return True
        return False

    @classmethod
    def marcar_salida_reparto(cls, session_id: str, reparto_id: int):
        repartos = cls.get_repartidor(session_id)
        for r in repartos:
            if r['reparto_id'] == reparto_id:
                r['estado_reparto'] = 'en_camino'
                r['hora_salida'] = datetime.utcnow().isoformat()
                cls.save_repartidor(session_id, repartos)
                return True
        return False

    @classmethod
    def marcar_entregado(cls, session_id: str, reparto_id: int):
        repartos = cls.get_repartidor(session_id)
        for r in repartos:
            if r['reparto_id'] == reparto_id:
                r['estado_reparto'] = 'entregado'
                r['hora_entrega_real'] = datetime.utcnow().isoformat()
                cls.save_repartidor(session_id, repartos)
                return True
        return False

    @classmethod
    def marcar_no_entregado(cls, session_id: str, reparto_id: int, motivo: str):
        repartos = cls.get_repartidor(session_id)
        for r in repartos:
            if r['reparto_id'] == reparto_id:
                r['estado_reparto'] = 'no_entregado'
                r['motivo_no_entrega'] = motivo
                cls.save_repartidor(session_id, repartos)
                return True
        return False


@blueprint_demo.route('/demo')
def index():
    return render_template('demo/index.html')


@blueprint_demo.route('/demo/autologin')
def autologin():
    role = request.args.get('role', 'picker')
    if role not in ('picker', 'repartidor'):
        role = 'picker'

    # Generar demo_session_id único por visita demo si no existe
    if 'demo_session_id' not in session:
        session['demo_session_id'] = str(uuid.uuid4())

    demo_sid = session['demo_session_id']

    session['empleado_id'] = 0
    session['empleado_nombre'] = 'Demo'
    session['rol'] = 'manager'
    session['demo_mode'] = True
    session.permanent = False

    # Inicializar datos demo en Redis
    try:
        DemoState.init_session(demo_sid)
    except Exception as e:
        logger.warning("DEMO: no se pudo inicializar Redis: %s", e)

    logger.info("DEMO_AUTOLOGIN role=%s sid=%s", role, demo_sid)
    return redirect('/picker' if role == 'picker' else '/repartidor')


@blueprint_demo.route('/demo/reset', methods=['POST'])
def reset():
    """Regenera los datos demo para esta sesión."""
    sid = session.get('demo_session_id')
    if not sid:
        return jsonify({"error": "No hay sesión demo activa"}), 400
    try:
        r = _get_redis()
        # Eliminar datos viejos
        r.delete(DemoState._key_picker(sid))
        r.delete(DemoState._key_rep(sid))
        r.delete(DemoState._key_cola_picker(sid))
        r.delete(DemoState._key_cola_rep(sid))
        # Regenerar frescos
        DemoState.init_session(sid)
        logger.info("DEMO_RESET sid=%s", sid)
        return jsonify({"ok": True, "mensaje": "Datos regenerados"})
    except Exception as e:
        logger.error("Error en /demo/reset: %s", e)
        return jsonify({"error": "Error interno"}), 500
