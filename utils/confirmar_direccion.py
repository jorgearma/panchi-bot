from data.estado_usuarios import estado_usuarios , obtener_estado_usuario, actualizar_estado_usuario
from data.usuarios import registrar_usuario 
from menu import mostrar_menu   
from data.carrito import  carrito_instancia
from utils.mensajes import enviar_mensaje_whatsapp


def manejar_respuesta_positiva(numero_cliente):
    estado = obtener_estado_usuario(numero_cliente)
    registrar_usuario(numero_cliente, estado["nombre"], estado["direccion"])
    menu_despues_registro = mostrar_menu()
    enviar_mensaje_registro(numero_cliente, estado["nombre"], menu_despues_registro)
    actualizar_estado_usuario(numero_cliente)
    carrito_instancia.inicializar_carrito(numero_cliente)
    return "Usuario registrado", 200

def manejar_respuesta_negativa(numero_cliente):
    estado_usuarios[numero_cliente]["estado"] = "esperando_direccion"
    enviar_mensaje_whatsapp("😊 *¡Vale!* Vamos a intentarlo de nuevo.\nPor favor, *ingresa una dirección* \n\n👇 *Ejemplos:* 👇 \n\n•Calle Los Labradores 3, 1B\n•avenida pablo iglecias 79, 1b", numero_cliente)
    return "Solicitud de dirección enviada de nuevo", 200

def confirmar_direccion(numero_cliente, mensaje_cliente):
    if mensaje_cliente.lower() == 'si':
        return manejar_respuesta_positiva(numero_cliente)
    else:
        return manejar_respuesta_negativa(numero_cliente)

def enviar_mensaje_registro(numero_cliente, nombre, menu_despues_registro):
    mensaje = (f"¡Gracias {nombre}! Ahora estás registrado. {menu_despues_registro} "
               "\nescribe el *numero* para elegir\n  "
               )
    enviar_mensaje_whatsapp(mensaje, numero_cliente)