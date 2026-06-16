"""Standard response envelope shared by every endpoint."""

from __future__ import annotations

from typing import Any

from app.connectors.base import Source


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
    return {
        "intent": intent,
        "query": query,
        "data": data,
        "sources": [s.as_dict() for s in sources],
        "degraded": degraded,
        "warnings": warnings or [],
        "cache": {"hit": cache_hit, "age_s": cache_age_s},
    }
