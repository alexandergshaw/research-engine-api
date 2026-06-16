"""Connector interface + auto-registry.

A connector is an adapter over one external data source. It declares which
intents it can serve and a capability score for a given request; the router
picks the best connectors per intent. Adding a source is just dropping a new
``@register`` class in this package — no core code changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.context import EngineContext

_REGISTRY: dict[str, Connector] = {}


@dataclass
class Source:
    """Provenance for a piece of returned data."""

    name: str
    url: str | None
    retrieved_at: str
    license: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "retrieved_at": self.retrieved_at,
            "license": self.license,
        }


@dataclass
class ConnectorResult:
    """What a connector returns on success."""

    connector: str
    data: dict[str, Any]
    sources: list[Source] = field(default_factory=list)
    relevance: float = 1.0


class Connector(ABC):
    name: str = ""
    reputation: float = 0.5  # static trust weight used in ranking (0..1)
    intents: set[str] = set()
    license: str | None = None

    def supports(self, intent: str, params: dict[str, Any]) -> float:
        """Capability score in [0, 1]. 0 means "cannot serve this request"."""
        return 1.0 if intent in self.intents else 0.0

    @abstractmethod
    def fetch(self, intent: str, params: dict[str, Any], ctx: EngineContext) -> ConnectorResult:
        """Fetch + normalize. Raise on failure; the engine handles isolation."""

    def health(self, ctx: EngineContext) -> bool:
        """True if the source's breaker is closed (cheap, no network call)."""
        return not ctx.http.breaker_open(self.name)


def register(cls: type[Connector]) -> type[Connector]:
    """Class decorator: instantiate and add the connector to the registry."""
    instance = cls()
    if not instance.name:
        raise ValueError(f"Connector {cls.__name__} must define a non-empty name")
    _REGISTRY[instance.name] = instance
    return cls


def all_connectors() -> list[Connector]:
    return list(_REGISTRY.values())


def get_connector(name: str) -> Connector | None:
    return _REGISTRY.get(name)


def known_intents() -> set[str]:
    intents: set[str] = set()
    for connector in _REGISTRY.values():
        intents |= connector.intents
    return intents
