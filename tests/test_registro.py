"""
Tests del flujo de registro de usuario (máquina de estados en Redis).
Mockea Redis y Twilio — sin efectos externos.
"""
import json
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.exc import SQLAlchemyError
from states import EstadoRegistro


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NUMERO = "whatsapp:+34600000000"


def make_redis_manager(estado_redis: dict | str = EstadoRegistro.SALUDO_INICIAL):
    """RedisManager simulado que guarda estado en memoria.

    Acepta un string (solo estado) o un dict completo (estado + datos).
    """
    store = {}
    if isinstance(estado_redis, str):
        store[NUMERO] = json.dumps({"estado": estado_redis})
    elif isinstance(estado_redis, dict):
        store[NUMERO] = json.dumps(estado_redis)

    rm = MagicMock()
    rm.get.side_effect = lambda k: store.get(k)
    rm.set.side_effect = lambda k, v, ex=None: store.update({k: v})
    return rm


def make_registro_usuario(estado_redis):
    """Crea RegistroUsuario con Redis simulado."""
    from controllers.registro import RegistroUsuario
    rm = make_redis_manager(estado_redis)
    return RegistroUsuario(NUMERO, rm), rm


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
# _es_nombre_valido
# ---------------------------------------------------------------------------

class TestEsNombreValido:
    def _valido(self, nombre):
        from controllers.registro import _es_nombre_valido
        return _es_nombre_valido(nombre)

    @pytest.mark.parametrize("nombre", [
        "Ana", "Juan Pérez", "María José", "O'Brien", "Jean-Luc",
        "Ñoño García", "  Ana García  ",  # strip manejado antes
    ])
    def test_nombres_validos(self, nombre):
        assert self._valido(nombre) is True

    @pytest.mark.parametrize("nombre", [
        "",         # vacío
        "A",        # demasiado corto
        "123",      # solo números
        "Ana123",   # letras y números
        "A" * 61,   # demasiado largo
        "Ana@mail",  # carácter inválido
    ])
    def test_nombres_invalidos(self, nombre):
        assert self._valido(nombre) is False


# ---------------------------------------------------------------------------
# saludo_inicial → esperando_confirmacion
# ---------------------------------------------------------------------------

class TestSaludoInicial:
    def test_cualquier_mensaje_envia_bienvenida(self):
        from controllers.registro import manejar_registro
        rm = make_redis_manager(EstadoRegistro.SALUDO_INICIAL)

        with patch("controllers.registro._enviar_bienvenida") as mock_bienvenida:
            with patch("controllers.registro_notifier.enviar_mensaje_whatsapp"):
                resultado = manejar_registro(NUMERO, "hola", rm)

        mock_bienvenida.assert_called_once_with(NUMERO)
        assert resultado[1] == 200

    def test_transiciona_a_esperando_confirmacion(self):
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

    def test_respuesta_negativa_borra_redis(self):
        from controllers.registro import manejar_registro
        rm = make_redis_manager(EstadoRegistro.ESPERANDO_CONFIRMACION)
        with patch("controllers.registro._enviar_registro_pendiente"):
            with patch("controllers.registro_notifier.enviar_mensaje_whatsapp"):
                manejar_registro(NUMERO, "no", rm)
        rm.delete.assert_called_once_with(NUMERO)


# ---------------------------------------------------------------------------
# esperando_nombre
# ---------------------------------------------------------------------------

class TestEsperandoNombre:
    def test_nombre_valido_avanza_a_direccion(self):
        from controllers.registro import manejar_registro
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
        assert result[1] == 200  # 200 para evitar reintento de Meta (H3)
        rm.set.assert_not_called()

    def test_nombre_invalido_envia_mensaje_error(self):
        from controllers.registro import manejar_registro
        rm = make_redis_manager(EstadoRegistro.ESPERANDO_NOMBRE)
        with patch("controllers.registro._es_nombre_valido", return_value=False):
            with patch("controllers.registro._enviar_nombre_invalido") as mock_err:
                with patch("controllers.registro_notifier.enviar_mensaje_whatsapp"):
                    manejar_registro(NUMERO, "123abc", rm)
        mock_err.assert_called_once_with(NUMERO)

    def test_nombre_con_espacios_extremos_se_strip(self):
        """El strip se aplica antes de validar y guardar."""
        from controllers.registro import manejar_registro
        rm = make_redis_manager(EstadoRegistro.ESPERANDO_NOMBRE)
        with patch("controllers.registro._solicitar_direccion"):
            with patch("controllers.registro_notifier.enviar_mensaje_whatsapp"):
                manejar_registro(NUMERO, "  Ana García  ", rm)
        datos = json.loads(rm.set.call_args[0][1])
        assert datos["nombre"] == "Ana García"


