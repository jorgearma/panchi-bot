import logging

from flask import jsonify

from container import gestor_pedidos

logger = logging.getLogger(__name__)


def register(bp):
    """Registra la ruta pública de seguimiento del pedido."""
    @bp.route('/api/seguimiento/<redis_id>', methods=['GET'])
    def seguimiento_pedido(redis_id):
        """Devuelve el estado del pedido y, si existe, su reparto asociado."""
        datos = gestor_pedidos.obtener_seguimiento(redis_id)
        if not datos:
            return jsonify({"error": "Pedido no encontrado"}), 404
        logger.debug("Seguimiento pedido redis_id=%s: estado=%s", redis_id, datos["estado"])
        return jsonify(datos)
