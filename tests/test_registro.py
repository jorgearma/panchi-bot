"""
Tests del flujo de registro de usuario (máquina de estados en Redis).
Mockea Redis y Twilio — sin efectos externos.
"""
import pytest
from unittest.mock import MagicMock, patch
from states import EstadoRegistro


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_redis_manager(estado_inicial: str = EstadoRegistro.SALUDO_INICIAL):
    """RedisManager simulado que guarda estado en memoria."""
    store = {}
    if estado_inicial:
        import json
        store["whatsapp:+34600000000"] = json.dumps({"estado": estado_inicial})

    rm = MagicMock()
    rm.get.side_effect = lambda k: store.get(k)
    rm.set.side_effect = lambda k, v, ex=None: store.update({k: v})
    return rm


NUMERO = "whatsapp:+34600000000"


def manejar(mensaje, estado_inicial=EstadoRegistro.SALUDO_INICIAL):
    """Helper: ejecuta manejar_registro con el estado dado, mockeando Twilio."""
    from controllers.registro import manejar_registro
    rm = make_redis_manager(estado_inicial)
    with patch("controllers.registro_notifier.enviar_mensaje_whatsapp"):
        with patch("controllers.registro._enviar_bienvenida"):
            with patch("controllers.registro._solicitar_nombre"):
                with patch("controllers.registro._solicitar_direccion"):
                    return manejar_registro(NUMERO, mensaje, rm), rm


# ---------------------------------------------------------------------------
# saludo_inicial → esperando_confirmacion
# ---------------------------------------------------------------------------

class TestSaludoInicial:
    def test_cualquier_mensaje_envia_bienvenida(self):
        from controllers.registro import manejar_registro, RegistroUsuario
        from managers.estado_usuario import EstadoUsuario
        rm = make_redis_manager(EstadoRegistro.SALUDO_INICIAL)

        with patch("controllers.registro._enviar_bienvenida") as mock_bienvenida:
            with patch("controllers.registro_notifier.enviar_mensaje_whatsapp"):
                resultado = manejar_registro(NUMERO, "hola", rm)

        mock_bienvenida.assert_called_once_with(NUMERO)
        assert resultado[1] == 200

    def test_transiciona_a_esperando_confirmacion(self):
        import json
        rm = make_redis_manager(EstadoRegistro.SALUDO_INICIAL)
        with patch("controllers.registro._enviar_bienvenida"):
            with patch("controllers.registro_notifier.enviar_mensaje_whatsapp"):
                from controllers.registro import manejar_registro
                manejar_registro(NUMERO, "hola", rm)

        estado_guardado = json.loads(rm.set.call_args[0][1])["estado"]
        assert estado_guardado == EstadoRegistro.ESPERANDO_CONFIRMACION


# ---------------------------------------------------------------------------
# esperando_confirmacion
# ---------------------------------------------------------------------------

class TestEsperandoConfirmacion:
    @pytest.mark.parametrize("respuesta", ["si", "sí", "quiero", "adelante"])
    def test_respuesta_afirmativa_avanza(self, respuesta):
        from controllers.registro import manejar_registro
        import json
        rm = make_redis_manager(EstadoRegistro.ESPERANDO_CONFIRMACION)
        with patch("controllers.registro._solicitar_nombre"):
            with patch("controllers.registro_notifier.enviar_mensaje_whatsapp"):
                result = manejar_registro(NUMERO, respuesta, rm)
        assert result[1] == 200
        estado_guardado = json.loads(rm.set.call_args[0][1])["estado"]
        assert estado_guardado == EstadoRegistro.ESPERANDO_NOMBRE

    def test_respuesta_negativa_cancela_sin_avanzar(self):
        from controllers.registro import manejar_registro
        rm = make_redis_manager(EstadoRegistro.ESPERANDO_CONFIRMACION)
        with patch("controllers.registro._enviar_registro_pendiente"):
            with patch("controllers.registro_notifier.enviar_mensaje_whatsapp"):
                result = manejar_registro(NUMERO, "no", rm)
        assert result[1] == 200
        rm.set.assert_not_called()


