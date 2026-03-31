# Adaptador para el API de Monei (pagos)
# Encapsula la construcción del payload y la llamada al SDK

import logging
from Monei import ApiException

logger = logging.getLogger(__name__)


def crear_pago(monei, amount_cents, pedido_id, redis_id, nombre_cliente,
               numero_cliente, direccion_cliente, public_url):
    """
    Construye el payload y crea el pago en Monei.

    Returns (redirect_url, None) en éxito o (None, error_str) en fallo.
    """
    payment_data = {
        "amount": amount_cents,
        "order_id": str(pedido_id),
        "currency": "EUR",
        "description": nombre_cliente,
        "completeUrl": f"{public_url}/pago_confirmado?pedido_id={redis_id}",
        "customer": {
            "email": f"whatsapp_{numero_cliente.replace('+', '').replace('whatsapp:', '')}@noreply.panchibot.internal",
            "name": nombre_cliente,
            "phone": numero_cliente,
        },
        "billingDetails": {
            "address": {
                "line1": direccion_cliente,
                "city": "tarancon",
                "postalCode": "16400",
                "country": "ES",
            }
        },
    }

    try:
        result = monei.payments.create(payment_data)
        logger.info("monei_service.crear_pago: respuesta para pedido %s: %s", pedido_id, result)
        redirect_url = result.get("next_action", {}).get("redirect_url")
        if redirect_url:
            return redirect_url, None
        return None, "No se encontró la URL de redirección en la respuesta"
    except ApiException as exc:
        logger.error("monei_service.crear_pago: ApiException: %s", exc)
        return None, str(exc)
