"""Two-tier cache: a short-TTL "fresh" entry plus a long-TTL "stale" copy.

The stale copy backs graceful degradation — when every upstream fails, the
engine serves the last good payload instead of erroring.
"""

from __future__ import annotations

import time
from typing import Any

from flask import current_app

from app.extensions import cache

_FRESH_PREFIX = "fresh:"
_STALE_PREFIX = "stale:"


def get_fresh(key: str) -> tuple[dict[str, Any], int] | None:
    entry = cache.get(_FRESH_PREFIX + key)
    if not entry:
        return None
    return entry["value"], int(time.time() - entry["ts"])


def get_stale(key: str) -> tuple[dict[str, Any], int] | None:
    entry = cache.get(_STALE_PREFIX + key)
    if not entry:
        return None
    return entry["value"], int(time.time() - entry["ts"])


def store(key: str, value: dict[str, Any]) -> None:
    entry = {"value": value, "ts": time.time()}
    cache.set(_FRESH_PREFIX + key, entry, timeout=current_app.config["CACHE_DEFAULT_TIMEOUT"])
    cache.set(_STALE_PREFIX + key, entry, timeout=current_app.config["STALE_CACHE_TIMEOUT"])
