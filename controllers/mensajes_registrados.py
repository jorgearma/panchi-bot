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
        from main import gestor_pedidos
        from main import gestor_usuarios

        usuario_datos = gestor_usuarios.obtener_usuario_completo(numero_cliente)
        print(usuario_datos ,"usario datos 2 ")
        id_usuario = usuario_datos["id"]

        
        #desarrollar logica de caundo el usuario esta en el  paso de  elegir restaurante 
        if gestor_pedidos.hay_pedido_pendiente(id_usuario):
            print("hola guapo")
            return procesar_mensaje_como_pedido(mensaje_cliente, numero_cliente)
        
        #desarrollar logica de  cuando el usuario este en el enlace
        if gestor_pedidos.hay_pedido_enlace(id_usuario):
            peido_receinte = gestor_pedidos.obtener_pedido_mas_reciente(id_usuario)
            enlace = peido_receinte.enlace
            mensaje = f"Puede continuar con su pedido en el *enlace* proporcionado \n\n▪*Enlace* unico 👇 \n\n🔗{(enlace)}"
            enviar_mensaje_whatsapp(mensaje, numero_cliente)
            return "mensaje eniado" , 200
        
        #desarrollar logica de cuando el usuario este la pagina de pago
        if gestor_pedidos.hay_pedido_confirmando_pago(id_usuario):
            peido_receinte = gestor_pedidos.obtener_pedido_mas_reciente(id_usuario)
            enlace_pago = peido_receinte.enlace
            enviar_mensaje_whatsapp(f"🔗 {enlace_pago}\n ✅ Pago seguro  con *MONEI*" , numero_cliente)
            return "mensaje enviado" , 200
        
        #esta es la primera interaccion del usuario aqui se crea el pedido y se le envia el mensaje de las obciones
        respuesta_usuario = manejar_usuario(numero_cliente)
        if respuesta_usuario:
            return respuesta_usuario

        # Consultar el carrito
        if manejar_consulta_carrito(mensaje_cliente, numero_cliente, self.carrito):
            print(carrito_instancia.carrito)
            return "Mensaje enviado", 200

        

def manejar_mensajes_registrados(numero_cliente, mensaje_cliente):
    
    manejador = ManejadorMensajesRegistrados(carrito_instancia)
    return manejador.manejar_mensajes_registrados(numero_cliente, mensaje_cliente)



