"""Environment-driven configuration. Stateless — no database, no external stores."""

from __future__ import annotations

import os


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


def _csv_set(name: str) -> frozenset[str]:
    return frozenset(p.strip() for p in os.getenv(name, "").split(",") if p.strip())


def _csv_list(name: str) -> list[str]:
    return [p.strip() for p in os.getenv(name, "").split(",") if p.strip()]


class Config:
    # --- Flask ---
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")

    # --- flask-smorest / OpenAPI ---
    API_TITLE = "Research Engine API"
    API_VERSION = "v1"
    OPENAPI_VERSION = "3.0.3"
    OPENAPI_URL_PREFIX = "/"
    OPENAPI_SWAGGER_UI_PATH = "/docs"
    OPENAPI_SWAGGER_UI_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"
    OPENAPI_JSON_PATH = "openapi.json"
    API_SPEC_OPTIONS = {
        "info": {
            "description": (
                "Source-agnostic, no-LLM knowledge-retrieval engine. Declare an "
                "intent and parameters; the engine routes to reputable sources, "
                "fetches in parallel, normalizes/merges, and returns structured "
                "JSON with provenance. Authenticate with the `X-API-Key` header."
            )
        },
        "security": [{"ApiKeyAuth": []}],
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"}
            }
        },
    }

    # --- Auth (stateless) ---
    # Comma-separated accepted API keys. Empty => open mode (no auth required).
    API_KEYS = _csv_set("API_KEYS")

    # --- CORS (optional; only needed for cross-origin dev) ---
    CORS_ORIGINS = _csv_list("CORS_ORIGINS")

    # --- Cache (in-memory only; ephemeral, not a datastore) ---
    CACHE_TYPE = "SimpleCache"
    CACHE_DEFAULT_TIMEOUT = _int("CACHE_DEFAULT_TIMEOUT", 300)
    STALE_CACHE_TIMEOUT = _int("STALE_CACHE_TIMEOUT", 7 * 24 * 3600)

    # --- Rate limiting (Flask-Limiter; in-memory, best-effort) ---
    RATELIMIT_STORAGE_URI = "memory://"
    RATELIMIT_DEFAULT = os.getenv("RATELIMIT_DEFAULT", "120/minute")
    RATELIMIT_HEADERS_ENABLED = True

    # --- Engine / outbound HTTP (resilience knobs) ---
    HTTP_TIMEOUT = _float("HTTP_TIMEOUT", 8.0)
    FANOUT_DEADLINE = _float("FANOUT_DEADLINE", 12.0)
    MAX_CONNECTORS_PER_INTENT = _int("MAX_CONNECTORS_PER_INTENT", 4)
    HTTP_MAX_RETRIES = _int("HTTP_MAX_RETRIES", 3)
    BREAKER_FAIL_MAX = _int("BREAKER_FAIL_MAX", 5)
    BREAKER_RESET_TIMEOUT = _int("BREAKER_RESET_TIMEOUT", 60)
    USER_AGENT = os.getenv("USER_AGENT", "research-engine-api/0.1 (+you@example.com)")

    # Connectors to skip (e.g. bulk-dataset sources unfit for serverless cold starts).
    DISABLED_CONNECTORS = _csv_set("DISABLED_CONNECTORS")

    # --- Source credentials (optional) ---
    SOURCE_CREDS = {
        "stackexchange_key": os.getenv("STACKEXCHANGE_KEY"),
        "github_token": os.getenv("GITHUB_TOKEN"),
        "nvd_api_key": os.getenv("NVD_API_KEY"),
        "semantic_scholar_key": os.getenv("SEMANTIC_SCHOLAR_KEY"),
    }


class TestConfig(Config):
    TESTING = True
    API_KEYS = frozenset({"test-key"})
    CORS_ORIGINS: list[str] = []
    DISABLED_CONNECTORS = frozenset()
    RATELIMIT_ENABLED = False
    HTTP_TIMEOUT = 2.0
    FANOUT_DEADLINE = 4.0
    HTTP_MAX_RETRIES = 2  # keep retry-backoff sleeps short in tests
