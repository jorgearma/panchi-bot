from utils.mensajes import enviar_mensaje_whatsapp
from utils.maps import generar_enlace_google_maps , validar_direccion
from data.usuarios import registrar_usuario , guardar_usuario_bd
from data.estado_usuarios import estado_usuarios
from data.carrito import carrito
from menu import mostrar_menu



def manejar_registro(numero_cliente, mensaje_cliente):
    estado = estado_usuarios.get(numero_cliente, {"estado": "saludo_inicial"})

    if estado["estado"] == "saludo_inicial":
        enviar_mensaje_whatsapp("💻 *Registro en el Sistema*\n\n¡Hola! 👋 No estás registrado en nuestro sistema. Vamos a proceder con tu registro. 📝\n\n👉 Por favor, envía tu *nombre completo* para continuar:", numero_cliente)

        estado_usuarios[numero_cliente] = {"estado": "esperando_nombre"}
        
        return "Saludo enviado y solicitud de nombre", 200

    elif estado["estado"] == "esperando_nombre":
        estado_usuarios[numero_cliente] = {"estado": "esperando_direccion", "nombre": mensaje_cliente}
        enviar_mensaje_whatsapp("📍 *Registro de Dirección* 📍\n\nGracias. Ahora, por favor envía tu *dirección completa* 🏠.\n\n👇 *Ejemplos:* 👇 \n\n•Calle Los Labradores 3, 1B\n•avenida pablo iglecias 79, 1b \n\n", numero_cliente)

        return "Solicitud de dirección enviada", 200

    elif estado["estado"] == "esperando_direccion":
        estado["direccion"] = mensaje_cliente
        estado["estado"] = "confirmando_direccion"
        ##enlace_maps = generar_enlace_google_maps(mensaje_cliente)

        validar, direccion_resultante = validar_direccion(mensaje_cliente)
        

        if validar:
        # Si la dirección es válida, enviamos el enlace de Google Maps y pedimos confirmación
            enviar_mensaje_whatsapp(f"({direccion_resultante})", numero_cliente)
            enviar_mensaje_whatsapp("⬆️ *Verifica tu Ubicación* ⬆️\n\n✅ ¿Es correcta?     *escribe:* *Si* \n❌¿No es correcta? *escribe:* *No*\n\n", numero_cliente)


            return "Solicitud de confirmación de dirección enviada", 200
        else:
            # Si la dirección no es válida, pedimos una nueva dirección
            enviar_mensaje_whatsapp("⛔ *La dirección no es válida* ⛔\n\nPor favor, revisa los detalles 📝.\n¡Gracias por tu ayuda! 😊 \n 👇 *Ejemplos:* 👇 \n\n•Calle Los Labradores 3, 1B\n•avenida pablo iglecias 79, 1b", numero_cliente)

            estado["estado"] = "esperando_direccion"  # Vuelve al estado de esperar una dirección

            
            return "Solicitud de confirmación de dirección enviada", 200

    elif estado["estado"] == "confirmando_direccion":
        if mensaje_cliente == 'si':
            registrar_usuario(numero_cliente, estado["nombre"], estado["direccion"])
            menu_despues_registro = mostrar_menu()
            enviar_mensaje_whatsapp(f"¡Gracias {estado['nombre']}! Ahora estás registrado. {menu_despues_registro}, ❗*Para agregar un producto*❗\n\n escribe el *nombre del producto* \n 👇 *Ejemplos:* 👇 \n\n 🔺pollo asado \n 🔺flan \n 🔺cafe y agua " , numero_cliente)
            estado_usuarios[numero_cliente] = {"recien_registrado": True}
            carrito[numero_cliente] = []
            return "Usuario registrado", 200
        else:
            estado_usuarios[numero_cliente]["estado"] = "esperando_direccion"
            enviar_mensaje_whatsapp("😊 *¡Vale!* Vamos a intentarlo de nuevo.\nPor favor, *ingresa una dirección* \n\n👇 *Ejemplos:* 👇 \n\n•Calle Los Labradores 3, 1B\n•avenida pablo iglecias 79, 1b", numero_cliente)


            return "Solicitud de dirección enviada de nuevo", 200
