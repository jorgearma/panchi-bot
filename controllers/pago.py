from data.carrito import carrito_instancia, mostrar_carrito_sin_mensaje, mostrar_carrito 
from utils.mensajes import enviar_mensaje_whatsapp
from data.pedidos import enviar_comanda_a_cocina, guardar_pedido, pedido 
from data.pedidos_activos import pedidos_activos

class PedidoHandler:
    def __init__(self, numero_cliente):
        self.numero_cliente = numero_cliente

    def preguntar_metodo_pago(self):
        mensaje = "🔷¿como te gustaria pagar?🔷\n           👇 Escribe 👇 \n\n▪️ *Efectivo*  O   *Tarjeta* ▪️"
        enviar_mensaje_whatsapp(mensaje, self.numero_cliente)

    def procesar_pago(self, total, metodo_pago):
        if metodo_pago == 'efectivo':
            mensaje_pago = f"El total es de ${total:.2f}. El pago se realizará en efectivo al momento de la entrega."
        elif metodo_pago == 'tarjeta':
            mensaje_pago = f"El total es de ${total:.2f}. El pago se procesará mediante tarjeta en el momento de la entrega."
        else:
            mensaje_pago = "Método de pago no reconocido."

        enviar_mensaje_whatsapp(mensaje_pago, self.numero_cliente)
        enviar_mensaje_whatsapp("Tu pedido ha sido registrado con éxito. ¡Gracias por tu compra!\n", self.numero_cliente)

    def salir_o_proceder_al_pago(self, mensaje_cliente):
        if mensaje_cliente in ["salir", "nada más", "eso es todo", "pagar"]:
            if not carrito_instancia.verificar_carrito(self.numero_cliente):
                enviar_mensaje_whatsapp("No tienes ningún pedido. ¡Gracias y que tenga un buen día!", self.numero_cliente)
            else:
                carrito_cliente1 = carrito_instancia.obtener_carrito_cliente(self.numero_cliente)
                total = mostrar_carrito_sin_mensaje(carrito_cliente1)
                enviar_mensaje_whatsapp(total, self.numero_cliente)
                self.preguntar_metodo_pago()
            return True
        return False

    def procesar_metodo_pago(self, mensaje_cliente):
        if mensaje_cliente in ["efectivo", "tarjeta"]:
            pedido1 = pedido(self.numero_cliente, mensaje_cliente)
            productos, total = mostrar_carrito(pedido1.contenido_pedido)
            self.procesar_pago(total, mensaje_cliente)

            pedidos_activos[self.numero_cliente] = {
                "id_pedido": pedido1.id_pedido,
                "contenido": pedido1.contenido_pedido
            }

            guardar_pedido(self.numero_cliente, pedido1.contenido_pedido, pedido1.id_pedido)
            pedido1.enviar_comanda_a_cocina()

            enviar_mensaje_whatsapp(
                f"Su pedido está confirmado y en preparación. Su número de pedido es: {pedido1.id_pedido}",
                self.numero_cliente
            )

            carrito_instancia.eliminar_carrito(self.numero_cliente)
            return True
        return False


