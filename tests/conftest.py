import fakeredis
from unittest.mock import patch

# Intercept redis.Redis before RedisManager singleton is created at module level.
# This allows the test suite to run without a live Redis instance.
_redis_patcher = patch('redis.Redis', fakeredis.FakeRedis)
_redis_patcher.start()

import pytest
from main import create_app


@pytest.fixture(scope="session")
def app():
    app = create_app({"TESTING": True})
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _flush_fakeredis():
    """Limpia el fakeredis del singleton redismanager entre tests.

    Sin esto, claves con TTL (locks, anti-spam, etc.) persisten entre tests
    y provocan falsos negativos cuando dos tests reutilizan el mismo id.
    """
    from managers.gestor_redis import redismanager
    try:
        redismanager.client.flushall()
    except Exception:
        pass
    yield
