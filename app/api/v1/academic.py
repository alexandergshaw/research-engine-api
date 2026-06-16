"""Granular academic/STEM endpoints."""

from __future__ import annotations

from flask.views import MethodView
from flask_smorest import Blueprint

from app.api.serve import serve
from app.auth.middleware import require_api_key, tenant_limit
from app.extensions import limiter
from app.schemas import EnvelopeSchema, PapersQueryArgs

blp = Blueprint("academic", __name__, url_prefix="/v1/academic", description="Academic research")


@blp.route("/papers")
class Papers(MethodView):
    decorators = [limiter.limit(tenant_limit), require_api_key]

    @blp.arguments(PapersQueryArgs, location="query")
    @blp.response(200, EnvelopeSchema)
    def get(self, args):
        """Papers matching a query (arXiv)."""
        return serve("academic.papers", {"query": args["query"], "limit": args["limit"]})
