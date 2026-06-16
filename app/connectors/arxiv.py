"""arXiv connector — academic papers (title, abstract, authors) for STEM topics.

arXiv's API returns Atom XML, so this connector uses ``get_text`` + ElementTree
rather than the JSON path.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from app.core.util import now_iso

from .base import Connector, ConnectorResult, Source, register

_API = "https://export.arxiv.org/api/query"
_ATOM = "{http://www.w3.org/2005/Atom}"


def _query(params: dict[str, Any]) -> str:
    term = params.get("query") or params.get("term") or params.get("topic")
    if not term:
        raise ValueError("missing 'query'")
    return str(term).strip()


def _text(node: ET.Element | None) -> str | None:
    if node is None or node.text is None:
        return None
    return node.text.strip()


@register
class ArxivConnector(Connector):
    name = "arxiv"
    reputation = 0.8
    intents = {"academic.papers"}
    license = "arXiv (per-paper licenses vary)"

    def fetch(self, intent: str, params: dict[str, Any], ctx) -> ConnectorResult:
        query = _query(params)
        limit = max(1, min(int(params.get("limit", 5)), 20))
        xml = ctx.http.get_text(
            self.name,
            _API,
            params={"search_query": f"all:{query}", "start": 0, "max_results": limit},
        )
        root = ET.fromstring(xml)
        papers = []
        for entry in root.findall(f"{_ATOM}entry"):
            authors = [
                _text(a.find(f"{_ATOM}name")) for a in entry.findall(f"{_ATOM}author")
            ]
            papers.append(
                {
                    "title": _text(entry.find(f"{_ATOM}title")),
                    "summary": _text(entry.find(f"{_ATOM}summary")),
                    "url": _text(entry.find(f"{_ATOM}id")),
                    "published": _text(entry.find(f"{_ATOM}published")),
                    "authors": [a for a in authors if a],
                }
            )
        if not papers:
            return ConnectorResult(connector=self.name, data={}, sources=[])

        data = {"query": query, "papers": papers}
        source = Source(
            name=self.name,
            url=f"https://arxiv.org/find/all?query={query}",
            retrieved_at=now_iso(),
            license=self.license,
        )
        return ConnectorResult(connector=self.name, data=data, sources=[source])
