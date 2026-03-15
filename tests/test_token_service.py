"""
Tests for services/token_service.py:
  - generar_token_temporal
  - generar_enlace
"""
import json
import pytest
from unittest.mock import patch, MagicMock


VALID_USER = {
    "id": 1,
    "nombre": "Ana García",
    "numero": "whatsapp:+34600000000",
    "direccion": "Calle Mayor 1",
}

INVALID_USER = {
    "id": "no-es-int",   # id debe ser entero
    "nombre": "",
    "numero": "",
    "direccion": "",
}


class TestGenerarTokenTemporal:

    def test_datos_validos_retorna_string(self):
        from services.token_service import generar_token_temporal

        with patch("services.token_service.redismanager") as mock_redis:
            mock_redis.set.return_value = True
            token = generar_token_temporal(VALID_USER)

        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_se_almacena_en_redis(self):
        from services.token_service import generar_token_temporal

        with patch("services.token_service.redismanager") as mock_redis:
            mock_redis.set.return_value = True
            token = generar_token_temporal(VALID_USER)

        mock_redis.set.assert_called_once()
        key, value = mock_redis.set.call_args[0][:2]
        assert key == token
        payload = json.loads(value)
        assert payload["id"] == VALID_USER["id"]
        assert payload["nombre"] == VALID_USER["nombre"]

    def test_datos_invalidos_lanza_value_error(self):
        from services.token_service import generar_token_temporal

        with pytest.raises(ValueError, match="inválidos"):
            generar_token_temporal(INVALID_USER)

    def test_datos_invalidos_no_escribe_redis(self):
        from services.token_service import generar_token_temporal

        with patch("services.token_service.redismanager") as mock_redis:
            with pytest.raises(ValueError):
                generar_token_temporal(INVALID_USER)

        mock_redis.set.assert_not_called()


class TestGenerarEnlace:

    def test_retorna_url_con_formato_correcto(self):
        from services.token_service import generar_enlace

        with patch("services.token_service.redismanager") as mock_redis:
            mock_redis.set.return_value = True
            with patch("services.token_service.config") as mock_cfg:
                mock_cfg.PUBLIC_URL = "https://example.com"
                enlace = generar_enlace("tienda", VALID_USER)

        assert enlace.startswith("https://example.com/menu/")
        token_part = enlace.split("/menu/")[1]
        assert len(token_part) > 0

    def test_error_en_token_no_genera_enlace_roto(self):
        """Si los datos son inválidos, generar_enlace debe propagar el ValueError,
        no devolver una URL con el mensaje de error como token."""
        from services.token_service import generar_enlace

        with pytest.raises(ValueError):
            generar_enlace("tienda", INVALID_USER)
