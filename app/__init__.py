"""Application factory for the Research Engine API."""

from __future__ import annotations

from dotenv import load_dotenv
from flask import Flask

from .config import Config
from .extensions import cache, db, limiter, migrate, rest_api


def create_app(config_object: type = Config) -> Flask:
    load_dotenv()
    app = Flask(__name__)
    app.config.from_object(config_object)

    # Core extensions.
    db.init_app(app)
    migrate.init_app(app, db)
    cache.init_app(app)
    limiter.init_app(app)
    rest_api.init_app(app)

    # Shared resilient outbound HTTP client (thread-safe; reused across requests).
    from .core.http import HttpClient

    app.extensions["http_client"] = HttpClient(
        user_agent=app.config["USER_AGENT"],
        timeout=app.config["HTTP_TIMEOUT"],
        max_retries=app.config["HTTP_MAX_RETRIES"],
        breaker_fail_max=app.config["BREAKER_FAIL_MAX"],
        breaker_reset_timeout=app.config["BREAKER_RESET_TIMEOUT"],
    )

    # Import connectors so the @register decorator populates the registry.
    from . import connectors  # noqa: F401

    # Structured request logging (registers a request-id + timer before_request).
    from .observability import configure_logging

    configure_logging(app)

    # Auth models + CLI (registered if present).
    from .auth import register_auth

    register_auth(app)

    # API blueprints.
    from .api import register_blueprints

    register_blueprints(rest_api)

    return app
