"""Granular cybersecurity endpoints."""

from __future__ import annotations

from flask.views import MethodView
from flask_smorest import Blueprint

from app.api.serve import serve
from app.auth.middleware import require_api_key, tenant_limit
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
        return serve(
            "security.vulnerabilities", {"product": args["product"], "limit": args["limit"]}
        )


@blp.route("/techniques")
class Techniques(MethodView):
    decorators = [limiter.limit(tenant_limit), require_api_key]

    @blp.arguments(TechniqueQueryArgs, location="query")
    @blp.response(200, EnvelopeSchema)
    def get(self, args):
        """MITRE ATT&CK techniques/tactics matching a query."""
        return serve("security.techniques", {"query": args["query"], "limit": args["limit"]})
