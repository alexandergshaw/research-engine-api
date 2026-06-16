"""Composite intents — orchestrate several single-source intents into one payload.

These reuse the full engine (routing, resilience, caching) for each sub-intent,
then deterministically assemble the results. No LLM: structuring only.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from app.processing.keywords import extract_keywords

Composer = Callable[[dict[str, Any], Callable], tuple[dict[str, Any], list[dict], list[str]]]

_COMPOSERS: dict[str, Composer] = {}


def register_composer(name: str, fn: Composer) -> None:
    _COMPOSERS[name] = fn


def get_composer(name: str) -> Composer | None:
    return _COMPOSERS.get(name)


def _topic(params: dict[str, Any]) -> str:
    return str(params.get("topic") or params.get("term") or params.get("query") or "").strip()


def _sentences(text: str | None, limit: int = 5) -> list[str]:
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p][:limit]


def _dedup_sources(sources: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for src in sources:
        key = (src.get("name"), src.get("url"))
        if key in seen:
            continue
        seen.add(key)
        out.append(src)
    return out


def slide_outline(
    params: dict[str, Any], run: Callable
) -> tuple[dict[str, Any], list[dict], list[str]]:
    """Build a slide-ready outline by composing overview + examples + papers."""
    from .engine import EngineError  # local import avoids a circular import at load time

    topic = _topic(params)
    slides: list[dict[str, Any]] = []
    sources: list[dict] = []
    warnings: list[str] = []

    try:
        overview = run("concept.overview", {"term": topic})
        data = overview.get("data", {})
        slides.append(
            {
                "type": "title",
                "title": data.get("title") or topic,
                "subtitle": data.get("description"),
            }
        )
        bullets = _sentences(data.get("summary"))
        if bullets:
            slides.append({"type": "overview", "title": "Overview", "bullets": bullets})
        terms = extract_keywords(data.get("summary"), limit=8)
        if terms:
            slides.append({"type": "key_terms", "title": "Key terms", "items": terms})
        if data.get("facts"):
            slides.append({"type": "key_facts", "title": "Key facts", "facts": data["facts"]})
        sources += overview.get("sources", [])
    except EngineError as exc:
        warnings.append(f"overview unavailable: {exc.message}")

    try:
        examples = run("concept.examples", {"term": topic, "limit": 5})
        questions = examples.get("data", {}).get("questions", [])
        if questions:
            slides.append(
                {
                    "type": "examples",
                    "title": "Q&A and examples",
                    "items": [{"title": q["title"], "url": q["url"]} for q in questions],
                }
            )
        sources += examples.get("sources", [])
    except EngineError as exc:
        warnings.append(f"examples unavailable: {exc.message}")

    try:
        papers = run("academic.papers", {"query": topic, "limit": 3})
        items = papers.get("data", {}).get("papers", [])
        if items:
            slides.append(
                {
                    "type": "references",
                    "title": "Further reading",
                    "items": [{"title": p["title"], "url": p["url"]} for p in items],
                }
            )
        sources += papers.get("sources", [])
    except EngineError:
        pass  # papers are optional enrichment

    sources = _dedup_sources(sources)
    if sources:
        slides.append(
            {"type": "sources", "title": "Sources", "items": [s["name"] for s in sources]}
        )

    data = {"topic": topic, "slide_count": len(slides), "slides": slides}
    return data, sources, warnings


register_composer("compose.slide_outline", slide_outline)
