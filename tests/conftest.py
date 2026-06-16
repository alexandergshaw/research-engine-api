import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db


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
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth(app):
    """Seed a tenant + API key; return the auth header for authenticated requests."""
    from app.auth.models import ApiKey, Tenant

    tenant = Tenant(name="test-tenant")
    db.session.add(tenant)
    db.session.flush()
    key, raw = ApiKey.generate(tenant, label="test")
    db.session.add(key)
    db.session.commit()
    return {"X-API-Key": raw}
