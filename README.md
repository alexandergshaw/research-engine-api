# Research Engine API

A **source-agnostic, no-LLM knowledge-retrieval engine**. A calling app declares *what knowledge
it needs* (an **intent** + params); the engine decides **where** to find it, fetches from reputable
sources in parallel, normalizes/merges the results, and returns structured JSON with provenance.
A separate downstream service consumes that JSON to populate files (slides, resumes, cover letters,
anything).

There is **no LLM** anywhere — only deterministic HTTP retrieval, parsing, RAKE keyword extraction,
and fuzzy matching. The service is **stateless** (no database) — it deploys as a single Vercel
project that serves both the API and a dev console.

## Features

- **Intent-driven, source-agnostic** — callers ask for a *kind of knowledge*, not a source.
- **Resilient** — per-source timeouts, retries, `pybreaker` circuit breakers, concurrent fan-out
  with a deadline, in-memory cache with stale-on-error, graceful `degraded`/`warnings` results.
- **9 connectors across 6 domains** — general reference, programming, cybersecurity, academic,
  companies, occupations. Adding a source touches no core code.
- **Stateless** — no database, no Redis. Auth is a static API key via env; logs go to stdout.
- **Composable** — a `compose.slide_outline` intent orchestrates several sources into a slide-ready
  payload; per-intent normalizers shape merged data.
- **Orchestrator-friendly** — `POST /v1/research/batch` (≤20, order-preserving, failure-isolated),
  ready-to-render `attribution` per source + `attribution_required`, deterministic `ETag`/`meta.version`,
  and a machine-detectable `source_disabled` signal.
- **Dev console** — a zero-build static UI to drive the engine, deployed alongside the API.

See [docs/API_SPEC.md](docs/API_SPEC.md) for the full integration contract.

## How it works

```
intent + params  ──►  router (scores connectors)  ──►  parallel fan-out (deadline)
                                                          │   each source: timeout,
                                                          │   retry, circuit breaker
                                                          ▼
                       structured JSON  ◄──  aggregator (merge, dedup, provenance)
                       + in-memory cache (stale-on-error)
```

- **Intents** (`app/core/intents.py`) are the public contract — decoupled from sources.
- **Connectors** (`app/connectors/`) adapt one source each and self-register.
- **Resilience** lives in `app/core/http.py` and `app/core/engine.py`.

## Quickstart

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows;  source .venv/bin/activate on macOS/Linux
pip install -e ".[dev]"
copy .env.example .env            # cp on macOS/Linux — set a real USER_AGENT contact

flask --app wsgi genkey           # prints an API key; put it in API_KEYS (or leave unset = open)
$env:API_KEYS="rek_…"             # Windows;  export API_KEYS=rek_… on macOS/Linux
flask --app wsgi run              # http://127.0.0.1:5000  (Swagger UI at /docs)
```

Auth: requests need an `X-API-Key` header matching one of the comma-separated keys in `API_KEYS`.
If `API_KEYS` is unset, the API runs **open** (no key) — fine for local/preview, not for public.

## Dev console

A zero-build static console lives in `console/` and ships in the same deployment. It lists the
intents (`GET /v1/intents`), builds a params form, runs everything through `POST /v1/research`, and
renders sources/licenses, the degraded/warnings banner, and a slide-outline preview.

- **On Vercel** it's served at `/` (same origin as the API — no CORS, no config needed).
- **Locally** run `vercel dev` (serves console + API together), or open `console/index.html` and set
  the API base URL + key in the top bar (set `CORS_ORIGINS` if cross-origin).

## Endpoints

Every endpoint except `/v1/health` and `/v1/ready` requires an `X-API-Key` (when `API_KEYS` is set).

| Method | Path | Intent |
|---|---|---|
| GET  | `/v1/health` · `/v1/ready` · `/v1/version` | liveness · source health + disablement · contract version |
| GET  | `/v1/intents` | list intents + serving sources |
| POST | `/v1/research` | any intent — body `{"intent": "...", "params": {...}}` |
| POST | `/v1/research/batch` | up to 20 intents in one call — `{"requests":[…]}`, results in order |
| GET  | `/v1/concepts/{term}/(overview|definition|examples)` | `concept.*` |
| GET  | `/v1/security/vulnerabilities?product=` · `/v1/security/techniques?query=` | `security.*` |
| GET  | `/v1/academic/papers?query=` | `academic.papers` |
| GET  | `/v1/companies/{name}/profile` | `company.profile` |
| GET  | `/v1/roles/{title}/responsibilities` | `role.responsibilities` |
| GET  | `/v1/compose/slide-outline?topic=` | `compose.slide_outline` (composite) |

### Try it

```bash
KEY=rek_...
curl -X POST http://127.0.0.1:5000/v1/research -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"intent": "company.profile", "params": {"name": "Microsoft"}}'

