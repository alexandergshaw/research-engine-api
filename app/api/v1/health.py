"""Health, readiness, and version endpoints (no auth required)."""

from __future__ import annotations

from flask import current_app
from flask_smorest import Blueprint

from app.connectors.base import all_connectors
from app.schemas import HealthSchema, ReadySchema, VersionSchema
from app.version import RESPONSE_VERSION

blp = Blueprint("health", __name__, url_prefix="/v1", description="Service health")


@blp.route("/health")
@blp.response(200, HealthSchema)
def health():
    """Liveness check."""
    return {"status": "ok", "version": current_app.config["API_VERSION"]}


@blp.route("/version")
@blp.response(200, VersionSchema)
def version():
    """Response-contract version (folded into ETags; also on every envelope's meta)."""
    return {"version": RESPONSE_VERSION, "api": current_app.config["API_VERSION"]}


@blp.route("/ready")
@blp.response(200, ReadySchema)
def ready():
    """Readiness + live per-source circuit-breaker health and per-deploy disablement."""
    http = current_app.extensions["http_client"]
    disabled = set(current_app.config.get("DISABLED_CONNECTORS", frozenset()))
    connectors = [
        {
            "name": c.name,
            "reputation": c.reputation,
            "intents": sorted(c.intents),
            "breaker_open": http.breaker_open(c.name),
            "disabled": c.name in disabled,
        }
        for c in all_connectors()
    ]
    degraded = any(c["breaker_open"] or c["disabled"] for c in connectors)
    return {
        "status": "degraded" if degraded else "ok",
        "connectors": connectors,
        "disabled_sources": sorted(d["name"] for d in connectors if d["disabled"]),
    }
