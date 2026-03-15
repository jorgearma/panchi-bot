import pytest
from main import create_app


@pytest.fixture(scope="session")
def app():
    app = create_app({"TESTING": True})
    yield app


@pytest.fixture
def client(app):
    return app.test_client()
