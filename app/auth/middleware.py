"""Stateless API-key auth + per-request rate-limit value.

Keys are configured via the `API_KEYS` env (comma-separated) and compared in
constant time. When `API_KEYS` is empty the API runs in open mode (no key
required) — convenient for local/preview, not for a public deployment.
"""

from __future__ import annotations

import functools
import hmac
from collections.abc import Callable
from typing import Any

from flask import current_app, g, request
from flask_smorest import abort


def _key_accepted(presented: str, accepted: frozenset[str]) -> bool:
    # Constant-time compare against each configured key.
    return any(hmac.compare_digest(presented, key) for key in accepted)


def require_api_key(fn: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        accepted: frozenset[str] = current_app.config.get("API_KEYS") or frozenset()
        if not accepted:
            return fn(*args, **kwargs)  # open mode

        presented = request.headers.get("X-API-Key", "")
        if not presented or not _key_accepted(presented, accepted):
            abort(401, message="missing or invalid X-API-Key")
        g.api_key = presented
        return fn(*args, **kwargs)

    return wrapper


def tenant_limit() -> str:
    """The rate limit applied per key (single global default; no per-tenant plans)."""
    return current_app.config["RATELIMIT_DEFAULT"]
