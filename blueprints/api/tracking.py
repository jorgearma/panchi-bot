import logging

from flask import jsonify

from database import get_db
from models import Pedido

logger = logging.getLogger(__name__)


def register(bp):
    """Registra la ruta pública de seguimiento del pedido."""
    @bp.route('/api/seguimiento/<redis_id>', methods=['GET'])
    def seguimiento_pedido(redis_id):
        """Devuelve el estado del pedido y, si existe, su reparto asociado."""
        pedido = get_db().query(Pedido).filter_by(redisID=redis_id).first()
        if not pedido:
            return jsonify({"error": "Pedido no encontrado"}), 404

        reparto_data = None
        if pedido.reparto:
            r = pedido.reparto
            repartidor_nombre = None
            repartidor_telefono = None
            if r.repartidor:
                repartidor_nombre = f"{r.repartidor.Nombre} {r.repartidor.Apellido}"
                repartidor_telefono = r.repartidor.Telefono
            reparto_data = {
                "estado": r.estado,
                "hora_salida": r.hora_salida.strftime("%H:%M") if r.hora_salida else None,
                "hora_estimada_entrega": r.hora_estimada_entrega.strftime("%H:%M") if r.hora_estimada_entrega else None,
                "repartidor_nombre": repartidor_nombre,
                "repartidor_telefono": repartidor_telefono,
                "calle_destino": pedido.DireccionEntrega,
            }

        logger.debug("Seguimiento pedido redis_id=%s: estado=%s", redis_id, pedido.Estado)
        return jsonify({
            "estado": pedido.Estado,
            "forma_pago": pedido.forma_pago,
            "reparto": reparto_data,
        })
