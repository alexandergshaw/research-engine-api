"""Deterministic field-mapping + cursor codec for the dynamic source adapter.

No LLM, no heuristics — a caller declares dotted paths into its source's JSON
(``"company.name"``, ``"items.0.title"``) and which mapped field is the
monotonic cursor. The cursor is an opaque, base64url token encoding the
high-water value + its ordering type so the engine can stay stateless: the
client carries it between polls and the engine returns only newer items.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
from typing import Any

CursorType = str  # "datetime" | "epoch" | "number" | "string"


def _tokens(path: str) -> list[str | int]:
    """Split a dotted/bracket path into keys and list indices."""
    normalized = path.replace("[", ".").replace("]", "")
    out: list[str | int] = []
    for part in normalized.split("."):
        if part == "":
            continue
        out.append(int(part) if part.lstrip("-").isdigit() else part)
    return out


def resolve_path(obj: Any, path: str) -> Any:
    """Follow a dotted path into nested dicts/lists; ``None`` if any hop misses."""
    if not path:
        return obj
    cur = obj
    for part in _tokens(path):
        if cur is None:
            return None
        if isinstance(part, int):
            if isinstance(cur, list) and -len(cur) <= part < len(cur):
                cur = cur[part]
            else:
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def map_item(raw: dict[str, Any], field_map: dict[str, str]) -> dict[str, Any]:
    """Project one raw record into the caller's target shape via dotted paths."""
    return {
        target: resolve_path(raw, src)
        for target, src in field_map.items()
        if isinstance(src, str)
    }


def stable_id(*parts: Any) -> str:
    """Deterministic short id from the source host + url/title (for client dedup)."""
    blob = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _parse_datetime(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.timestamp()


def to_sortable(value: Any, cursor_type: CursorType) -> float | str | None:
    """A comparable key for ordering/filtering by the cursor field (``None`` if unusable)."""
    if value is None:
        return None
    try:
        if cursor_type == "datetime":
            return _parse_datetime(value)
        if cursor_type in ("epoch", "number"):
            return float(value)
        return str(value)
    except (TypeError, ValueError):
        return None


def encode_cursor(value: Any, cursor_type: CursorType) -> str:
    """Opaque token carrying the high-water value + its ordering type."""
    raw = json.dumps({"v": value, "t": cursor_type}, default=str, sort_keys=True)
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(token: str) -> tuple[Any, CursorType | None]:
    """Inverse of :func:`encode_cursor`; ``(None, None)`` if the token is unreadable."""
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        obj = json.loads(raw)
        return obj.get("v"), obj.get("t")
    except (ValueError, TypeError):
        return None, None
