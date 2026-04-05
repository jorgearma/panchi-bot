import logging
from container import gestor_pedidos, gestor_usuarios
from utils.menu_opciones import mostrar_menu
from controllers.pedido import procesar_pedido
from controllers.mensajes_registrados_notifier import (
    _enviar_error_usuario_no_encontrado,
    _enviar_error_sistema,
    _enviar_bienvenida_menu,
    _enviar_enlace_caducado,
    _enviar_enlace_pedido,
    _enviar_enlace_pago,
    _enviar_error_generico,
    _enviar_estado_en_curso,
    _enviar_respuesta_pedido,
)
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from tenacity import RetryError
from states import EstadoPedido

logger = logging.getLogger(__name__)


class ManejadorMensajesRegistrados:

    @staticmethod
    def _iniciar_pedido_y_enviar_menu(numero_cliente, usuario_datos):
        """Abre un pedido nuevo para el usuario y le envía el menú inicial."""

        id_usuario = usuario_datos["id"]
        direccion_usuario = usuario_datos["direccion"]
        nombre_usuario = usuario_datos["nombre"]

        try:
            gestor_pedidos.iniciar_pedido(id_usuario, direccion_usuario, numero_cliente)
        except (SQLAlchemyError, OperationalError) as error:
            logger.error("Error al iniciar el pedido para el usuario %s: %s", id_usuario, error)
            return "Error al procesar el pedido. Inténtalo más tarde.", 500

        menu_texto = mostrar_menu()
        _enviar_bienvenida_menu(nombre_usuario, menu_texto, numero_cliente)
        return "Mensaje enviado", 200

    @staticmethod
    def manejar_mensajes_registrados(numero_cliente, mensaje_cliente):
        """Orquesta la respuesta según el estado del pedido activo del usuario."""

        try:
            usuario_datos = gestor_usuarios.obtener_usuario_completo(numero_cliente)
            if not usuario_datos:
                logger.error("Error: No se encontraron datos para el usuario %s.", numero_cliente)
                _enviar_error_usuario_no_encontrado(numero_cliente)
                return "Error: Usuario no encontrado.", 404
            id_usuario = usuario_datos["id"]
        except (SQLAlchemyError, RetryError) as e:
            logger.error("Error al obtener el usuario tras varios intentos: %s", e)
            _enviar_error_sistema(numero_cliente)
            return "Error en la base de datos. Intente más tarde.", 500

        try:
            pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(id_usuario)
        except (SQLAlchemyError, RetryError) as e:
            logger.error("Error al obtener el pedido tras varios intentos: %s", e)
            _enviar_error_sistema(numero_cliente)
            return "Error en la base de datos. Intente más tarde.", 500

        if not pedido_activo:
            logger.info("Usuario %s sin pedido activo — iniciando nuevo pedido.", numero_cliente)
            return ManejadorMensajesRegistrados._iniciar_pedido_y_enviar_menu(numero_cliente, usuario_datos)

        estado_del_pedido = pedido_activo.Estado
        logger.debug("Estado del pedido: %s", estado_del_pedido)
        id_pedido_activo = pedido_activo.PedidoID

        if estado_del_pedido == EstadoPedido.PENDIENTE:
            mensaje = procesar_pedido(mensaje_cliente, numero_cliente, id_pedido_activo, usuario_datos)
            logger.debug("Mensaje procesado para usuario: %s", numero_cliente)
            _enviar_respuesta_pedido(mensaje, numero_cliente)
            return " mensaje enviado", 200

        if estado_del_pedido == EstadoPedido.ENLACE or estado_del_pedido == EstadoPedido.ENLACE2:
            enlace = pedido_activo.enlace
            if not enlace:
                _enviar_enlace_caducado(numero_cliente)
                return " mensaje enviado", 200
            _enviar_enlace_pedido(enlace, numero_cliente)
            return " mensaje enviado", 200

        if estado_del_pedido == EstadoPedido.CONFIRMANDO_PAGO:
            _enviar_enlace_pago(pedido_activo.enlace, numero_cliente)
            return " mensaje enviado", 200

        # Pedido activo (pagado, confirmado o en proceso) — bloquear nuevo pedido e informar al cliente
        if estado_del_pedido in (
            EstadoPedido.PAGADO,
            EstadoPedido.CONTRA_REEMBOLSO,
            EstadoPedido.EN_PREPARACION,
            EstadoPedido.PREPARADO,
            EstadoPedido.EN_REPARTO,
        ):
            logger.info(
                "Pedido %s en estado '%s' — bloqueando nuevo pedido para %s.",
                id_pedido_activo, estado_del_pedido, numero_cliente,
            )
            return _enviar_estado_en_curso(pedido_activo, numero_cliente)

        _enviar_error_generico(numero_cliente)
        return " mensaje enviado", 200
