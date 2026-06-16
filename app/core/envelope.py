"""Standard response envelope shared by every endpoint."""

from __future__ import annotations

from typing import Any

from app.connectors.base import Source
from app.version import RESPONSE_VERSION

from .attribution import attribution_line, requires_attribution


def source_to_dict(source: Source) -> dict[str, Any]:
    """Source as a dict, enriched with a ready-to-render attribution string."""
    data = source.as_dict()
    data["attribution"] = attribution_line(source.name, source.license, source.url)
    return data


def build_envelope(
    *,
    intent: str,
    query: dict[str, Any],
    data: dict[str, Any],
    sources: list[Source],
    degraded: bool = False,
    warnings: list[str] | None = None,
    cache_hit: bool = False,
    cache_age_s: int | None = None,
) -> dict[str, Any]:
    source_dicts = [source_to_dict(s) for s in sources]
    attribution_required = any(requires_attribution(s.license) for s in sources)
    return {
        "intent": intent,
        "query": query,
        "data": data,
        "sources": source_dicts,
        "degraded": degraded,
        "warnings": warnings or [],
        "attribution_required": attribution_required,
        "cache": {"hit": cache_hit, "age_s": cache_age_s},
        "meta": {"version": RESPONSE_VERSION},
    }
