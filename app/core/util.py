"""Small deterministic helpers shared across the engine."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from typing import Any


def now_iso() -> str:
    """UTC timestamp, ISO-8601 with a trailing Z."""
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def cache_key(intent: str, params: dict[str, Any]) -> str:
    """Stable cache key from an intent + params (order-independent)."""
    blob = json.dumps({"intent": intent, "params": params}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
