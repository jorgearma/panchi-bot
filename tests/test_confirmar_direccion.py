import unittest
from unittest.mock import patch, MagicMock

# Suponiendo que tu función está en un archivo llamado "utils.confirmar_direccion.py"
from utils.confirmar_direccion import manejar_respuesta_positiva , manejar_respuesta_negativa , confirmar_direccion , enviar_mensaje_registro

class TestManejarRespuestaPositiva(unittest.TestCase):

    @patch("utils.confirmar_direccion.obtener_estado_usuario")
    @patch("utils.confirmar_direccion.registrar_usuario")
    @patch("utils.confirmar_direccion.mostrar_menu")
    @patch("utils.confirmar_direccion.enviar_mensaje_registro")
    @patch("utils.confirmar_direccion.actualizar_estado_usuario")
    @patch("utils.confirmar_direccion.carrito_instancia.inicializar_carrito")
    def test_manejar_respuesta_positiva(
        self,
        mock_inicializar_carrito,
        mock_actualizar_estado_usuario,
        mock_enviar_mensaje_registro,
        mock_mostrar_menu,
        mock_registrar_usuario,
        mock_obtener_estado_usuario,
    ):
        # Configurar valores simulados
        numero_cliente = 12345
        estado_simulado = {"nombre": "Juan", "direccion": "Calle Falsa 123"}
        menu_simulado = "Menu principal"

        mock_obtener_estado_usuario.return_value = estado_simulado
        mock_mostrar_menu.return_value = menu_simulado

        # Ejecutar la función
        resultado, codigo = manejar_respuesta_positiva(numero_cliente)

        # Verificar comportamiento esperado
        mock_obtener_estado_usuario.assert_called_once_with(numero_cliente)
        mock_registrar_usuario.assert_called_once_with(numero_cliente, "Juan", "Calle Falsa 123")
        mock_mostrar_menu.assert_called_once()
        mock_enviar_mensaje_registro.assert_called_once_with(numero_cliente, "Juan", "Menu principal")
        mock_actualizar_estado_usuario.assert_called_once_with(numero_cliente)
        mock_inicializar_carrito.assert_called_once_with(numero_cliente)

        # Verificar resultado
        self.assertEqual(resultado, "Usuario registrado")
        self.assertEqual(codigo, 200)


class TestManejarRespuestaNegativa(unittest.TestCase):

    @patch("utils.confirmar_direccion.enviar_mensaje_whatsapp")  # Mock para enviar_mensaje_whatsapp
    @patch("utils.confirmar_direccion.estado_usuarios", new_callable=dict)  # Mock para estado_usuarios
    def test_manejar_respuesta_negativa(self, mock_estado_usuarios, mock_enviar_mensaje_whatsapp):
        # Configurar valores simulados
        numero_cliente = 12345
        mock_estado_usuarios[numero_cliente] = {"estado": "activo"}

        # Ejecutar la función
        resultado, codigo = manejar_respuesta_negativa(numero_cliente)

        # Verificar que el estado del cliente fue actualizado
        self.assertEqual(mock_estado_usuarios[numero_cliente]["estado"], "esperando_direccion")

        # Verificar que enviar_mensaje_whatsapp fue llamado con los parámetros correctos
        mock_enviar_mensaje_whatsapp.assert_called_once_with(
            "😊 *¡Vale!* Vamos a intentarlo de nuevo.\nPor favor, *ingresa una dirección* \n\n👇 *Ejemplos:* 👇 \n\n•Calle Los Labradores 3, 1B\n•avenida pablo iglecias 79, 1b",
            numero_cliente
        )

        # Verificar el resultado de la función
        self.assertEqual(resultado, "Solicitud de dirección enviada de nuevo")
        self.assertEqual(codigo, 200)

class TestConfirmarDireccion(unittest.TestCase):

    @patch("utils.confirmar_direccion.manejar_respuesta_positiva")  # Mock para manejar_respuesta_positiva
    @patch("utils.confirmar_direccion.manejar_respuesta_negativa")  # Mock para manejar_respuesta_negativa
    def test_confirmar_direccion_respuesta_positiva(self, mock_manejar_respuesta_negativa, mock_manejar_respuesta_positiva):
        # Configurar valores simulados
        numero_cliente = 12345
        mensaje_cliente = "si"
        resultado_esperado = ("Usuario registrado", 200)
        mock_manejar_respuesta_positiva.return_value = resultado_esperado

        # Ejecutar la función
        resultado = confirmar_direccion(numero_cliente, mensaje_cliente)

        # Verificar que manejar_respuesta_positiva fue llamado y manejar_respuesta_negativa no
        mock_manejar_respuesta_positiva.assert_called_once_with(numero_cliente)
        mock_manejar_respuesta_negativa.assert_not_called()

        # Verificar el resultado
        self.assertEqual(resultado, resultado_esperado)

    @patch("utils.confirmar_direccion.manejar_respuesta_positiva")  # Mock para manejar_respuesta_positiva
    @patch("utils.confirmar_direccion.manejar_respuesta_negativa")  # Mock para manejar_respuesta_negativa
    def test_confirmar_direccion_respuesta_negativa(self, mock_manejar_respuesta_negativa, mock_manejar_respuesta_positiva):
        # Configurar valores simulados
        numero_cliente = 12345
        mensaje_cliente = "no"
        resultado_esperado = ("Solicitud de dirección enviada de nuevo", 200)
        mock_manejar_respuesta_negativa.return_value = resultado_esperado

        # Ejecutar la función
        resultado = confirmar_direccion(numero_cliente, mensaje_cliente)

        # Verificar que manejar_respuesta_negativa fue llamado y manejar_respuesta_positiva no
        mock_manejar_respuesta_negativa.assert_called_once_with(numero_cliente)
        mock_manejar_respuesta_positiva.assert_not_called()

        # Verificar el resultado
        self.assertEqual(resultado, resultado_esperado)        

class TestEnviarMensajeRegistro(unittest.TestCase):

    @patch("utils.confirmar_direccion.enviar_mensaje_whatsapp")  # Mock para enviar_mensaje_whatsapp
    def test_enviar_mensaje_registro(self, mock_enviar_mensaje_whatsapp):
        # Configurar valores simulados
        numero_cliente = 12345
        nombre = "Juan"
        menu_despues_registro = "Este es el menú principal"

        # Ejecutar la función
        enviar_mensaje_registro(numero_cliente, nombre, menu_despues_registro)

        # Mensaje esperado
        mensaje_esperado = (
            f"¡Gracias {nombre}! Ahora estás registrado. {menu_despues_registro}                ⬆️ *MENU* ⬆️ \n"
            "❗*Para agregar un producto*❗\n\nescribe el *numero* o su *nombre* \n\n      👇 *Ejemplos* 👇 \n\n"
            " ▪️ *clasica*    o    *301* \n ▪️ *helado*    o    *503* "
        )

        # Verificar que enviar_mensaje_whatsapp fue llamado con los argumentos correctos
        mock_enviar_mensaje_whatsapp.assert_called_once_with(mensaje_esperado, numero_cliente)


if __name__ == "__main__":
    unittest.main()

