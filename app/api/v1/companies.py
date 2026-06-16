"""Granular company endpoints."""

from __future__ import annotations

from flask.views import MethodView
from flask_smorest import Blueprint

from app.api.serve import serve
from app.auth.middleware import require_api_key, tenant_limit
from app.extensions import limiter
from app.schemas import EnvelopeSchema

blp = Blueprint("companies", __name__, url_prefix="/v1/companies", description="Company research")


@blp.route("/<string:name>/profile")
class CompanyProfile(MethodView):
    decorators = [limiter.limit(tenant_limit), require_api_key]

    @blp.response(200, EnvelopeSchema)
    def get(self, name):
        """Company profile (SEC EDGAR + Wikidata facts): industry, HQ, founding, financials."""
        return serve("company.profile", {"name": name})
