"""Structured request logging via structlog.

Emits one structured line per request (JSON in prod, human-readable in debug),
carrying a request id, latency, tenant, and the resolved intent/sources. This is
separate from the DB usage log (auth.middleware.log_usage) which is for billing.
"""

from __future__ import annotations

import logging
import time
import uuid

import structlog
from flask import Flask, Response, g, request

# Health/docs noise we don't log per-request.
_SKIP = {"/v1/health", "/v1/ready", "/openapi.json", "/docs"}


def configure_logging(app: Flask) -> None:
    level = logging.DEBUG if app.debug else logging.INFO
    logging.basicConfig(format="%(message)s", level=level)

    renderer = (
        structlog.dev.ConsoleRenderer()
        if app.debug
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    log = structlog.get_logger("request")

    @app.before_request
    def _begin() -> None:
        g.request_id = uuid.uuid4().hex[:12]
        g.request_start = time.perf_counter()

    @app.after_request
    def _emit(response: Response) -> Response:
        if request.path in _SKIP or request.path.startswith("/docs"):
            return response
        start = g.get("request_start")
        duration_ms = round((time.perf_counter() - start) * 1000, 1) if start else None
        audit = g.get("audit", {}) or {}
        log.info(
            "request",
            request_id=g.get("request_id"),
            method=request.method,
            path=request.path,
            status=response.status_code,
            duration_ms=duration_ms,
            intent=audit.get("intent"),
            sources=audit.get("sources"),
            cache_hit=audit.get("cache_hit"),
            degraded=audit.get("degraded"),
        )
        return response
