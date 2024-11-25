import unittest
from unittest.mock import patch, MagicMock

# Suponiendo que la clase está en un archivo llamado "controllers.mensajes_registrados.py"
from controllers.mensajes_registrados import ManejadorMensajesRegistrados

class TestManejadorMensajesRegistrados(unittest.TestCase):

    @patch("controllers.mensajes_registrados.verificar_pedido_activo")
    @patch("controllers.mensajes_registrados.manejar_usuario")
    @patch("controllers.mensajes_registrados.manejar_consulta_carrito")
    @patch("controllers.mensajes_registrados.PedidoHandler")
    @patch("controllers.mensajes_registrados.procesar_mensaje_como_pedido")
    def test_manejar_mensajes_registrados(
        self,
        mock_procesar_mensaje_como_pedido,
        mock_PedidoHandler,
        mock_manejar_consulta_carrito,
        mock_manejar_usuario,
        mock_verificar_pedido_activo
    ):
        # Configuración inicial
        carrito_mock = MagicMock()
        pedidos_activos_mock = {}
        manejador = ManejadorMensajesRegistrados(carrito_mock)
        manejador.pedidos_activos = pedidos_activos_mock

        numero_cliente = 12345
        mensaje_cliente = "Test mensaje"

        # Caso 1: verificar_pedido_activo devuelve respuesta
        mock_verificar_pedido_activo.return_value = "Pedido activo"
        respuesta = manejador.manejar_mensajes_registrados(numero_cliente, mensaje_cliente)
        self.assertEqual(respuesta, "Pedido activo")
        mock_verificar_pedido_activo.assert_called_once_with(numero_cliente, mensaje_cliente, pedidos_activos_mock)

        # Caso 2: manejar_usuario devuelve respuesta
        mock_verificar_pedido_activo.reset_mock()
        mock_verificar_pedido_activo.return_value = None
        mock_manejar_usuario.return_value = "Usuario manejado"
        respuesta = manejador.manejar_mensajes_registrados(numero_cliente, mensaje_cliente)
        self.assertEqual(respuesta, "Usuario manejado")
        mock_manejar_usuario.assert_called_once_with(numero_cliente)

        # Caso 3: manejar_consulta_carrito devuelve True
        mock_manejar_usuario.reset_mock()
        mock_manejar_usuario.return_value = None
        mock_manejar_consulta_carrito.return_value = True
        respuesta = manejador.manejar_mensajes_registrados(numero_cliente, mensaje_cliente)
        self.assertEqual(respuesta, ("Mensaje enviado", 200))
        mock_manejar_consulta_carrito.assert_called_once_with(mensaje_cliente, numero_cliente, carrito_mock)

        # Caso 4: PedidoHandler.salir_o_proceder_al_pago devuelve True
        mock_manejar_consulta_carrito.reset_mock()
        mock_manejar_consulta_carrito.return_value = False
        mock_pedido_handler_instance = MagicMock()
        mock_pedido_handler_instance.salir_o_proceder_al_pago.return_value = True
        mock_PedidoHandler.return_value = mock_pedido_handler_instance
        respuesta = manejador.manejar_mensajes_registrados(numero_cliente, mensaje_cliente)
        self.assertEqual(respuesta, ("Mensaje enviado", 200))
        mock_PedidoHandler.assert_called_once_with(numero_cliente)
        mock_pedido_handler_instance.salir_o_proceder_al_pago.assert_called_once_with(mensaje_cliente)

        # Caso 5: PedidoHandler.procesar_metodo_pago devuelve True
        mock_pedido_handler_instance.reset_mock()
        mock_pedido_handler_instance.salir_o_proceder_al_pago.return_value = False
        mock_pedido_handler_instance.procesar_metodo_pago.return_value = True
        respuesta = manejador.manejar_mensajes_registrados(numero_cliente, mensaje_cliente)
        self.assertEqual(respuesta, ("Mensaje enviado", 200))
        mock_pedido_handler_instance.procesar_metodo_pago.assert_called_once_with(mensaje_cliente)

        # Caso 6: procesar_mensaje_como_pedido maneja el mensaje
        mock_pedido_handler_instance.reset_mock()
        mock_pedido_handler_instance.procesar_metodo_pago.return_value = False
        mock_procesar_mensaje_como_pedido.return_value = "Mensaje procesado como pedido"
        respuesta = manejador.manejar_mensajes_registrados(numero_cliente, mensaje_cliente)
        self.assertEqual(respuesta, "Mensaje procesado como pedido")
        mock_procesar_mensaje_como_pedido.assert_called_once_with(mensaje_cliente, numero_cliente)

if __name__ == "__main__":
    unittest.main()
