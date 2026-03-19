import pytest
import os
from unittest.mock import patch


def test_create_app_falla_si_falta_secret_key():
    from main import create_app
    env_sin_key = {k: v for k, v in os.environ.items() if k != 'SECRET_KEY'}
    with patch.dict(os.environ, env_sin_key, clear=True):
        with pytest.raises((EnvironmentError, RuntimeError, SystemExit)):
            create_app()
