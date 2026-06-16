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


def build_context() -> EngineContext:
    cfg = current_app.config
    return EngineContext(
        http=current_app.extensions["http_client"],
        source_creds=dict(cfg.get("SOURCE_CREDS", {})),
        timeout=cfg["HTTP_TIMEOUT"],
        deadline=cfg["FANOUT_DEADLINE"],
        max_connectors=cfg["MAX_CONNECTORS_PER_INTENT"],
    )
