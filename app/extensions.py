"""Shared Flask extension singletons, instantiated unbound and wired in the app factory."""

from __future__ import annotations

from flask_caching import Cache
from flask_limiter import Limiter
from flask_migrate import Migrate
from flask_smorest import Api
from flask_sqlalchemy import SQLAlchemy


def rate_limit_key() -> str:
    """Rate-limit bucket: the caller's API key when present, else remote address."""
    from flask import g, request

    tenant = getattr(g, "tenant", None)
    if tenant is not None:
        return f"tenant:{tenant.id}"
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"key:{api_key[:16]}"
    return request.remote_addr or "anonymous"


db = SQLAlchemy()
migrate = Migrate()
cache = Cache()
rest_api = Api()
limiter = Limiter(key_func=rate_limit_key)
