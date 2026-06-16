"""Granular role/occupation endpoints."""

from __future__ import annotations

from flask.views import MethodView
from flask_smorest import Blueprint

from app.api.serve import serve
from app.auth.middleware import require_api_key, tenant_limit
from app.extensions import limiter
from app.schemas import EnvelopeSchema

blp = Blueprint("roles", __name__, url_prefix="/v1/roles", description="Occupation research")


@blp.route("/<string:title>/responsibilities")
class Responsibilities(MethodView):
    decorators = [limiter.limit(tenant_limit), require_api_key]

    @blp.response(200, EnvelopeSchema)
    def get(self, title):
        """Typical duties + skills for a job title (ESCO occupational taxonomy)."""
        return serve("role.responsibilities", {"title": title})
