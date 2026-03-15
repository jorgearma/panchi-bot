# /services/registro_usuario.py
import logging
from services.twilio_service import enviar_mensaje_whatsapp
from services.maps_service import validar_direccion
from managers.estado_usuario import EstadoUsuario
from states import EstadoRegistro
from utils.menu_opciones import mostrar_menu

logger = logging.getLogger(__name__)







def _enviar_mensaje_registro(numero_cliente, nombre, menu_despues_registro):
    mensaje = (f"¡Gracias {nombre}! Ahora estás registrado. {menu_despues_registro} "
               "\nescribe el *numero* para elegir\n  "
               )
    enviar_mensaje_whatsapp(mensaje, numero_cliente)


def confirmar_direccion(numero_cliente, mensaje_cliente, data_redis):
    if mensaje_cliente.lower() == 'si':
        from services import gestor_usuarios, gestor_pedidos
        estado = data_redis
        gestor_usuarios.guardar_usuario(numero_cliente, estado["nombre"], estado["direccion"])
        menu_despues_registro = mostrar_menu()
        _enviar_mensaje_registro(numero_cliente, estado["nombre"], menu_despues_registro)
        usuario_info = gestor_usuarios.obtener_usuario_completo(numero_cliente)
        if usuario_info:
            gestor_pedidos.iniciar_pedido(usuario_info["id"], estado["direccion"], numero_cliente)
        return "Usuario registrado", 200
    else:
        return False


def _enviar_bienvenida(numero_cliente):
    enviar_mensaje_whatsapp(
        "*Registro en el Sistema*💻\n\n"
        "¡Hola!👋 Aun no estás registrado en nuestro sistema. "
        "¿Te gustaría continuar con tu registro? 📝\n\n"
        "▪️Escribe: *Si*",
        numero_cliente
    )


def _enviar_cancelacion_registro(numero_cliente):
    enviar_mensaje_whatsapp(
        "No se ha realizado el registro , escriba si para continuar. 😊",
        numero_cliente
    )


def _solicitar_nombre(numero_cliente):
    enviar_mensaje_whatsapp(
        "▪️ *Registro de Usuario* 👤\n\nEscribe tu 🫵 *Nombre* \nPara continuar",
        numero_cliente
    )


def _solicitar_direccion(numero_cliente):
    enviar_mensaje_whatsapp(
        "📍 *Registro de Dirección* 📍\n\nGracias. Ahora, por favor envía tu *Dirección Completa* 🏠.\n\n"
        "👇 *Ejemplos:* 👇 \n\n🔹_Calle Labradores, 3, 1B_\n🔹_Avenida Pablo Iglesias, 79, 1B_\n\n",
        numero_cliente
    )


def _enviar_confirmacion_direccion(numero_cliente, direccion):
    enviar_mensaje_whatsapp(
        f"{direccion} \n\n ⬆️ *Verifica tu Ubicación* ⬆️\n\n"
        "👉 *Escribe:* *Si* para confirmar\n"
        "👉 *Escribe:* *No* para corregir\n\n",
        numero_cliente
    )


def _enviar_direccion_invalida(numero_cliente):
    enviar_mensaje_whatsapp(
        "⛔ *La dirección no es válida* ⛔\n\nPor favor, revisa los *detalles* 📝.\n"
        "¡Gracias por tu ayuda! 😊 \n\n 👇 *Ejemplos:* 👇 \n\n"
        "•_Calle Los Labradores 3, 1B_\n•_Avenida Pablo Iglesias 79, 1B_",
        numero_cliente
    )

_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load("es_core_news_sm")
    return _nlp


def _es_nombre_valido(nombre):
    doc = _get_nlp()(nombre)
    for ent in doc.ents:
        if ent.label_ == "PER":
            return True
    return False


def _validar_y_confirmar_direccion(numero_cliente, direccion):
    validar, direccion_resultante = validar_direccion(direccion)
    if validar:
        _enviar_confirmacion_direccion(numero_cliente, direccion_resultante)
        return direccion_resultante
    else:
        _enviar_direccion_invalida(numero_cliente)
        return None

class RegistroUsuario:
    """Clase principal para gestionar el registro del usuario usando Redis."""
    def __init__(self, numero_cliente, redismanager):
        self.numero_cliente = numero_cliente
        self.estado_usuario = EstadoUsuario(numero_cliente, redismanager)

    def manejar_registro(self, mensaje_cliente):
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
                _enviar_cancelacion_registro(self.numero_cliente)
                return "Registro cancelado", 200

        elif estado_actual == EstadoRegistro.ESPERANDO_NOMBRE:
            if _es_nombre_valido(mensaje_cliente):
                self.estado_usuario.actualizar_estado(EstadoRegistro.ESPERANDO_DIRECCION, {"nombre": mensaje_cliente})
                _solicitar_direccion(self.numero_cliente)
                return "Solicitud de dirección enviada", 200
            else:
                enviar_mensaje_whatsapp(
                    "⛔ *El nombre ingresado no es válido* ⛔\n\nPor favor, escribe tu *Nombre Completo* 📝.\n"
                    "Ejemplo: _Juan Pérez_ o _María López_",
                    self.numero_cliente
                )
                return "Nombre inválido", 400

        elif estado_actual == EstadoRegistro.ESPERANDO_DIRECCION:
            direccion_validada = _validar_y_confirmar_direccion(self.numero_cliente, mensaje_cliente)
            if direccion_validada:
                # Se actualiza el estado en Redis guardando la dirección validada
                self.estado_usuario.actualizar_estado(EstadoRegistro.CONFIRMANDO_DIRECCION, {"direccion": direccion_validada})
                return "Solicitud de confirmación de dirección enviada", 200
            else:
                return "Dirección inválida", 400

        elif estado_actual == EstadoRegistro.CONFIRMANDO_DIRECCION:
            data_redis = self.estado_usuario.obtener_estado()
            logger.debug("data redis: %s", data_redis)
            respuesta = confirmar_direccion(self.numero_cliente, mensaje_cliente, data_redis)
            if respuesta is False:
                self.estado_usuario.actualizar_estado(EstadoRegistro.ESPERANDO_DIRECCION)
                enviar_mensaje_whatsapp(
                    "😊 *¡Vale!* Vamos a intentarlo de nuevo.\nPor favor, *ingresa una dirección* \n\n👇 *Ejemplos:* 👇 \n\n•Calle Los Labradores 3, 1B\n•avenida pablo iglecias 79, 1b", 
                    self.numero_cliente
                )
                return "paso atras", 200
            
            return respuesta

def manejar_registro(numero_cliente, mensaje_cliente, redismanager):
    registro_usuario = RegistroUsuario(numero_cliente, redismanager)
    return registro_usuario.manejar_registro(mensaje_cliente)
