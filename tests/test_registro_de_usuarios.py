import unittest
from unittest.mock import patch , MagicMock
from controllers.registro_de_usuarios.registro import RegistroUsuario , validar_direccion , ValidacionDireccion
from controllers.registro_de_usuarios.registro import Mensajeria


estado_usuarios = {123456789: {"estado": "saludo_inicial"}}


class TestEstadoUsuario(unittest.TestCase):

    @patch('controllers.registro_de_usuarios.registro.estado_usuarios', new_callable=dict)
    def setUp(self, mock_estado_usuarios):
        """Configura el entorno para cada prueba."""
        self.numero_cliente = 123456789
        mock_estado_usuarios[self.numero_cliente] = {"estado": "saludo_inicial"}
        self.estado_usuario = mock_estado_usuarios

    def test_obtener_estado_inicial(self):
        """Prueba que el estado inicial sea 'saludo_inicial' si no hay datos previos."""
        estado = self.estado_usuario[self.numero_cliente]
        self.assertEqual(estado, {"estado": "saludo_inicial"})

    def test_actualizar_estado_nuevo(self):
        """Prueba que el estado se actualice correctamente."""
        nuevo_estado = "registro_nombre"
        self.estado_usuario[self.numero_cliente]["estado"] = nuevo_estado

        # Verificar el nuevo estado
        estado_actualizado = self.estado_usuario[self.numero_cliente]
        self.assertEqual(estado_actualizado["estado"], nuevo_estado)

    def test_actualizar_estado_con_datos_adicionales(self):
        """Prueba que el estado y los datos adicionales se actualicen correctamente."""
        nuevo_estado = "registro_direccion"
        datos_adicionales = {"nombre": "Juan Pérez"}
        self.estado_usuario[self.numero_cliente].update(datos_adicionales)
        self.estado_usuario[self.numero_cliente]["estado"] = nuevo_estado

        # Verificar el estado y los datos adicionales
        estado_actualizado = self.estado_usuario[self.numero_cliente]
        self.assertEqual(estado_actualizado["estado"], nuevo_estado)
        self.assertEqual(estado_actualizado["nombre"], "Juan Pérez")

    def test_actualizar_estado_sobrescribir(self):
        """Prueba que un estado existente se sobrescriba con uno nuevo."""
        nuevo_estado = "registro_completo"
        self.estado_usuario[self.numero_cliente]["estado"] = nuevo_estado

        # Verificar que el estado se haya sobrescrito
        estado_actualizado = self.estado_usuario[self.numero_cliente]
        self.assertEqual(estado_actualizado["estado"], nuevo_estado)


