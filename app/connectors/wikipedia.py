"""Wikipedia connector — summaries, definitions, key facts for almost any topic."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.core.util import now_iso

from .base import Connector, ConnectorResult, Source, register

_BASE = "https://en.wikipedia.org/api/rest_v1"


def _term(params: dict[str, Any]) -> str:
    term = params.get("term") or params.get("name") or params.get("query") or params.get("topic")
    if not term:
        raise ValueError("missing 'term'")
    return str(term).strip()


@register
class WikipediaConnector(Connector):
    name = "wikipedia"
    reputation = 0.82
    intents = {"concept.overview", "concept.definition", "entity.facts"}
    license = "CC BY-SA 4.0"

    def fetch(self, intent: str, params: dict[str, Any], ctx) -> ConnectorResult:
        term = _term(params)
        title = quote(term.replace(" ", "_"), safe="")
        payload = ctx.http.get_json(
            self.name,
            f"{_BASE}/page/summary/{title}",
            headers={"Accept": "application/json"},
        )

        page_url = (payload.get("content_urls", {}).get("desktop", {}) or {}).get("page")
        extract = payload.get("extract")

        if intent == "concept.definition":
            data: dict[str, Any] = {
                "term": payload.get("title", term),
                "definition": extract,
            }
        else:
            data = {
                "title": payload.get("title", term),
                "summary": extract,
                "description": payload.get("description"),
                "thumbnail": (payload.get("thumbnail") or {}).get("source"),
                "url": page_url,
            }

        source = Source(
            name=self.name,
            url=page_url or f"{_BASE}/page/summary/{title}",
            retrieved_at=now_iso(),
            license=self.license,
        )
        return ConnectorResult(connector=self.name, data=data, sources=[source])
