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
