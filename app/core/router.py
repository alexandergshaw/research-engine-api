"""Intent → connector routing.

Scores every registered connector for an intent and returns the top-N healthy
candidates, ranked by ``supports * reputation``.
"""

from __future__ import annotations

from typing import Any

from app.connectors.base import Connector, all_connectors

from .context import EngineContext


def route(intent: str, params: dict[str, Any], ctx: EngineContext) -> list[Connector]:
    scored: list[tuple[float, Connector]] = []
    for connector in all_connectors():
        if connector.name in ctx.disabled_connectors:
            continue
        score = connector.supports(intent, params)
        if score <= 0:
            continue
        scored.append((score * connector.reputation, connector))

    # Highest score first; healthy (closed-breaker) connectors ahead of tripped ones.
    scored.sort(key=lambda item: (connector_is_healthy(item[1], ctx), item[0]), reverse=True)
    return [connector for _, connector in scored[: ctx.max_connectors]]


def connector_is_healthy(connector: Connector, ctx: EngineContext) -> bool:
    return connector.health(ctx)


def candidates_for(intent: str) -> list[str]:
    """Names of connectors that declare support for an intent (no scoring)."""
    return [c.name for c in all_connectors() if intent in c.intents]
