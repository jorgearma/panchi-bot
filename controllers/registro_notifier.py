# Capa de notificación para el flujo de registro
# Responsable de todos los mensajes WhatsApp hacia el usuario durante el registro

from services.whatsapp_service import enviar_mensaje_whatsapp


# Notificaciones del flujo principal

def _enviar_bienvenida(numero_cliente):
    """Mensaje inicial de bienvenida al registro."""
    enviar_mensaje_whatsapp(
        "*Registro en el Sistema*💻\n\n"
        "¡Hola!👋 Aun no estás registrado en nuestro sistema. "
        "¿Te gustaría continuar con tu registro? 📝\n\n"
        "▪️Escribe: *Si*",
        numero_cliente
    )


def _enviar_cancelacion_registro(numero_cliente):
    """Mensaje cuando el usuario no confirma el registro."""
    enviar_mensaje_whatsapp(
        "No se ha realizado el registro , escriba si para continuar. 😊",
        numero_cliente
    )


def _solicitar_nombre(numero_cliente):
    """Solicitud del nombre del usuario."""
    enviar_mensaje_whatsapp(
        "▪️ *Registro de Usuario* 👤\n\nEscribe tu 🫵 *Nombre* \nPara continuar",
        numero_cliente
    )


def _solicitar_direccion(numero_cliente):
    """Solicitud de la dirección del usuario."""
    enviar_mensaje_whatsapp(
        "📍 *Registro de Dirección* 📍\n\nGracias. Ahora, por favor envía tu *Dirección Completa* 🏠.\n\n"
        "👇 *Ejemplos:* 👇 \n\n🔹_Calle Labradores, 3, 1B_\n🔹_Avenida Pablo Iglesias, 79, 1B_\n\n",
        numero_cliente
    )


def _enviar_confirmacion_direccion(numero_cliente, direccion):
    """Solicitud de confirmación de la dirección validada."""
    enviar_mensaje_whatsapp(
        f"{direccion} \n\n ⬆️ *Verifica tu Ubicación* ⬆️\n\n"
        "👉 *Escribe:* *Si* para confirmar\n"
        "👉 *Escribe:* *No* para corregir\n\n",
        numero_cliente
    )


def _enviar_direccion_invalida(numero_cliente):
    """Aviso de dirección inválida."""
    enviar_mensaje_whatsapp(
        "⛔ *La dirección no es válida* ⛔\n\nPor favor, revisa los *detalles* 📝.\n"
        "¡Gracias por tu ayuda! 😊 \n\n 👇 *Ejemplos:* 👇 \n\n"
        "•_Calle Los Labradores 3, 1B_\n•_Avenida Pablo Iglesias 79, 1B_",
        numero_cliente
    )


def _enviar_mensaje_registro(numero_cliente, nombre, menu_despues_registro):
    """Confirmación final del registro completado."""
    mensaje = (f"¡Gracias {nombre}! Ahora estás registrado. {menu_despues_registro} "
               "\nescribe el *numero* para elegir\n  "
               )
    enviar_mensaje_whatsapp(mensaje, numero_cliente)


# Notificaciones de errores de validación

def _enviar_nombre_invalido(numero_cliente):
    """Aviso cuando el nombre es inválido."""
    enviar_mensaje_whatsapp(
        "⛔ *El nombre ingresado no es válido* ⛔\n\nPor favor, escribe tu *Nombre Completo* 📝.\n"
        "Ejemplo: _Juan Pérez_ o _María López_",
        numero_cliente
    )


def _enviar_registro_pendiente(numero_cliente):
    """Recordatorio para confirmar el registro."""
    enviar_mensaje_whatsapp(
        "Para comenzar tu registro escribe *Si* ✅\n"
        "Si no quieres registrarte ahora, simplemente ignora este mensaje.",
        numero_cliente
    )


def _enviar_pedir_confirmacion(numero_cliente):
    """Solicitud de confirmación de la dirección nuevamente."""
    enviar_mensaje_whatsapp(
        "Escribe *Si* para confirmar tu dirección, o *No* para escribirla de nuevo.",
        numero_cliente
    )


def _enviar_reintentar_direccion(numero_cliente):
    """Mensaje para reintentar la dirección después de "No"."""
    enviar_mensaje_whatsapp(
        "😊 *¡Vale!* Vamos a intentarlo de nuevo.\nPor favor, *ingresa una dirección* \n\n"
        "👇 *Ejemplos:* 👇 \n\n•Calle Los Labradores 3, 1B\n•avenida pablo iglecias 79, 1b",
        numero_cliente
    )
