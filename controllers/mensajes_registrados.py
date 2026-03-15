from services.twilio_service import enviar_mensaje_whatsapp
from utils.menu_opciones import mostrar_menu
from controllers.pedido import procesar_pedido
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from tenacity import RetryError
from states import EstadoPedido


# # esta clase maneja el flujo de mensajes 
# # y la logica de los registrados

class ManejadorMensajesRegistrados:

    @staticmethod
    def _iniciar_pedido_y_enviar_menu(numero_cliente, usuario_datos):
        """Inicia un nuevo pedido en BD y envía el menú al usuario por WhatsApp."""
        from services import gestor_pedidos

        id_usuario = usuario_datos["id"]
        direccion_usuario = usuario_datos["direccion"]
        nombre_usuario = usuario_datos["nombre"]

        try:
            gestor_pedidos.iniciar_pedido(id_usuario, direccion_usuario, nombre_usuario)
        except (SQLAlchemyError, OperationalError) as error:
            print(f"Error al iniciar el pedido para el usuario {id_usuario}: {error}")
            return "Error al procesar el pedido. Inténtalo más tarde.", 500

        menu_texto = mostrar_menu()
        enviar_mensaje_whatsapp(
            f"¡Hola *{nombre_usuario}*! 🙂 {menu_texto} \nescribe el *numero* para elegir ",
            numero_cliente
        )
        return "Mensaje enviado", 200

    @staticmethod
    def manejar_mensajes_registrados(numero_cliente, mensaje_cliente):
        from services import gestor_pedidos, gestor_usuarios

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
        except (SQLAlchemyError, RetryError) as e:
            print(f"Error al obtener el pedido tras varios intentos: {e}")
            enviar_mensaje_whatsapp(
                "Lo sentimos, se presentó un error en el sistema. Por favor, intente más tarde.",
                numero_cliente
            )
            return "Error en la base de datos. Intente más tarde.", 500

        if not pedido_activo:
            print(f"Usuario {numero_cliente} sin pedido activo — iniciando nuevo pedido.")
            return ManejadorMensajesRegistrados._iniciar_pedido_y_enviar_menu(numero_cliente, usuario_datos)

        estado_del_pedido = pedido_activo.Estado
        print(f"Estado del pedido: {estado_del_pedido}")
        id_pedido_activo = pedido_activo.PedidoID
        #desarrollar logica de caundo el usuario esta en el  paso de  elegir restaurante  estado "pendiente"
        if estado_del_pedido == EstadoPedido.PENDIENTE:
            mensaje = procesar_pedido(mensaje_cliente, numero_cliente, id_pedido_activo , usuario_datos)
            print(f"Mensaje procesado: {usuario_datos}")
            enviar_mensaje_whatsapp(mensaje, numero_cliente)
            return " mensaje enviado",200




        #desarrollar logica cuando el estado del pedido es "enlace" o enlace2
        if estado_del_pedido == EstadoPedido.ENLACE or estado_del_pedido == EstadoPedido.ENLACE2:
            enlace = pedido_activo.enlace
            mensaje = f"Puede continuar con su pedido en el *enlace* proporcionado \n\n▪*Enlace* unico 👇 \n\n🔗{(enlace)}"
            enviar_mensaje_whatsapp(mensaje, numero_cliente)
            return  " mensaje enviado",200

        #desarrollar logica de cuando el usuario este la pagina de pago
        if estado_del_pedido == EstadoPedido.CONFIRMANDO_PAGO:
            enlace_pago = pedido_activo.enlace
            enviar_mensaje_whatsapp(f"🔗 {enlace_pago}\n ✅ Pago seguro  con *MONEI*" , numero_cliente)
            return  " mensaje enviado",200

       

        





