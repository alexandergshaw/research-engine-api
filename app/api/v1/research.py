"""Generic intent endpoint + intent catalog listing."""

from __future__ import annotations

from flask.views import MethodView
from flask_smorest import Blueprint, abort

from app.auth.middleware import require_api_key, tenant_limit
from app.core.engine import EngineError, research_intent
from app.core.intents import all_intents
from app.core.router import candidates_for
from app.extensions import limiter
from app.schemas import EnvelopeSchema, IntentSpecSchema, ResearchRequestSchema

blp = Blueprint("research", __name__, url_prefix="/v1", description="Generic intent research")


@blp.route("/research")
class Research(MethodView):
    decorators = [limiter.limit(tenant_limit), require_api_key]

    @blp.arguments(ResearchRequestSchema)
    @blp.response(200, EnvelopeSchema)
    def post(self, payload):
        """Run any intent. Body: {"intent": "...", "params": {...}}."""
        try:
            return research_intent(payload["intent"], payload["params"])
        except EngineError as exc:
            abort(exc.status_code, message=exc.message, errors=exc.extra.get("errors"))


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
                "composite": spec.composite,
                "sources": candidates_for(spec.name),
            }
            for spec in all_intents()
        ]
