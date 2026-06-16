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
    composite = fields.Bool()
    sources = fields.List(fields.Str())


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
