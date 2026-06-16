"""NVD connector — CVE vulnerabilities (id, CVSS severity, references) by keyword."""

from __future__ import annotations

from typing import Any

from app.core.util import now_iso

from .base import Connector, ConnectorResult, Source, register

_API = "https://services.nvd.nist.gov/rest/json/cves/2.0"


def _keyword(params: dict[str, Any]) -> str:
    term = (
        params.get("product")
        or params.get("keyword")
        or params.get("term")
        or params.get("query")
    )
    if not term:
        raise ValueError("missing 'product'/'keyword'")
    return str(term).strip()


def _cvss(metrics: dict[str, Any]) -> dict[str, Any]:
    for version in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        entries = metrics.get(version)
        if entries:
            data = entries[0].get("cvssData", {})
            return {
                "version": data.get("version"),
                "base_score": data.get("baseScore"),
                "severity": data.get("baseSeverity") or entries[0].get("baseSeverity"),
            }
    return {}


@register
class NvdConnector(Connector):
    name = "nvd"
    reputation = 0.85
    intents = {"security.vulnerabilities"}
    license = "NVD / public domain"

    def fetch(self, intent: str, params: dict[str, Any], ctx) -> ConnectorResult:
        keyword = _keyword(params)
        limit = max(1, min(int(params.get("limit", 5)), 20))
        headers = {}
        api_key = ctx.source_creds.get("nvd_api_key")
        if api_key:
            headers["apiKey"] = api_key

        payload = ctx.http.get_json(
            self.name,
            _API,
            params={"keywordSearch": keyword, "resultsPerPage": limit},
            headers=headers or None,
        )
        vulns = payload.get("vulnerabilities", [])
        cves = []
        for entry in vulns[:limit]:
            cve = entry.get("cve", {})
            descriptions = cve.get("descriptions", [])
            english = next(
                (d["value"] for d in descriptions if d.get("lang") == "en"),
                descriptions[0]["value"] if descriptions else None,
            )
            cves.append(
                {
                    "id": cve.get("id"),
                    "description": english,
                    "published": cve.get("published"),
                    "cvss": _cvss(cve.get("metrics", {})),
                    "references": [r.get("url") for r in cve.get("references", [])[:5]],
                }
            )
        if not cves:
            return ConnectorResult(connector=self.name, data={}, sources=[])

        data = {"keyword": keyword, "total": payload.get("totalResults"), "cves": cves}
        source = Source(
            name=self.name,
            url=f"https://nvd.nist.gov/vuln/search/results?query={keyword}",
            retrieved_at=now_iso(),
            license=self.license,
        )
        return ConnectorResult(connector=self.name, data=data, sources=[source])
