from utils.mensajes import enviar_mensaje_whatsapp
from utils.maps import generar_enlace_google_maps , validar_direccion
from utils.confirmar_direccion import confirmar_direccion
from data.usuarios import registrar_usuario , guardar_usuario_bd
from data.estado_usuarios import estado_usuarios
from data.carrito import carrito
from menu import mostrar_menu
from controllers.registro_de_usuarios.proceso_de_registro import enviar_mensaje_bienvenida, procesar_confirmacion, solicitar_nombre, solicitar_direccion, confirmar_direccion




def manejar_registro(numero_cliente, mensaje_cliente):
    estado = estado_usuarios.get(numero_cliente, {"estado": "saludo_inicial"})
    if estado["estado"] == "saludo_inicial":
        return enviar_mensaje_bienvenida(numero_cliente)
    elif estado["estado"] == "esperando_confirmacion":
        return procesar_confirmacion(numero_cliente, mensaje_cliente)
    elif estado["estado"] == "esperando_nombre":
        return solicitar_nombre(numero_cliente, mensaje_cliente)
    elif estado["estado"] == "esperando_direccion":
        return solicitar_direccion(numero_cliente, mensaje_cliente)
    elif estado["estado"] == "confirmando_direccion":
        return confirmar_direccion(numero_cliente, mensaje_cliente)