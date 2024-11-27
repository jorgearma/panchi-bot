from utils.mensajes import enviar_mensaje_whatsapp
from menu import mostrar_menu, procesar_pedido
from controllers.pago import PedidoHandler
from openai_api import obtener_respuesta_openai
from data.usuarios import obtener_usuario_bd, manejar_usuario
from data.carrito import carrito_instancia, manejar_consulta_carrito, mostrar_carrito, mostrar_carrito_sin_mensaje
from data.estado_usuarios import estado_usuarios
from data.pedidos import enviar_comanda_a_cocina, verificar_pedido_activo , pedido
from data.pedidos_activos import pedidos_activos
from controllers.pedido_Y_respuestas import procesar_mensaje_como_pedido

import random

class ManejadorMensajesRegistrados:
    def __init__(self , carrito):
        self.carrito = carrito
        self.pedidos_activos = pedidos_activos

    def manejar_mensajes_registrados(self, numero_cliente, mensaje_cliente):
        respuesta = verificar_pedido_activo(numero_cliente, mensaje_cliente, self.pedidos_activos)
        if respuesta:
            return respuesta

        respuesta_usuario = manejar_usuario(numero_cliente)
        if respuesta_usuario:
            return respuesta_usuario

        # Consultar el carrito
        if manejar_consulta_carrito(mensaje_cliente, numero_cliente, self.carrito):
            print(carrito_instancia.carrito)
            return "Mensaje enviado", 200

        Pago_Handler = PedidoHandler(numero_cliente)
        if Pago_Handler.salir_o_proceder_al_pago(mensaje_cliente):
            return "Mensaje enviado", 200

        if Pago_Handler.procesar_metodo_pago(mensaje_cliente):
            return "Mensaje enviado", 200

        return procesar_mensaje_como_pedido(mensaje_cliente, numero_cliente)

def manejar_mensajes_registrados(numero_cliente, mensaje_cliente):
    
    manejador = ManejadorMensajesRegistrados(carrito_instancia)
    return manejador.manejar_mensajes_registrados(numero_cliente, mensaje_cliente)



