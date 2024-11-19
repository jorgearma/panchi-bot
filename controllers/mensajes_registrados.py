from utils.mensajes import enviar_mensaje_whatsapp
from menu import mostrar_menu, procesar_pedido
from controllers.pago import preguntar_metodo_pago , procesar_pago, salir_o_proceder_al_pago , procesar_metodo_pago
from openai_api import obtener_respuesta_openai
from data.usuarios import  obtener_usuario_bd , manejar_usuario 
from data.carrito import carrito , guardar_pedido , manejar_consulta_carrito , mostrar_carrito, mostrar_carrito_sin_mensaje
from data.estado_usuarios import estado_usuarios
from data.pedidos import enviar_comanda_a_cocina , verificar_pedido_activo
from data.pedidos_activos import pedidos_activos
from controllers.pedido_Y_respuestas import procesar_mensaje_como_pedido

import random


def manejar_mensajes_registrados(numero_cliente, mensaje_cliente):
    
    respuesta = verificar_pedido_activo(numero_cliente, mensaje_cliente, pedidos_activos)
    if respuesta:
        return respuesta

        
    respuesta_usuario = manejar_usuario(numero_cliente)
    if respuesta_usuario:
        return respuesta_usuario

     # Consultar el carrito
    if manejar_consulta_carrito(mensaje_cliente, numero_cliente,carrito):
        return "Mensaje enviado", 200

    # Salir o proceder al pago
    if salir_o_proceder_al_pago(mensaje_cliente, numero_cliente):
        return "Mensaje enviado", 200

    if procesar_metodo_pago(mensaje_cliente, numero_cliente):
        return "Mensaje enviado", 200

    return procesar_mensaje_como_pedido(mensaje_cliente, numero_cliente)


