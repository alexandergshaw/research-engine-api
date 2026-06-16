"""Composite slide-outline endpoint."""

from __future__ import annotations

from flask.views import MethodView
from flask_smorest import Blueprint

from app.api.serve import serve
from app.auth.middleware import require_api_key, tenant_limit
from app.extensions import limiter
from app.schemas import EnvelopeSchema, SlideOutlineArgs

blp = Blueprint("compose", __name__, url_prefix="/v1/compose", description="Composite research")


@blp.route("/slide-outline")
class SlideOutline(MethodView):
    decorators = [limiter.limit(tenant_limit), require_api_key]

    @blp.arguments(SlideOutlineArgs, location="query")
    @blp.response(200, EnvelopeSchema)
    def get(self, args):
        """Slide-ready structured outline for a topic (overview + examples + papers)."""
        return serve("compose.slide_outline", {"topic": args["topic"]})
