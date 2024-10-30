from utils.mensajes import enviar_mensaje_whatsapp
from utils.maps import generar_enlace_google_maps
from data.usuarios import registrar_usuario , guardar_usuario_bd
from data.estado_usuarios import estado_usuarios
from data.carrito import carrito
from menu import mostrar_menu



def manejar_registro(numero_cliente, mensaje_cliente):
    estado = estado_usuarios.get(numero_cliente, {"estado": "saludo_inicial"})

    if estado["estado"] == "saludo_inicial":
        enviar_mensaje_whatsapp("Hola! No estás registrado en nuestro sistema. Vamos a proceder con tu registro.", numero_cliente)
        estado_usuarios[numero_cliente] = {"estado": "esperando_nombre"}
        enviar_mensaje_whatsapp("Por favor, envía tu nombre para continuar.", numero_cliente)
        return "Saludo enviado y solicitud de nombre", 200

    elif estado["estado"] == "esperando_nombre":
        estado_usuarios[numero_cliente] = {"estado": "esperando_direccion", "nombre": mensaje_cliente}
        enviar_mensaje_whatsapp("Gracias. Ahora, por favor envía tu dirección. EJEMPLO: calle los labradores 3 1b", numero_cliente)
        return "Solicitud de dirección enviada", 200

    elif estado["estado"] == "esperando_direccion":
        estado["direccion"] = mensaje_cliente
        estado["estado"] = "confirmando_direccion"
        enlace_maps = generar_enlace_google_maps(mensaje_cliente)
        enviar_mensaje_whatsapp(f"Aquí tienes un enlace de Google Maps con la ubicación de tu calle: {enlace_maps}", numero_cliente)
        enviar_mensaje_whatsapp("Si tu dirección es esta, responde 'sí' para confirmar.", numero_cliente)
        return "Solicitud de confirmación de dirección enviada", 200

    elif estado["estado"] == "confirmando_direccion":
        if mensaje_cliente == 'si':
            registrar_usuario(numero_cliente, estado["nombre"], estado["direccion"],guardar_usuario_bd)
            menu_despues_registro = mostrar_menu()
            enviar_mensaje_whatsapp(f"¡Gracias {estado['nombre']}! Ahora estás registrado. {menu_despues_registro}", numero_cliente)
            estado_usuarios[numero_cliente] = {"recien_registrado": True}
            carrito[numero_cliente] = []
            return "Usuario registrado", 200
        else:
            estado_usuarios[numero_cliente]["estado"] = "esperando_direccion"
            enviar_mensaje_whatsapp("Vamos a intentar de nuevo. Por favor envía tu dirección.", numero_cliente)
            return "Solicitud de dirección enviada de nuevo", 200
