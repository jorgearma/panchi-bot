"""
Tests for managers/gestor_usuarios.py:
  - verificar_usuario
  - obtener_usuario_completo
  - guardar_usuario
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from sqlalchemy.exc import SQLAlchemyError

from managers.gestor_usuarios import GestorUsuarios


NUMERO = "whatsapp:+34600000000"


def make_usuario(nombre="Ana García", numero=NUMERO, direccion="Calle Mayor 1", id=1):
    u = MagicMock()
    u.id = id
    u.nombre = nombre
    u.numero_cliente = numero
    u.direccion = direccion
    return u


def make_gestor_with_session(session_mock):
    """Crea un GestorUsuarios con la propiedad session mockeada."""
    g = GestorUsuarios()
    # La propiedad session hace get_db() — la mockeamos a nivel de instancia
    type(g).session = PropertyMock(return_value=session_mock)
    return g


class TestVerificarUsuario:

    def test_usuario_existente_retorna_true(self):
        session = MagicMock()
        usuario = make_usuario()
        session.query.return_value.filter_by.return_value.scalar.return_value = usuario

        gestor = make_gestor_with_session(session)
        result = gestor.verificar_usuario(NUMERO)

        assert result is True

    def test_usuario_no_existente_retorna_false(self):
        session = MagicMock()
        session.query.return_value.filter_by.return_value.scalar.return_value = None

        gestor = make_gestor_with_session(session)
        result = gestor.verificar_usuario(NUMERO)

        assert result is False

    def test_error_bd_relanza_excepcion(self):
        """Tras 3 reintentos fallidos, tenacity lanza RetryError."""
        from tenacity import RetryError
        session = MagicMock()
        session.query.side_effect = SQLAlchemyError("error de prueba")

        gestor = make_gestor_with_session(session)
        with pytest.raises(RetryError):
            gestor.verificar_usuario(NUMERO)


class TestObtenerUsuarioCompleto:

    def test_usuario_existente_retorna_dict(self):
        session = MagicMock()
        usuario = make_usuario()
        session.query.return_value.filter_by.return_value.first.return_value = usuario

        gestor = make_gestor_with_session(session)
        result = gestor.obtener_usuario_completo(NUMERO)

        assert result["id"] == 1
        assert result["nombre"] == "Ana García"
        assert result["numero"] == NUMERO
        assert result["direccion"] == "Calle Mayor 1"

    def test_usuario_no_existente_retorna_none(self):
        session = MagicMock()
        session.query.return_value.filter_by.return_value.first.return_value = None

        gestor = make_gestor_with_session(session)
        result = gestor.obtener_usuario_completo(NUMERO)

        assert result is None


class TestGuardarUsuario:

    def test_usuario_nuevo_llama_add_y_commit(self):
        session = MagicMock()

        gestor = make_gestor_with_session(session)
        gestor.guardar_usuario(NUMERO, "Ana García", "Calle Mayor 1")

        session.add.assert_called_once()
        session.commit.assert_called_once()

    def test_error_bd_hace_rollback_y_relanza(self):
        session = MagicMock()
        session.commit.side_effect = SQLAlchemyError("fallo al guardar")

        gestor = make_gestor_with_session(session)
        with pytest.raises(SQLAlchemyError):
            gestor.guardar_usuario(NUMERO, "Ana García", "Calle Mayor 1")

        session.rollback.assert_called_once()

    def test_devuelve_id_tras_commit(self):
        session = MagicMock()
        usuario_mock = MagicMock()
        usuario_mock.id = 42

        with patch("managers.gestor_usuarios.Usuario", return_value=usuario_mock):
            gestor = make_gestor_with_session(session)
            result = gestor.guardar_usuario(NUMERO, "Ana García", "Calle Mayor 1")

        assert result == 42
