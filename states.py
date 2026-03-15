from enum import Enum


class EstadoRegistro(str, Enum):
    SALUDO_INICIAL = "saludo_inicial"
    ESPERANDO_CONFIRMACION = "esperando_confirmacion"
    ESPERANDO_NOMBRE = "esperando_nombre"
    ESPERANDO_DIRECCION = "esperando_direccion"
    CONFIRMANDO_DIRECCION = "confirmando_direccion"


class EstadoPedido(str, Enum):
    PENDIENTE = "Pendiente"
    ENLACE = "enlace"
    ENLACE2 = "enlace2"
    CONFIRMANDO_PAGO = "confirmando-pago"
    PAGADO = "pagado"


# Transiciones válidas del flujo de registro.
# La transición terminal confirmando_direccion → [registrado en DB] es implícita
# (el controlador borra la clave de Redis y persiste el usuario).
TRANSICIONES_REGISTRO: dict = {
    EstadoRegistro.SALUDO_INICIAL: [EstadoRegistro.ESPERANDO_CONFIRMACION],
    EstadoRegistro.ESPERANDO_CONFIRMACION: [EstadoRegistro.ESPERANDO_NOMBRE],
    EstadoRegistro.ESPERANDO_NOMBRE: [EstadoRegistro.ESPERANDO_DIRECCION],
    EstadoRegistro.ESPERANDO_DIRECCION: [EstadoRegistro.CONFIRMANDO_DIRECCION],
    EstadoRegistro.CONFIRMANDO_DIRECCION: [EstadoRegistro.ESPERANDO_DIRECCION],  # rollback si el usuario corrige
}

# Transiciones válidas del flujo de pedido/pago.
# Las transiciones de retroceso (*) son navegación UI (botón "atrás"), no flujo de usuario normal.
# TODO (deuda UX): PAGADO → ENLACE no debería ser posible; el pedido ya fue cobrado.
#   Mientras ver_comandas.html siga llamando a /api/cambiar_estado_a_enlace hay que permitirlo.
TRANSICIONES_PEDIDO: dict = {
    EstadoPedido.PENDIENTE: [EstadoPedido.ENLACE],
    EstadoPedido.ENLACE: [EstadoPedido.ENLACE2, EstadoPedido.PENDIENTE],  # PENDIENTE = rollback por error interno
    EstadoPedido.ENLACE2: [EstadoPedido.CONFIRMANDO_PAGO, EstadoPedido.ENLACE],  # * ENLACE = botón atrás
    EstadoPedido.CONFIRMANDO_PAGO: [EstadoPedido.PAGADO],
    EstadoPedido.PAGADO: [EstadoPedido.ENLACE],  # * botón atrás desde ver_comandas.html (deuda UX)
}


def transicion_valida_pedido(estado_actual: str, nuevo_estado: str) -> bool:
    """Devuelve True si estado_actual → nuevo_estado está en TRANSICIONES_PEDIDO."""
    try:
        origen = EstadoPedido(estado_actual)
    except ValueError:
        return False
    return nuevo_estado in TRANSICIONES_PEDIDO.get(origen, [])


def transicion_valida_registro(estado_actual: str, nuevo_estado: str) -> bool:
    """Devuelve True si estado_actual → nuevo_estado está en TRANSICIONES_REGISTRO."""
    try:
        origen = EstadoRegistro(estado_actual)
    except ValueError:
        return False
    return nuevo_estado in TRANSICIONES_REGISTRO.get(origen, [])
