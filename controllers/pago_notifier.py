# Capa de notificación para el flujo de pago

from services.whatsapp_service import enviar_mensaje_whatsapp


def _enviar_confirmacion_efectivo(numero_cliente, nombre_cliente, total_euros,
                                   pedido_id, direccion_cliente):
    """Envía al cliente el resumen final de un pedido confirmado en efectivo."""
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
