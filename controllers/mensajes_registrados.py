from utils.mensajes import enviar_mensaje_whatsapp
from data.usuarios import  manejar_usuario
from data.pedidos_activos import pedidos_activos
from menu import procesar_mensaje_como_pedido
import random


# # esta clase maneja el flujo de mensajes 
# # y la logica de los registrados

class ManejadorMensajesRegistrados:
    
    def __init__(self ):
        self.pedidos_activos = pedidos_activos

    def manejar_mensajes_registrados(self, numero_cliente, mensaje_cliente):
        from main import gestor_pedidos
        from main import gestor_usuarios

        usuario_datos = gestor_usuarios.obtener_usuario_completo(numero_cliente)
        id_usuario = usuario_datos["id"]

        
        #desarrollar logica de caundo el usuario esta en el  paso de  elegir restaurante 
        if gestor_pedidos.hay_pedido_pendiente(id_usuario):
            return procesar_mensaje_como_pedido(mensaje_cliente, numero_cliente)
        
        #desarrollar logica de  cuando el usuario este en el enlace
        if gestor_pedidos.hay_pedido_enlace(id_usuario) or gestor_pedidos.hay_pedido_enlace2(id_usuario):
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
        

        #esta es la primera interaccion del usuario aqui se crea el pedido y se le envia 
        # el mensaje de las obciones que hay 
        respuesta_usuario = manejar_usuario(numero_cliente)
        if respuesta_usuario:
            return respuesta_usuario

       

        

def manejar_mensajes_registrados(numero_cliente, mensaje_cliente):
    
    manejador = ManejadorMensajesRegistrados()
    return manejador.manejar_mensajes_registrados(numero_cliente, mensaje_cliente)



