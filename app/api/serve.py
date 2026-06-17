"""Shared endpoint helpers: run an intent, attach cache headers, map engine errors.

`serve` is for single-result endpoints (sets ETag + Cache-Control on success, raises
the right error otherwise). `serve_safe` is for batch — it never raises; failures
become a degraded envelope so one bad sub-request can't sink the batch.
"""

from __future__ import annotations

from typing import Any

from flask import abort, after_this_request, current_app, jsonify
from flask_smorest import abort as smorest_abort

from app.core.engine import EngineError, research_intent
from app.core.envelope import build_envelope
from app.core.intents import bucket_for
from app.core.util import response_etag
from app.version import RESPONSE_VERSION


def _abort_engine(exc: EngineError) -> None:
    # Structured, machine-detectable signal for per-deploy source disablement.
    if exc.extra.get("code") == "source_disabled":
        resp = jsonify(
            {
                "detail": exc.message,
                "code": "source_disabled",
                "disabled_sources": exc.extra.get("disabled_sources", []),
            }
        )
        resp.status_code = exc.status_code  # 501
        abort(resp)
    smorest_abort(exc.status_code, message=exc.message, errors=exc.extra.get("errors"))


def serve(intent: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        envelope = research_intent(intent, params)
    except EngineError as exc:
        _abort_engine(exc)

    etag = response_etag(intent, params, RESPONSE_VERSION, bucket_for(intent))
    max_age = current_app.config["CACHE_DEFAULT_TIMEOUT"]

    @after_this_request
    def _headers(response):  # set only on success
        response.headers["ETag"] = etag
        response.headers["Cache-Control"] = f"public, max-age={max_age}"
        return response

    return envelope


def serve_safe(intent: str, params: dict[str, Any]) -> dict[str, Any]:
    """Run an intent for batch: never raises — failures become a degraded envelope."""
    try:
        return research_intent(intent, params)
    except EngineError as exc:
        code = exc.extra.get("code", "error")
        return build_envelope(
            intent=intent,
            query=params,
            data={},
            sources=[],
            degraded=True,
            warnings=[f"{code}: {exc.message}"],
        )
