# Research Engine API

A **source-agnostic, no-LLM knowledge-retrieval engine**. A calling app declares *what knowledge
it needs* (an **intent** + params); the engine decides **where** to find it, fetches from reputable
sources in parallel, normalizes/merges the results, and returns structured JSON with provenance.
A separate downstream service consumes that JSON to populate files (slides, resumes, cover letters,
anything).

There is **no LLM** anywhere — only deterministic HTTP retrieval, parsing, RAKE keyword extraction,
and fuzzy matching.

## Features

- **Intent-driven, source-agnostic** — callers ask for a *kind of knowledge*, not a source. The
  router picks the best connectors per intent.
- **Resilient by design** — per-source timeouts, retries with backoff, `pybreaker` circuit breakers,
  concurrent fan-out with a wall-clock deadline, a two-tier cache with stale-on-error fallback, and
  graceful `degraded`/`warnings` partial results.
- **9 connectors across 6 domains** — general reference, programming, cybersecurity, academic,
  companies, and occupations. Adding a source touches no core code.
- **Multi-tenant** — hashed API keys, per-tenant rate limits, per-request usage logging, admin CLI.
- **Composable** — a `compose.slide_outline` intent orchestrates several sources into a slide-ready
  payload; per-intent normalizers shape merged data.
- **Operable** — OpenAPI/Swagger docs, structured JSON request logging (structlog), Alembic
  migrations, and a Docker/compose deploy path with Redis + Postgres.

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
- **Resilience** lives in `app/core/http.py` and `app/core/engine.py`.

## Quickstart

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows;  source .venv/bin/activate on macOS/Linux
pip install -e ".[dev]"
copy .env.example .env            # cp on macOS/Linux — then set a real USER_AGENT contact

flask --app wsgi db upgrade       # create tables (or: flask init-db)
flask --app wsgi tenant create acme --rate-limit "120/minute"
flask --app wsgi key mint acme    # prints the API key once — copy it

flask --app wsgi run              # http://127.0.0.1:5000  (Swagger UI at /docs)
```

## Endpoints

Every endpoint except `/v1/health` and `/v1/ready` requires an `X-API-Key` header.

| Method | Path | Intent |
|---|---|---|
| GET  | `/v1/health` | — (liveness) |
| GET  | `/v1/ready` | — (per-source breaker health) |
| GET  | `/v1/intents` | list intents + which sources serve each |
| POST | `/v1/research` | any intent — body `{"intent": "...", "params": {...}}` |
| GET  | `/v1/concepts/{term}/overview` | `concept.overview` |
| GET  | `/v1/concepts/{term}/definition` | `concept.definition` |
| GET  | `/v1/concepts/{term}/examples` | `concept.examples` |
| GET  | `/v1/security/vulnerabilities?product=` | `security.vulnerabilities` |
| GET  | `/v1/security/techniques?query=` | `security.techniques` |
| GET  | `/v1/academic/papers?query=` | `academic.papers` |
| GET  | `/v1/companies/{name}/profile` | `company.profile` |
| GET  | `/v1/roles/{title}/responsibilities` | `role.responsibilities` |
| GET  | `/v1/compose/slide-outline?topic=` | `compose.slide_outline` (composite) |

### Try it

```bash
KEY=rek_...                          # the minted key

# Generic intent endpoint
curl -X POST http://127.0.0.1:5000/v1/research -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"intent": "company.profile", "params": {"name": "Apple Inc"}}'

# Topic research (slideshows)
curl -H "X-API-Key: $KEY" http://127.0.0.1:5000/v1/concepts/RSA/overview
curl -H "X-API-Key: $KEY" http://127.0.0.1:5000/v1/concepts/asyncio/examples
curl -H "X-API-Key: $KEY" "http://127.0.0.1:5000/v1/security/vulnerabilities?product=openssl"
curl -H "X-API-Key: $KEY" "http://127.0.0.1:5000/v1/security/techniques?query=phishing"
curl -H "X-API-Key: $KEY" "http://127.0.0.1:5000/v1/academic/papers?query=transformers"

# Resume/cover-letter (company stats + position duties)
curl -H "X-API-Key: $KEY" http://127.0.0.1:5000/v1/companies/MSFT/profile
curl -H "X-API-Key: $KEY" "http://127.0.0.1:5000/v1/roles/data%20scientist/responsibilities"

# Composite: slide-ready outline
curl -H "X-API-Key: $KEY" "http://127.0.0.1:5000/v1/compose/slide-outline?topic=TLS"
```

## Response envelope

Every research endpoint returns the same shape:

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

`degraded` is `true` when some (but not all) sources failed; `warnings` explains what was lost.
`sources` always carries provenance (name, URL, retrieval time, license).

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

**Adding a source:** drop an `@register` `Connector` subclass in `app/connectors/`, declare the
intents it serves, and list it in `app/connectors/__init__.py`. The router discovers it
automatically — no core changes.

## Configuration

Env-driven (12-factor); everything has a sane default. Full list in [`.env.example`](.env.example).

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///research_engine.db` | Tenants, API keys, usage logs. Use `postgresql+psycopg://...` in prod. |
| `REDIS_URL` | _(unset → in-memory)_ | Backs cache + rate limiting when set. |
| `RATELIMIT_DEFAULT` | `120/minute` | Per-key limit when a tenant has no explicit plan. |
| `USER_AGENT` | `research-engine-api/0.1 (+you@example.com)` | **Required** by Wikipedia & SEC — set a real contact. |
| `HTTP_TIMEOUT` | `8.0` | Per-request timeout (seconds). |
| `FANOUT_DEADLINE` | `12.0` | Wall-clock budget for a whole multi-source request. |
| `BREAKER_FAIL_MAX` / `BREAKER_RESET_TIMEOUT` | `5` / `60` | Circuit-breaker thresholds. |
| `SECRET_KEY` | `dev-secret` | Flask secret — change in production. |

Optional **source credentials** (raise upstream quotas; the engine degrades gracefully without
them): `STACKEXCHANGE_KEY`, `GITHUB_TOKEN`, `NVD_API_KEY`, `SEMANTIC_SCHOLAR_KEY`,
`ONET_USERNAME`/`ONET_PASSWORD`.

## Project layout

```
app/
  __init__.py        # app factory
  config.py          # env-driven config
  extensions.py      # db, cache, limiter, smorest Api
  observability.py   # structlog request logging
  api/v1/            # endpoints (thin wrappers over intents)
  auth/              # tenants, hashed API keys, usage logging, admin CLI
  core/              # http (resilience), router, aggregator, engine, intents, compose, cache
  connectors/        # one module per source (self-registering)
  processing/        # no-LLM text utils (RAKE keyword extraction)
migrations/          # Alembic
tests/               # pytest (+ opt-in live suite)
```

## Testing

```bash
pytest                         # mocked upstreams (no network)
pytest --run-live -m live      # opt-in: hits real sources
ruff check .
```

## Deployment

For a production-shaped stack (gunicorn + Postgres + Redis):

```bash
docker compose up --build      # api on :8000, runs migrations on start
```

- Set `REDIS_URL` to move cache + rate-limiting onto Redis; `DATABASE_URL` to a Postgres DSN. With
  neither set, the app runs on SQLite + in-memory (dev).
- Requests are logged as structured JSON via structlog (`FLASK_DEBUG=1` → human-readable console).

## Roadmap

Optional, non-blocking enhancements: more connectors (Semantic Scholar; O*NET as a credentialed
alternative to ESCO), HTML article extraction for any future scraping connector, and richer
per-intent normalizers.
