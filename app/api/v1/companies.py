"""Granular company endpoints — the 'stats on a specific company' use case."""

from __future__ import annotations

from flask.views import MethodView
from flask_smorest import Blueprint, abort

from app.auth.middleware import require_api_key, tenant_limit
from app.core.engine import EngineError, research_intent
from app.extensions import limiter
from app.schemas import EnvelopeSchema

blp = Blueprint("companies", __name__, url_prefix="/v1/companies", description="Company research")


@blp.route("/<string:name>/profile")
class CompanyProfile(MethodView):
    decorators = [limiter.limit(tenant_limit), require_api_key]

    @blp.response(200, EnvelopeSchema)
    def get(self, name):
        """Company profile (SEC EDGAR + Wikidata): industry, HQ, founding, financial facts."""
        try:
            return research_intent("company.profile", {"name": name})
        except EngineError as exc:
            abort(exc.status_code, message=exc.message, errors=exc.extra.get("errors"))
