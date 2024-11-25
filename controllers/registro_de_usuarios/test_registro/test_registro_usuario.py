import pytest
import unittest
from unittest.mock import patch, MagicMock
from controllers.registro_de_usuarios.registro import manejar_registro, Mensajeria, EstadoUsuario
from data.estado_usuarios import estado_usuarios
from utils.confirmar_direccion import confirmar_direccion

class TestRegistroUsuario(unittest.TestCase):

    @patch.object(Mensajeria, 'enviar_bienvenida')
    @patch.object(EstadoUsuario, 'actualizar_estado')
    def test_saludo_inicial(self, mock_actualizar_estado, mock_enviar_bienvenida):
        numero_cliente = '12345'
        mensaje_cliente = 'Hola'
        
        response = manejar_registro(numero_cliente, mensaje_cliente)
        
        mock_enviar_bienvenida.assert_called_once_with(numero_cliente)
        mock_actualizar_estado.assert_called_once_with('esperando_confirmacion')
        self.assertEqual(response, ("Mensaje de bienvenida enviado", 200))

    @patch.object(confirmar_direccion, 'confirmar_direccion', return_value=True)
    @patch.object(Mensajeria, 'confirmar_direccion')
    @patch.object(EstadoUsuario, 'obtener_estado', return_value={"estado": "esperando_direccion"})
    @patch.object(EstadoUsuario, 'actualizar_estado')
    def test_esperando_direccion_valida(self, mock_actualizar_estado, mock_obtener_estado, mock_confirmar_direccion, mock_confirmar_direccion):
        numero_cliente = '12345'
        mensaje_cliente = 'Calle Falsa 123'
        
        response = manejar_registro(numero_cliente, mensaje_cliente)
        
        mock_confirmar_direccion.assert_called_once_with(numero_cliente, mensaje_cliente)
        mock_actualizar_estado.assert_called_once_with('confirmando_direccion', {'direccion': mensaje_cliente})
        self.assertEqual(response, ("Solicitud de confirmación de dirección enviada", 200))

    @patch.object(confirmar_direccion, 'confirmar_direccion', return_value=False)
    @patch.object(Mensajeria, 'direccion_invalida')
    @patch.object(EstadoUsuario, 'obtener_estado', return_value={"estado": "esperando_direccion"})
    def test_esperando_direccion_invalida(self, mock_obtener_estado, mock_direccion_invalida, mock_confirmar_direccion):
        numero_cliente = '12345'
        mensaje_cliente = 'Dirección inválida'
    
        response = manejar_registro(numero_cliente, mensaje_cliente)
    
        mock_confirmar_direccion.assert_called_once_with(numero_cliente, mensaje_cliente)
        mock_direccion_invalida.assert_called_once_with(numero_cliente)
        self.assertEqual(response, ("Dirección inválida", 400))

if __name__ == '__main__':
    unittest.main()