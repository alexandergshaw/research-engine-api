"""Auth + multi-tenancy: models, key validation, usage logging, admin CLI."""

from __future__ import annotations

from flask import Flask


def register_auth(app: Flask) -> None:
    """Wire auth models, request hooks (timer + usage log), and the CLI onto the app."""
    from . import models  # noqa: F401 — import so Flask-Migrate/create_all discover tables
    from .cli import register_cli
    from .middleware import log_usage

    app.after_request(log_usage)
    register_cli(app)
