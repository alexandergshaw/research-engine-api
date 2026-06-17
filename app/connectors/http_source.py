"""Dynamic source connector — an incremental stream over a caller-supplied feed.

Unlike the other connectors, this one has no hard-coded upstream. The caller
describes *its own* JSON source in ``params.source`` — where to fetch and how to
read it — and the engine fetches it, projects each record into a flat shape, and
returns only the records newer than the caller's cursor. The calling app owns the
poll cadence (one-shot or continuous); the engine stays stateless and the cursor
travels with the client. Canonical use case: job postings.

Because the URL is caller-controlled, every fetch is SSRF-guarded (``core.ssrf``),
redirects are not followed, the response is size-capped, and auth headers the
caller passes are masked everywhere they could leak (see ``util.redact_params``).
"""

from __future__ import annotations

import json
from typing import Any

from app.core.mapping import (
    decode_cursor,
    encode_cursor,
    map_item,
    resolve_path,
    stable_id,
    to_sortable,
)
from app.core.ssrf import SsrfError, validate_url
from app.core.util import now_iso, utc_date

from .base import Connector, ConnectorBadRequest, ConnectorResult, Source, register


def _clamp(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(int(value), hi))
    except (TypeError, ValueError):
        return default


def _since_value(params: dict[str, Any], cursor_type: str) -> Any:
    """The high-water value to filter against, from an opaque cursor or a raw ``since``."""
    token = params.get("cursor")
    if token:
        value, _ = decode_cursor(str(token))
        return value if value is not None else token  # lenient: treat as a raw value
    since = params.get("since")
    return since if since not in (None, "") else None


@register
class HttpSourceConnector(Connector):
    name = "http_source"
    reputation = 0.5
    intents = {"feed.poll"}
    license = None

    def supports(self, intent: str, params: dict[str, Any]) -> float:
        # Only this connector serves feed.poll, and only when a source is supplied.
        return 1.0 if (intent in self.intents and params.get("source")) else 0.0

    def fetch(self, intent: str, params: dict[str, Any], ctx) -> ConnectorResult:
        source = params.get("source")
        if not isinstance(source, dict):
            raise ConnectorBadRequest("'source' must be an object")

        url = source.get("url")
        if not url or not isinstance(url, str):
            raise ConnectorBadRequest("'source.url' is required")

        method = str(source.get("method") or "GET").upper()
        if method not in ("GET", "POST"):
            raise ConnectorBadRequest("'source.method' must be GET or POST")

        field_map = source.get("map") or {}
        if not isinstance(field_map, dict):
            raise ConnectorBadRequest("'source.map' must be an object of target -> path")

        cursor_field = source.get("cursor_field")
        cursor_type = source.get("cursor_type") or "datetime"
        if cursor_field and field_map and cursor_field not in field_map:
            raise ConnectorBadRequest(
                f"'source.cursor_field' ({cursor_field}) must be one of the mapped fields"
            )

        items_path = source.get("items_path") or ""
        query = source.get("query") if isinstance(source.get("query"), dict) else None
        headers = source.get("headers") if isinstance(source.get("headers"), dict) else None
        json_body = source.get("body") if method == "POST" else None
        limit = _clamp(params.get("limit", 50), 1, 200, 50)

        # --- SSRF guard (caller controls the URL) --------------------------------
        try:
            host = validate_url(
                url,
                allow_http=ctx.dynamic_source_allow_http,
                block_private=ctx.dynamic_source_block_private,
                allowlist=ctx.dynamic_source_allowlist,
            )
        except SsrfError as exc:
            raise ConnectorBadRequest(f"source url rejected: {exc}") from exc

        # --- Fetch (per-host breaker, no redirects, size-capped) -----------------
        resp = ctx.http.request(
            method,
            f"http_source:{host}",
            url,
            params=query,
            headers=headers,
            json=json_body,
            timeout=min(ctx.timeout, 8.0),
            follow_redirects=False,
        )
        if resp.is_redirect:
            raise ConnectorBadRequest("source returned a redirect; redirects are not followed")
        if len(resp.content) > ctx.dynamic_source_max_bytes:
            raise ConnectorBadRequest(
                f"source response exceeds the {ctx.dynamic_source_max_bytes}-byte limit"
            )
        try:
            payload = resp.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ConnectorBadRequest("source response is not valid JSON") from exc

        # --- Project records into a flat shape -----------------------------------
        raw_items = resolve_path(payload, items_path) if items_path else payload
        if not isinstance(raw_items, list):
            raw_items = []

        postings: list[dict[str, Any]] = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            item = map_item(raw, field_map) if field_map else dict(raw)
            if not item.get("id"):
                item["id"] = stable_id(host, item.get("url"), item.get("title"))
            postings.append(item)

        # --- Incremental filter + ordering by the cursor field -------------------
        since_value = _since_value(params, cursor_type)
        since_key = to_sortable(since_value, cursor_type) if since_value is not None else None
        has_more = False

        if cursor_field:
            keyed = [(to_sortable(p.get(cursor_field), cursor_type), p) for p in postings]
            if since_key is not None:
                keyed = [(k, p) for k, p in keyed if k is not None and k > since_key]
            with_key = sorted(
                (kp for kp in keyed if kp[0] is not None), key=lambda kp: kp[0], reverse=True
            )
            without_key = [kp for kp in keyed if kp[0] is None]
            ordered = with_key + without_key
            has_more = len(ordered) > limit
            postings = [p for _, p in ordered[:limit]]
            new_cursor = self._next_cursor(
                postings, cursor_field, cursor_type, since_value
            )
        else:
            has_more = len(postings) > limit
            postings = postings[:limit]
            new_cursor = None  # no cursor field => full (non-incremental) fetch each poll

        data = {
            "source": host,
            "as_of": utc_date(),
            "postings": postings,
            "cursor": new_cursor,
            "count": len(postings),
            "has_more": has_more,
        }

        sources = [
            Source(
                name=host,
                url=url,
                retrieved_at=now_iso(),
                license=source.get("license"),
            )
        ]

        if postings:
            warnings: list[str] = []
        elif since_key is not None:
            warnings = ["no new items since cursor"]
        else:
            warnings = ["no items found for source"]
        return ConnectorResult(connector=self.name, data=data, sources=sources, warnings=warnings)

    @staticmethod
    def _next_cursor(
        postings: list[dict[str, Any]], cursor_field: str, cursor_type: str, since_value: Any
    ) -> str | None:
        """High-water cursor for the returned page; echo the incoming one if nothing is new."""
        keyed = [
            (to_sortable(p.get(cursor_field), cursor_type), p.get(cursor_field))
            for p in postings
        ]
        keyed = [(k, raw) for k, raw in keyed if k is not None]
        if keyed:
            _, newest_raw = max(keyed, key=lambda kr: kr[0])
            return encode_cursor(newest_raw, cursor_type)
        if since_value is not None:
            return encode_cursor(since_value, cursor_type)
        return None
