# Orquestador de la máquina de estados de registro
import logging
import re
from maps_module import validar_direccion, sugerir_calle
from managers.estado_usuario import EstadoUsuario
from states import EstadoRegistro
from utils.menu_opciones import mostrar_menu
from controllers.registro_notifier import (
    _enviar_bienvenida,
    _solicitar_nombre,
    _solicitar_direccion,
    _enviar_confirmacion_direccion,
    _enviar_direccion_invalida,
    _enviar_mensaje_registro,
    _enviar_nombre_invalido,
    _enviar_registro_pendiente,
    _enviar_pedir_confirmacion,
    _enviar_reintentar_direccion,
)

logger = logging.getLogger(__name__)





def confirmar_direccion(numero_cliente, mensaje_cliente, data_redis):
    """Confirma la dirección validada y completa el alta del usuario."""
    if mensaje_cliente.lower() == 'si':
        from container import gestor_usuarios, gestor_pedidos
        estado = data_redis
        gestor_usuarios.guardar_usuario(numero_cliente, estado["nombre"], estado["direccion"])
        logger.info("REGISTRO_COMPLETADO usuario=%s", numero_cliente)
        menu_despues_registro = mostrar_menu()
        _enviar_mensaje_registro(numero_cliente, estado["nombre"], menu_despues_registro)
        usuario_info = gestor_usuarios.obtener_usuario_completo(numero_cliente)
        if usuario_info:
            gestor_pedidos.iniciar_pedido(usuario_info["id"], estado["direccion"], numero_cliente)
        return "Usuario registrado", 200
    else:
        return False

def _es_nombre_valido(nombre):
    """Valida nombres simples permitiendo letras, espacios y apellidos compuestos."""
    nombre = nombre.strip()
    if len(nombre) < 2 or len(nombre) > 60:
        return False
    return bool(re.match(r"^[A-Za-zÁÉÍÓÚáéíóúÜüÑñ\s'\-]+$", nombre))


class RegistroUsuario:
    """Orquesta el registro conversacional del usuario usando estado en Redis."""
    def __init__(self, numero_cliente, redismanager):
        """Prepara el gestor de estado para un número concreto de WhatsApp."""
        self.numero_cliente = numero_cliente
        self.estado_usuario = EstadoUsuario(numero_cliente, redismanager)

    def manejar_registro(self, mensaje_cliente):
        """Avanza la máquina de estados del registro según el mensaje recibido."""
        # Se obtiene el estado actual del usuario desde Redis.
        estado_actual = self.estado_usuario.obtener_estado()["estado"]

        if estado_actual == EstadoRegistro.SALUDO_INICIAL:
            _enviar_bienvenida(self.numero_cliente)
            self.estado_usuario.actualizar_estado(EstadoRegistro.ESPERANDO_CONFIRMACION)
            return "Mensaje de bienvenida enviado", 200

        elif estado_actual == EstadoRegistro.ESPERANDO_CONFIRMACION:
            if mensaje_cliente.lower() in {"sí", "si", "quiero", "adelante"}:
                _solicitar_nombre(self.numero_cliente)
                self.estado_usuario.actualizar_estado(EstadoRegistro.ESPERANDO_NOMBRE)
                return "Solicitud de nombre enviada", 200
            else:
                _enviar_registro_pendiente(self.numero_cliente)
                return "Registro cancelado", 200

        elif estado_actual == EstadoRegistro.ESPERANDO_NOMBRE:
            if _es_nombre_valido(mensaje_cliente):
                self.estado_usuario.actualizar_estado(EstadoRegistro.ESPERANDO_DIRECCION, {"nombre": mensaje_cliente})
                _solicitar_direccion(self.numero_cliente)
                return "Solicitud de dirección enviada", 200
            else:
                _enviar_nombre_invalido(self.numero_cliente)
                return "Nombre inválido", 400

        elif estado_actual == EstadoRegistro.ESPERANDO_DIRECCION:
            validada, direccion_resultante, motivo = validar_direccion(mensaje_cliente)
            if validada:
                _enviar_confirmacion_direccion(self.numero_cliente, direccion_resultante)
                self.estado_usuario.actualizar_estado(EstadoRegistro.CONFIRMANDO_DIRECCION, {"direccion": direccion_resultante})
                return "Solicitud de confirmación de dirección enviada", 200
            else:
                if motivo != "fuera_de_zona":
                    sugerencia, alta_confianza = sugerir_calle(mensaje_cliente)
                else:
                    sugerencia, alta_confianza = None, None
                _enviar_direccion_invalida(self.numero_cliente, sugerencia, alta_confianza)
                return "Dirección inválida", 400

        elif estado_actual == EstadoRegistro.CONFIRMANDO_DIRECCION:
            data_redis = self.estado_usuario.obtener_estado()
            logger.debug("data redis: %s", data_redis)
            if mensaje_cliente.lower() not in {"si", "sí", "no"}:
                _enviar_pedir_confirmacion(self.numero_cliente)
                return "Respuesta inválida en confirmación", 200
            respuesta = confirmar_direccion(self.numero_cliente, mensaje_cliente, data_redis)
            if respuesta is False:
                self.estado_usuario.actualizar_estado(EstadoRegistro.ESPERANDO_DIRECCION)
                _enviar_reintentar_direccion(self.numero_cliente)
                return "paso atras", 200

            return respuesta

def manejar_registro(numero_cliente, mensaje_cliente, redismanager):
    """Punto de entrada del flujo de registro para mensajes entrantes."""
    registro_usuario = RegistroUsuario(numero_cliente, redismanager)
    return registro_usuario.manejar_registro(mensaje_cliente)
