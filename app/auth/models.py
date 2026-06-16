"""Multi-tenant data model: tenants, hashed API keys, and per-request usage logs."""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets

from app.extensions import db

_KEY_PREFIX = "rek_"


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Tenant(db.Model):
    __tablename__ = "tenants"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    plan = db.Column(db.String(40), nullable=False, default="free")
    rate_limit = db.Column(db.String(40), nullable=False, default="120/minute")
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    api_keys = db.relationship(
        "ApiKey", back_populates="tenant", cascade="all, delete-orphan"
    )


class ApiKey(db.Model):
    __tablename__ = "api_keys"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    prefix = db.Column(db.String(16), index=True, nullable=False)
    key_hash = db.Column(db.String(64), unique=True, nullable=False)
    label = db.Column(db.String(120))
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    last_used_at = db.Column(db.DateTime)

    tenant = db.relationship("Tenant", back_populates="api_keys")

    @staticmethod
    def hash_key(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def generate(cls, tenant: Tenant, label: str | None = None) -> tuple[ApiKey, str]:
        """Create a key. Returns (model, raw_key); the raw key is shown only once."""
        raw = _KEY_PREFIX + secrets.token_urlsafe(32)
        key = cls(
            tenant=tenant,
            prefix=raw[: len(_KEY_PREFIX) + 8],
            key_hash=cls.hash_key(raw),
            label=label,
        )
        return key, raw


class UsageLog(db.Model):
    __tablename__ = "usage_logs"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), index=True)
    api_key_id = db.Column(db.Integer, db.ForeignKey("api_keys.id"))
    method = db.Column(db.String(8))
    path = db.Column(db.String(255))
    intent = db.Column(db.String(80))
    status = db.Column(db.Integer)
    latency_ms = db.Column(db.Integer)
    sources = db.Column(db.String(255))
    cache_hit = db.Column(db.Boolean, default=False)
    degraded = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow, index=True)
