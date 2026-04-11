# Orquestador de la máquina de estados de registro
import logging
import re
from maps_module import validar_direccion, sugerir_calle
from managers.estado_usuario import EstadoUsuario
from services.whatsapp_service import enviar_mensaje_whatsapp
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

RESPUESTAS_POSITIVAS = {
    "si", "sí", "vale", "ok", "okey", "esta bien", "está bien",
    "claro", "perfecto", "de acuerdo", "correcto", "exacto", "bueno", "sip",
}


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
        if mensaje_cliente.lower() not in RESPUESTAS_POSITIVAS:
            return False

        from container import gestor_usuarios, gestor_pedidos

        estado = data_redis

        # Guardia de integridad: nombre y dirección deben estar en Redis.
        # Por flujo normal es imposible llegar aquí sin ellos, pero si Redis
        # estuviera corrupto un KeyError daría 500 silencioso y el usuario
        # quedaría bloqueado sin poder avanzar ni retroceder.
        if not estado.get("nombre") or not estado.get("direccion"):
            logger.error(
                "ESTADO_REDIS_CORRUPTO usuario=%s — faltan campos en CONFIRMANDO_DIRECCION: %s",
                self.numero_cliente, list(estado.keys()),
            )
            self.estado_usuario.eliminar_estado()
            enviar_mensaje_whatsapp(
                "Ha ocurrido un problema con tu registro. Por favor, escríbenos de nuevo para empezar.",
                self.numero_cliente,
            )
            return "Estado Redis corrupto — registro reiniciado", 200

        # H1: Guardia de idempotencia — el usuario ya existe en DB.
        # Puede ser un duplicado real (reintento de Meta) o una recuperación de
        # fallo parcial (guardar_usuario OK pero iniciar_pedido falló antes).
        # Distinguimos comprobando si ya tiene pedido activo.
        try:
            usuario_existente = gestor_usuarios.obtener_usuario_completo(self.numero_cliente)
        except Exception as e:
            logger.error("ERROR_BD_CONFIRMACION usuario=%s error=%s", self.numero_cliente, e)
            enviar_mensaje_whatsapp(
                "Ha ocurrido un problema al verificar tu registro. Por favor, escríbenos de nuevo.",
                self.numero_cliente,
            )
            return "Error en BD al confirmar registro", 200
        if usuario_existente:
            if not gestor_pedidos.hay_pedido_pendiente(usuario_existente["id"]):
                # Recuperación: usuario en DB sin pedido — crear pedido y avisar
                logger.warning(
                    "REGISTRO_PARCIAL_RECUPERADO usuario=%s — creando pedido faltante",
                    self.numero_cliente,
                )
                try:
                    gestor_pedidos.iniciar_pedido(
                        usuario_existente["id"], estado["direccion"], self.numero_cliente
                    )
                except Exception as e:
                    logger.error(
                        "RECUPERACION_FALLIDA usuario=%s error=%s", self.numero_cliente, e
                    )
                    self.estado_usuario.eliminar_estado()
                    enviar_mensaje_whatsapp(
                        "Ha habido un problema técnico con tu registro. Escríbenos de nuevo y lo resolvemos.",
                        self.numero_cliente,
                    )
                    return "Error en registro", 200
            else:
                logger.warning("REGISTRO_DUPLICADO usuario=%s — ya existe en DB con pedido", self.numero_cliente)

            menu_despues_registro = mostrar_menu()
            _enviar_mensaje_registro(self.numero_cliente, usuario_existente["nombre"], menu_despues_registro)
            self.estado_usuario.eliminar_estado()
            return "Usuario ya registrado", 200

        # Caso normal: usuario nuevo — guardar primero, luego crear pedido
        try:
            usuario_id = gestor_usuarios.guardar_usuario(self.numero_cliente, estado["nombre"], estado["direccion"])
        except Exception as e:
            logger.error("REGISTRO_FALLIDO_GUARDAR usuario=%s error=%s", self.numero_cliente, e)
            return "Error en registro", 200  # Redis queda en CONFIRMANDO_DIRECCION → reintento posible

        try:
            gestor_pedidos.iniciar_pedido(usuario_id, estado["direccion"], self.numero_cliente)
        except Exception as e:
            # Usuario guardado pero pedido no creado. El próximo "si" del usuario
            # entrará por la rama de recuperación de la guardia de idempotencia.
            logger.error(
                "REGISTRO_PARCIAL usuario=%s — usuario guardado, pedido no creado: %s",
                self.numero_cliente, e,
            )

        logger.info("REGISTRO_COMPLETADO usuario=%s", self.numero_cliente)
        menu_despues_registro = mostrar_menu()
        _enviar_mensaje_registro(self.numero_cliente, estado["nombre"], menu_despues_registro)
        # H2: Limpiar estado Redis tras registro exitoso — evita estado fantasma
        self.estado_usuario.eliminar_estado()
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
                self.estado_usuario.eliminar_estado()
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
            if mensaje_cliente.lower() not in RESPUESTAS_POSITIVAS | {"no"}:
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
