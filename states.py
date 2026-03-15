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
# ENLACE → PENDIENTE es un rollback de error interno (menu.py), no un flujo de usuario.
# PAGADO es estado terminal.
TRANSICIONES_PEDIDO: dict = {
    EstadoPedido.PENDIENTE: [EstadoPedido.ENLACE],
    EstadoPedido.ENLACE: [EstadoPedido.ENLACE2, EstadoPedido.PENDIENTE],
    EstadoPedido.ENLACE2: [EstadoPedido.CONFIRMANDO_PAGO],
    EstadoPedido.CONFIRMANDO_PAGO: [EstadoPedido.PAGADO],
    EstadoPedido.PAGADO: [],
}
