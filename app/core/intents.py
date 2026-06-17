"""Intent catalog — the public contract callers program against.

An intent names a *kind of knowledge* (e.g. ``company.profile``), independent of
which source supplies it. Each spec declares the accepted identifier params and,
optionally, a normalizer (structured shaping) or composite sub-intents.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.connectors.base import ConnectorResult, known_intents
from app.core.util import utc_date

Normalizer = Callable[[list[ConnectorResult]], dict[str, Any]]


@dataclass
class IntentSpec:
    name: str
    description: str
    accepts: list[str] = field(default_factory=list)  # identifier params, one required
    optional: list[str] = field(default_factory=list)
    returns: list[str] = field(default_factory=list)  # top-level data keys (discovery)
    normalizer: Normalizer | None = None
    composite: bool = False
    subintents: list[str] = field(default_factory=list)
    volatile: bool = False  # time-varying — cache/ETag rotate per UTC day


_INTENTS: dict[str, IntentSpec] = {}


def _merge(results: list[ConnectorResult]) -> dict[str, Any]:
    """Shallow merge, best-ranked wins (results are best-first)."""
    data: dict[str, Any] = {}
    for result in reversed(results):
        for key, value in result.data.items():
            if value not in (None, "", [], {}):
                data[key] = value
    return data


def company_profile_normalizer(results: list[ConnectorResult]) -> dict[str, Any]:
    """Prefer authoritative sources (SEC); take only structured `facts` from Wikidata
    so its fuzzy entity match can't overwrite the company's name/description."""
    authoritative = [r for r in results if r.connector != "wikidata"]
    wikidata = [r for r in results if r.connector == "wikidata"]

    if not authoritative:
        return _merge(wikidata)  # Wikidata is all we have — use it wholesale

    data = _merge(authoritative)
    facts: dict[str, Any] = {}
    for result in wikidata:
        if result.data.get("facts"):
            facts.update(result.data["facts"])
    if facts:
        data.setdefault("facts", {}).update(facts)
    return data


def company_news_normalizer(results: list[ConnectorResult]) -> dict[str, Any]:
    """Preserve the full news shape — keep `articles` even when empty (no-news case)."""
    data: dict[str, Any] = {}
    for result in reversed(results):  # best-ranked wins on conflict
        data.update(result.data)
    data.setdefault("articles", [])
    return data


def feed_poll_normalizer(results: list[ConnectorResult]) -> dict[str, Any]:
    """Preserve the full feed shape — keep `postings`/`cursor` even when empty."""
    data: dict[str, Any] = {}
    for result in reversed(results):  # best-ranked wins on conflict
        data.update(result.data)
    data.setdefault("postings", [])
    return data


def register_intent(spec: IntentSpec) -> IntentSpec:
    _INTENTS[spec.name] = spec
    return spec


def get_intent(name: str) -> IntentSpec | None:
    return _INTENTS.get(name)


def all_intents() -> list[IntentSpec]:
    return sorted(_INTENTS.values(), key=lambda s: s.name)


def normalizer_for(name: str) -> Normalizer | None:
    spec = _INTENTS.get(name)
    return spec.normalizer if spec else None


def is_known(name: str) -> bool:
    return name in _INTENTS or name in known_intents()


def bucket_for(name: str) -> str | None:
    """Time bucket folded into cache key/ETag for volatile intents (else None)."""
    spec = _INTENTS.get(name)
    return utc_date() if (spec and spec.volatile) else None


def validate_params(name: str, params: dict[str, Any]) -> list[str]:
    spec = _INTENTS.get(name)
    if spec is None or not spec.accepts:
        return []
    if not any(params.get(key) for key in spec.accepts):
        return [f"intent '{name}' requires one of: {', '.join(spec.accepts)}"]
    return []


# --- First-set intents -----------------------------------------------------
register_intent(
    IntentSpec(
        "concept.overview",
        "Summary, description and key facts about a topic.",
        accepts=["term", "topic", "query"],
    )
)
register_intent(
    IntentSpec(
        "concept.definition",
        "Concise definition of a term.",
        accepts=["term", "query"],
    )
)
register_intent(
    IntentSpec(
        "entity.facts",
        "Structured facts about a named entity.",
        accepts=["name", "term"],
    )
)
register_intent(
    IntentSpec(
        "company.profile",
        "Company profile: founding, HQ, employees, financial facts.",
        accepts=["name", "ticker", "term"],
        normalizer=company_profile_normalizer,
    )
)
register_intent(
    IntentSpec(
        "role.responsibilities",
        "Typical duties and skills for a job title/occupation.",
        accepts=["title", "term", "query"],
    )
)
register_intent(
    IntentSpec(
        "concept.examples",
        "Relevant Q&A / code-example pointers for a topic.",
        accepts=["term", "topic", "query"],
        optional=["language", "tag", "limit"],
    )
)
register_intent(
    IntentSpec(
        "security.vulnerabilities",
        "CVE vulnerabilities (id, CVSS severity, references) for a product/keyword.",
        accepts=["product", "keyword", "term", "query"],
        optional=["limit"],
    )
)
register_intent(
    IntentSpec(
        "security.techniques",
        "MITRE ATT&CK adversary techniques/tactics matching a query.",
        accepts=["technique", "tactic", "term", "query", "keyword"],
        optional=["limit"],
    )
)
register_intent(
    IntentSpec(
        "academic.papers",
        "Academic papers (title, abstract, authors) matching a query.",
        accepts=["query", "term", "topic"],
        optional=["limit"],
    )
)
register_intent(
    IntentSpec(
        "company.news",
        "Recent news articles about an organization, with a deterministic tone filter "
        "(headline + link + metadata only; time-varying).",
        accepts=["name", "ticker", "query", "term"],
        optional=["limit", "since_days", "min_tone", "sort"],
        returns=["company", "as_of", "articles"],
        normalizer=company_news_normalizer,
        volatile=True,
    )
)
register_intent(
    IntentSpec(
        "feed.poll",
        "Incremental stream of items from a caller-supplied HTTP JSON source "
        "(e.g. job postings). Returns only items newer than the caller's cursor; the "
        "caller owns the poll cadence (one-shot or continuous). Time-varying.",
        accepts=["source"],
        optional=["since", "cursor", "limit"],
        returns=["source", "as_of", "postings", "cursor", "count", "has_more"],
        normalizer=feed_poll_normalizer,
        volatile=True,
    )
)
register_intent(
    IntentSpec(
        "compose.slide_outline",
        "Slide-ready outline for a topic (composes overview + examples + papers).",
        accepts=["topic", "term", "query"],
        composite=True,
        subintents=["concept.overview", "concept.examples", "academic.papers"],
    )
)
