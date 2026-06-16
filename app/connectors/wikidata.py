"""Wikidata connector — structured facts (entities, companies) via the action API.

Resolves a search term to an entity, then surfaces the label, description,
aliases, and a curated set of *literal-valued* claims (dates, quantities, URLs)
that don't require a second round-trip to resolve Q-id references.
"""

from __future__ import annotations

from typing import Any

from app.core.util import now_iso

from .base import Connector, ConnectorResult, Source, register

_API = "https://www.wikidata.org/w/api.php"

# Property id -> output field. Restricted to literal datatypes we can render directly.
_LITERAL_PROPS: dict[str, tuple[str, str]] = {
    "P571": ("inception", "time"),
    "P577": ("publication_date", "time"),
    "P856": ("official_website", "string"),
    "P1128": ("employees", "quantity"),
    "P2139": ("total_revenue", "quantity"),
    "P2403": ("total_assets", "quantity"),
    "P159": ("headquarters_qid", "wikibase-entityid"),
}


def _term(params: dict[str, Any]) -> str:
    term = params.get("term") or params.get("name") or params.get("query") or params.get("topic")
    if not term:
        raise ValueError("missing 'term'")
    return str(term).strip()


def _literal(snak: dict[str, Any], datatype: str) -> Any:
    try:
        value = snak["datavalue"]["value"]
    except (KeyError, TypeError):
        return None
    if datatype == "time":
        return value.get("time", "").lstrip("+") or None
    if datatype == "quantity":
        amount = value.get("amount", "").lstrip("+")
        return amount or None
    if datatype == "wikibase-entityid":
        return value.get("id")
    return value  # plain string/url


@register
class WikidataConnector(Connector):
    name = "wikidata"
    reputation = 0.7
    intents = {"entity.facts", "company.profile", "concept.overview"}
    license = "CC0 1.0"

    def supports(self, intent: str, params: dict[str, Any]) -> float:
        if intent == "concept.overview":
            return 0.4  # fallback/augment behind Wikipedia
        return 1.0 if intent in self.intents else 0.0

    def fetch(self, intent: str, params: dict[str, Any], ctx) -> ConnectorResult:
        term = _term(params)
        search = ctx.http.get_json(
            self.name,
            _API,
            params={
                "action": "wbsearchentities",
                "search": term,
                "language": "en",
                "format": "json",
                "limit": 1,
            },
        )
        hits = search.get("search", [])
        if not hits:
            return ConnectorResult(connector=self.name, data={}, sources=[])
        qid = hits[0]["id"]

        entity_resp = ctx.http.get_json(
            self.name,
            _API,
            params={
                "action": "wbgetentities",
                "ids": qid,
                "format": "json",
                "props": "labels|descriptions|aliases|claims",
                "languages": "en",
            },
        )
        entity = entity_resp.get("entities", {}).get(qid, {})

        data: dict[str, Any] = {
            "wikidata_id": qid,
            "label": entity.get("labels", {}).get("en", {}).get("value", term),
            "description": entity.get("descriptions", {}).get("en", {}).get("value"),
            "aliases": [a["value"] for a in entity.get("aliases", {}).get("en", [])],
        }

        facts: dict[str, Any] = {}
        claims = entity.get("claims", {})
        for prop, (field_name, datatype) in _LITERAL_PROPS.items():
            statements = claims.get(prop)
            if not statements:
                continue
            value = _literal(statements[0].get("mainsnak", {}), datatype)
            if value is not None:
                facts[field_name] = value
        if facts:
            data["facts"] = facts

        source = Source(
            name=self.name,
            url=f"https://www.wikidata.org/wiki/{qid}",
            retrieved_at=now_iso(),
            license=self.license,
        )
        return ConnectorResult(connector=self.name, data=data, sources=[source])