# ---------------------------------------------------------------------------
# esperando_nombre
# ---------------------------------------------------------------------------

class TestEsperandoNombre:
    def test_nombre_valido_avanza_a_direccion(self):
        from controllers.registro import manejar_registro
        import json
        rm = make_redis_manager(EstadoRegistro.ESPERANDO_NOMBRE)
        with patch("controllers.registro._es_nombre_valido", return_value=True):
            with patch("controllers.registro._solicitar_direccion"):
                with patch("controllers.registro_notifier.enviar_mensaje_whatsapp"):
                    result = manejar_registro(NUMERO, "Juan Pérez", rm)
        assert result[1] == 200
        datos = json.loads(rm.set.call_args[0][1])
        assert datos["estado"] == EstadoRegistro.ESPERANDO_DIRECCION
        assert datos["nombre"] == "Juan Pérez"

    def test_nombre_invalido_no_avanza(self):
        from controllers.registro import manejar_registro
        rm = make_redis_manager(EstadoRegistro.ESPERANDO_NOMBRE)
        with patch("controllers.registro._es_nombre_valido", return_value=False):
            with patch("controllers.registro_notifier.enviar_mensaje_whatsapp"):
                result = manejar_registro(NUMERO, "123abc", rm)
        assert result[1] == 400
        rm.set.assert_not_called()


# ---------------------------------------------------------------------------
# esperando_direccion
# ---------------------------------------------------------------------------

class TestEsperandoDireccion:
    def test_direccion_valida_avanza_a_confirmando(self):
        from controllers.registro import manejar_registro
        import json
        rm = make_redis_manager(EstadoRegistro.ESPERANDO_DIRECCION)
        with patch("controllers.registro.validar_direccion",
                   return_value=(True, "Calle Mayor 1")):
            with patch("controllers.registro_notifier.enviar_mensaje_whatsapp"):
                result = manejar_registro(NUMERO, "Calle Mayor 1", rm)
        assert result[1] == 200
        datos = json.loads(rm.set.call_args[0][1])
        assert datos["estado"] == EstadoRegistro.CONFIRMANDO_DIRECCION
        assert datos["direccion"] == "Calle Mayor 1"

    def test_direccion_invalida_no_avanza(self):
        from controllers.registro import manejar_registro
        rm = make_redis_manager(EstadoRegistro.ESPERANDO_DIRECCION)
        with patch("controllers.registro.validar_direccion",
                   return_value=(False, None)):
            with patch("controllers.registro_notifier.enviar_mensaje_whatsapp"):
                result = manejar_registro(NUMERO, "xyz", rm)
        assert result[1] == 400
        rm.set.assert_not_called()


# ---------------------------------------------------------------------------
# confirmando_direccion
# ---------------------------------------------------------------------------

class TestConfirmandoDireccion:
    def test_confirmar_avanza_al_handler_externo(self):
        """confirmar_direccion devuelve algo != 1 → se propaga la respuesta."""
        from controllers.registro import manejar_registro
        rm = make_redis_manager(EstadoRegistro.CONFIRMANDO_DIRECCION)
        with patch("controllers.registro.confirmar_direccion", return_value=("ok", 200)):
            with patch("controllers.registro_notifier.enviar_mensaje_whatsapp"):
                result = manejar_registro(NUMERO, "si", rm)
        assert result == ("ok", 200)
        rm.set.assert_not_called()

    def test_rollback_si_usuario_dice_no(self):
        """confirmar_direccion devuelve 1 → rollback a esperando_direccion."""
        from controllers.registro import manejar_registro
        import json
        rm = make_redis_manager(EstadoRegistro.CONFIRMANDO_DIRECCION)
        with patch("controllers.registro.confirmar_direccion", return_value=False):
            with patch("controllers.registro_notifier.enviar_mensaje_whatsapp"):
                result = manejar_registro(NUMERO, "no", rm)
        assert result[1] == 200
        estado_guardado = json.loads(rm.set.call_args[0][1])["estado"]
        assert estado_guardado == EstadoRegistro.ESPERANDO_DIRECCION
