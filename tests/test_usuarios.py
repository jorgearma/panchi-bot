import unittest
from unittest.mock import MagicMock, patch
from data.usuarios import GestorUsuarios

class TestGestorUsuarios(unittest.TestCase):

    @patch('data.usuarios.GestorUsuariosBD')
    def test_registrar_usuario(self, mock_bd):
        """Prueba el registro de un usuario."""
        # Configuración del mock
        mock_bd.guardar_usuario.return_value = None
        mock_bd.obtener_usuario.return_value = {
            "numero": "12345",
            "nombre": "Test Usuario",
            "direccion": "Calle Falsa 123"
        }

        # Llamar al método
        usuario = GestorUsuarios.registrar_usuario("12345", "Test Usuario", "Calle Falsa 123")

        # Verificar resultados
        mock_bd.guardar_usuario.assert_called_once_with("12345", "Test Usuario", "Calle Falsa 123")
        mock_bd.obtener_usuario.assert_called_once_with("12345")
        self.assertEqual(usuario["nombre"], "Test Usuario")
        self.assertEqual(usuario["direccion"], "Calle Falsa 123")

    @patch('data.usuarios.obtener_usuario_bd')
    def test_obtener_nombre_usuario(self, mock_obtener_usuario_bd):
        """Prueba la obtención del nombre del usuario."""
        # Configuración del mock
        mock_obtener_usuario_bd.return_value = {"nombre": "Test Usuario"}

        # Llamar al método
        nombre = GestorUsuarios.obtener_nombre_usuario("12345")

        # Verificar resultados
        mock_obtener_usuario_bd.assert_called_once_with("12345")
        self.assertEqual(nombre, "Test Usuario")

    @patch('data.usuarios.enviar_mensaje_whatsapp')
    @patch('data.usuarios.mostrar_menu')
    @patch('data.usuarios.carrito_instancia')
    @patch('data.usuarios.estado_usuarios', {})
    @patch('data.usuarios.GestorUsuarios.obtener_nombre_usuario')
    class TestGestorUsuarios(unittest.TestCase):

        def setUp(self):
            """Configuración inicial para las pruebas de manejo de usuario."""
            # Mocks comunes
            self.mock_carrito_instancia = patch('data.gestor_usuarios.carrito_instancia').start()
            self.mock_mostrar_menu = patch('data.gestor_usuarios.mostrar_menu').start()
            self.mock_enviar_mensaje = patch('data.gestor_usuarios.enviar_mensaje_whatsapp').start()
            self.mock_obtener_nombre_usuario = patch('data.gestor_usuarios.GestorUsuarios.obtener_nombre_usuario').start()

            # Configuración de los mocks
            self.mock_carrito_instancia.verificar_carrito.return_value = False
            self.mock_mostrar_menu.return_value = "Este es el menú."
            self.mock_obtener_nombre_usuario.return_value = "Test Usuario"

            # Estado inicial
            self.estado_usuarios = {"12345": {"recien_registrado": True}}
            patch('data.gestor_usuarios.estado_usuarios', self.estado_usuarios).start()

        def tearDown(self):
            """Detener todos los mocks después de cada prueba."""
            patch.stopall()

        def test_manejar_usuario(self):
            """Prueba el manejo del usuario."""
            from data.gestor_usuarios import GestorUsuarios

            # Primera llamada: elimina "recien_registrado"
            GestorUsuarios.manejar_usuario("12345")
            self.assertNotIn("recien_registrado", self.estado_usuarios["12345"])

            # Segunda llamada: inicializa el carrito y envía mensaje
            self.estado_usuarios["12345"] = {}
            GestorUsuarios.manejar_usuario("12345")
            
            self.mock_carrito_instancia.verificar_carrito.assert_called_once_with("12345")
            self.mock_carrito_instancia.inicializar_carrito.assert_called_once_with("12345")
            self.mock_mostrar_menu.assert_called_once()
            self.mock_enviar_mensaje.assert_called_once_with(
                "¡Hola Test Usuario! 👋 Bienvenido de nuevo. Este es el menú.                ⬆️ *MENU* ⬆️ \n❗*Para agregar un producto*❗\n\nescribe el *numero* o su *nombre* \n\n      👇 *Ejemplos* 👇 \n\n ▪️ *clasica*    o    *301* \n ▪️ *helado*    o    *503* ",
                "12345"
            )
