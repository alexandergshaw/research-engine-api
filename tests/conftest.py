import pytest

from app import create_app
from app.config import TestConfig


def pytest_addoption(parser):
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="run tests marked @pytest.mark.live that hit real upstream sources",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-live"):
        return
    skip_live = pytest.mark.skip(reason="needs --run-live (hits real upstream sources)")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture
def app():
    application = create_app(TestConfig)
    with application.app_context():
        yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth():
    """Auth header matching TestConfig.API_KEYS."""
    return {"X-API-Key": "test-key"}
