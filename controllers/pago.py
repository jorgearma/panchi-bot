import logging

from states import EstadoPedido
from services.monei_service import crear_pago as monei_crear_pago
from controllers.pago_notifier import _enviar_confirmacion_efectivo

logger = logging.getLogger(__name__)


def _validar_carrito(productos_recibidos, gestor_productos):
    """Recalcula el carrito con datos de BD para evitar importes manipulados."""
    productos_validos = []
    total = 0.0
    for item in productos_recibidos:
        codigo = item.get("codigo")
        cantidad = item.get("cantidad", 1)
        producto_db = gestor_productos.obtener_producto_por_codigo(codigo)
        if not producto_db:
            logger.error("_validar_carrito: producto %s no encontrado en BD", codigo)
            return None, None, f"Producto con código {codigo} no encontrado"
        total += float(producto_db["Precio"]) * cantidad
        productos_validos.append([codigo, cantidad])
    return productos_validos, total, None


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
    notas: str = "",
) -> tuple:
    """Crea el pago online y mueve el pedido al estado de confirmación de pago."""
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

    productos_validos, total_calculado, error = _validar_carrito(productos_recibidos, gestor_productos)
    if error:
        return False, error

    pedido_activo_id = pedido_activo.PedidoID
    redis_id = pedido_activo.redisID

    gestor_pedidos.agregar_productos_a_pedido(pedido_activo_id, productos_validos)

    if notas:
        pedido_activo.Notas = notas

    amount_in_cents = int(round(total_calculado * 100))

    redirect_url, error = monei_crear_pago(
        monei=monei,
        amount_cents=amount_in_cents,
        pedido_id=pedido_activo_id,
        redis_id=redis_id,
        nombre_cliente=nombre_cliente,
        numero_cliente=numero_cliente,
        direccion_cliente=direccion_cliente,
        public_url=public_url,
    )

    if error:
        return False, error

    gestor_pedidos.actualizar_estado(pedido_activo_id, EstadoPedido.CONFIRMANDO_PAGO)
    gestor_pedidos.guardar_enlace(pedido_activo_id, redirect_url)
    logger.info(
        "PAGO_INICIADO pedido_id=%s importe=%s",
        pedido_activo_id, amount_in_cents,
    )
    return True, redirect_url


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
    notas: str = "",
) -> tuple:
    """Confirma un pedido contra reembolso sin pasar por Monei."""
    pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(user_id)

    if not pedido_activo:
        return False, "No se encontró un pedido activo para este usuario"

    if pedido_activo.Estado != EstadoPedido.ENLACE2:
        logger.error(
            "iniciar_pago_efectivo: pedido %s en estado inesperado '%s'",
            pedido_activo.PedidoID, pedido_activo.Estado,
        )
        return False, "El pedido no está listo para confirmar"

    productos_validos, total_calculado, error = _validar_carrito(productos_recibidos, gestor_productos)
    if error:
        return False, error

    pedido_id = pedido_activo.PedidoID
    redis_id = pedido_activo.redisID

    gestor_pedidos.agregar_productos_a_pedido(pedido_id, productos_validos)

    if notas:
        pedido_activo.Notas = notas

    gestor_pedidos.guardar_forma_pago(pedido_id, "efectivo")
    gestor_pedidos.actualizar_estado(pedido_id, EstadoPedido.CONTRA_REEMBOLSO)

    total_euros = round(total_calculado, 2)
    _enviar_confirmacion_efectivo(numero_cliente, nombre_cliente, total_euros, pedido_id, direccion_cliente)
    logger.info("iniciar_pago_efectivo: pedido %s confirmado contra reembolso", pedido_id)

    return True, f"{public_url}/pago_confirmado?pedido_id={redis_id}"
