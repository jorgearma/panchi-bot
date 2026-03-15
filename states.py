from enum import Enum


class EstadoRegistro(str, Enum):
    SALUDO_INICIAL = "saludo_inicial"
    ESPERANDO_CONFIRMACION = "esperando_confirmacion"
    ESPERANDO_NOMBRE = "esperando_nombre"
    ESPERANDO_DIRECCION = "esperando_direccion"
    CONFIRMANDO_DIRECCION = "confirmando_direccion"

    def __str__(self):
        return self.value


class EstadoPedido(str, Enum):
    PENDIENTE = "Pendiente"
    ENLACE = "enlace"
    ENLACE2 = "enlace2"
    CONFIRMANDO_PAGO = "confirmando-pago"
    PAGADO = "pagado"

    def __str__(self):
        return self.value


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
# ENLACE → PENDIENTE es rollback por error interno (menu.py), no flujo de usuario.
# ENLACE2 → ENLACE es navegación UI (botón "atrás" en confirmacion_pago.html).
# PAGADO es estado terminal.
TRANSICIONES_PEDIDO: dict = {
    EstadoPedido.PENDIENTE: [EstadoPedido.ENLACE],
    EstadoPedido.ENLACE: [EstadoPedido.ENLACE2, EstadoPedido.PENDIENTE],
    EstadoPedido.ENLACE2: [EstadoPedido.CONFIRMANDO_PAGO, EstadoPedido.ENLACE],  # ENLACE = botón atrás
    EstadoPedido.CONFIRMANDO_PAGO: [EstadoPedido.PAGADO],
    EstadoPedido.PAGADO: [],
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
