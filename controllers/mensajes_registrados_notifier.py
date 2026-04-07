# Capa de notificación para el flujo de mensajes de usuarios registrados
# Responsable de todos los mensajes WhatsApp sobre el estado del pedido

import logging
import config
from sqlalchemy.orm.exc import DetachedInstanceError
from services.whatsapp_service import enviar_mensaje_whatsapp
from states import EstadoPedido

logger = logging.getLogger(__name__)


def _enviar_respuesta_pedido(mensaje, numero_cliente):
    """Envía al cliente la respuesta generada por el procesador de pedido."""
    enviar_mensaje_whatsapp(mensaje, numero_cliente)


def _enviar_error_usuario_no_encontrado(numero_cliente):
    """Informa que no se pudo recuperar el perfil del usuario registrado."""
    enviar_mensaje_whatsapp(
        "Lo sentimos, no pudimos encontrar su información. Por favor, intente más tarde.",
        numero_cliente
    )


def _enviar_error_sistema(numero_cliente):
    """Informa de un fallo temporal del sistema durante la atención."""
    enviar_mensaje_whatsapp(
        "Lo sentimos, se presentó un error en el sistema. Por favor, intente más tarde.",
        numero_cliente
    )


def _enviar_bienvenida_menu(nombre_usuario, menu_texto, numero_cliente):
    """Saluda al usuario registrado y le vuelve a mostrar el menú disponible."""
    enviar_mensaje_whatsapp(
        f"¡Hola *{nombre_usuario}*! 🙂 {menu_texto} \nescribe el *numero* para elegir ",
        numero_cliente
    )


def _enviar_enlace_caducado(numero_cliente):
    """Explica que el enlace anterior ya no sirve y cómo generar uno nuevo."""
    enviar_mensaje_whatsapp(
        "Tu enlace de pedido ha caducado ⏱️\n"
        "Escribe *1* para generar un nuevo enlace y continuar tu pedido.",
        numero_cliente,
    )


def _enviar_enlace_pedido(enlace, numero_cliente):
    """Reenvía el enlace activo del pedido cuando el cliente lo solicita."""
    enviar_mensaje_whatsapp(
        f"Puede continuar con su pedido en el *enlace* proporcionado \n\n▪*Enlace* unico 👇 \n\n🔗{enlace}",
        numero_cliente
    )


def _enviar_enlace_pago(enlace_pago, numero_cliente):
    """Reenvía el enlace de pago cuando el pedido sigue pendiente de cobro."""
    enviar_mensaje_whatsapp(
        f"🔗 {enlace_pago}\n ✅ Pago seguro  con *MONEI*",
        numero_cliente
    )


def _enviar_error_generico(numero_cliente):
    """Devuelve un mensaje neutro cuando no se pudo procesar la solicitud."""
    enviar_mensaje_whatsapp(
        "Lo sentimos, no pudimos procesar su mensaje. Por favor, intente más tarde.",
        numero_cliente
    )


def _enviar_estado_en_curso(pedido_activo, numero_cliente):
    """Explica el estado actual del pedido para evitar duplicar pedidos activos."""
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
        try:
            reparto = pedido_activo.reparto
            repartidor = reparto.repartidor if reparto else None
        except DetachedInstanceError:
            logger.warning(
                "_enviar_estado_en_curso: sesión cerrada al acceder a reparto del pedido %s",
                pedido_activo.PedidoID,
            )
            repartidor = None
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
            "_enviar_estado_en_curso llamado con estado inesperado: %s (pedido %s)",
            estado, pedido_activo.PedidoID,
        )
        return None

    enviar_mensaje_whatsapp(mensaje, numero_cliente)
    return "mensaje enviado", 200