# ---------------------------------------------------------------------------
# esperando_direccion
# ---------------------------------------------------------------------------

class TestEsperandoDireccion:
    def test_direccion_valida_avanza_a_confirmando(self):
        from controllers.registro import manejar_registro
        rm = make_redis_manager(EstadoRegistro.ESPERANDO_DIRECCION)
        with patch("controllers.registro.validar_direccion",
                   return_value=(True, "Calle Mayor 1", None)):
            with patch("controllers.registro._enviar_confirmacion_direccion"):
                result = manejar_registro(NUMERO, "Calle Mayor 1", rm)
        assert result[1] == 200
        datos = json.loads(rm.set.call_args[0][1])
        assert datos["estado"] == EstadoRegistro.CONFIRMANDO_DIRECCION
        assert datos["direccion"] == "Calle Mayor 1"

    def test_direccion_invalida_no_avanza(self):
        from controllers.registro import manejar_registro
        rm = make_redis_manager(EstadoRegistro.ESPERANDO_DIRECCION)
        with patch("controllers.registro.validar_direccion",
                   return_value=(False, None, "no_encontrada")):
            with patch("controllers.registro_notifier.enviar_mensaje_whatsapp"):
                result = manejar_registro(NUMERO, "xyz", rm)
        assert result[1] == 200  # 200 para evitar reintento de Meta (H3)
        rm.set.assert_not_called()

    def test_fuera_de_zona_no_llama_sugerir_calle(self):
        """Motivo fuera_de_zona no debe intentar sugerir calle alternativa."""
        from controllers.registro import manejar_registro
        rm = make_redis_manager(EstadoRegistro.ESPERANDO_DIRECCION)
        with patch("controllers.registro.validar_direccion",
                   return_value=(False, None, "fuera_de_zona")):
            with patch("controllers.registro.sugerir_calle") as mock_sugerir:
                with patch("controllers.registro._enviar_direccion_invalida"):
                    manejar_registro(NUMERO, "Calle Inexistente 1", rm)
        mock_sugerir.assert_not_called()

    def test_sugerir_calle_falla_continua_sin_sugerencia(self):
        """Si sugerir_calle lanza excepción, el flujo continúa sin bloquear."""
        from controllers.registro import manejar_registro
        rm = make_redis_manager(EstadoRegistro.ESPERANDO_DIRECCION)
        with patch("controllers.registro.validar_direccion",
                   return_value=(False, None, "no_encontrada")):
            with patch("controllers.registro.sugerir_calle", side_effect=Exception("Maps caído")):
                with patch("controllers.registro._enviar_direccion_invalida") as mock_env:
                    result = manejar_registro(NUMERO, "Calle Rota", rm)
        assert result[1] == 200
        mock_env.assert_called_once_with(NUMERO, None, None)


# ---------------------------------------------------------------------------
# confirmando_direccion — manejar_registro nivel
# ---------------------------------------------------------------------------

class TestConfirmandoDireccion:
    def test_confirmar_avanza_al_handler_externo(self):
        """_confirmar_direccion devuelve algo != False → se propaga la respuesta."""
        from controllers.registro import manejar_registro, RegistroUsuario
        rm = make_redis_manager(EstadoRegistro.CONFIRMANDO_DIRECCION)
        with patch.object(RegistroUsuario, "_confirmar_direccion", return_value=("ok", 200)):
            with patch("controllers.registro_notifier.enviar_mensaje_whatsapp"):
                result = manejar_registro(NUMERO, "si", rm)
        assert result == ("ok", 200)
        rm.set.assert_not_called()

    def test_rollback_si_usuario_dice_no(self):
        """_confirmar_direccion devuelve False → rollback a esperando_direccion."""
        from controllers.registro import manejar_registro, RegistroUsuario
        rm = make_redis_manager(EstadoRegistro.CONFIRMANDO_DIRECCION)
        with patch.object(RegistroUsuario, "_confirmar_direccion", return_value=False):
            with patch("controllers.registro_notifier.enviar_mensaje_whatsapp"):
                result = manejar_registro(NUMERO, "no", rm)
        assert result[1] == 200
        estado_guardado = json.loads(rm.set.call_args[0][1])["estado"]
        assert estado_guardado == EstadoRegistro.ESPERANDO_DIRECCION

    def test_respuesta_invalida_pide_confirmacion_sin_cambiar_estado(self):
        """Respuesta que no sea si/sí/no → pide que confirme, estado intacto."""
        from controllers.registro import manejar_registro
        rm = make_redis_manager(EstadoRegistro.CONFIRMANDO_DIRECCION)
        with patch("controllers.registro._enviar_pedir_confirmacion") as mock_pedir:
            with patch("controllers.registro_notifier.enviar_mensaje_whatsapp"):
                result = manejar_registro(NUMERO, "quizás", rm)
        assert result[1] == 200
        mock_pedir.assert_called_once_with(NUMERO)
        rm.set.assert_not_called()


