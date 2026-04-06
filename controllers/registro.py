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
        self.redismanager = redismanager
        self.estado_usuario = EstadoUsuario(numero_cliente, redismanager)

    def _confirmar_direccion(self, mensaje_cliente, data_redis):
        """Confirma la dirección validada y completa el alta del usuario."""
        if mensaje_cliente.lower() != 'si':
            return False

        from container import gestor_usuarios, gestor_pedidos

        # H1: Guardia de idempotencia — evita duplicados por reintento de Meta
        if gestor_usuarios.obtener_usuario_completo(self.numero_cliente):
            logger.warning("REGISTRO_DUPLICADO usuario=%s — ya existe en DB", self.numero_cliente)
            self.redismanager.delete(self.numero_cliente)
            return "Usuario ya registrado", 200

        estado = data_redis
        # H5: Capturar excepciones de DB para evitar estado Redis inconsistente
        try:
            gestor_usuarios.guardar_usuario(self.numero_cliente, estado["nombre"], estado["direccion"])
            usuario_info = gestor_usuarios.obtener_usuario_completo(self.numero_cliente)
            if usuario_info:
                gestor_pedidos.iniciar_pedido(usuario_info["id"], estado["direccion"], self.numero_cliente)
            logger.info("REGISTRO_COMPLETADO usuario=%s", self.numero_cliente)
        except Exception as e:
            logger.error("REGISTRO_FALLIDO usuario=%s error=%s", self.numero_cliente, e)
            return "Error en registro", 200  # 200 para evitar reintento de Meta

        menu_despues_registro = mostrar_menu()
        _enviar_mensaje_registro(self.numero_cliente, estado["nombre"], menu_despues_registro)
        # H2: Limpiar estado Redis tras registro exitoso — evita estado fantasma
        self.redismanager.delete(self.numero_cliente)
        return "Usuario registrado", 200

    def manejar_registro(self, mensaje_cliente):
        """Avanza la máquina de estados del registro según el mensaje recibido."""
        # H8: Una sola lectura de Redis; estado_actual se extrae del mismo objeto
        estado_data = self.estado_usuario.obtener_estado()
        estado_actual = estado_data["estado"]

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
                # H4: Reset de Redis — el usuario puede empezar de nuevo en el futuro
                self.redismanager.delete(self.numero_cliente)
                _enviar_registro_pendiente(self.numero_cliente)
                return "Registro cancelado", 200

        elif estado_actual == EstadoRegistro.ESPERANDO_NOMBRE:
            nombre_limpio = mensaje_cliente.strip()  # H7: strip antes de validar y guardar
            if _es_nombre_valido(nombre_limpio):
                self.estado_usuario.actualizar_estado(EstadoRegistro.ESPERANDO_DIRECCION, {"nombre": nombre_limpio})
                _solicitar_direccion(self.numero_cliente)
                return "Solicitud de dirección enviada", 200
            else:
                logger.info("NOMBRE_INVALIDO usuario=%s input=%r", self.numero_cliente, mensaje_cliente)  # H10
                _enviar_nombre_invalido(self.numero_cliente)
                return "Nombre inválido", 200  # H3: 200 para evitar reintento de Meta

        elif estado_actual == EstadoRegistro.ESPERANDO_DIRECCION:
            validada, direccion_resultante, motivo = validar_direccion(mensaje_cliente)
            if validada:
                _enviar_confirmacion_direccion(self.numero_cliente, direccion_resultante)
                self.estado_usuario.actualizar_estado(EstadoRegistro.CONFIRMANDO_DIRECCION, {"direccion": direccion_resultante})
                return "Solicitud de confirmación de dirección enviada", 200
            else:
                logger.info("DIRECCION_INVALIDA usuario=%s motivo=%s input=%r", self.numero_cliente, motivo, mensaje_cliente)  # H10
                if motivo != "fuera_de_zona":
                    # H9: Proteger sugerir_calle ante fallos de la API de mapas
                    try:
                        sugerencia, alta_confianza = sugerir_calle(mensaje_cliente)
                    except Exception:
                        logger.warning("sugerir_calle falló para usuario=%s", self.numero_cliente, exc_info=True)
                        sugerencia, alta_confianza = None, None
                else:
                    sugerencia, alta_confianza = None, None
                _enviar_direccion_invalida(self.numero_cliente, sugerencia, alta_confianza)
                return "Dirección inválida", 200  # H3: 200 para evitar reintento de Meta

        elif estado_actual == EstadoRegistro.CONFIRMANDO_DIRECCION:
            logger.debug("data redis: %s", estado_data)  # H8: reutiliza estado ya leído
            if mensaje_cliente.lower() not in {"si", "sí", "no"}:
                _enviar_pedir_confirmacion(self.numero_cliente)
                return "Respuesta inválida en confirmación", 200
            respuesta = self._confirmar_direccion(mensaje_cliente, estado_data)
            if respuesta is False:
                self.estado_usuario.actualizar_estado(EstadoRegistro.ESPERANDO_DIRECCION)
                _enviar_reintentar_direccion(self.numero_cliente)
                return "paso atras", 200
            return respuesta


def manejar_registro(numero_cliente, mensaje_cliente, redismanager):
    """Punto de entrada del flujo de registro para mensajes entrantes."""
    registro_usuario = RegistroUsuario(numero_cliente, redismanager)
    return registro_usuario.manejar_registro(mensaje_cliente)
