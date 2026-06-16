"""Granular concept endpoints — thin wrappers over concept.* intents."""

from __future__ import annotations

from flask.views import MethodView
from flask_smorest import Blueprint, abort

from app.auth.middleware import require_api_key, tenant_limit
from app.core.engine import EngineError, research_intent
from app.extensions import limiter
from app.schemas import EnvelopeSchema

blp = Blueprint("concepts", __name__, url_prefix="/v1/concepts", description="Concept research")


def _run(intent: str, term: str):
    try:
        return research_intent(intent, {"term": term})
    except EngineError as exc:
        abort(exc.status_code, message=exc.message, errors=exc.extra.get("errors"))


@blp.route("/<string:term>/overview")
class Overview(MethodView):
    decorators = [limiter.limit(tenant_limit), require_api_key]

    @blp.response(200, EnvelopeSchema)
    def get(self, term):
        """Summary + key facts about a topic."""
        return _run("concept.overview", term)


@blp.route("/<string:term>/definition")
class Definition(MethodView):
    decorators = [limiter.limit(tenant_limit), require_api_key]

    @blp.response(200, EnvelopeSchema)
    def get(self, term):
        """Concise definition of a term."""
        return _run("concept.definition", term)


@blp.route("/<string:term>/examples")
class Examples(MethodView):
    decorators = [limiter.limit(tenant_limit), require_api_key]

    @blp.response(200, EnvelopeSchema)
    def get(self, term):
        """Relevant Q&A / code-example pointers for a topic."""
        return _run("concept.examples", term)
