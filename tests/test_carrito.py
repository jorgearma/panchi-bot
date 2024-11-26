import unittest
from unittest.mock import patch, MagicMock
from data.carrito import Carrito

class TestCarrito(unittest.TestCase):

    def setUp(self):
        """Se ejecuta antes de cada prueba, inicializando un carrito"""
        self.carrito = Carrito()

    def test_inicializar_carrito(self):
        """Prueba que un carrito se inicialice correctamente para un cliente"""
        self.carrito.inicializar_carrito(123)
        self.assertIn(123, self.carrito.carrito)
        self.assertEqual(self.carrito.carrito[123], [])

    def test_obtener_carrito_cliente(self):
        """Prueba la obtención de un carrito para un cliente"""
        self.carrito.inicializar_carrito(123)
        carrito_cliente = self.carrito.obtener_carrito_cliente(123)
        self.assertEqual(carrito_cliente, [])
        self.assertIsNone(self.carrito.obtener_carrito_cliente(456))  # Cliente no inicializado

    def test_agregar_productos(self):
        """Prueba la adición de productos al carrito"""
        self.carrito.agregar_productos(123, [("Producto1", 10.0), ("Producto2", 20.0)])
        self.assertEqual(self.carrito.carrito[123], [("Producto1", 10.0), ("Producto2", 20.0)])
        
        # Agregar más productos al mismo cliente
        self.carrito.agregar_productos(123, [("Producto3", 30.0)])
        self.assertEqual(self.carrito.carrito[123], [("Producto1", 10.0), ("Producto2", 20.0), ("Producto3", 30.0)])

    def test_calcular_total(self):
        """Prueba el cálculo del total del carrito"""
        carrito_cliente = [("Producto1", 10.0), ("Producto2", 20.0), ("Producto3", 30.0)]
        total = self.carrito.calcular_total(carrito_cliente)
        self.assertEqual(total, 60.0)

    def test_mostrar_carrito_sin_mensaje(self):
        """Prueba la generación del resumen del carrito sin mensaje adicional"""
        # Caso: Carrito vacío
        resultado, total = self.carrito.mostrar_carrito_sin_mensaje([])
        self.assertEqual(resultado, "Tu carrito está vacío.\n")
        self.assertEqual(total, 0)

        # Caso: Carrito con productos
        carrito_cliente = [("Producto1", 10.0), ("Producto2", 20.0)]
        resultado, total = self.carrito.mostrar_carrito_sin_mensaje(carrito_cliente)
        self.assertIn("Producto1: *€10.00*", resultado)
        self.assertIn("Producto2: *€20.00*", resultado)
        self.assertIn("Total a pagar: *€30.00*", resultado)
        self.assertEqual(total, 30.0)

if __name__ == "__main__":
    unittest.main()
