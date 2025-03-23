from utils.mensajes import enviar_mensaje_whatsapp
from managers.gestor_usuarios import GestorUsuarios
from menu import procesar_mensaje_como_pedido
from sqlalchemy.exc import SQLAlchemyError




# # esta clase maneja el flujo de mensajes 
# # y la logica de los registrados

class ManejadorMensajesRegistrados:
    
    @staticmethod    
    def manejar_mensajes_registrados( numero_cliente, mensaje_cliente):
        from main import gestor_pedidos
        from main import gestor_usuarios

        

        try:
            usuario_datos = gestor_usuarios.obtener_usuario_completo(numero_cliente)
            if not usuario_datos:  # Verifica si el resultado es None o vacío
                print("Error: No se encontraron datos para el usuario.")
                enviar_mensaje_whatsapp(
                    "Lo sentimos, no pudimos encontrar su información. Por favor, intente más tarde.",
                    numero_cliente
                )
                return "Error: Usuario no encontrado.", 404
            id_usuario = usuario_datos["id"]
        except SQLAlchemyError as e:
            print(f"Error al obtener el usuario: {e}")
            
            return "Error en la base de datos. Intente más tarde.", 500


        
        #desarrollar logica de caundo el usuario esta en el  paso de  elegir restaurante  estado "pendiente"
        if gestor_pedidos.hay_pedido_pendiente(id_usuario):
            return procesar_mensaje_como_pedido(mensaje_cliente, numero_cliente,id_usuario)
        
        #desarrollar logica cuando el estado del pedido es "enlace" o enlace2
        if gestor_pedidos.hay_pedido_enlace(id_usuario) or gestor_pedidos.hay_pedido_enlace2(id_usuario):
            peido_receinte = gestor_pedidos.obtener_pedido_mas_reciente(id_usuario)
            enlace = peido_receinte.enlace
            mensaje = f"Puede continuar con su pedido en el *enlace* proporcionado \n\n▪*Enlace* unico 👇 \n\n🔗{(enlace)}"
            enviar_mensaje_whatsapp(mensaje, numero_cliente)
            return  " mensaje enviado",200
        
        #desarrollar logica de cuando el usuario este la pagina de pago
        if gestor_pedidos.hay_pedido_confirmando_pago(id_usuario):
            peido_receinte = gestor_pedidos.obtener_pedido_mas_reciente(id_usuario)
            enlace_pago = peido_receinte.enlace
            enviar_mensaje_whatsapp(f"🔗 {enlace_pago}\n ✅ Pago seguro  con *MONEI*" , numero_cliente)
            return  " mensaje enviado",200
        

        # esta es la primera interaccion del usuario aqui se crea el pedido y se le envia 
        # el mensaje de las obciones que hay  la logica esta en el archivo menu.py

        respuesta_usuario = GestorUsuarios.manejar_usuario(numero_cliente , usuario_datos)
        if respuesta_usuario:
            return respuesta_usuario

       

        





