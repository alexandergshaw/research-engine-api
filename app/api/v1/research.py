"""Generic intent endpoint, batch endpoint, and intent catalog listing."""

from __future__ import annotations

from flask import after_this_request, request
from flask.views import MethodView
from flask_smorest import Blueprint

from app.api.serve import serve, serve_safe
from app.auth.middleware import require_api_key, tenant_limit
from app.core.intents import all_intents
from app.core.router import candidates_for
from app.extensions import limiter
from app.schemas import (
    BatchRequestSchema,
    BatchResponseSchema,
    EnvelopeSchema,
    IntentSpecSchema,
    ResearchRequestSchema,
)

blp = Blueprint("research", __name__, url_prefix="/v1", description="Generic intent research")

_BATCH_CAP = 20


def _batch_cost() -> int:
    """Rate-limit cost = number of sub-requests (each sub-request counts as one)."""
    body = request.get_json(silent=True) or {}
    reqs = body.get("requests")
    if isinstance(reqs, list) and reqs:
        return max(1, min(len(reqs), _BATCH_CAP))
    return 1


@blp.route("/research")
class Research(MethodView):
    decorators = [limiter.limit(tenant_limit), require_api_key]

    @blp.arguments(ResearchRequestSchema)
    @blp.response(200, EnvelopeSchema)
    def post(self, payload):
        """Run any intent. Body: {"intent": "...", "params": {...}}."""
        return serve(payload["intent"], payload["params"])


@blp.route("/research/batch")
class ResearchBatch(MethodView):
    decorators = [limiter.limit(tenant_limit, cost=_batch_cost), require_api_key]

    @blp.arguments(BatchRequestSchema)
    @blp.response(200, BatchResponseSchema)
    def post(self, payload):
        """Run up to 20 intents in one call. Results are returned in input order;
        a failing/degraded/empty sub-request never fails the batch (each result
        carries its own degraded/warnings/cache). Rate-limit cost = #sub-requests."""
        results = [serve_safe(rq["intent"], rq.get("params", {})) for rq in payload["requests"]]

        @after_this_request
        def _no_store(response):  # batch is a POST aggregation — not cacheable as a unit
            response.headers["Cache-Control"] = "no-store"
            return response

        return {"results": results}


@blp.route("/intents")
class Intents(MethodView):
    decorators = [limiter.limit(tenant_limit), require_api_key]

    @blp.response(200, IntentSpecSchema(many=True))
    def get(self):
        """List the supported intents and which sources can serve each."""
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "accepts": spec.accepts,
                "optional": spec.optional,
                "returns": spec.returns,
                "composite": spec.composite,
                "volatile": spec.volatile,
                "sources": candidates_for(spec.name),
            }
            for spec in all_intents()
        ]
