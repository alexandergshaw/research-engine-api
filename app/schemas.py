"""Marshmallow schemas for request validation and OpenAPI documentation."""

from __future__ import annotations

from marshmallow import Schema, fields
from marshmallow.validate import Length


class SourceSchema(Schema):
    name = fields.Str()
    url = fields.Str(allow_none=True)
    retrieved_at = fields.Str()
    license = fields.Str(allow_none=True)
    attribution = fields.Str(metadata={"description": "ready-to-render attribution line"})


class CacheInfoSchema(Schema):
    hit = fields.Bool()
    age_s = fields.Int(allow_none=True)


class MetaSchema(Schema):
    version = fields.Str(metadata={"description": "response-contract version"})


class EnvelopeSchema(Schema):
    """Standard response shape for every research endpoint."""

    intent = fields.Str()
    query = fields.Dict()
    data = fields.Raw()  # intent-specific structured payload
    sources = fields.List(fields.Nested(SourceSchema))
    degraded = fields.Bool()
    warnings = fields.List(fields.Str())
    attribution_required = fields.Bool(
        metadata={"description": "true if any source license requires attribution"}
    )
    cache = fields.Nested(CacheInfoSchema)
    meta = fields.Nested(MetaSchema)


class ResearchRequestSchema(Schema):
    intent = fields.Str(required=True, metadata={"description": "e.g. 'company.profile'"})
    params = fields.Dict(
        required=True, metadata={"description": "identifier params, e.g. {'name': 'Apple Inc'}"}
    )


class BatchRequestSchema(Schema):
    requests = fields.List(
        fields.Nested(ResearchRequestSchema),
        required=True,
        validate=Length(min=1, max=20, error="requests must contain between 1 and 20 items"),
        metadata={"description": "1–20 research requests; results are returned in the same order"},
    )


class BatchResponseSchema(Schema):
    results = fields.List(fields.Nested(EnvelopeSchema))


class VulnQueryArgs(Schema):
    product = fields.Str(
        required=True, metadata={"description": "product or keyword, e.g. openssl"}
    )
    limit = fields.Int(load_default=5)


class PapersQueryArgs(Schema):
    query = fields.Str(required=True, metadata={"description": "search query"})
    limit = fields.Int(load_default=5)


class TechniqueQueryArgs(Schema):
    query = fields.Str(
        required=True, metadata={"description": "technique id/name or tactic, e.g. phishing"}
    )
    limit = fields.Int(load_default=8)


class SlideOutlineArgs(Schema):
    topic = fields.Str(required=True, metadata={"description": "topic to build slides for"})


class IntentSpecSchema(Schema):
    name = fields.Str()
    description = fields.Str()
    accepts = fields.List(fields.Str())
    optional = fields.List(fields.Str())
    returns = fields.List(fields.Str(), metadata={"description": "top-level data keys"})
    composite = fields.Bool()
    volatile = fields.Bool(metadata={"description": "time-varying; not reproducible across time"})
    sources = fields.List(fields.Str())


class CompanyNewsArticleSchema(Schema):
    title = fields.Str()
    source = fields.Str(metadata={"description": "publisher / domain"})
    url = fields.Str()
    published = fields.Str(allow_none=True)
    tone = fields.Float(metadata={"description": "deterministic headline tone (ranking key)"})
    language = fields.Str()


class CompanyNewsDataSchema(Schema):
    """`data` shape for the company.news intent (headline + link + metadata only)."""

    company = fields.Str()
    as_of = fields.Str(metadata={"description": "UTC date the query ran"})
    articles = fields.List(fields.Nested(CompanyNewsArticleSchema))


class SourceSpecSchema(Schema):
    """A caller-supplied HTTP JSON source: where to fetch and how to read it."""

    url = fields.Str(required=True, metadata={"description": "source endpoint (https)"})
    method = fields.Str(load_default="GET", metadata={"description": "GET (default) or POST"})
    query = fields.Dict(metadata={"description": "querystring params"})
    headers = fields.Dict(metadata={"description": "request headers, e.g. auth (masked in echo)"})
    body = fields.Raw(metadata={"description": "JSON body (POST only)"})
    items_path = fields.Str(metadata={"description": "dotted path to the records array"})
    map = fields.Dict(metadata={"description": "target field -> dotted source path"})
    cursor_field = fields.Str(metadata={"description": "mapped field used as the high-water mark"})
    cursor_type = fields.Str(
        metadata={"description": "ordering of cursor_field: datetime | epoch | number | string"}
    )
    license = fields.Str(metadata={"description": "optional license/attribution for the source"})


class FeedPollArgs(Schema):
    """Request body for POST /v1/jobs/postings (the feed.poll intent)."""

    source = fields.Nested(SourceSpecSchema, required=True)
    since = fields.Raw(allow_none=True, metadata={"description": "raw high-water value"})
    cursor = fields.Str(metadata={"description": "opaque cursor from a prior poll's data.cursor"})
    limit = fields.Int(load_default=50, metadata={"description": "max items this poll (1-200)"})


class FeedItemSchema(Schema):
    """Representative projected item (the actual keys follow the caller's `map`)."""

    id = fields.Str(metadata={"description": "stable id for client-side dedup"})
    title = fields.Str()
    company = fields.Str()
    location = fields.Str()
    url = fields.Str()
    posted_at = fields.Str()
    tags = fields.Raw()


class FeedPollDataSchema(Schema):
    """`data` shape for the feed.poll intent (e.g. job postings)."""

    source = fields.Str(metadata={"description": "resolved source host"})
    as_of = fields.Str(metadata={"description": "UTC date the poll ran"})
    postings = fields.List(fields.Nested(FeedItemSchema))
    cursor = fields.Str(
        allow_none=True,
        metadata={"description": "opaque high-water cursor; pass back to poll for more"},
    )
    count = fields.Int()
    has_more = fields.Bool(metadata={"description": "upstream had more than `limit` new items"})


class HealthSchema(Schema):
    status = fields.Str()
    version = fields.Str()


class VersionSchema(Schema):
    version = fields.Str(metadata={"description": "response-contract version"})
    api = fields.Str(metadata={"description": "URL version prefix, e.g. v1"})


class SourceHealthSchema(Schema):
    name = fields.Str()
    reputation = fields.Float()
    intents = fields.List(fields.Str())
    breaker_open = fields.Bool()
    disabled = fields.Bool(metadata={"description": "disabled in this deployment"})


class ReadySchema(Schema):
    status = fields.Str()
    connectors = fields.List(fields.Nested(SourceHealthSchema))
    disabled_sources = fields.List(fields.Str())
