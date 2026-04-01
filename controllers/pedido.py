import json
import logging

from pydantic import ValidationError
from utils.es_pregunta import es_pregunta
from container import gestor_pedidos
from services.token_service import generar_enlace
from services.whatsapp_service import enviar_mensaje_whatsapp
from services.maps_service import geocodificar_direccion
from utils.menu_opciones import menu, mostrar_menu
from utils.text_utils import limpiar_texto
from schemas.twilio import PedidoInput
from states import EstadoPedido

logger = logging.getLogger(__name__)


def procesar_pedido(pedido, numero_cliente, id_pedido_actual, usuario_datos):
    """Interpreta la opción elegida por el cliente y responde según el menú."""
    try:
        # Validar los datos de entrada con Pydantic
        datos = PedidoInput(pedido=pedido, numero_cliente=numero_cliente, id_pedido_actual=id_pedido_actual)
        logger.debug("Datos validados: pedido=%s, cliente=%s", datos.pedido, datos.numero_cliente)

    except ValidationError as e:
        # Retornar errores de validación como respuesta
        return f"❌ Error en los datos de entrada:\n{e}"

    if es_pregunta(datos.pedido):
        return "Lo siento, no reconocí tu pregunta."

    pedido_limpio = limpiar_texto(datos.pedido)

    for categoria, items in menu.items():
        for item, info in items.items():
            item_limpio = limpiar_texto(item)
            codigo_producto = str(info["codigo"])

            if item_limpio in pedido_limpio or codigo_producto in pedido_limpio:
                mensaje_respuesta = info["mensaje"]

                if mensaje_respuesta == "Tienda online":
                    try:
                        enlace = generar_enlace(item, usuario_datos)
                        actualizado = gestor_pedidos.actualizar_estado(datos.id_pedido_actual, EstadoPedido.ENLACE)
                        guardado = gestor_pedidos.guardar_enlace(datos.id_pedido_actual, enlace)

                        if actualizado and guardado:
                            logger.info(
                                "PEDIDO_INICIADO pedido_id=%s usuario=%s",
                                datos.id_pedido_actual, datos.numero_cliente,
                            )
                            return f"❕ {mensaje_respuesta} ❕\n\n🔗 *Enlace único*: {enlace}"
                        else:
                            gestor_pedidos.actualizar_estado(datos.id_pedido_actual, EstadoPedido.PENDIENTE)
                            return "❌ Ocurrió un error al procesar la opción. Intente nuevamente."

                    except Exception as e:
                        logger.error("Error al generar el enlace: %s", e)
                        return "❌ Error inesperado. Intente nuevamente."
                return mensaje_respuesta

    menu_comando_no_reconocido = mostrar_menu()
    return f"❌Comando no reconocido \n▪️ Por favor, elige una *opción*  {menu_comando_no_reconocido}\nEscribe el *Número* correspondiente para elegir."


def confirmar_carrito(
    pedido_id_redis: str,
    name: str,
    token: str,
    user_id,
    numero: str,
    direccion: str,
    productos_recibidos: list,
    cache,
    gestor_pedidos,
    gestor_productos,
    public_url: str,
) -> tuple:
    """Guarda el carrito validado, calcula su total y lo deja listo para confirmar."""
    productos = []
    total = 0.0

    for p in productos_recibidos:
        nombre_producto = p.get("nombre", "Producto desconocido")

        codigo = p.get("Codigo")
        if not codigo:
            logger.error("confirmar_carrito: producto sin código identificador")
            return False, "Producto sin código identificador"

        cantidad = p.get("cantidad", 1)
        if cantidad <= 0:
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

        productos.append({
            "nombre": nombre_producto,
            "cantidad": cantidad,
            "precio": precio_total,
            "codigo": codigo,
        })
        total += precio_total

    total = round(total, 2)

    pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(user_id)
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

    coords = geocodificar_direccion(direccion)
    lat, lng = (coords[0], coords[1]) if coords else (None, None)
    if not coords:
        logger.warning("confirmar_carrito: no se pudieron geocodificar las coordenadas del pedido %s", pedido_id_db)

    # Single atomic commit: redisID + coordinates + state transition to ENLACE2.
    gestor_pedidos.fijar_carrito_confirmado(pedido_id_db, pedido_id_redis, lat=lat, lng=lng)
    logger.info("CARRITO_CONFIRMADO pedido_id=%s", pedido_id_db)

    confirmacion_url = f"{public_url}/confirmacion_pago?pedido_id={pedido_id_redis}"
    return True, confirmacion_url
