# Research Engine API

A **source-agnostic, no-LLM knowledge-retrieval engine**. A calling app declares *what
knowledge it needs* (an **intent** + params); the engine decides **where** to find it, fetches
from reputable sources in parallel, normalizes/merges the results, and returns structured JSON
with provenance. A separate downstream service consumes that JSON to populate files (slides,
resumes, cover letters, anything).

There is **no LLM** anywhere — only deterministic HTTP retrieval, parsing, keyword extraction,
and fuzzy matching.

## Quickstart

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows;  source .venv/bin/activate on macOS/Linux
pip install -e ".[dev]"
copy .env.example .env            # cp on macOS/Linux — then set a real USER_AGENT contact

flask --app wsgi run              # http://127.0.0.1:5000
```

Swagger UI: <http://127.0.0.1:5000/docs>

Every endpoint except `/v1/health` and `/v1/ready` needs an `X-API-Key`. Mint one:

```bash
flask --app wsgi db upgrade          # create tables (or: flask init-db)
flask --app wsgi tenant create acme --rate-limit "120/minute"
flask --app wsgi key mint acme       # prints the key once
```

### Try it

```bash
KEY=rek_...                          # the minted key

# Generic intent endpoint
curl -X POST http://127.0.0.1:5000/v1/research -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"intent": "company.profile", "params": {"name": "Apple Inc"}}'

# Granular wrappers
curl -H "X-API-Key: $KEY" http://127.0.0.1:5000/v1/concepts/RSA/overview
curl -H "X-API-Key: $KEY" http://127.0.0.1:5000/v1/concepts/asyncio/examples
curl -H "X-API-Key: $KEY" "http://127.0.0.1:5000/v1/security/vulnerabilities?product=openssl"
curl -H "X-API-Key: $KEY" "http://127.0.0.1:5000/v1/security/techniques?query=phishing"
curl -H "X-API-Key: $KEY" "http://127.0.0.1:5000/v1/academic/papers?query=transformers"

# Resume/cover-letter use case: company stats + position duties
curl -H "X-API-Key: $KEY" http://127.0.0.1:5000/v1/companies/MSFT/profile
curl -H "X-API-Key: $KEY" "http://127.0.0.1:5000/v1/roles/data%20scientist/responsibilities"

# Composite: slide-ready outline (the 'populate a slideshow' use case)
curl -H "X-API-Key: $KEY" "http://127.0.0.1:5000/v1/compose/slide-outline?topic=TLS"

# What can it do?
curl -H "X-API-Key: $KEY" http://127.0.0.1:5000/v1/intents
```

## How it works

```
intent + params  ──►  router (scores connectors)  ──►  parallel fan-out (deadline)
                                                          │   each source: timeout,
                                                          │   retry, circuit breaker
                                                          ▼
                       structured JSON  ◄──  aggregator (merge, dedup, provenance)
                       + cache (stale-on-error fallback)
```

- **Intents** (`app/core/intents.py`) are the public contract — decoupled from sources.
- **Connectors** (`app/connectors/`) adapt one source each and self-register; adding a source
  touches no core code.
- **Resilience** (`app/core/http.py`, `engine.py`): per-source timeouts, `tenacity` retries,
  `pybreaker` circuit breakers, concurrent fan-out with a wall-clock deadline, two-tier cache
  with stale-on-error, and graceful `degraded`/`warnings` partial results.

## Response envelope

```json
{
  "intent": "concept.overview",
  "query": {"term": "TLS handshake"},
  "data": { "...": "intent-specific structured fields" },
  "sources": [{"name": "wikipedia", "url": "...", "retrieved_at": "...", "license": "CC BY-SA 4.0"}],
  "degraded": false,
  "warnings": [],
  "cache": {"hit": false, "age_s": null}
}
```

## Testing

```bash
pytest                         # mocked upstreams (no network)
pytest --run-live -m live      # opt-in: hits real sources
ruff check .
```

## Deployment

Env-driven (12-factor). For a production-shaped stack (gunicorn + Postgres + Redis):

```bash
docker compose up --build      # api on :8000, runs migrations on start
```

- Set `REDIS_URL` to move cache + rate-limiting onto Redis; `DATABASE_URL` to a Postgres DSN
  (`postgresql+psycopg://...`). With neither set, the app runs on SQLite + in-memory (dev).
- Requests are logged as structured JSON via structlog (`FLASK_DEBUG=1` → human-readable console).

## Connectors (sources)

| Domain | Connector | Intents served |
|---|---|---|
| General reference | Wikipedia, Wikidata | `concept.overview`, `concept.definition`, `entity.facts` |
| Programming | Stack Exchange, GitHub | `concept.examples` |
| Cybersecurity | NVD/CVE, MITRE ATT&CK | `security.vulnerabilities`, `security.techniques` |
| Academic / STEM | arXiv | `academic.papers` |
| Companies | SEC EDGAR (+ Wikidata facts) | `company.profile` |
| Occupations | ESCO | `role.responsibilities` |

`company.profile` uses SEC EDGAR as the authoritative source and only enriches with Wikidata's
structured *facts* (founding, employees, revenue). Wikidata facts are best-effort: pass a company
**name** (not just a ticker) for the most reliable enrichment.

Adding a source = drop an `@register` class in `app/connectors/` and list it in
`app/connectors/__init__.py`. The router discovers it automatically.

## Status

- **Phase 1 — scaffold**: app factory, config, OpenAPI/Swagger, Docker. ✅
- **Phase 2 — resilient core**: HTTP client (timeouts/retries/breakers), router, aggregator,
  two-tier cache with stale-on-error, generic `/v1/research`. ✅
- **Phase 3 — multi-tenancy**: tenants, hashed API keys, per-tenant rate limiting, usage logging,
  Alembic migrations, admin CLI. ✅
- **Phase 4 — domains**: 9 connectors across 6 domains + granular endpoints
  (`concepts`, `security`, `academic`, `companies`, `roles`). ✅
- **Phase 5 — composition + processing**: composite `compose.slide_outline` intent, per-intent
  normalizers, and RAKE keyword extraction (a `key_terms` slide). ✅
- **Phase 6 — hardening**: structlog JSON request logging, Redis/Postgres prod backends +
  docker-compose, opt-in live-source test suite (`--run-live`). ✅

Future: more connectors (Semantic Scholar, O*NET as a credentialed alternative to ESCO) and HTML
article extraction (for any future scraping connector).
