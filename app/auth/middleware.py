"""API-key auth, per-tenant rate-limit resolution, and usage logging."""

from __future__ import annotations

import datetime as dt
import functools
import time
from collections.abc import Callable
from typing import Any

from flask import Response, current_app, g, request
from flask_smorest import abort

from app.extensions import db

from .models import ApiKey, UsageLog

# Paths under /v1 that are health-noise and should not be logged/limited.
_UNLOGGED = {"/v1/health", "/v1/ready"}


def require_api_key(fn: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        raw = request.headers.get("X-API-Key")
        if not raw:
            abort(401, message="missing X-API-Key header")
        key = (
            db.session.query(ApiKey)
            .filter_by(key_hash=ApiKey.hash_key(raw), active=True)
            .first()
        )
        if key is None or not key.tenant.active:
            abort(401, message="invalid or inactive API key")
        g.tenant = key.tenant
        g.api_key = key
        return fn(*args, **kwargs)

    return wrapper


def tenant_limit() -> str:
    """Dynamic rate limit: the tenant's plan limit, else the configured default."""
    tenant = g.get("tenant", None)
    if tenant is not None:
        return tenant.rate_limit
    return current_app.config["RATELIMIT_DEFAULT"]


def log_usage(response: Response) -> Response:
    if not request.path.startswith("/v1") or request.path in _UNLOGGED:
        return response

    start = g.get("request_start")
    latency_ms = int((time.perf_counter() - start) * 1000) if start else None
    audit = g.get("audit", {}) or {}
    key = g.get("api_key", None)
    tenant = g.get("tenant", None)

    try:
        db.session.add(
            UsageLog(
                tenant_id=tenant.id if tenant else None,
                api_key_id=key.id if key else None,
                method=request.method,
                path=request.path,
                intent=audit.get("intent"),
                status=response.status_code,
                latency_ms=latency_ms,
                sources=(",".join(audit.get("sources", [])) or None),
                cache_hit=bool(audit.get("cache_hit", False)),
                degraded=bool(audit.get("degraded", False)),
            )
        )
        if key is not None:
            key.last_used_at = dt.datetime.now(dt.UTC)
        db.session.commit()
    except Exception:  # noqa: BLE001 — logging must never break the response
        db.session.rollback()

    return response
