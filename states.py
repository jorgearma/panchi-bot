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
    # Flujo de compra (bot → pago)
    PENDIENTE = "Pendiente"
    ENLACE = "enlace"
    ENLACE2 = "enlace2"
    CONFIRMANDO_PAGO = "confirmando-pago"
    PAGADO = "pagado"
    # Flujo operativo (almacén → reparto)
    EN_PREPARACION = "en_preparacion"
    PREPARADO = "preparado"
    EN_REPARTO = "en_reparto"
    ENTREGADO = "entregado"
    # Estados de cancelación
    CANCELADO = "cancelado"
    REEMBOLSADO = "reembolsado"

    def __str__(self):
        return self.value


# Estados que indican que el pedido ya no está activo para el cliente
ESTADOS_TERMINALES_PEDIDO = {
    EstadoPedido.ENTREGADO,
    EstadoPedido.CANCELADO,
    EstadoPedido.REEMBOLSADO,
}


class EstadoPicking(str, Enum):
    PENDIENTE = "pendiente"
    EN_PROCESO = "en_proceso"
    COMPLETADO = "completado"
    CON_INCIDENCIAS = "con_incidencias"
    CANCELADO = "cancelado"

    def __str__(self):
        return self.value


class EstadoReparto(str, Enum):
    PENDIENTE = "pendiente"
    ASIGNADO = "asignado"
    EN_CAMINO = "en_camino"
    ENTREGADO = "entregado"
    NO_ENTREGADO = "no_entregado"
    CANCELADO = "cancelado"

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

# Transiciones válidas del flujo completo de pedido.
# ENLACE → PENDIENTE es rollback por error interno (menu.py), no flujo de usuario.
# ENLACE2 → ENLACE es navegación UI (botón "atrás" en confirmacion_pago.html).
TRANSICIONES_PEDIDO: dict = {
    EstadoPedido.PENDIENTE:         [EstadoPedido.ENLACE, EstadoPedido.CANCELADO],
    EstadoPedido.ENLACE:            [EstadoPedido.ENLACE2, EstadoPedido.PENDIENTE, EstadoPedido.CANCELADO],
    EstadoPedido.ENLACE2:           [EstadoPedido.CONFIRMANDO_PAGO, EstadoPedido.ENLACE],
    EstadoPedido.CONFIRMANDO_PAGO:  [EstadoPedido.PAGADO, EstadoPedido.CANCELADO],
    EstadoPedido.PAGADO:            [EstadoPedido.EN_PREPARACION, EstadoPedido.REEMBOLSADO],
    EstadoPedido.EN_PREPARACION:    [EstadoPedido.PREPARADO, EstadoPedido.CANCELADO],
    EstadoPedido.PREPARADO:         [EstadoPedido.EN_REPARTO],
    EstadoPedido.EN_REPARTO:        [EstadoPedido.ENTREGADO],
    EstadoPedido.ENTREGADO:         [],
    EstadoPedido.CANCELADO:         [EstadoPedido.REEMBOLSADO],
    EstadoPedido.REEMBOLSADO:       [],
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
