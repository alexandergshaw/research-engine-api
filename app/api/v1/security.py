"""Granular cybersecurity endpoints."""

from __future__ import annotations

from flask.views import MethodView
from flask_smorest import Blueprint, abort

from app.auth.middleware import require_api_key, tenant_limit
from app.core.engine import EngineError, research_intent
from app.extensions import limiter
from app.schemas import EnvelopeSchema, TechniqueQueryArgs, VulnQueryArgs

blp = Blueprint("security", __name__, url_prefix="/v1/security", description="Security research")


@blp.route("/vulnerabilities")
class Vulnerabilities(MethodView):
    decorators = [limiter.limit(tenant_limit), require_api_key]

    @blp.arguments(VulnQueryArgs, location="query")
    @blp.response(200, EnvelopeSchema)
    def get(self, args):
        """CVEs affecting a product/keyword (NVD)."""
        try:
            return research_intent(
                "security.vulnerabilities",
                {"product": args["product"], "limit": args["limit"]},
            )
        except EngineError as exc:
            abort(exc.status_code, message=exc.message, errors=exc.extra.get("errors"))


@blp.route("/techniques")
class Techniques(MethodView):
    decorators = [limiter.limit(tenant_limit), require_api_key]

    @blp.arguments(TechniqueQueryArgs, location="query")
    @blp.response(200, EnvelopeSchema)
    def get(self, args):
        """MITRE ATT&CK techniques/tactics matching a query."""
        try:
            return research_intent(
                "security.techniques", {"query": args["query"], "limit": args["limit"]}
            )
        except EngineError as exc:
            abort(exc.status_code, message=exc.message, errors=exc.extra.get("errors"))