curl -H "X-API-Key: $KEY" http://127.0.0.1:5000/v1/concepts/asyncio/examples
curl -H "X-API-Key: $KEY" "http://127.0.0.1:5000/v1/security/vulnerabilities?product=openssl"
curl -H "X-API-Key: $KEY" "http://127.0.0.1:5000/v1/compose/slide-outline?topic=TLS"
```

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

## Connectors (sources)

| Domain | Connector | Intents served |
|---|---|---|
| General reference | Wikipedia, Wikidata | `concept.overview`, `concept.definition`, `entity.facts` |
| Programming | Stack Exchange, GitHub | `concept.examples` |
| Cybersecurity | NVD/CVE, MITRE ATT&CK | `security.vulnerabilities`, `security.techniques` |
| Academic / STEM | arXiv | `academic.papers` |
| Companies | SEC EDGAR (+ Wikidata facts) | `company.profile` |
| Occupations | ESCO | `role.responsibilities` |
| News | GDELT | `company.news` (headline + link + metadata, deterministic tone filter) |

**Adding a source:** drop an `@register` `Connector` subclass in `app/connectors/`, declare its
intents, list it in `app/connectors/__init__.py`. The router discovers it automatically.

## Configuration

Env-driven; everything has a sane default. Full list in [`.env.example`](.env.example).

| Variable | Default | Purpose |
|---|---|---|
| `API_KEYS` | _(empty → open)_ | Comma-separated accepted API keys (`X-API-Key`). |
| `USER_AGENT` | `research-engine-api/0.1 (+you@example.com)` | **Required** by Wikipedia & SEC. |
| `DISABLED_CONNECTORS` | _(none)_ | Connectors to skip (e.g. `mitre_attack` on serverless). |
| `CORS_ORIGINS` | _(none)_ | Allowed origins for cross-origin dev (csv). Unneeded same-origin. |
| `RATELIMIT_DEFAULT` | `120/minute` | Per-key in-memory rate limit (best-effort). |
| `HTTP_TIMEOUT` · `FANOUT_DEADLINE` | `8.0` · `12.0` | Per-request timeout · whole-request budget. |
| `SECRET_KEY` | `dev-secret` | Flask secret — change in production. |

Optional source credentials (raise upstream quotas; degrade gracefully without): `STACKEXCHANGE_KEY`,
`GITHUB_TOKEN`, `NVD_API_KEY`, `SEMANTIC_SCHOLAR_KEY`.

## Project layout

```
api/index.py         # Vercel serverless entrypoint (exposes the WSGI app)
vercel.json          # routes: console at /, API at /v1
console/             # zero-build static dev console (index.html, app.js, styles.css)
app/
  __init__.py        # app factory (stateless)
  config.py          # env-driven config
  observability.py   # structlog request logging
  api/v1/            # endpoints (thin wrappers over intents)
  auth/              # env-key auth + genkey CLI
  core/              # http (resilience), router, aggregator, engine, intents, compose, cache
  connectors/        # one module per source (self-registering)
  processing/        # no-LLM text utils (RAKE keyword extraction)
tests/               # pytest (+ opt-in live suite)
```

## Testing

```bash
pytest                         # mocked upstreams (no network)
pytest --run-live -m live      # opt-in: hits real sources
ruff check .
```

## Deployment

### Vercel (primary — one deployable, no services to provision)

1. Import the GitHub repo as a Vercel project (`vercel.json` configures the rest).
2. Set env vars: `API_KEYS` (from `flask genkey`), `USER_AGENT`, `SECRET_KEY`,
   `DISABLED_CONNECTORS=mitre_attack`.
3. Push to GitHub → Vercel builds and serves the console at `/` and the API at `/v1/*`. No database,
   no Redis. Pushes auto-deploy.

> MITRE ATT&CK is disabled on Vercel — its 35 MB bulk dataset relies on an in-process cache that
> can't survive serverless cold starts. It stays fully functional when self-hosted.

### Self-host (always-on, all connectors)

```bash
docker compose up --build      # gunicorn on :8000
```

A stateless container; set `API_KEYS`/`USER_AGENT` via env. Best for heavy traffic or to keep MITRE.

## Roadmap

Optional: more connectors (Semantic Scholar; O*NET as a credentialed alternative to ESCO),
HTML article extraction, and richer per-intent normalizers.
