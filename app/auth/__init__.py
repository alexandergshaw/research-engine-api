"""Auth: stateless env-key validation (middleware) + key-generation CLI."""

from __future__ import annotations

from flask import Flask


def register_auth(app: Flask) -> None:
    """Register the key-generation CLI. Auth itself is enforced per-endpoint by
    the `require_api_key` decorator (see middleware)."""
    from .cli import register_cli

    register_cli(app)
