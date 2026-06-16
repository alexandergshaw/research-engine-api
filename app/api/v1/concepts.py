"""Granular concept endpoints — thin wrappers over concept.* intents."""

from __future__ import annotations

from flask.views import MethodView
from flask_smorest import Blueprint

from app.api.serve import serve
from app.auth.middleware import require_api_key, tenant_limit
from app.extensions import limiter
from app.schemas import EnvelopeSchema

blp = Blueprint("concepts", __name__, url_prefix="/v1/concepts", description="Concept research")


@blp.route("/<string:term>/overview")
class Overview(MethodView):
    decorators = [limiter.limit(tenant_limit), require_api_key]

    @blp.response(200, EnvelopeSchema)
    def get(self, term):
        """Summary + key facts about a topic."""
        return serve("concept.overview", {"term": term})


@blp.route("/<string:term>/definition")
class Definition(MethodView):
    decorators = [limiter.limit(tenant_limit), require_api_key]

    @blp.response(200, EnvelopeSchema)
    def get(self, term):
        """Concise definition of a term."""
        return serve("concept.definition", {"term": term})


@blp.route("/<string:term>/examples")
class Examples(MethodView):
    decorators = [limiter.limit(tenant_limit), require_api_key]

    @blp.response(200, EnvelopeSchema)
    def get(self, term):
        """Relevant Q&A / code-example pointers for a topic."""
        return serve("concept.examples", {"term": term})
