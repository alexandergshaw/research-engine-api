"""ESCO connector — occupational duties/skills from the EU ESCO taxonomy (public API).

Serves ``role.responsibilities``: given a job title, returns the occupation's
description plus its essential and optional skills (the "duties/competencies").
"""

from __future__ import annotations

from typing import Any

from app.core.util import now_iso

from .base import Connector, ConnectorResult, Source, register

_SEARCH = "https://ec.europa.eu/esco/api/search"


def _title(params: dict[str, Any]) -> str:
    value = params.get("title") or params.get("term") or params.get("query") or params.get("topic")
    if not value:
        raise ValueError("missing 'title'")
    return str(value).strip()


def _skills(links: dict[str, Any], relation: str, limit: int = 15) -> list[str]:
    return [s.get("title") for s in links.get(relation, []) if s.get("title")][:limit]


@register
class EscoConnector(Connector):
    name = "esco"
    reputation = 0.72
    intents = {"role.responsibilities"}
    license = "ESCO (CC BY 4.0)"

    def fetch(self, intent: str, params: dict[str, Any], ctx) -> ConnectorResult:
        title = _title(params)
        search = ctx.http.get_json(
            self.name,
            _SEARCH,
            params={"text": title, "language": "en", "type": "occupation", "limit": 1},
        )
        results = (search.get("_embedded", {}) or {}).get("results", [])
        if not results:
            return ConnectorResult(connector=self.name, data={}, sources=[])

        first = results[0]
        href = ((first.get("_links", {}) or {}).get("self", {}) or {}).get("href")
        occupation = ctx.http.get_json(self.name, href) if href else first

        description = (
            ((occupation.get("description", {}) or {}).get("en", {}) or {}).get("literal")
        )
        links = occupation.get("_links", {}) or {}
        data = {
            "title": occupation.get("title", title),
            "description": description,
            "essential_skills": _skills(links, "hasEssentialSkill"),
            "optional_skills": _skills(links, "hasOptionalSkill"),
            "uri": occupation.get("uri") or first.get("uri"),
        }
        source = Source(
            name=self.name,
            url=occupation.get("uri") or _SEARCH,
            retrieved_at=now_iso(),
            license=self.license,
        )
        return ConnectorResult(connector=self.name, data=data, sources=[source])
