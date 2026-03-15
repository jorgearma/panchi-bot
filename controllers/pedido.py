import json
import logging

from pydantic import ValidationError
from utils.es_pregunta import es_pregunta
from utils.crear_token import generar_enlace
from utils.mensajes import enviar_mensaje_whatsapp
from utils.menu_opciones import menu, limpiar_texto, mostrar_menu
from schemas.twilio import PedidoInput
from states import EstadoPedido

logger = logging.getLogger(__name__)


def procesar_pedido(pedido, numero_cliente, id_pedido_actual, usuario_datos):
    """
    Procesa un pedido realizado por un cliente y genera una respuesta adecuada.
    """
    try:
        # Validar los datos de entrada con Pydantic
        datos = PedidoInput(pedido=pedido, numero_cliente=numero_cliente, id_pedido_actual=id_pedido_actual)
        print(f"Datos validados: {datos}")

    except ValidationError as e:
        # Retornar errores de validación como respuesta
        return f"❌ Error en los datos de entrada:\n{e}"

    # Si los datos son válidos, continuar con el procesamiento
    from services import gestor_pedidos

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
                            return f"❕ {mensaje_respuesta} ❕\n\n🔗 *Enlace único*: {enlace}"
                        else:
                            gestor_pedidos.actualizar_estado(datos.id_pedido_actual, EstadoPedido.PENDIENTE)
                            return "❌ Ocurrió un error al procesar la opción. Intente nuevamente."

                    except Exception as e:
                        print(f"Error al generar el enlace: {e}")
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
    public_url: str,
) -> tuple:
    """
    Stores the assembled cart in Redis and transitions the order to ENLACE2.

    Returns (success: bool, redirect_url_or_error: str).
    The caller is responsible for obtaining pedido_id_redis (a UUID string)
    and passing all injected dependencies.
    """
    productos = []
    total = 0.0

    for p in productos_recibidos:
        nombre_producto = p.get("nombre", "Producto desconocido")
        cantidad = p.get("cantidad", 1)
        precio_unitario = p.get("precio_unitario", 0.0)
        codigo = p.get("Codigo")
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

    gestor_pedidos.guardar_redis_id(pedido_id_db, pedido_id_redis)

    if pedido_activo.Estado != EstadoPedido.ENLACE:
        logger.warning(
            "confirmar_carrito: cannot transition order %s from state '%s' to ENLACE2",
            pedido_id_db,
            pedido_activo.Estado,
        )
    else:
        gestor_pedidos.actualizar_estado(pedido_id_db, EstadoPedido.ENLACE2)

    confirmacion_url = f"{public_url}/confirmacion_pago?pedido_id={pedido_id_redis}"
    return True, confirmacion_url
