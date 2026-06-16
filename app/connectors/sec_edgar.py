"""SEC EDGAR connector — authoritative profile data for US-listed companies.

Resolves a name/ticker to a CIK via the public company-tickers file (loaded once
per process), then pulls company metadata from the submissions API. SEC requires
a descriptive User-Agent, which the shared HTTP client already sends.
"""

from __future__ import annotations

import threading
from typing import Any

from app.core.util import now_iso

from .base import Connector, ConnectorResult, Source, register

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"


def _name(params: dict[str, Any]) -> str:
    value = params.get("name") or params.get("ticker") or params.get("term")
    if not value:
        raise ValueError("missing 'name'")
    return str(value).strip()


@register
class SecEdgarConnector(Connector):
    name = "sec_edgar"
    reputation = 0.8
    intents = {"company.profile"}
    license = "U.S. SEC / public domain"

    def __init__(self) -> None:
        self._tickers: list[dict[str, Any]] | None = None
        self._lock = threading.Lock()

    def _load_tickers(self, ctx) -> list[dict[str, Any]]:
        if self._tickers is None:
            with self._lock:
                if self._tickers is None:
                    raw = ctx.http.get_json(self.name, _TICKERS_URL)
                    self._tickers = list(raw.values())
        return self._tickers

    def _resolve(self, query: str, ctx) -> dict[str, Any] | None:
        entries = self._load_tickers(ctx)
        low = query.lower()
        for entry in entries:  # exact ticker
            if str(entry.get("ticker", "")).lower() == low:
                return entry
        for entry in entries:  # exact title
            if str(entry.get("title", "")).lower() == low:
                return entry
        for entry in entries:  # title contains
            if low in str(entry.get("title", "")).lower():
                return entry
        return None

    def fetch(self, intent: str, params: dict[str, Any], ctx) -> ConnectorResult:
        match = self._resolve(_name(params), ctx)
        if match is None:
            return ConnectorResult(connector=self.name, data={}, sources=[])

        cik = int(match["cik_str"])
        submissions = ctx.http.get_json(self.name, _SUBMISSIONS.format(cik=cik))
        business = (submissions.get("addresses", {}) or {}).get("business", {}) or {}

        data = {
            "name": submissions.get("name", match.get("title")),
            "ticker": match.get("ticker"),
            "cik": f"{cik:010d}",
            "exchanges": submissions.get("exchanges", []),
            "industry": submissions.get("sicDescription"),
            "sic": submissions.get("sic"),
            "entity_type": submissions.get("entityType"),
            "fiscal_year_end": submissions.get("fiscalYearEnd"),
            "state_of_incorporation": submissions.get("stateOfIncorporation"),
            "headquarters": {
                "street": business.get("street1"),
                "city": business.get("city"),
                "state": business.get("stateOrCountry"),
                "zip": business.get("zipCode"),
            },
        }
        source = Source(
            name=self.name,
            url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik:010d}",
            retrieved_at=now_iso(),
            license=self.license,
        )
        return ConnectorResult(connector=self.name, data=data, sources=[source])
