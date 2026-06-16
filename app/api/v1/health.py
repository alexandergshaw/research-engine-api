"""Health + readiness endpoints (no auth required)."""

from __future__ import annotations

from flask import current_app
from flask_smorest import Blueprint

from app.connectors.base import all_connectors
from app.schemas import HealthSchema, ReadySchema

blp = Blueprint("health", __name__, url_prefix="/v1", description="Service health")


@blp.route("/health")
@blp.response(200, HealthSchema)
def health():
    """Liveness check."""
    return {"status": "ok", "version": current_app.config["API_VERSION"]}


@blp.route("/ready")
@blp.response(200, ReadySchema)
def ready():
    """Readiness + live per-source circuit-breaker health."""
    http = current_app.extensions["http_client"]
    connectors = [
        {
            "name": c.name,
            "reputation": c.reputation,
            "intents": sorted(c.intents),
            "breaker_open": http.breaker_open(c.name),
        }
        for c in all_connectors()
    ]
    degraded = any(c["breaker_open"] for c in connectors)
    return {"status": "degraded" if degraded else "ok", "connectors": connectors}
