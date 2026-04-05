"""Estado de sesión demo almacenado en Redis.

Centraliza la lógica de lectura/escritura de datos demo para picker,
repartidor y dashboard. Las blueprints solo delegan a esta clase.
"""
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

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
        r.setex(cls._key_picker(session_id), DEMO_TTL, json.dumps(get_demo_picker_data()))
        r.setex(cls._key_rep(session_id), DEMO_TTL, json.dumps(get_demo_repartidor_data()))
        r.setex(cls._key_cola_picker(session_id), DEMO_TTL, json.dumps(get_demo_cola_picker()))
        r.setex(cls._key_cola_rep(session_id), DEMO_TTL, json.dumps(get_demo_cola_repartidor()))

    @classmethod
    def reset(cls, session_id: str):
        """Borra los datos demo y los regenera frescos para esta sesión."""
        r = _get_redis()
        r.delete(cls._key_picker(session_id))
        r.delete(cls._key_rep(session_id))
        r.delete(cls._key_cola_picker(session_id))
        r.delete(cls._key_cola_rep(session_id))
        cls.init_session(session_id)

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

        picking_obj = None
        for i, item in enumerate(cola["cola"]):
            if item["picking_id"] == picking_id:
                picking_obj = cola["cola"].pop(i)
                break

        if not picking_obj:
            return False

        cola["total"] = len(cola["cola"])
        r.setex(cls._key_cola_picker(session_id), DEMO_TTL, json.dumps(cola))

        pickings_raw = r.get(cls._key_picker(session_id))
        pickings = json.loads(pickings_raw) if pickings_raw else []
        pickings.append(picking_obj)
        r.setex(cls._key_picker(session_id), DEMO_TTL, json.dumps(pickings))
        return True

    @classmethod
    def reclamar_picking_by_pedido(cls, session_id: str, pedido_id: int):
        """Reclamar un picking de la cola usando pedido_id."""
        r = _get_redis()
        cola_raw = r.get(cls._key_cola_picker(session_id))
        if not cola_raw:
            return False
        cola = json.loads(cola_raw)

        picking_obj = None
        for i, item in enumerate(cola["cola"]):
            if item["pedido_id"] == pedido_id:
                picking_obj = cola["cola"].pop(i)
                break

        if not picking_obj:
            return False

        cola["total"] = len(cola["cola"])
        r.setex(cls._key_cola_picker(session_id), DEMO_TTL, json.dumps(cola))

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

        reparto_obj = None
        for i, item in enumerate(cola["cola"]):
            if item["reparto_id"] == reparto_id:
                reparto_obj = cola["cola"].pop(i)
                break

        if not reparto_obj:
            return False

        cola["total"] = len(cola["cola"])
        r.setex(cls._key_cola_rep(session_id), DEMO_TTL, json.dumps(cola))

        repartos_raw = r.get(cls._key_rep(session_id))
        repartos = json.loads(repartos_raw) if repartos_raw else []
        repartos.append(reparto_obj)
        r.setex(cls._key_rep(session_id), DEMO_TTL, json.dumps(repartos))
        return True

    @classmethod
    def reclamar_reparto_by_pedido(cls, session_id: str, pedido_id: int):
        """Reclamar un reparto de la cola usando pedido_id."""
        r = _get_redis()
        cola_raw = r.get(cls._key_cola_rep(session_id))
        if not cola_raw:
            return False
        cola = json.loads(cola_raw)

        reparto_obj = None
        for i, item in enumerate(cola["cola"]):
            if item["pedido_id"] == pedido_id:
                reparto_obj = cola["cola"].pop(i)
                break

        if not reparto_obj:
            return False

        cola["total"] = len(cola["cola"])
        r.setex(cls._key_cola_rep(session_id), DEMO_TTL, json.dumps(cola))

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
        """Marca un picking como completado y lo traslada a la cola del repartidor."""
        r = _get_redis()
        pickings = cls.get_picker(session_id)

        picking_obj = None
        for i, picking in enumerate(pickings):
            if picking['picking_id'] == picking_id:
                picking_obj = pickings.pop(i)
                break

        if not picking_obj:
            return False

        cls.save_picker(session_id, pickings)

        reparto = cls._converting_picking_to_reparto(picking_obj)
        cola_raw = r.get(cls._key_cola_rep(session_id))
        cola = json.loads(cola_raw) if cola_raw else {"cola": [], "total": 0}
        cola["cola"].append(reparto)
        cola["total"] = len(cola["cola"])
        r.setex(cls._key_cola_rep(session_id), DEMO_TTL, json.dumps(cola))
        return True

    @staticmethod
    def _converting_picking_to_reparto(picking: dict) -> dict:
        """Convierte un picking completado a un reparto para la cola del repartidor."""
        reparto_id = 3000 + picking['picking_id']
        items_reparto = [
            {
                'nombre': item['nombre'],
                'cantidad': item['cantidad'],
                'subtotal': item.get('subtotal', item['cantidad'] * 5.0),
            }
            for item in picking.get('items', [])
        ]
        return {
            'reparto_id': reparto_id,
            'pedido_id': picking['pedido_id'],
            'estado_reparto': 'asignado',
            'estado_pedido': 'PREPARADO',
            'cliente_nombre': picking['cliente_nombre'],
            'cliente_telefono': picking['cliente_telefono'],
            'direccion_entrega': picking['direccion_entrega'],
            'lat': 40.0053 + (reparto_id % 100) * 0.0001,
            'lng': -2.9956 - (reparto_id % 100) * 0.0001,
            'total': picking['total'],
            'pago': {
                'estado': 'cobrar_efectivo' if reparto_id % 2 == 0 else 'pagado_online',
                'label': 'Cobrar en efectivo' if reparto_id % 2 == 0 else 'Pagado online',
                'importe': picking['total'],
                'proveedor': None if reparto_id % 2 == 0 else 'Monei',
            },
            'items': items_reparto,
            'fecha_creacion': picking['iniciado_en'],
            'hora_salida': None,
            'hora_estimada_entrega': None,
            'hora_entrega_real': None,
            'motivo_no_entrega': None,
            'notas': None,
        }

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
        reparto_obj = None
        for i, r in enumerate(repartos):
            if r['reparto_id'] == reparto_id:
                reparto_obj = repartos.pop(i)
                break
        if not reparto_obj:
            return False
        reparto_obj['estado_reparto'] = 'entregado'
        reparto_obj['hora_entrega_real'] = datetime.utcnow().isoformat()
        cls.save_repartidor(session_id, repartos)
        return True

    @classmethod
    def marcar_no_entregado(cls, session_id: str, reparto_id: int, motivo: str):
        repartos = cls.get_repartidor(session_id)
        reparto_obj = None
        for i, r in enumerate(repartos):
            if r['reparto_id'] == reparto_id:
                reparto_obj = repartos.pop(i)
                break
        if not reparto_obj:
            return False
        reparto_obj['estado_reparto'] = 'no_entregado'
        reparto_obj['motivo_no_entrega'] = motivo
        cls.save_repartidor(session_id, repartos)
        return True
