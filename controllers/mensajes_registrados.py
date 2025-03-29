from utils.mensajes import enviar_mensaje_whatsapp
from managers.gestor_usuarios import GestorUsuarios
from menu import procesar_pedido
from sqlalchemy.exc import SQLAlchemyError
from tenacity import RetryError


# # esta clase maneja el flujo de mensajes 
# # y la logica de los registrados

class ManejadorMensajesRegistrados:
    
    @staticmethod    
    def manejar_mensajes_registrados( numero_cliente, mensaje_cliente):
        from main import gestor_pedidos
        from main import gestor_usuarios

        try:
            usuario_datos = gestor_usuarios.obtener_usuario_completo(numero_cliente)
            if not usuario_datos:  # No se encontraron datos para el usuario.
                print("Error: No se encontraron datos para el usuario.")
                enviar_mensaje_whatsapp(
                    "Lo sentimos, no pudimos encontrar su información. Por favor, intente más tarde.",
                    numero_cliente
                )
                return "Error: Usuario no encontrado.", 404
            id_usuario = usuario_datos["id"]
        except (SQLAlchemyError, RetryError) as e:
            # Aquí se captura la excepción después de 3 intentos fallidos.
            print(f"Error al obtener el usuario tras varios intentos: {e}")
            enviar_mensaje_whatsapp(
                "Lo sentimos, se presentó un error en el sistema. Por favor, intente más tarde.",
                numero_cliente
            )
            return "Error en la base de datos. Intente más tarde.", 500

        try:
            pedido_activo = gestor_pedidos.obtener_pedido_mas_reciente(id_usuario)
            if not pedido_activo:  # No se encontraron datos para el usuario.
                print("Error: No se pedido.")
                enviar_mensaje_whatsapp(
                    "Lo sentimos, no pudimos encontrar su información. Por favor, intente más tarde.",
                    numero_cliente
                )
                return "Error: Usuario no encontrado.", 404
            estado_del_pedido =  pedido_activo.Estado
            print(f"Estado del pedido: {estado_del_pedido}")
        except (SQLAlchemyError, RetryError) as e:
            # Aquí se captura la excepción después de 3 intentos fallidos.
            print(f"Error al obtener el pedido tras varios intentos: {e}")
            enviar_mensaje_whatsapp(
                "Lo sentimos, se presentó un error en el sistema. Por favor, intente más tarde.",
                numero_cliente
            )
            return "Error en la base de datos. Intente más tarde.", 500
        
        id_pedido_activo = pedido_activo.PedidoID
        #desarrollar logica de caundo el usuario esta en el  paso de  elegir restaurante  estado "pendiente"
        if estado_del_pedido == "Pendiente":
            mensaje = procesar_pedido(mensaje_cliente, numero_cliente, id_pedido_activo , usuario_datos)
            print(f"Mensaje procesado: {usuario_datos}")
            enviar_mensaje_whatsapp(mensaje, numero_cliente)
            return " mensaje enviado",200
           
            
            
        
        #desarrollar logica cuando el estado del pedido es "enlace" o enlace2
        if estado_del_pedido == "enlace" or estado_del_pedido == "enlace2":
            enlace = pedido_activo.enlace
            mensaje = f"Puede continuar con su pedido en el *enlace* proporcionado \n\n▪*Enlace* unico 👇 \n\n🔗{(enlace)}"
            enviar_mensaje_whatsapp(mensaje, numero_cliente)
            return  " mensaje enviado",200
        
        #desarrollar logica de cuando el usuario este la pagina de pago
        if estado_del_pedido == "confirmando-pago":
            enlace_pago = pedido_activo.enlace
            enviar_mensaje_whatsapp(f"🔗 {enlace_pago}\n ✅ Pago seguro  con *MONEI*" , numero_cliente)
            return  " mensaje enviado",200
        

        # esta es la primera interaccion del usuario aqui se crea el pedido y se le envia 
        # el mensaje de las obciones que hay  la logica esta en el archivo menu.py

        respuesta_usuario = GestorUsuarios.manejar_usuario(numero_cliente , usuario_datos)
        if respuesta_usuario:
            return respuesta_usuario

       

        





