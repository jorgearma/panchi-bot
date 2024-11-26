import unittest
from unittest.mock import MagicMock, patch
import random
import json
from data.pedidos import pedido

def normalize_sql(query):
    """Normaliza la consulta SQL eliminando espacios y saltos de línea redundantes."""
    return " ".join(query.split())

class TestPedido(unittest.TestCase):

    def setUp(self):
        """Configuración inicial para cada prueba."""
        self.carrito_instancia = MagicMock()  # Crear el mock localmente
        self.carrito_instancia.carrito = {
            123: [("Producto1", 10.0), ("Producto2", 20.0)]
        }
        self.numero_cliente = 123
        self.mensaje_cliente = "Pedido urgente, por favor."
        self.pedido = pedido(self.numero_cliente, self.mensaje_cliente, self.carrito_instancia)

    def test_generar_id_pedido(self):
        """Prueba que se genere un ID de pedido válido."""
        id_pedido = self.pedido.generar_id_pedido()
        self.assertTrue(1000 <= id_pedido <= 9999)

    def test_inicializar_pedido(self):
        """Prueba que el contenido del pedido se inicialice correctamente."""
        self.assertEqual(self.pedido.contenido_pedido, [("Producto1", 10.0), ("Producto2", 20.0)])
        self.assertIn(self.pedido.id_pedido, range(1000, 10000))

    @patch('builtins.print')  # Para verificar impresiones
    @patch('data.pedidos.conectar_bd')  # Mock de la conexión a la base de datos
    def test_enviar_comanda_a_cocina(self, mock_conectar_bd, mock_print):
        """Prueba el envío de la comanda a la cocina."""
        # Simulación de la conexión y el cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conectar_bd.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # Ejecutar el método
        self.pedido.enviar_comanda_a_cocina()

        # Normalizar las consultas para comparación
        expected_query = normalize_sql("""
            INSERT INTO comandas (id_pedido, contenido)
            VALUES (?, ?);
        """)
        actual_query = normalize_sql(mock_cursor.execute.call_args[0][0])

        # Validar la consulta SQL
        self.assertEqual(expected_query, actual_query)

        # Validar los parámetros
        self.assertEqual(
            (self.pedido.id_pedido, json.dumps(self.pedido.contenido_pedido)),
            mock_cursor.execute.call_args[0][1]
        )

        # Verificar que se llamó a commit
        mock_conn.commit.assert_called_once()

        # Verificar la impresión en consola
        mock_print.assert_called_once_with(
            f"Comanda #{self.pedido.id_pedido} enviada a la cocina: {self.pedido.contenido_pedido}"
        )


if __name__ == "__main__":
    unittest.main()
