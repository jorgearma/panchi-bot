from menu import mostrar_menu
from utils.mensajes import enviar_mensaje_whatsapp



def manejar_respuesta_positiva(numero_cliente , data_redis):
    from main import gestor_usuarios
    from main import gestor_pedidos
    
    
    estado = data_redis  
    print("estado",estado)     
    gestor_usuarios.guardar_usuario(numero_cliente, estado["nombre"], estado["direccion"])
    menu_despues_registro = mostrar_menu()
    enviar_mensaje_registro(numero_cliente, estado["nombre"], menu_despues_registro)
    usuario_info = gestor_usuarios.obtener_usuario_completo(numero_cliente)
    print("info usuario",usuario_info)
    
    if usuario_info:
        # Se obtiene el id del usuario para crear el pedido
        gestor_pedidos.iniciar_pedido(usuario_info["id"],  estado["direccion"], estado["nombre"])
    return "Usuario registrado", 200

def manejar_respuesta_negativa(numero_cliente):
    #enviar_mensaje_whatsapp("😊 *¡Vale!* Vamos a intentarlo de nuevo.\nPor favor, *ingresa una dirección* \n\n👇 *Ejemplos:* 👇 \n\n•Calle Los Labradores 3, 1B\n•avenida pablo iglecias 79, 1b", numero_cliente)
    return 1

def confirmar_direccion(numero_cliente, mensaje_cliente , data_redis):
    if mensaje_cliente.lower() == 'si':
        return manejar_respuesta_positiva(numero_cliente, data_redis)
    else:
        return manejar_respuesta_negativa(numero_cliente)

def enviar_mensaje_registro(numero_cliente, nombre, menu_despues_registro):
    mensaje = (f"¡Gracias {nombre}! Ahora estás registrado. {menu_despues_registro} "
               "\nescribe el *numero* para elegir\n  "
               )
    enviar_mensaje_whatsapp(mensaje, numero_cliente)