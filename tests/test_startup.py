import pytest
import os
from unittest.mock import patch


def test_create_app_falla_si_falta_secret_key():
    from main import create_app
    env_sin_key = {k: v for k, v in os.environ.items() if k != 'SECRET_KEY'}
    with patch.dict(os.environ, env_sin_key, clear=True):
        with pytest.raises((EnvironmentError, RuntimeError, SystemExit)):
            create_app()


def test_app_mode_invalido_lanza_error():
    """APP_MODE con valor no reconocido debe levantar EnvironmentError."""
    import importlib
    with patch.dict(os.environ, {'APP_MODE': 'invalid_mode'}):
        import config
        importlib.reload(config)
        from main import create_app
        with pytest.raises(EnvironmentError, match="APP_MODE"):
            create_app()
    # Restaurar config al valor por defecto
    with patch.dict(os.environ, {'APP_MODE': 'warehouse'}):
        importlib.reload(config)


def test_app_mode_warehouse_es_valido():
    """Con APP_MODE=warehouse el valor se lee correctamente."""
    import config
    import importlib
    with patch.dict(os.environ, {'APP_MODE': 'warehouse'}):
        importlib.reload(config)
        assert config.APP_MODE == 'warehouse'
    importlib.reload(config)  # restaurar


def test_app_mode_restaurant_es_valido():
    """Con APP_MODE=restaurant el valor se lee correctamente."""
    import config
    import importlib
    with patch.dict(os.environ, {'APP_MODE': 'restaurant'}):
        importlib.reload(config)
        assert config.APP_MODE == 'restaurant'
    importlib.reload(config)  # restaurar al default (warehouse)
