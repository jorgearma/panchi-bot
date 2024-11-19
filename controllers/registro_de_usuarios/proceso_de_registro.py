from utils.mensajes import enviar_mensaje_whatsapp
from utils.maps import generar_enlace_google_maps , validar_direccion
from utils.confirmar_direccion import confirmar_direccion
from data.usuarios import registrar_usuario , guardar_usuario_bd
from data.estado_usuarios import estado_usuarios
from data.carrito import carrito
from menu import mostrar_menu
from data.estado_usuarios import obtener_estado_usuario

def enviar_mensaje_bienvenida(numero_cliente):
    enviar_mensaje_whatsapp("💻 *Registro en el Sistema* 💻\n       ✨ *Urban Kitchen* ✨\n\n¡Hola!👋 No estás registrado en nuestro sistema. te gustaria continuar con tu registro. 📝\n\n▪️Escribe: *Si*\n\nSolo necesito tu *Nombre* y *Dirección* para la _entrega_ 🛵", numero_cliente)
    estado_usuarios[numero_cliente] = {"estado": "esperando_confirmacion"}
    return "Mensaje de confirmación enviado", 200

def procesar_confirmacion(numero_cliente, mensaje_cliente):
    if mensaje_cliente.lower() in ["sí", "si", "quiero", "adelante"]:
        enviar_mensaje_whatsapp("📍 *Registro de Usuario* 📍\n\n🫵  Escribe tu *Nombre*  🫵 \n           para continuar", numero_cliente)
        estado_usuarios[numero_cliente] = {"estado": "esperando_nombre"}
        return "Solicitud de nombre enviada", 200
    else:
        enviar_mensaje_whatsapp("No se ha realizado el registro. Si deseas continuar más tarde, solo avísanos. 😊", numero_cliente)
        return "Registro cancelado", 200

def solicitar_nombre(numero_cliente, mensaje_cliente):
    estado_usuarios[numero_cliente] = {"estado": "esperando_direccion", "nombre": mensaje_cliente}
    enviar_mensaje_whatsapp("📍 *Registro de Dirección* 📍\n\nGracias. Ahora, por favor envía tu *Dirección Completa*  🏠.\n\n         👇 *Ejemplos:* 👇 \n\n🔹_Calle Labradores, 3, 1B_\n🔹_Avenida Pablo Iglesias, 79, 1B_\n\n", numero_cliente)
    return "Solicitud de dirección enviada", 200

def solicitar_direccion(numero_cliente, mensaje_cliente):
    estado = obtener_estado_usuario(numero_cliente)
    estado["direccion"] = mensaje_cliente
    estado["estado"] = "confirmando_direccion"
    validar, direccion_resultante = validar_direccion(mensaje_cliente)
    if validar:
        enviar_mensaje_whatsapp(f"({direccion_resultante})", numero_cliente)
        enviar_mensaje_whatsapp("⬆️ *Verifica tu Ubicación* ⬆️\n\n✅¿Es correcta? 👉 *escribe:* *Si* \n❌  ¿No lo es?     👉 *escribe:* *No*\n\n", numero_cliente)
        return "Solicitud de confirmación de dirección enviada", 200
    else:
        enviar_mensaje_whatsapp("⛔ *La dirección no es válida* ⛔\n\nPor favor, revisa los *detalles* 📝.\n¡Gracias por tu ayuda! 😊 \n\n 👇 *Ejemplos:* 👇 \n\n•_Calle Los Labradores 3, 1B_\n•_avenida pablo iglecias 79, 1b_", numero_cliente)
        estado["estado"] = "esperando_direccion"
        return "Solicitud de dirección enviada de nuevo", 200