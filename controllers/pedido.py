import logging

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from utils.es_pregunta import es_pregunta
from container import gestor_pedidos
from services.token_service import generar_enlace
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
        logger.info("PREGUNTA_DETECTADA usuario=%s input=%r", numero_cliente, datos.pedido)
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
                        pedido_actual = gestor_pedidos.obtener_pedido(datos.id_pedido_actual)
                        if not pedido_actual or pedido_actual.Estado != EstadoPedido.PENDIENTE:
                            logger.warning(
                                "procesar_pedido: pedido %s en estado inesperado, no se genera enlace",
                                datos.id_pedido_actual,
                            )
                            return "❌ Ocurrió un error al procesar la opción. Intente nuevamente."
                        enlace = generar_enlace(item, usuario_datos)
                        if not gestor_pedidos.iniciar_enlace(datos.id_pedido_actual, enlace):
                            return "❌ Ocurrió un error al procesar la opción. Intente nuevamente."
                        logger.info(
                            "PEDIDO_INICIADO pedido_id=%s usuario=%s",
                            datos.id_pedido_actual, datos.numero_cliente,
                        )
                        return f"❕ {mensaje_respuesta} ❕\n\n🔗 *Enlace único*: {enlace}"
                    except (ValueError, SQLAlchemyError, OperationalError) as e:
                        logger.error("Error al generar el enlace [%s]: %s", type(e).__name__, e)
                        return "❌ Error inesperado. Intente nuevamente."
                return mensaje_respuesta

    logger.info("COMANDO_NO_RECONOCIDO usuario=%s input=%r", numero_cliente, pedido_limpio)
    menu_comando_no_reconocido = mostrar_menu()
    return f"❌Comando no reconocido \n▪️ Por favor, elige una *opción*  {menu_comando_no_reconocido}\nEscribe el *Número* correspondiente para elegir."
