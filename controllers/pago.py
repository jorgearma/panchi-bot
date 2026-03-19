import logging

from Monei import ApiException

from states import EstadoPedido
from services.twilio_service import enviar_mensaje_whatsapp

logger = logging.getLogger(__name__)


def iniciar_pago(
    user_id,
    productos_recibidos: list,
    nombre_cliente: str,
    numero_cliente: str,
    direccion_cliente: str,
    cache,
    gestor_pedidos,
    gestor_productos,
    monei,
    public_url: str,
) -> tuple:
    """
    Validates cart prices against DB, creates a Monei payment, and transitions
    the order to CONFIRMANDO_PAGO.

    Returns (success: bool, redirect_url_or_error: str).
    """
    pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(user_id)

    if not pedido_activo:
        return False, "No se encontró un pedido activo para este usuario"

    if pedido_activo.Estado == EstadoPedido.CONFIRMANDO_PAGO:
        return True, "El pedido ya está en proceso de pago."

    if pedido_activo.Estado != EstadoPedido.ENLACE2:
        logger.error(
            "iniciar_pago: pedido %s en estado inesperado '%s'",
            pedido_activo.PedidoID, pedido_activo.Estado
        )
        return False, "El pedido no está listo para procesar el pago"

    productos_validos = []
    total_calculado = 0.0

    for item in productos_recibidos:
        codigo = item.get("codigo")
        cantidad = item.get("cantidad", 1)

        producto_db = gestor_productos.obtener_producto_por_codigo(codigo)
        if not producto_db:
            logger.error("iniciar_pago: product with code %s not found in DB", codigo)
            return False, f"Producto con código {codigo} no encontrado"

        precio_db = float(producto_db["Precio"])
        total_calculado += precio_db * cantidad
        productos_validos.append([codigo, cantidad])

    pedido_activo_id = pedido_activo.PedidoID
    redis_id = pedido_activo.redisID

    gestor_pedidos.agregar_productos_a_pedido(pedido_activo_id, productos_validos)

    amount_in_cents = int(round(total_calculado * 100))

    payment_data = {
        "amount": amount_in_cents,
        "order_id": str(pedido_activo_id),
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
        logger.info("iniciar_pago: Monei response for order %s: %s", pedido_activo_id, result)

        redirect_url = result.get("next_action", {}).get("redirect_url")

        gestor_pedidos.actualizar_estado(pedido_activo_id, EstadoPedido.CONFIRMANDO_PAGO)
        gestor_pedidos.guardar_enlace(pedido_activo_id, redirect_url)
        logger.info(
            "PAGO_INICIADO pedido_id=%s importe=%s",
            pedido_activo_id, amount_in_cents,
        )

        if redirect_url:
            return True, redirect_url
        else:
            return False, "No se encontró la URL de redirección en la respuesta"

    except ApiException as exc:
        logger.error("iniciar_pago: Monei ApiException: %s", exc)
        return False, str(exc)


def iniciar_pago_efectivo(
    user_id,
    productos_recibidos: list,
    nombre_cliente: str,
    numero_cliente: str,
    direccion_cliente: str,
    cache,
    gestor_pedidos,
    gestor_productos,
    public_url: str,
) -> tuple:
    """
    Confirma el pedido con pago en efectivo a la entrega.
    Valida precios contra BD (misma protección antifraude que iniciar_pago),
    no llama a Monei, y transiciona el pedido a CONTRA_REEMBOLSO.

    Returns (success: bool, redirect_url_or_error: str).
    """
    pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(user_id)

    if not pedido_activo:
        return False, "No se encontró un pedido activo para este usuario"

    if pedido_activo.Estado != EstadoPedido.ENLACE2:
        logger.error(
            "iniciar_pago_efectivo: pedido %s en estado inesperado '%s'",
            pedido_activo.PedidoID, pedido_activo.Estado,
        )
        return False, "El pedido no está listo para confirmar"

    productos_validos = []
    total_calculado = 0.0

    for item in productos_recibidos:
        codigo = item.get("codigo")
        cantidad = item.get("cantidad", 1)

        producto_db = gestor_productos.obtener_producto_por_codigo(codigo)
        if not producto_db:
            logger.error("iniciar_pago_efectivo: producto con código %s no encontrado en BD", codigo)
            return False, f"Producto con código {codigo} no encontrado"

        precio_db = float(producto_db["Precio"])
        total_calculado += precio_db * cantidad
        productos_validos.append([codigo, cantidad])

    pedido_id = pedido_activo.PedidoID
    redis_id = pedido_activo.redisID

    gestor_pedidos.agregar_productos_a_pedido(pedido_id, productos_validos)
    gestor_pedidos.guardar_forma_pago(pedido_id, "efectivo")
    gestor_pedidos.actualizar_estado(pedido_id, EstadoPedido.CONTRA_REEMBOLSO)

    total_euros = round(total_calculado, 2)
    mensaje = (
        f"❕*Pedido confirmado*❕\n      ------------------  \n"
        f"▪️Nombre: *{nombre_cliente}*\n"
        f"▪️Importe: *{total_euros}*€\n"
        f"▪️ID pedido: *#{pedido_id}*\n"
        f"▪️Forma de pago: *Efectivo (a la entrega)*\n"
        f"▪️Tiempo estimado: *15m*\n"
        f"▪️Dirección: 👇🏼 \n\n{direccion_cliente}"
    )
    enviar_mensaje_whatsapp(mensaje, numero_cliente)
    logger.info("iniciar_pago_efectivo: pedido %s confirmado contra reembolso", pedido_id)

    return True, f"{public_url}/pago_confirmado?pedido_id={redis_id}"
