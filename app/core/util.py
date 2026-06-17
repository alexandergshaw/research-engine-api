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


def utc_date() -> str:
    """Today's UTC date, ISO (YYYY-MM-DD)."""
    return _dt.datetime.now(_dt.UTC).date().isoformat()


def cache_key(intent: str, params: dict[str, Any], bucket: str | None = None) -> str:
    """Stable cache key from an intent + params (+ optional time bucket for volatile intents)."""
    blob = json.dumps(
        {"intent": intent, "params": params, "bucket": bucket}, sort_keys=True, default=str
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def response_etag(
    intent: str, params: dict[str, Any], version: str, bucket: str | None = None
) -> str:
    """Strong-form ETag over intent + normalized params + contract version (+ time bucket).

    Deterministic for identical inputs so gateways/clients cache uniformly; a version
    bump changes every ETag, and a `bucket` (e.g. the UTC date) rotates volatile intents
    like ``company.news`` daily.
    """
    blob = json.dumps(
        {"intent": intent, "params": params, "version": version, "bucket": bucket},
        sort_keys=True,
        default=str,
    )
    return '"' + hashlib.sha256(blob.encode("utf-8")).hexdigest() + '"'
