"""Merge connector results into a single payload with provenance.

Default strategy: shallow-merge data dicts with higher-ranked connectors taking
precedence on key conflicts, union + dedup the sources. Intents can register a
custom normalizer in ``intents.py`` for structured shaping.
"""

from __future__ import annotations

from typing import Any

from app.connectors.base import ConnectorResult, Source

from . import intents as intent_registry


def aggregate(
    intent: str, ranked_results: list[ConnectorResult]
) -> tuple[dict[str, Any], list[Source]]:
    """``ranked_results`` is ordered best-first."""
    normalizer = intent_registry.normalizer_for(intent)
    if normalizer is not None:
        data = normalizer(ranked_results)
    else:
        data = _shallow_merge(ranked_results)
    sources = _dedup_sources(ranked_results)
    return data, sources


def _shallow_merge(ranked_results: list[ConnectorResult]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    # Iterate worst-first so the best connector's values win on conflict.
    for result in reversed(ranked_results):
        for key, value in result.data.items():
            if value in (None, "", [], {}):
                continue
            merged[key] = value
    return merged


def _dedup_sources(ranked_results: list[ConnectorResult]) -> list[Source]:
    seen: set[tuple[str, str | None]] = set()
    sources: list[Source] = []
    for result in ranked_results:
        for source in result.sources:
            key = (source.name, source.url)
            if key in seen:
                continue
            seen.add(key)
            sources.append(source)
    return sources
