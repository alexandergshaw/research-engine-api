"""GitHub connector — popular repositories for a topic (enriches concept.examples).

Works unauthenticated (low rate limit); set GITHUB_TOKEN to raise the quota.
"""

from __future__ import annotations

from typing import Any

from app.core.util import now_iso

from .base import Connector, ConnectorResult, Source, register

_SEARCH = "https://api.github.com/search/repositories"


def _term(params: dict[str, Any]) -> str:
    term = params.get("term") or params.get("query") or params.get("topic")
    if not term:
        raise ValueError("missing 'term'")
    return str(term).strip()


@register
class GitHubConnector(Connector):
    name = "github"
    reputation = 0.75
    intents = {"concept.examples"}
    license = "varies per repository"

    def fetch(self, intent: str, params: dict[str, Any], ctx) -> ConnectorResult:
        term = _term(params)
        limit = max(1, min(int(params.get("limit", 5)), 20))
        headers = {"Accept": "application/vnd.github+json"}
        token = ctx.source_creds.get("github_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        payload = ctx.http.get_json(
            self.name,
            _SEARCH,
            params={"q": term, "sort": "stars", "order": "desc", "per_page": limit},
            headers=headers,
        )
        repos = [
            {
                "name": item.get("full_name"),
                "url": item.get("html_url"),
                "description": item.get("description"),
                "stars": item.get("stargazers_count"),
                "language": item.get("language"),
            }
            for item in payload.get("items", [])[:limit]
        ]
        if not repos:
            return ConnectorResult(connector=self.name, data={}, sources=[])

        data = {"repositories": repos}
        source = Source(
            name=self.name,
            url=f"https://github.com/search?q={term}",
            retrieved_at=now_iso(),
            license=self.license,
        )
        return ConnectorResult(connector=self.name, data=data, sources=[source])
