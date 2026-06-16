"""Admin CLI: provision tenants and mint API keys."""

from __future__ import annotations

import click
from flask import Flask
from flask.cli import AppGroup

from app.extensions import db

from .models import ApiKey, Tenant


def register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db() -> None:
        """Create all tables (quick start; use `flask db upgrade` in production)."""
        db.create_all()
        click.echo("Tables created.")

    tenant_cli = AppGroup("tenant", help="Manage tenants.")
    key_cli = AppGroup("key", help="Manage API keys.")

    @tenant_cli.command("create")
    @click.argument("name")
    @click.option("--plan", default="free", show_default=True)
    @click.option("--rate-limit", "rate_limit", default="120/minute", show_default=True)
    def tenant_create(name: str, plan: str, rate_limit: str) -> None:
        tenant = Tenant(name=name, plan=plan, rate_limit=rate_limit)
        db.session.add(tenant)
        db.session.commit()
        click.echo(f"Created tenant '{name}' (id={tenant.id}, plan={plan}, limit={rate_limit}).")

    @tenant_cli.command("list")
    def tenant_list() -> None:
        for tenant in Tenant.query.order_by(Tenant.id).all():
            click.echo(
                f"{tenant.id}\t{tenant.name}\t{tenant.plan}\t{tenant.rate_limit}\t"
                f"active={tenant.active}"
            )

    @key_cli.command("mint")
    @click.argument("tenant_name")
    @click.option("--label", default=None)
    def key_mint(tenant_name: str, label: str | None) -> None:
        tenant = Tenant.query.filter_by(name=tenant_name).first()
        if tenant is None:
            raise click.ClickException(f"No tenant named '{tenant_name}'.")
        key, raw = ApiKey.generate(tenant, label=label)
        db.session.add(key)
        db.session.commit()
        click.echo(f"API key for '{tenant_name}' (shown once - store it now):\n  {raw}")

    app.cli.add_command(tenant_cli)
    app.cli.add_command(key_cli)
