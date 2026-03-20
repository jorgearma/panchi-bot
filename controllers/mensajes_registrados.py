import logging
import config
from services.whatsapp_service import enviar_mensaje_whatsapp
from services import gestor_pedidos, gestor_usuarios
from utils.menu_opciones import mostrar_menu
from controllers.pedido import procesar_pedido
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from tenacity import RetryError
from states import EstadoPedido

logger = logging.getLogger(__name__)


class ManejadorMensajesRegistrados:

    @staticmethod
    def _iniciar_pedido_y_enviar_menu(numero_cliente, usuario_datos):
        """Inicia un nuevo pedido en BD y envía el menú al usuario por WhatsApp."""

        id_usuario = usuario_datos["id"]
        direccion_usuario = usuario_datos["direccion"]
        nombre_usuario = usuario_datos["nombre"]

        try:
            gestor_pedidos.iniciar_pedido(id_usuario, direccion_usuario, numero_cliente)
        except (SQLAlchemyError, OperationalError) as error:
            logger.error("Error al iniciar el pedido para el usuario %s: %s", id_usuario, error)
            return "Error al procesar el pedido. Inténtalo más tarde.", 500

        menu_texto = mostrar_menu()
        enviar_mensaje_whatsapp(
            f"¡Hola *{nombre_usuario}*! 🙂 {menu_texto} \nescribe el *numero* para elegir ",
            numero_cliente
        )
        return "Mensaje enviado", 200

    @staticmethod
    def _responder_pedido_en_curso(pedido_activo, numero_cliente):
        """
        Informa al cliente sobre su pedido activo en preparación o reparto.
        Bloquea cualquier intento de iniciar un nuevo pedido.
        """
        estado = pedido_activo.Estado
        soporte = config.CUSTOMER_SUPPORT_PHONE or "atención al cliente"

        if estado == EstadoPedido.PAGADO:
            mensaje = (
                "Hemos recibido tu pedido y el pago se ha confirmado. ✅\n"
                "En breve nuestro equipo comenzará a prepararlo.\n"
                f"Si necesitas ayuda, contacta con atención al cliente: {soporte}."
            )

        elif estado == EstadoPedido.CONTRA_REEMBOLSO:
            mensaje = (
                "Tu pedido ha sido confirmado. ✅\n"
                "El pago se realizará a la entrega.\n"
                "En breve nuestro equipo comenzará a prepararlo.\n"
                f"Si necesitas ayuda, contacta con atención al cliente: {soporte}."
            )

        elif estado in (EstadoPedido.EN_PREPARACION, EstadoPedido.PREPARADO):
            mensaje = (
                "Tu pedido ya está en preparación. 🛒\n"
                "Ahora mismo nuestro equipo lo está preparando en almacén.\n"
                f"Si necesitas ayuda, contacta con atención al cliente: {soporte}."
            )

        elif estado == EstadoPedido.EN_REPARTO:
            reparto = pedido_activo.reparto
            repartidor = reparto.repartidor if reparto else None
            if repartidor:
                nombre = f"{repartidor.Nombre} {repartidor.Apellido}".strip()
                telefono = repartidor.Telefono or "no disponible"
                mensaje = (
                    "Tu pedido está en camino. 🚚\n"
                    f"Repartidor asignado: {nombre}.\n"
                    f"Teléfono del repartidor: {telefono}.\n"
                    f"Si necesitas ayuda adicional, contacta con atención al cliente: {soporte}."
                )
            else:
                mensaje = (
                    "Tu pedido está en camino. 🚚\n"
                    f"Si necesitas ayuda, contacta con atención al cliente: {soporte}."
                )

        else:
            logger.warning(
                "_responder_pedido_en_curso llamado con estado inesperado: %s (pedido %s)",
                estado, pedido_activo.PedidoID,
            )
            return None

        enviar_mensaje_whatsapp(mensaje, numero_cliente)
        return "mensaje enviado", 200

    @staticmethod
    def manejar_mensajes_registrados(numero_cliente, mensaje_cliente):

        try:
            usuario_datos = gestor_usuarios.obtener_usuario_completo(numero_cliente)
            if not usuario_datos:  # No se encontraron datos para el usuario.
                logger.error("Error: No se encontraron datos para el usuario %s.", numero_cliente)
                enviar_mensaje_whatsapp(
                    "Lo sentimos, no pudimos encontrar su información. Por favor, intente más tarde.",
                    numero_cliente
                )
                return "Error: Usuario no encontrado.", 404
            id_usuario = usuario_datos["id"]
        except (SQLAlchemyError, RetryError) as e:
            logger.error("Error al obtener el usuario tras varios intentos: %s", e)
            enviar_mensaje_whatsapp(
                "Lo sentimos, se presentó un error en el sistema. Por favor, intente más tarde.",
                numero_cliente
            )
            return "Error en la base de datos. Intente más tarde.", 500

        try:
            pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(id_usuario)
        except (SQLAlchemyError, RetryError) as e:
            logger.error("Error al obtener el pedido tras varios intentos: %s", e)
            enviar_mensaje_whatsapp(
                "Lo sentimos, se presentó un error en el sistema. Por favor, intente más tarde.",
                numero_cliente
            )
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
            enviar_mensaje_whatsapp(mensaje, numero_cliente)
            return " mensaje enviado", 200

        if estado_del_pedido == EstadoPedido.ENLACE or estado_del_pedido == EstadoPedido.ENLACE2:
            enlace = pedido_activo.enlace
            if not enlace:
                enviar_mensaje_whatsapp(
                    "Tu enlace de pedido ha caducado ⏱️\n"
                    "Escribe *1* para generar un nuevo enlace y continuar tu pedido.",
                    numero_cliente,
                )
                return " mensaje enviado", 200
            mensaje = f"Puede continuar con su pedido en el *enlace* proporcionado \n\n▪*Enlace* unico 👇 \n\n🔗{(enlace)}"
            enviar_mensaje_whatsapp(mensaje, numero_cliente)
            return " mensaje enviado", 200

        if estado_del_pedido == EstadoPedido.CONFIRMANDO_PAGO:
            enlace_pago = pedido_activo.enlace
            enviar_mensaje_whatsapp(f"🔗 {enlace_pago}\n ✅ Pago seguro  con *MONEI*", numero_cliente)
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
            return ManejadorMensajesRegistrados._responder_pedido_en_curso(pedido_activo, numero_cliente)

        enviar_mensaje_whatsapp("Lo sentimos, no pudimos procesar su mensaje. Por favor, intente más tarde.", numero_cliente)
        return " mensaje enviado", 200
