"""MITRE ATT&CK connector — adversary techniques/tactics for security topics.

ATT&CK ships as a single large STIX bundle, so this connector demonstrates the
*bulk-dataset* pattern: download once per process (longer timeout), parse into an
in-memory index, then answer queries from memory. Contrast with the per-query API
connectors. In production you'd pre-warm or refresh this on a schedule.
"""

from __future__ import annotations

import threading
from typing import Any

from app.core.util import now_iso

from .base import Connector, ConnectorResult, Source, register

_BUNDLE = (
    "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/"
    "enterprise-attack/enterprise-attack.json"
)


def _query(params: dict[str, Any]) -> str:
    value = (
        params.get("technique")
        or params.get("tactic")
        or params.get("term")
        or params.get("query")
        or params.get("keyword")
    )
    if not value:
        raise ValueError("missing 'technique'/'tactic'/'query'")
    return str(value).strip()


@register
class MitreAttackConnector(Connector):
    name = "mitre_attack"
    reputation = 0.85
    intents = {"security.techniques"}
    license = "MITRE ATT&CK Terms of Use"

    def __init__(self) -> None:
        self._index: list[dict[str, Any]] | None = None
        self._lock = threading.Lock()

    def _load(self, ctx) -> list[dict[str, Any]]:
        if self._index is None:
            with self._lock:
                if self._index is None:
                    bundle = ctx.http.get_json(self.name, _BUNDLE, timeout=45.0)
                    self._index = self._build_index(bundle)
        return self._index

    @staticmethod
    def _build_index(bundle: dict[str, Any]) -> list[dict[str, Any]]:
        techniques = []
        for obj in bundle.get("objects", []):
            if obj.get("type") != "attack-pattern":
                continue
            if obj.get("revoked") or obj.get("x_mitre_deprecated"):
                continue
            ref = next(
                (
                    r
                    for r in obj.get("external_references", [])
                    if r.get("source_name") == "mitre-attack"
                ),
                {},
            )
            techniques.append(
                {
                    "id": ref.get("external_id"),
                    "name": obj.get("name"),
                    "description": obj.get("description"),
                    "tactics": [p.get("phase_name") for p in obj.get("kill_chain_phases", [])],
                    "url": ref.get("url"),
                    "is_subtechnique": obj.get("x_mitre_is_subtechnique", False),
                }
            )
        return techniques

    def fetch(self, intent: str, params: dict[str, Any], ctx) -> ConnectorResult:
        query = _query(params)
        limit = max(1, min(int(params.get("limit", 8)), 25))
        needle = query.lower()
        index = self._load(ctx)

        matches = [
            t
            for t in index
            if (t["id"] and t["id"].lower() == needle)
            or (t["name"] and needle in t["name"].lower())
            or any(needle in (tactic or "") for tactic in t["tactics"])
        ][:limit]
        if not matches:
            return ConnectorResult(connector=self.name, data={}, sources=[])

        techniques = [
            {
                "id": t["id"],
                "name": t["name"],
                "tactics": t["tactics"],
                "url": t["url"],
                "description": (t["description"][:400] if t["description"] else None),
            }
            for t in matches
        ]
        data = {"query": query, "techniques": techniques}
        source = Source(
            name=self.name,
            url="https://attack.mitre.org/",
            retrieved_at=now_iso(),
            license=self.license,
        )
        return ConnectorResult(connector=self.name, data=data, sources=[source])
