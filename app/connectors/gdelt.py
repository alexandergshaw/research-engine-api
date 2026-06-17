"""GDELT connector — recent news headlines about an organization (company.news).

Backed by the GDELT DOC 2.0 API (free, no key). Returns HEADLINE + LINK + METADATA
only — never article body text. Tone is computed deterministically from the headline
via a small bundled lexicon (no LLM); it is the ranking key and the value callers
filter on with ``min_tone``. News is time-varying, so the intent is marked volatile
(its cache/ETag rotate per UTC day) and every response carries ``data.as_of``.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from urllib.parse import urlparse

from app.core.util import now_iso, utc_date
from app.processing.tone import headline_tone

from .base import Connector, ConnectorResult, Source, register

_API = "https://api.gdeltproject.org/api/v2/doc/doc"


def _identifier(params: dict[str, Any]) -> str:
    value = (
        params.get("name")
        or params.get("ticker")
        or params.get("query")
        or params.get("term")
    )
    if not value:
        raise ValueError("missing 'name'/'ticker'/'query'/'term'")
    return str(value).strip()


def _clamp(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(int(value), hi))
    except (TypeError, ValueError):
        return default


def _published(seendate: str | None) -> str | None:
    if not seendate:
        return None
    try:
        return (
            dt.datetime.strptime(seendate, "%Y%m%dT%H%M%SZ")
            .replace(tzinfo=dt.UTC)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except ValueError:
        return None


@register
class GdeltConnector(Connector):
    name = "gdelt"
    reputation = 0.6
    intents = {"company.news"}
    license = "GDELT Project (open data)"

    def fetch(self, intent: str, params: dict[str, Any], ctx) -> ConnectorResult:
        identifier = _identifier(params)
        limit = _clamp(params.get("limit", 10), 1, 25, 10)
        since_days = _clamp(params.get("since_days", 90), 1, 365, 90)
        sort = params.get("sort") if params.get("sort") in ("tone", "recency") else "tone"
        try:
            min_tone = float(params.get("min_tone", 0.0))
        except (TypeError, ValueError):
            min_tone = 0.0

        payload = ctx.http.get_json(
            self.name,
            _API,
            params={
                "query": f'"{identifier}" sourcelang:english',
                "mode": "ArtList",
                "format": "json",
                "maxrecords": min(max(limit * 3, limit), 75),
                "timespan": f"{since_days}d",
                "sort": "datedesc" if sort == "recency" else "tonedesc",
            },
            timeout=6.0,
        )

        articles = []
        for item in payload.get("articles", []):
            url = item.get("url")
            if not url:
                continue
            domain = item.get("domain") or urlparse(url).netloc
            title = item.get("title")
            articles.append(
                {
                    "title": title,
                    "source": domain,
                    "url": url,
                    "published": _published(item.get("seendate")),
                    "tone": headline_tone(title),
                    "language": "en",
                }
            )

        # Deterministic favorable filter + ranking (caller-controlled via min_tone/sort).
        articles = [a for a in articles if a["tone"] >= min_tone]
        if sort == "recency":
            articles.sort(key=lambda a: a["published"] or "", reverse=True)
        else:
            articles.sort(key=lambda a: (a["tone"], a["published"] or ""), reverse=True)
        articles = articles[:limit]

        data = {"company": identifier, "as_of": utc_date(), "articles": articles}

        sources = [
            Source(
                name=self.name,
                url="https://www.gdeltproject.org/",
                retrieved_at=now_iso(),
                license=self.license,
            )
        ]
        for domain in dict.fromkeys(a["source"] for a in articles if a["source"]):
            sources.append(
                Source(name=domain, url=f"https://{domain}", retrieved_at=now_iso(), license=None)
            )

        warnings = [] if articles else ["no news found for query"]
        return ConnectorResult(connector=self.name, data=data, sources=sources, warnings=warnings)
