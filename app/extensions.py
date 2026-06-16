"""Shared Flask extension singletons, instantiated unbound and wired in the app factory."""

from __future__ import annotations

from flask_caching import Cache
from flask_limiter import Limiter
from flask_smorest import Api


def rate_limit_key() -> str:
    """Rate-limit bucket: the caller's API key when present, else remote address."""
    from flask import g, request

    api_key = g.get("api_key", None) or request.headers.get("X-API-Key")
    if api_key:
        return f"key:{api_key[:16]}"
    return request.remote_addr or "anonymous"


cache = Cache()
rest_api = Api()
limiter = Limiter(key_func=rate_limit_key)
