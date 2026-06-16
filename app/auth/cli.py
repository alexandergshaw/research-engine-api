"""Admin CLI: generate API keys to put in the API_KEYS env var (no storage)."""

from __future__ import annotations

import secrets

import click
from flask import Flask


def register_cli(app: Flask) -> None:
    @app.cli.command("genkey")
    @click.option("--count", default=1, show_default=True, help="How many keys to generate.")
    def genkey(count: int) -> None:
        """Print secure random API key(s). Put them in API_KEYS (comma-separated)."""
        keys = [f"rek_{secrets.token_urlsafe(32)}" for _ in range(max(1, count))]
        for key in keys:
            click.echo(key)
        click.echo("\nAdd to your environment, e.g.:")
        click.echo(f'  API_KEYS="{",".join(keys)}"')
