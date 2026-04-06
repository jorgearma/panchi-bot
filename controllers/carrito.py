import json
import logging

from sqlalchemy.exc import SQLAlchemyError, OperationalError
from tenacity import RetryError
from maps_module import geocodificar_direccion
from states import EstadoPedido

logger = logging.getLogger(__name__)


def _validar_productos(productos_recibidos: list, gestor_productos) -> tuple:
    """Valida cada producto contra la BD y construye la lista con precios confirmados.

    Devuelve (True, lista_productos) o (False, mensaje_error).
    """
    productos = []
    total = 0.0

    for p in productos_recibidos:
        nombre_producto = p.get("nombre", "Producto desconocido")

        codigo = p.get("Codigo")
        if not codigo:
            logger.error("confirmar_carrito: producto sin código identificador")
            return False, "Producto sin código identificador"

        cantidad = p.get("cantidad", 1)
        if isinstance(cantidad, bool) or not isinstance(cantidad, int) or cantidad <= 0:
            logger.error(
                "confirmar_carrito: cantidad inválida %s para código %s", cantidad, codigo
            )
            return False, f"Cantidad inválida para el producto {codigo}"

        producto_db = gestor_productos.obtener_producto_por_codigo(codigo)
        if not producto_db:
            logger.error(
                "confirmar_carrito: código %s no encontrado o error de BD", codigo
            )
            return False, f"Producto con código {codigo} no encontrado"

        precio_db = producto_db.get("Precio")
        if precio_db is None:
            logger.error(
                "confirmar_carrito: precio NULL en BD para código %s", codigo
            )
            return False, f"Precio no disponible para el producto {codigo}"

        precio_unitario = float(precio_db)
        precio_total = round(precio_unitario * cantidad, 2)

        removed = p.get("ingredientes_removidos", [])
        notas   = f"Sin: {', '.join(removed)}" if removed else ""
        productos.append({
            "nombre": nombre_producto,
            "cantidad": cantidad,
            "precio": precio_total,
            "codigo": codigo,
            "notas": notas,
        })
        total += precio_total

    return True, (productos, round(total, 2))


def confirmar_carrito(
    pedido_id_redis: str,
    name: str,
    token: str,
    user_id,
    numero: str,
    direccion: str,
    productos_recibidos: list,
    cache,
    pedidos_manager,
    gestor_productos,
    public_url: str,
) -> tuple:
    """Guarda el carrito validado, calcula su total y lo deja listo para confirmar."""
    if not productos_recibidos:
        logger.warning("confirmar_carrito: carrito vacío para usuario %s", user_id)
        return False, "El carrito no puede estar vacío"

    ok, resultado = _validar_productos(productos_recibidos, gestor_productos)
    if not ok:
        return False, resultado
    productos, total = resultado

    try:
        pedido_activo = pedidos_manager.obtener_pedido_mas_reciente(user_id)
    except (SQLAlchemyError, OperationalError, RetryError) as e:
        logger.error("confirmar_carrito: DB error obteniendo pedido usuario=%s: %s", user_id, e)
        return False, "Error de base de datos. Intente más tarde."
    if pedido_activo is None:
        logger.error("confirmar_carrito: no active order found for user %s", user_id)
        return False, "No se encontró un pedido activo para este usuario"

    pedido_id_db = pedido_activo.PedidoID

    if pedido_activo.Estado != EstadoPedido.ENLACE:
        logger.warning(
            "confirmar_carrito: cannot transition order %s from state '%s' to ENLACE2",
            pedido_id_db,
            pedido_activo.Estado,
        )
        return False, "El pedido no se encuentra en el estado correcto para confirmar el carrito"

    coords = geocodificar_direccion(direccion)
    lat, lng = (coords[0], coords[1]) if coords else (None, None)
    if not coords:
        logger.warning("confirmar_carrito: no se pudieron geocodificar las coordenadas del pedido %s", pedido_id_db)

    # DB primero: la transición de estado es la operación crítica.
    try:
        pedidos_manager.fijar_carrito_confirmado(pedido_id_db, pedido_id_redis, lat=lat, lng=lng)
    except (SQLAlchemyError, OperationalError, RetryError) as e:
        logger.error("confirmar_carrito: DB error en fijar_carrito_confirmado pedido=%s: %s", pedido_id_db, e)
        return False, "Error de base de datos al confirmar el carrito. Intente más tarde."

    # Redis solo si DB confirma — el carrito es cache recuperable.
    try:
        cache.set(
            pedido_id_redis,
            json.dumps({
                "name": name,
                "token": token,
                "userID": user_id,
                "pedidoID": pedido_id_db,
                "numero": numero,
                "direccion": direccion,
                "productos": productos,
                "total": total,
            }),
            ex=3600,
        )
    except Exception as e:
        logger.warning("confirmar_carrito: fallo al guardar carrito en Redis pedido=%s: %s", pedido_id_db, e)
    logger.info("CARRITO_CONFIRMADO pedido_id=%s", pedido_id_db)

    confirmacion_url = f"{public_url}/confirmacion_pago?pedido_id={pedido_id_redis}"
    return True, confirmacion_url
