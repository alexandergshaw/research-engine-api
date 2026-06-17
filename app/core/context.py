"""EngineContext: the immutable bundle of settings/clients passed into connectors.

Built once per request in the request thread (so it can read ``current_app``),
then handed to connector worker threads — which must NOT touch the Flask app
context themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from flask import current_app

from .http import HttpClient


@dataclass(frozen=True)
class EngineContext:
    http: HttpClient
    source_creds: dict[str, Any] = field(default_factory=dict)
    timeout: float = 8.0
    deadline: float = 12.0
    max_connectors: int = 4
    disabled_connectors: frozenset[str] = frozenset()
    # Caller-supplied dynamic source (feed.poll) — SSRF/abuse limits, resolved in the
    # request thread so connector worker threads never touch current_app.
    dynamic_source_allow_http: bool = False
    dynamic_source_block_private: bool = True
    dynamic_source_allowlist: frozenset[str] = frozenset()
    dynamic_source_max_bytes: int = 2_000_000


def build_context() -> EngineContext:
    cfg = current_app.config
    return EngineContext(
        http=current_app.extensions["http_client"],
        source_creds=dict(cfg.get("SOURCE_CREDS", {})),
        timeout=cfg["HTTP_TIMEOUT"],
        deadline=cfg["FANOUT_DEADLINE"],
        max_connectors=cfg["MAX_CONNECTORS_PER_INTENT"],
        disabled_connectors=frozenset(cfg.get("DISABLED_CONNECTORS", frozenset())),
        dynamic_source_allow_http=cfg["DYNAMIC_SOURCE_ALLOW_HTTP"],
        dynamic_source_block_private=cfg["DYNAMIC_SOURCE_BLOCK_PRIVATE"],
        dynamic_source_allowlist=frozenset(cfg.get("DYNAMIC_SOURCE_ALLOWLIST", frozenset())),
        dynamic_source_max_bytes=cfg["DYNAMIC_SOURCE_MAX_BYTES"],
    )
