# LEGACY — no importado por ningún blueprint activo.
# La lógica activa está en controllers/no_resgistrados.py (usa Redis, no dict en memoria).
# Candidato a eliminación en Fase 4 tras validar que no hay dependencias externas.

# /services/registro_usuario.py
from utils.mensajes import enviar_mensaje_whatsapp
from utils.maps import validar_direccion
from utils.confirmar_direccion import confirmar_direccion
from data.estado_usuarios import estado_usuarios


MENSAJES = {
    "bienvenida": (
        "💻 *Registro en el Sistema* 💻\n       ✨ *Urban Kitchen* ✨\n\n"
        "¡Hola!👋 No estás registrado en nuestro sistema. "
        "¿Te gustaría continuar con tu registro? 📝\n\n"
        "▪️Escribe: *Si*\n\nSolo necesito tu *Nombre* y *Dirección* para la _entrega_ 🛵"
    ),
    "cancelacion": (
        "No se ha realizado el registro. Si deseas continuar más tarde, solo avísanos. 😊"
    ),
    "solicitar_nombre": (
        "📍 *Registro de Usuario* 📍\n\n🫵 Escribe tu *Nombre* 🫵\n           para continuar"
    ),
    "solicitar_direccion": (
        "📍 *Registro de Dirección* 📍\n\nGracias. Ahora, por favor envía tu *Dirección Completa* 🏠.\n\n"
        "👇 *Ejemplos:* 👇 \n\n🔹_Calle Labradores, 3, 1B_\n🔹_Avenida Pablo Iglesias, 79, 1B_\n\n"
    ),
    "direccion_invalida": (
        "⛔ *La dirección no es válida* ⛔\n\nPor favor, revisa los *detalles* 📝.\n"
        "¡Gracias por tu ayuda! 😊 \n\n 👇 *Ejemplos:* 👇 \n\n"
        "•_Calle Los Labradores 3, 1B_\n•_Avenida Pablo Iglesias 79, 1B_"
    ),
}


class EstadoUsuario:
    """Clase para gestionar el estado del usuario."""
    def __init__(self, numero_cliente):
        self.numero_cliente = numero_cliente

    def obtener_estado(self):
        return estado_usuarios.get(self.numero_cliente, {"estado": "saludo_inicial"})

    def actualizar_estado(self, nuevo_estado, datos_adicionales=None):
        # Obtener el estado actual
        estado_actual = estado_usuarios.get(self.numero_cliente, {})
        
        # Actualizar solo el estado
        estado_actual["estado"] = nuevo_estado
        
        # Incorporar datos adicionales si existen
        if datos_adicionales:
            estado_actual.update(datos_adicionales)
        
        # Guardar de nuevo el estado actualizado
        estado_usuarios[self.numero_cliente] = estado_actual



class Mensajeria:
    """Clase para enviar mensajes de WhatsApp."""
    @staticmethod
    def enviar_bienvenida(numero_cliente):
        enviar_mensaje_whatsapp(
            "*Registro en el Sistema*💻\n\n"
            "¡Hola!👋 Aun no estás registrado en nuestro sistema. "
            "¿Te gustaría continuar con tu registro? 📝\n\n"
            "▪️Escribe: *Si*",
            numero_cliente
        )

    @staticmethod
    def confirmar_cancelacion(numero_cliente):
        enviar_mensaje_whatsapp(
            "No se ha realizado el registro , escriba si para continuar. 😊",
            numero_cliente
        )

    @staticmethod
    def solicitar_nombre(numero_cliente):
        enviar_mensaje_whatsapp(
            "▪️ *Registro de Usuario* 👤\n\nEscribe tu 🫵 *Nombre* \nPara continuar",
            numero_cliente
        )

    @staticmethod
    def solicitar_direccion(numero_cliente):
        enviar_mensaje_whatsapp(
            "📍 *Registro de Dirección* 📍\n\nGracias. Ahora, por favor envía tu *Dirección Completa* 🏠.\n\n"
            "👇 *Ejemplos:* 👇 \n\n🔹_Calle Labradores, 3, 1B_\n🔹_Avenida Pablo Iglesias, 79, 1B_\n\n",
            numero_cliente
        )

    @staticmethod
    def confirmar_direccion(numero_cliente, direccion):
        enviar_mensaje_whatsapp(
            f"{direccion} \n\n ⬆️ *Verifica tu Ubicación* ⬆️\n\n"
            "👉 *Escribe:* *Si* para confirmar\n"
            "👉 *Escribe:* *No* para corregir\n\n",
            numero_cliente
        )

    @staticmethod
    def direccion_invalida(numero_cliente):
        enviar_mensaje_whatsapp(
            "⛔ *La dirección no es válida* ⛔\n\nPor favor, revisa los *detalles* 📝.\n"
            "¡Gracias por tu ayuda! 😊 \n\n 👇 *Ejemplos:* 👇 \n\n"
            "•_Calle Los Labradores 3, 1B_\n•_Avenida Pablo Iglesias 79, 1B_",
            numero_cliente
        )


class ValidacionDireccion:
    """Clase para manejar la validación de direcciones."""
    @staticmethod
    def validar_y_confirmar_direccion(numero_cliente, direccion):
        validar, direccion_resultante = validar_direccion(direccion)
        if validar:
            Mensajeria.confirmar_direccion(numero_cliente, direccion_resultante)
            return True
        else:
            Mensajeria.direccion_invalida(numero_cliente)
            return False

#cambair esto con estados  gestionados desde la base de datos
class RegistroUsuario:
    """Clase principal para gestionar el registro del usuario."""
    def __init__(self, numero_cliente):
        self.numero_cliente = numero_cliente
        self.estado_usuario = EstadoUsuario(numero_cliente)

    def manejar_registro(self, mensaje_cliente):
        estado_actual = self.estado_usuario.obtener_estado()["estado"]

        if estado_actual == "saludo_inicial":
            Mensajeria.enviar_bienvenida(self.numero_cliente)
            self.estado_usuario.actualizar_estado("esperando_confirmacion")
            return "Mensaje de bienvenida enviado", 200

        elif estado_actual == "esperando_confirmacion":
            if mensaje_cliente.lower() in {"sí", "si", "quiero", "adelante"}:
                Mensajeria.solicitar_nombre(self.numero_cliente)
                self.estado_usuario.actualizar_estado("esperando_nombre")
                return "Solicitud de nombre enviada", 200
            else:
                Mensajeria.confirmar_cancelacion(self.numero_cliente)
                return "Registro cancelado", 200

        elif estado_actual == "esperando_nombre":
            self.estado_usuario.actualizar_estado("esperando_direccion", {"nombre": mensaje_cliente})
            Mensajeria.solicitar_direccion(self.numero_cliente)
            return "Solicitud de dirección enviada", 200

        elif estado_actual == "esperando_direccion":
            if ValidacionDireccion.validar_y_confirmar_direccion(self.numero_cliente, mensaje_cliente):
                self.estado_usuario.actualizar_estado("confirmando_direccion", {"direccion": mensaje_cliente})
                return "Solicitud de confirmación de dirección enviada", 200

        elif estado_actual == "confirmando_direccion":
            return confirmar_direccion(self.numero_cliente, mensaje_cliente)


def manejar_registro(numero_cliente, mensaje_cliente):
    registro_usuario = RegistroUsuario(numero_cliente)
    print("estdo" , estado_usuarios)
    return registro_usuario.manejar_registro(mensaje_cliente)
