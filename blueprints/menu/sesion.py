import json
import logging

from flask import jsonify, render_template, request

import config
from services import cache
from blueprints.menu._helpers import _extraer_calle

logger = logging.getLogger(__name__)


def register(bp):
    """Registra las pantallas de confirmación y seguimiento postpedido."""
    @bp.route('/confirmacion_pago')
    def mostrar_confirmacion():
        """Renderiza la confirmación previa al pago usando datos temporales en caché."""
        pedido_id = request.args.get("pedido_id")
        if not pedido_id:
            return jsonify({"error": "Pedido no encontrado"}), 404

        pedido_data = cache.get(pedido_id)
        if not pedido_data:
            return jsonify({"error": "Pedido expirado o no encontrado"}), 404

        pedido = json.loads(pedido_data)
        return render_template(
            "confirmacion_pago.html",
            name=pedido["name"],
            userID=pedido["userID"],
            token=pedido["token"],
            numero=pedido["numero"],
            direccion=pedido["direccion"],
            calle=_extraer_calle(pedido["direccion"]),
            total=pedido["total"],
            productos=pedido["productos"],
            pedidoID=pedido["pedidoID"],
            public_url=config.PUBLIC_URL or "",
        )

    @bp.route('/pago_confirmado')
    def mostrar_confirmacion_depago():
        """Renderiza la vista final del pedido ya confirmado o pagado."""
        pedido_id = request.args.get("pedido_id")
        if not pedido_id:
            return jsonify({"error": "Pedido no encontrado"}), 404

        pedido_data = cache.get(pedido_id)
        if not pedido_data:
            return jsonify({"error": "Pedido expirado o no encontrado"}), 404

        pedido = json.loads(pedido_data)
        return render_template(
            "ver_comandas.html",
            name=pedido["name"],
            userID=pedido["userID"],
            token=pedido["token"],
            numero=pedido["numero"],
            direccion=pedido["direccion"],
            calle=_extraer_calle(pedido["direccion"]),
            total=pedido["total"],
            productos=pedido["productos"],
            pedidoID=pedido["pedidoID"],
            public_url=config.PUBLIC_URL or "",
            store_phone=config.STORE_PHONE or "",
            store_address=config.STORE_ADDRESS or "",
            redis_id=pedido_id,
        )