class TestRegistroUsuario(unittest.TestCase):
    def setUp(self):
        self.numero_cliente = "12345"
        self.registro_usuario = RegistroUsuario(self.numero_cliente)

        # Mock de EstadoUsuario y Mensajeria
        self.registro_usuario.estado_usuario = MagicMock()
        self.registro_usuario.estado_usuario.obtener_estado.return_value = {"estado": "saludo_inicial"}
        Mensajeria.enviar_bienvenida = MagicMock()

        Mensajeria.solicitar_nombre = MagicMock()
        Mensajeria.confirmar_cancelacion = MagicMock()
        Mensajeria.solicitar_direccion = MagicMock()
        ValidacionDireccion.validar_y_confirmar_direccion = MagicMock(return_value=True)

    

    def test_manejar_registro_envia_bienvenida(self):
        mensaje_cliente = "Hola"
        respuesta, codigo = self.registro_usuario.manejar_registro(mensaje_cliente)

        # Verificar el resultado
        self.assertEqual(respuesta, "Mensaje de bienvenida enviado")
        self.assertEqual(codigo, 200)

        # Verificar que se llamó a enviar_bienvenida
        Mensajeria.enviar_bienvenida.assert_called_once_with(self.numero_cliente)

        # Verificar que se actualizó el estado
        self.registro_usuario.estado_usuario.actualizar_estado.assert_called_once_with("esperando_confirmacion")


    def test_manejar_registro_confirmacion_exitosa(self):
        self.registro_usuario.estado_usuario.obtener_estado.return_value = {"estado": "esperando_confirmacion"}
        mensaje_cliente = "sí"

        respuesta, codigo = self.registro_usuario.manejar_registro(mensaje_cliente)

        # Verificar resultados
        self.assertEqual(respuesta, "Solicitud de nombre enviada")
        self.assertEqual(codigo, 200)

        # Verificar que se llamó a solicitar_nombre
        Mensajeria.solicitar_nombre.assert_called_once_with(self.numero_cliente)

        # Verificar que se actualizó el estado
        self.registro_usuario.estado_usuario.actualizar_estado.assert_called_once_with("esperando_nombre")

    def test_manejar_registro_cancelacion(self):
        self.registro_usuario.estado_usuario.obtener_estado.return_value = {"estado": "esperando_confirmacion"}
        mensaje_cliente = "no"

        respuesta, codigo = self.registro_usuario.manejar_registro(mensaje_cliente)

        # Verificar resultados
        self.assertEqual(respuesta, "Registro cancelado")
        self.assertEqual(codigo, 200)

        # Verificar que se llamó a confirmar_cancelacion
        Mensajeria.confirmar_cancelacion.assert_called_once_with(self.numero_cliente)

        # Verificar que no se actualizó el estado a "esperando_nombre"
        self.registro_usuario.estado_usuario.actualizar_estado.assert_not_called()


    def test_manejar_registro_solicita_direccion(self):
        self.registro_usuario.estado_usuario.obtener_estado.return_value = {"estado": "esperando_nombre"}
        mensaje_cliente = "Juan Pérez"

        respuesta, codigo = self.registro_usuario.manejar_registro(mensaje_cliente)

        # Verificar resultados
        self.assertEqual(respuesta, "Solicitud de dirección enviada")
        self.assertEqual(codigo, 200)

        # Verificar que se actualizó el estado correctamente
        self.registro_usuario.estado_usuario.actualizar_estado.assert_called_once_with(
            "esperando_direccion", {"nombre": "Juan Pérez"}
        )

        # Verificar que se solicitó la dirección
        Mensajeria.solicitar_direccion.assert_called_once_with(self.numero_cliente)   

    def test_manejar_registro_validar_direccion(self):
        self.registro_usuario.estado_usuario.obtener_estado.return_value = {"estado": "esperando_direccion"}
        mensaje_cliente = "Calle 123, Ciudad, País"

        respuesta, codigo = self.registro_usuario.manejar_registro(mensaje_cliente)

        # Verificar resultados
        self.assertEqual(respuesta, "Solicitud de confirmación de dirección enviada")
        self.assertEqual(codigo, 200)

        # Verificar que la dirección fue validada
        ValidacionDireccion.validar_y_confirmar_direccion.assert_called_once_with(self.numero_cliente, mensaje_cliente)

        # Verificar que el estado fue actualizado correctamente
        self.registro_usuario.estado_usuario.actualizar_estado.assert_called_once_with(
            "confirmando_direccion", {"direccion": mensaje_cliente}
        )         
    @patch('controllers.registro_de_usuarios.registro.confirmar_direccion')
    def test_confirmar_direccion_exitosa(self , mock_confirmar_direccion):
        self.registro_usuario.estado_usuario.obtener_estado.return_value = {"estado": "confirmando_direccion"}
        mensaje_cliente = "confirmar"

        mock_confirmar_direccion.return_value = ("Dirección confirmada", 200)

        respuesta, codigo = self.registro_usuario.manejar_registro(mensaje_cliente)

        # Verificar resultados
        self.assertEqual(respuesta, "Dirección confirmada")
        self.assertEqual(codigo, 200)

        # Verificar que confirmar_direccion fue llamado correctamente
        mock_confirmar_direccion.assert_called_once_with(self.numero_cliente, mensaje_cliente)

    @patch('controllers.registro_de_usuarios.registro.confirmar_direccion')
    def test_confirmar_direccion_fallida(self , mock_confirmar_direccion):
        self.registro_usuario.estado_usuario.obtener_estado.return_value = {"estado": "confirmando_direccion"}
        mensaje_cliente = "no confirmar"

        mock_confirmar_direccion.return_value = ("Dirección no confirmada", 400)

        respuesta, codigo = self.registro_usuario.manejar_registro(mensaje_cliente)

        # Verificar resultados
        self.assertEqual(respuesta, "Dirección no confirmada")
        self.assertEqual(codigo, 400)

        # Verificar que confirmar_direccion fue llamado correctamente
        mock_confirmar_direccion.assert_called_once_with(self.numero_cliente, mensaje_cliente)



if __name__ == '__main__':
    unittest.main()
