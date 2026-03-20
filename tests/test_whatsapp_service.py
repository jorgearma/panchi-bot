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
