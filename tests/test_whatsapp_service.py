import os
import pytest
from unittest.mock import patch, MagicMock


class TestEnviarMensajeTwilio:

    def test_twilio_es_proveedor_por_defecto(self):
        """Sin WHATSAPP_PROVIDER, usa Twilio."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WHATSAPP_PROVIDER", None)
            with patch("services.whatsapp_service._get_client") as mock_client:
                mock_client.return_value.messages.create = MagicMock()
                from services.whatsapp_service import enviar_mensaje_whatsapp
                enviar_mensaje_whatsapp("hola", "whatsapp:+34600000000")
                mock_client.return_value.messages.create.assert_called_once()

    def test_twilio_pasa_numero_con_prefijo(self):
        """_enviar_twilio pasa el número tal cual (con prefijo whatsapp:+)."""
        with patch.dict(os.environ, {"WHATSAPP_PROVIDER": "twilio"}):
            with patch("services.whatsapp_service._get_client") as mock_client:
                mock_create = mock_client.return_value.messages.create
                from services.whatsapp_service import enviar_mensaje_whatsapp
                enviar_mensaje_whatsapp("hola", "whatsapp:+34600000000")
                call_kwargs = mock_create.call_args.kwargs
                assert call_kwargs["to"] == "whatsapp:+34600000000"
                assert call_kwargs["body"] == "hola"


class TestEnviarMensajeMeta:

    def test_meta_normaliza_numero(self):
        """_enviar_meta elimina el prefijo whatsapp:+ antes de enviar."""
        with patch.dict(os.environ, {"WHATSAPP_PROVIDER": "meta"}):
            with patch("services.whatsapp_service.requests.post") as mock_post:
                mock_post.return_value.raise_for_status = MagicMock()
                with patch("services.whatsapp_service.config") as mock_cfg:
                    mock_cfg.META_PHONE_NUMBER_ID = "123456"
                    mock_cfg.META_ACCESS_TOKEN = "token-test"
                    from services.whatsapp_service import enviar_mensaje_whatsapp
                    enviar_mensaje_whatsapp("hola", "whatsapp:+34600000000")
                call_kwargs = mock_post.call_args.kwargs
                assert call_kwargs["json"]["to"] == "34600000000"

    def test_meta_envia_mensaje_correcto(self):
        """_enviar_meta construye el payload correcto para la Cloud API."""
        with patch.dict(os.environ, {"WHATSAPP_PROVIDER": "meta"}):
            with patch("services.whatsapp_service.requests.post") as mock_post:
                mock_post.return_value.raise_for_status = MagicMock()
                with patch("services.whatsapp_service.config") as mock_cfg:
                    mock_cfg.META_PHONE_NUMBER_ID = "123456"
                    mock_cfg.META_ACCESS_TOKEN = "mi-token"
                    from services.whatsapp_service import enviar_mensaje_whatsapp
                    enviar_mensaje_whatsapp("Pedido listo", "whatsapp:+34611222333")
                call_kwargs = mock_post.call_args.kwargs
                assert call_kwargs["json"]["messaging_product"] == "whatsapp"
                assert call_kwargs["json"]["type"] == "text"
                assert call_kwargs["json"]["text"]["body"] == "Pedido listo"
                assert "Bearer mi-token" in call_kwargs["headers"]["Authorization"]

    def test_meta_llama_raise_for_status(self):
        """_enviar_meta llama raise_for_status para detectar errores HTTP."""
        with patch.dict(os.environ, {"WHATSAPP_PROVIDER": "meta"}):
            with patch("services.whatsapp_service.requests.post") as mock_post:
                mock_post.return_value.raise_for_status = MagicMock()
                with patch("services.whatsapp_service.config") as mock_cfg:
                    mock_cfg.META_PHONE_NUMBER_ID = "123456"
                    mock_cfg.META_ACCESS_TOKEN = "token"
                    from services.whatsapp_service import enviar_mensaje_whatsapp
                    enviar_mensaje_whatsapp("hola", "whatsapp:+34600000000")
                mock_post.return_value.raise_for_status.assert_called_once()