# ---------------------------------------------------------------------------
# _confirmar_direccion — lógica interna completa
# ---------------------------------------------------------------------------

ESTADO_COMPLETO = {
    "estado": EstadoRegistro.CONFIRMANDO_DIRECCION,
    "nombre": "Ana García",
    "direccion": "Calle Mayor 1",
}


class TestConfirmarDireccionInterno:
    """Cubre directamente _confirmar_direccion — lógica nueva añadida."""

    def test_mensaje_no_retorna_false(self):
        ru, rm = make_registro_usuario(ESTADO_COMPLETO)
        result = ru._confirmar_direccion("no", ESTADO_COMPLETO)
        assert result is False

    # -- Guardia de integridad: Redis corrupto --

    def test_redis_corrupto_sin_nombre_limpia_y_notifica(self):
        estado = {"estado": EstadoRegistro.CONFIRMANDO_DIRECCION, "direccion": "Calle Mayor 1"}
        ru, rm = make_registro_usuario(estado)
        with patch("controllers.registro.enviar_mensaje_whatsapp") as mock_ws:
            result = ru._confirmar_direccion("si", estado)
        assert result[1] == 200
        rm.delete.assert_called_once_with(NUMERO)
        mock_ws.assert_called_once()

    def test_redis_corrupto_sin_direccion_limpia_y_notifica(self):
        estado = {"estado": EstadoRegistro.CONFIRMANDO_DIRECCION, "nombre": "Ana"}
        ru, rm = make_registro_usuario(estado)
        with patch("controllers.registro.enviar_mensaje_whatsapp") as mock_ws:
            result = ru._confirmar_direccion("si", estado)
        assert result[1] == 200
        rm.delete.assert_called_once_with(NUMERO)
        mock_ws.assert_called_once()

    def test_redis_corrupto_no_escribe_en_db(self):
        estado = {"estado": EstadoRegistro.CONFIRMANDO_DIRECCION}
        ru, rm = make_registro_usuario(estado)
        with patch("controllers.registro.enviar_mensaje_whatsapp"):
            with patch("container.gestor_usuarios") as mock_gu:
                ru._confirmar_direccion("si", estado)
        mock_gu.guardar_usuario.assert_not_called()

    # -- Guardia de idempotencia: usuario ya en DB --

    def test_idempotencia_duplicado_real_con_pedido(self):
        """Usuario en DB con pedido activo → duplicado, envía bienvenida, limpia Redis."""
        ru, rm = make_registro_usuario(ESTADO_COMPLETO)
        usuario_existente = {"id": 1, "nombre": "Ana García"}
        with patch("container.gestor_usuarios") as mock_gu, \
             patch("container.gestor_pedidos") as mock_gp, \
             patch("controllers.registro._enviar_mensaje_registro") as mock_msg, \
             patch("controllers.registro.mostrar_menu", return_value="menu"):
            mock_gu.obtener_usuario_completo.return_value = usuario_existente
            mock_gp.hay_pedido_pendiente.return_value = True
            result = ru._confirmar_direccion("si", ESTADO_COMPLETO)
        assert result[1] == 200
        mock_gp.iniciar_pedido.assert_not_called()
        mock_msg.assert_called_once()
        rm.delete.assert_called_once_with(NUMERO)

    def test_idempotencia_recuperacion_usuario_sin_pedido(self):
        """Usuario en DB sin pedido (fallo parcial anterior) → crea pedido y envía bienvenida."""
        ru, rm = make_registro_usuario(ESTADO_COMPLETO)
        usuario_existente = {"id": 1, "nombre": "Ana García"}
        with patch("container.gestor_usuarios") as mock_gu, \
             patch("container.gestor_pedidos") as mock_gp, \
             patch("controllers.registro._enviar_mensaje_registro"), \
             patch("controllers.registro.mostrar_menu", return_value="menu"):
            mock_gu.obtener_usuario_completo.return_value = usuario_existente
            mock_gp.hay_pedido_pendiente.return_value = False
            result = ru._confirmar_direccion("si", ESTADO_COMPLETO)
        assert result[1] == 200
        mock_gp.iniciar_pedido.assert_called_once_with(1, "Calle Mayor 1", NUMERO)
        rm.delete.assert_called_once_with(NUMERO)

    def test_idempotencia_recuperacion_iniciar_pedido_falla(self):
        """Recuperación: usuario sin pedido pero iniciar_pedido falla → error 200."""
        ru, rm = make_registro_usuario(ESTADO_COMPLETO)
        usuario_existente = {"id": 1, "nombre": "Ana García"}
        with patch("container.gestor_usuarios") as mock_gu, \
             patch("container.gestor_pedidos") as mock_gp, \
             patch("controllers.registro._enviar_mensaje_registro"):
            mock_gu.obtener_usuario_completo.return_value = usuario_existente
            mock_gp.hay_pedido_pendiente.return_value = False
            mock_gp.iniciar_pedido.side_effect = SQLAlchemyError("DB caída")
            result = ru._confirmar_direccion("si", ESTADO_COMPLETO)
        assert result[1] == 200
        rm.delete.assert_not_called()  # Redis no se limpia en error de recuperación

    # -- Caso normal: usuario nuevo --

    def test_happy_path_guarda_usuario_y_crea_pedido(self):
        ru, rm = make_registro_usuario(ESTADO_COMPLETO)
        with patch("container.gestor_usuarios") as mock_gu, \
             patch("container.gestor_pedidos") as mock_gp, \
             patch("controllers.registro._enviar_mensaje_registro"), \
             patch("controllers.registro.mostrar_menu", return_value="menu"):
            mock_gu.obtener_usuario_completo.return_value = None
            mock_gu.guardar_usuario.return_value = 42
            result = ru._confirmar_direccion("si", ESTADO_COMPLETO)
        assert result[1] == 200
        mock_gu.guardar_usuario.assert_called_once_with(NUMERO, "Ana García", "Calle Mayor 1")
        mock_gp.iniciar_pedido.assert_called_once_with(42, "Calle Mayor 1", NUMERO)

    def test_happy_path_limpia_redis_tras_registro(self):
        ru, rm = make_registro_usuario(ESTADO_COMPLETO)
        with patch("container.gestor_usuarios") as mock_gu, \
             patch("container.gestor_pedidos"), \
             patch("controllers.registro._enviar_mensaje_registro"), \
             patch("controllers.registro.mostrar_menu", return_value="menu"):
            mock_gu.obtener_usuario_completo.return_value = None
            mock_gu.guardar_usuario.return_value = 42
            ru._confirmar_direccion("si", ESTADO_COMPLETO)
        rm.delete.assert_called_once_with(NUMERO)

    def test_happy_path_envia_bienvenida_con_nombre(self):
        ru, rm = make_registro_usuario(ESTADO_COMPLETO)
        with patch("container.gestor_usuarios") as mock_gu, \
             patch("container.gestor_pedidos"), \
             patch("controllers.registro._enviar_mensaje_registro") as mock_msg, \
             patch("controllers.registro.mostrar_menu", return_value="menu"):
            mock_gu.obtener_usuario_completo.return_value = None
            mock_gu.guardar_usuario.return_value = 42
            ru._confirmar_direccion("si", ESTADO_COMPLETO)
        mock_msg.assert_called_once_with(NUMERO, "Ana García", "menu")

    def test_guardar_usuario_falla_redis_queda_intacto(self):
        """Si guardar_usuario lanza excepción, Redis queda en CONFIRMANDO_DIRECCION."""
        ru, rm = make_registro_usuario(ESTADO_COMPLETO)
        with patch("container.gestor_usuarios") as mock_gu, \
             patch("container.gestor_pedidos") as mock_gp:
            mock_gu.obtener_usuario_completo.return_value = None
            mock_gu.guardar_usuario.side_effect = SQLAlchemyError("timeout")
            result = ru._confirmar_direccion("si", ESTADO_COMPLETO)
        assert result[1] == 200
        mock_gp.iniciar_pedido.assert_not_called()
        rm.delete.assert_not_called()  # Redis intacto → usuario puede reintentar

    def test_iniciar_pedido_falla_registro_parcial_envia_bienvenida(self):
        """guardar_usuario OK pero iniciar_pedido falla → REGISTRO_PARCIAL,
        bienvenida enviada y Redis limpiado para no bloquear al usuario."""
        ru, rm = make_registro_usuario(ESTADO_COMPLETO)
        with patch("container.gestor_usuarios") as mock_gu, \
             patch("container.gestor_pedidos") as mock_gp, \
             patch("controllers.registro._enviar_mensaje_registro") as mock_msg, \
             patch("controllers.registro.mostrar_menu", return_value="menu"):
            mock_gu.obtener_usuario_completo.return_value = None
            mock_gu.guardar_usuario.return_value = 42
            mock_gp.iniciar_pedido.side_effect = SQLAlchemyError("timeout")
            result = ru._confirmar_direccion("si", ESTADO_COMPLETO)
        assert result[1] == 200
        mock_msg.assert_called_once()      # bienvenida sí se envía
        rm.delete.assert_called_once_with(NUMERO)  # Redis se limpia
