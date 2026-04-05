# Capa de notificación para el flujo de registro
# Responsable de todos los mensajes WhatsApp hacia el usuario durante el registro

from services.whatsapp_service import (
    enviar_boton_unico,
    enviar_botones_si_no,
    enviar_mensaje_whatsapp,
)


# Notificaciones del flujo principal

def _enviar_bienvenida(numero_cliente):
    """Abre la conversación de registro e invita al usuario a continuar."""
    cuerpo = (
        "*Panchi-Bot* \n\n"
        "¡Hola!👋 Aun no estás registrado en nuestro sistema. "
        "¿Te gustaría continuar con tu registro? "
    )
    enviar_boton_unico(
        cuerpo=cuerpo,
        destinatario=numero_cliente,
        boton_id="registro_continuar",
        titulo="Continuar",
    )


def _enviar_cancelacion_registro(numero_cliente):
    """Recuerda cómo retomar el registro si el usuario no lo confirma."""
    enviar_mensaje_whatsapp(
        "No se ha realizado el registro , escriba si para continuar. 😊",
        numero_cliente
    )


def _solicitar_nombre(numero_cliente):
    """Pide el nombre que se guardará en el perfil del cliente."""
    enviar_mensaje_whatsapp(
        "▪️ *Registro de Usuario* 👤\n\nEscribe tu 🫵 *Nombre* \nPara continuar",
        numero_cliente
    )


def _solicitar_direccion(numero_cliente):
    """Pide la dirección completa con ejemplos del formato esperado."""
    enviar_mensaje_whatsapp(
        "📍 *Registro de Dirección* 📍\n\nGracias. Ahora, por favor envía tu *Dirección Completa* 🏠.\n\n"
        ,
        numero_cliente
    )


def _enviar_confirmacion_direccion(numero_cliente, direccion):
    """Muestra la dirección interpretada y pide confirmación explícita."""
    cuerpo = (
        f"{direccion}\n\n"  # Dirección interpretada
        "⬆️ *Verifica tu Ubicación* ⬆️\n\n"
        "Selecciona una opción:"
    )
    enviar_botones_si_no(
        cuerpo=cuerpo,
        destinatario=numero_cliente,
        id_si="direccion_si",
        titulo_si="Correcta",
        id_no="direccion_no",
        titulo_no="Incorrecta",
    )


def _enviar_direccion_invalida(numero_cliente, sugerencia=None, alta_confianza=False):
    """Explica que la dirección no pudo validarse. Si hay sugerencia, la incluye."""
    if sugerencia:
        nombre = sugerencia.title()
        if alta_confianza:
            mensaje = (
                f"⛔ *No reconocí esa dirección*\n\n"
                f"¿Quisiste decir *{nombre}*? ✍️\n\n"
                f"Escríbela con el número de portal. Por ejemplo:\n"
                f"•_{nombre} 5_\n•_{nombre} 12, 2B_"
            )
        else:
            mensaje = (
                f"⛔ *No reconocí esa dirección*\n\n"
                f"¿Te refieres a *{nombre}*? ✍️\n\n"
                f"Si es así, escríbela con el número de portal.\n"
                f"Si no, prueba con otro nombre de calle y el número."
            )
    else:
        mensaje = (
            "⛔ *La dirección no es válida* ⛔\n\nPor favor, revisa los *detalles* 📝.\n"
            "¡Gracias por tu ayuda! 😊 \n\n 👇 *Ejemplos:* 👇 \n\n"
            "•_Calle Los Labradores 3, 1B_\n•_Avenida Pablo Iglesias 79, 1B_"
        )
    enviar_mensaje_whatsapp(mensaje, numero_cliente)


def _enviar_mensaje_registro(numero_cliente, nombre, menu_despues_registro):
    """Confirma el alta y enlaza directamente con el menú de compra."""
    mensaje = (f"¡Gracias {nombre}! Ahora estás registrado. {menu_despues_registro} "
               "\nescribe el *numero* para elegir\n  "
               )
    enviar_mensaje_whatsapp(mensaje, numero_cliente)


# Notificaciones de errores de validación

def _enviar_nombre_invalido(numero_cliente):
    """Pide repetir el nombre cuando no cumple el formato esperado."""
    enviar_mensaje_whatsapp(
        "⛔ *El nombre ingresado no es válido* ⛔\n\nPor favor, escribe tu *Nombre Completo* 📝.\n"
        "Ejemplo: _Juan Pérez_ o _María López_",
        numero_cliente
    )


def _enviar_registro_pendiente(numero_cliente):
    """Recuerda al usuario que el registro sigue pendiente de confirmación."""
    enviar_mensaje_whatsapp(
        "Para comenzar tu registro escribe *Si* ✅\n"
        "Si no quieres registrarte ahora, simplemente ignora este mensaje.",
        numero_cliente
    )


def _enviar_pedir_confirmacion(numero_cliente):
    """Repite las opciones válidas para confirmar o corregir la dirección."""
    enviar_mensaje_whatsapp(
        "Escribe *Si* para confirmar tu dirección, o *No* para escribirla de nuevo.",
        numero_cliente
    )


def _enviar_reintentar_direccion(numero_cliente):
    """Invita a reenviar la dirección cuando el usuario la rechaza."""
    enviar_mensaje_whatsapp(
        "😊 *¡Vale!* Vamos a intentarlo de nuevo.\nPor favor, *ingresa una dirección* \n\n"
        "👇 *Ejemplos:* 👇 \n\n•Calle Los Labradores 3, 1B\n•avenida pablo iglecias 79, 1b",
        numero_cliente
    )
