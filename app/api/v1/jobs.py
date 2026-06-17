"""Caller-configured incremental streams (e.g. job postings) — the feed.poll intent.

The caller supplies its own source in the body; the engine fetches it (SSRF-guarded),
projects each record via the caller's field map, and returns only items newer than the
supplied cursor. Poll continuously by passing each response's ``data.cursor`` back as
``cursor`` on the next call — the engine stays stateless, the cursor travels with you.
"""

from __future__ import annotations

from flask.views import MethodView
from flask_smorest import Blueprint

from app.api.serve import serve
from app.auth.middleware import require_api_key, tenant_limit
from app.extensions import limiter
from app.schemas import EnvelopeSchema, FeedPollArgs

blp = Blueprint(
    "jobs",
    __name__,
    url_prefix="/v1/jobs",
    description="Caller-configured incremental streams (e.g. job postings)",
)


@blp.route("/postings")
class JobPostings(MethodView):
    decorators = [limiter.limit(tenant_limit), require_api_key]

    @blp.arguments(FeedPollArgs)
    @blp.response(200, EnvelopeSchema)
    def post(self, payload):
        """Stream items from a caller-supplied source. Returns only items newer than the
        supplied `cursor`/`since`; pass the returned `data.cursor` back to poll for more."""
        return serve("feed.poll", payload)
