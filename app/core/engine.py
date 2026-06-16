"""Top-level orchestrator: validate → cache → route → resilient fan-out → aggregate.

Endpoints call ``research_intent`` and get back a ready-to-serialize envelope.
"""

from __future__ import annotations

import concurrent.futures as cf
from typing import Any

from flask import g, has_request_context

from app.connectors.base import Connector, ConnectorResult
from app.version import RESPONSE_VERSION

from .aggregator import aggregate
from .attribution import any_required
from .cache import get_fresh, get_stale, store
from .context import build_context
from .envelope import build_envelope
from .http import NotFoundUpstream
from .intents import get_intent, is_known, validate_params
from .router import candidates_for, route
from .util import cache_key


class EngineError(Exception):
    """Base class for engine-level failures; carries an HTTP status hint."""

    status_code = 500

    def __init__(self, message: str, **extra: Any):
        super().__init__(message)
        self.message = message
        self.extra = extra


class IntentNotSupported(EngineError):
    status_code = 422


class InvalidParams(EngineError):
    status_code = 422


class NoSourcesAvailable(EngineError):
    status_code = 501


class UpstreamUnavailable(EngineError):
    status_code = 502


def research_intent(intent: str, params: dict[str, Any]) -> dict[str, Any]:
    if not is_known(intent):
        raise IntentNotSupported(f"unknown intent '{intent}'")
    errors = validate_params(intent, params)
    if errors:
        raise InvalidParams("; ".join(errors), errors=errors)

    key = cache_key(intent, params)

    fresh = get_fresh(key)
    if fresh is not None:
        value, age = fresh
        return _audit({**value, "cache": {"hit": True, "age_s": age}})

    spec = get_intent(intent)
    if spec is not None and spec.composite:
        return _audit(_run_composite(intent, params, key))

    ctx = build_context()
    connectors = route(intent, params, ctx)
    if not connectors:
        disabled = [n for n in candidates_for(intent) if n in ctx.disabled_connectors]
        if disabled:
            raise NoSourcesAvailable(
                f"intent '{intent}' is unavailable: source(s) disabled in this deployment",
                code="source_disabled",
                disabled_sources=sorted(disabled),
            )
        raise NoSourcesAvailable(f"no source can serve intent '{intent}'")

    results, failures = _fanout(connectors, intent, params, ctx)

    if not results:
        if failures:
            stale = get_stale(key)
            if stale is not None:
                value, age = stale
                return _audit(
                    {
                        **value,
                        "degraded": True,
                        "warnings": [
                            *value.get("warnings", []),
                            "served stale: all sources failed",
                        ],
                        "cache": {"hit": True, "age_s": age},
                    }
                )
            raise UpstreamUnavailable(
                f"all sources failed for intent '{intent}'",
                failures=[name for name, _ in failures],
            )
        return _audit(
            build_envelope(
                intent=intent,
                query=params,
                data={},
                sources=[],
                warnings=["no data found for query"],
            )
        )

    data, sources = aggregate(intent, results)
    warnings = [f"source '{name}' failed: {msg}" for name, msg in failures]
    envelope = build_envelope(
        intent=intent,
        query=params,
        data=data,
        sources=sources,
        degraded=bool(failures),
        warnings=warnings,
    )
    store(key, envelope)
    return _audit(envelope)


def _run_composite(intent: str, params: dict[str, Any], key: str) -> dict[str, Any]:
    from .compose import get_composer

    composer = get_composer(intent)
    if composer is None:
        raise NoSourcesAvailable(f"no composer registered for '{intent}'")
    data, sources, warnings = composer(params, research_intent)
    envelope = {
        "intent": intent,
        "query": params,
        "data": data,
        "sources": sources,
        "degraded": bool(warnings),
        "warnings": warnings,
        "attribution_required": any_required(sources),
        "cache": {"hit": False, "age_s": None},
        "meta": {"version": RESPONSE_VERSION},
    }
    store(key, envelope)
    return envelope


def _audit(envelope: dict[str, Any]) -> dict[str, Any]:
    """Stash request-scoped audit info for the usage logger (if in a request)."""
    if has_request_context():
        g.audit = {
            "intent": envelope.get("intent"),
            "sources": [s["name"] for s in envelope.get("sources", [])],
            "cache_hit": envelope.get("cache", {}).get("hit", False),
            "degraded": envelope.get("degraded", False),
        }
    return envelope


def _fanout(
    connectors: list[Connector],
    intent: str,
    params: dict[str, Any],
    ctx,
) -> tuple[list[ConnectorResult], list[tuple[str, str]]]:
    order = {c.name: i for i, c in enumerate(connectors)}
    results: list[ConnectorResult] = []
    failures: list[tuple[str, str]] = []

    with cf.ThreadPoolExecutor(max_workers=max(1, len(connectors))) as pool:
        future_map = {
            pool.submit(_safe_fetch, c, intent, params, ctx): c for c in connectors
        }
        done, not_done = cf.wait(future_map, timeout=ctx.deadline)
        for future in done:
            connector = future_map[future]
            kind, payload = future.result()
            if kind == "ok":
                results.append(payload)
            elif kind == "err":
                failures.append((connector.name, payload))
        for future in not_done:
            future.cancel()
            failures.append((future_map[future].name, "deadline exceeded"))

    results.sort(key=lambda r: order.get(r.connector, len(order)))
    return results, failures


def _safe_fetch(connector: Connector, intent, params, ctx) -> tuple[str, Any]:
    """Never raises — classifies the outcome for the fan-out collector."""
    try:
        result = connector.fetch(intent, params, ctx)
    except NotFoundUpstream:
        return ("nodata", None)
    except Exception as exc:  # noqa: BLE001 — isolate any source failure
        return ("err", f"{type(exc).__name__}: {exc}")
    if not result.data:
        return ("nodata", None)
    return ("ok", result)
