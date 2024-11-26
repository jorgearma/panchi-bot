import unittest
from unittest.mock import patch, MagicMock
from controllers.pago import PedidoHandler

class TestPedidoHandler(unittest.TestCase):
    def setUp(self):
        self.numero_cliente = "123456789"
        self.handler = PedidoHandler(self.numero_cliente)

    @patch('controllers.pago.enviar_mensaje_whatsapp')
    def test_preguntar_metodo_pago(self, mock_enviar_mensaje):
        self.handler.preguntar_metodo_pago()
        mock_enviar_mensaje.assert_called_once_with(
            "🔷¿como te gustaria pagar?🔷\n           👇 Escribe 👇 \n\n▪️ *Efectivo*  O   *Tarjeta* ▪️",
            self.numero_cliente
        )

    @patch('controllers.pago.enviar_mensaje_whatsapp')
    def test_procesar_pago_efectivo(self, mock_enviar_mensaje):
        self.handler.procesar_pago(100, "efectivo")
        mock_enviar_mensaje.assert_any_call(
            "El total es de $100.00. El pago se realizará en efectivo al momento de la entrega.",
            self.numero_cliente
        )
        mock_enviar_mensaje.assert_any_call(
            "Tu pedido ha sido registrado con éxito. ¡Gracias por tu compra!\n",
            self.numero_cliente
        )

    @patch('controllers.pago.enviar_mensaje_whatsapp')
    def test_procesar_pago_tarjeta(self, mock_enviar_mensaje):
        self.handler.procesar_pago(100, "tarjeta")
        mock_enviar_mensaje.assert_any_call(
            "El total es de $100.00. El pago se procesará mediante tarjeta en el momento de la entrega.",
            self.numero_cliente
        )
        mock_enviar_mensaje.assert_any_call(
            "Tu pedido ha sido registrado con éxito. ¡Gracias por tu compra!\n",
            self.numero_cliente
        )

    

    @patch('controllers.pago.enviar_mensaje_whatsapp')
    @patch('controllers.pago.carrito_instancia')
    def test_salir_o_proceder_al_pago_sin_pedido(self, mock_carrito_instancia, mock_enviar_mensaje):
        mock_carrito_instancia.verificar_carrito.return_value = False
        result = self.handler.salir_o_proceder_al_pago("salir")
        self.assertTrue(result)
        mock_enviar_mensaje.assert_called_once_with(
            "No tienes ningún pedido. ¡Gracias y que tenga un buen día!",
            self.numero_cliente
        )

    @patch('controllers.pago.enviar_mensaje_whatsapp')
    @patch('controllers.pago.carrito_instancia')
    @patch('controllers.pago.mostrar_carrito_sin_mensaje')
    def test_salir_o_proceder_al_pago_con_pedido(self, mock_mostrar_carrito, mock_carrito_instancia, mock_enviar_mensaje):
        mock_carrito_instancia.verificar_carrito.return_value = True
        mock_carrito_instancia.obtener_carrito_cliente.return_value = ["item1", "item2"]
        mock_mostrar_carrito.return_value = "Total: $200"

        result = self.handler.salir_o_proceder_al_pago("pagar")
        self.assertTrue(result)
        mock_enviar_mensaje.assert_any_call("Total: $200", self.numero_cliente)
        mock_enviar_mensaje.assert_any_call(
            "🔷¿como te gustaria pagar?🔷\n           👇 Escribe 👇 \n\n▪️ *Efectivo*  O   *Tarjeta* ▪️",
            self.numero_cliente
        )

    @patch('controllers.pago.guardar_pedido')
    @patch('controllers.pago.pedido')
    @patch('controllers.pago.enviar_mensaje_whatsapp')
    @patch('controllers.pago.mostrar_carrito')
    @patch('controllers.pago.carrito_instancia')
    def test_procesar_metodo_pago(self, mock_carrito_instancia, mock_mostrar_carrito, mock_enviar_mensaje, mock_pedido, mock_guardar_pedido):
        mock_pedido.return_value.id_pedido = "1234"
        mock_pedido.return_value.contenido_pedido = ["item1", "item2"]
        mock_mostrar_carrito.return_value = (["item1", "item2"], 200)

        result = self.handler.procesar_metodo_pago("efectivo")
        self.assertTrue(result)

        mock_pedido.assert_called_once_with(self.numero_cliente, "efectivo")
        mock_mostrar_carrito.assert_called_once_with(["item1", "item2"])
        mock_guardar_pedido.assert_called_once_with(self.numero_cliente, ["item1", "item2"], "1234")
        mock_carrito_instancia.eliminar_carrito.assert_called_once_with(self.numero_cliente)
        mock_enviar_mensaje.assert_any_call(
            "Su pedido está confirmado y en preparación. Su número de pedido es: 1234",
            self.numero_cliente
        )

