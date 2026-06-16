"""Stack Exchange connector — relevant Q&A / code-example pointers for CS topics."""

from __future__ import annotations

from typing import Any

from app.core.util import now_iso

from .base import Connector, ConnectorResult, Source, register

_API = "https://api.stackexchange.com/2.3/search/advanced"


def _term(params: dict[str, Any]) -> str:
    term = params.get("term") or params.get("query") or params.get("topic")
    if not term:
        raise ValueError("missing 'term'")
    return str(term).strip()


@register
class StackExchangeConnector(Connector):
    name = "stackexchange"
    reputation = 0.7
    intents = {"concept.examples"}
    license = "CC BY-SA 4.0"

    def fetch(self, intent: str, params: dict[str, Any], ctx) -> ConnectorResult:
        term = _term(params)
        limit = int(params.get("limit", 5))
        query = {
            "order": "desc",
            "sort": "relevance",
            "q": term,
            "site": params.get("site", "stackoverflow"),
            "pagesize": max(1, min(limit, 20)),
            "filter": "default",
        }
        tag = params.get("language") or params.get("tag")
        if tag:
            query["tagged"] = tag
        key = ctx.source_creds.get("stackexchange_key")
        if key:
            query["key"] = key

        payload = ctx.http.get_json(self.name, _API, params=query)
        items = payload.get("items", [])
        questions = [
            {
                "title": item.get("title"),
                "url": item.get("link"),
                "score": item.get("score"),
                "is_answered": item.get("is_answered"),
                "answer_count": item.get("answer_count"),
                "tags": item.get("tags", []),
            }
            for item in items[:limit]
        ]
        if not questions:
            return ConnectorResult(connector=self.name, data={}, sources=[])

        data = {"questions": questions, "site": query["site"]}
        source = Source(
            name=self.name,
            url=f"https://stackoverflow.com/search?q={term}",
            retrieved_at=now_iso(),
            license=self.license,
        )
        return ConnectorResult(connector=self.name, data=data, sources=[source])
