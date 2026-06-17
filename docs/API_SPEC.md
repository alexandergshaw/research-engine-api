# Research Engine API — Integration Spec

Version: `v1` · Response contract `1.1.0` · Stateless · No-LLM · JSON over HTTPS

This document is the integration contract: base URL, auth, the universal response envelope, error
semantics, the full intent catalog, and the **exact `data` shape returned per intent**. It is the
source of truth for wiring the engine into another system.

---

## 1. Basics

| | |
|---|---|
| Base URL | `https://<your-vercel-project>.vercel.app` (or your self-host origin) |
| Version prefix | `/v1` |
| Transport | HTTPS, `Content-Type: application/json` |
| Auth | `X-API-Key: <key>` header (see §3). Omit only if the server runs in open mode. |
| Machine-readable schema | `GET /openapi.json` (OpenAPI 3.0.3) · Swagger UI at `/docs` |
| Determinism | No LLM. Same inputs → same outputs (modulo upstream-source changes). |

The API is **read-only and side-effect-free** — every call is safe to retry. There is no persistence;
nothing you send is stored.

---

## 2. Core model

A caller sends an **intent** (a *kind of knowledge*, e.g. `company.profile`) plus **params**. The
engine routes to one or more reputable sources, fetches them in parallel, merges the results, and
returns a single envelope with provenance. Two ways to call:

- **Generic:** `POST /v1/research` with `{"intent": "...", "params": {...}}` — covers every intent.
- **Granular wrappers:** convenience GET routes (e.g. `/v1/companies/{name}/profile`) that map 1:1
  to an intent. Same envelope.

Prefer the **generic endpoint** for programmatic integration: one code path, discoverable via
`GET /v1/intents`.

---

## 3. Authentication

- Send `X-API-Key: <key>`. Accepted keys are configured server-side (the `API_KEYS` env, comma-
  separated). Keys are compared in constant time.
- If the server has no keys configured it runs **open** (no header required) — intended for
  local/preview only.
- `GET /v1/health` and `GET /v1/ready` never require a key.
- Missing/invalid key → **401** `{"code":401,"status":"Unauthorized","message":"missing or invalid X-API-Key"}`.

---

## 4. The response envelope (every research endpoint)

```jsonc
{
  "intent": "concept.overview",         // echoed intent
  "query":  { "term": "TLS handshake" },// echoed params
  "data":   { /* intent-specific, see §8 */ },
  "sources": [                          // provenance — always present
    { "name": "wikipedia", "url": "https://en.wikipedia.org/wiki/TLS",
      "retrieved_at": "2026-06-16T13:29:36Z", "license": "CC BY-SA 4.0",
      "attribution": "Wikipedia — CC BY-SA 4.0 — https://en.wikipedia.org/wiki/TLS" }
  ],
  "degraded": false,                    // true if SOME sources failed but others succeeded
  "warnings": [],                       // human-readable notes (failed sources, "no data", stale)
  "attribution_required": true,         // true if ANY source license requires attribution
  "cache":   { "hit": false, "age_s": null },  // age_s set when hit=true
  "meta":    { "version": "1.1.0" }     // response-contract version (also in the ETag)
}
```

Integration rules:

- **Always read `degraded` and `warnings`.** A `200` can be a *partial* result (one source failed)
  or carry **no data**: when nothing matched, `data` is `{}`, `degraded` is `false`, and
  `warnings` contains `"no data found for query"`. Treat empty `data` as "not found", not an error.
- **Attribution is ready-to-render.** Each `sources[]` entry includes a preformatted `attribution`
  string ("Display — License — URL"). If `attribution_required` is `true`, display every source's
  `attribution` (only public-domain / CC0 sources are exempt). You never need to parse license codes.
- `cache.hit=true` means a recent identical `(intent, params)` was served from an in-memory cache
  (default TTL ~300 s, per server instance; ephemeral on serverless).
- `meta.version` is the response-contract version; it is folded into the `ETag` (§6).

---

## 5. Error model & status codes

Errors are JSON: `{"code": <int>, "status": "<reason>", "message": "<text>", "errors": <optional>}`.

| Status | When | Retry? |
|---|---|---|
| `200` | Success — **including** `degraded` results and empty `data` ("no data found") | — |
| `401` | Missing/invalid `X-API-Key` | No (fix the key) |
| `422` | Unknown intent, or missing required param, or malformed body | No (fix the request) |
| `429` | Rate limit exceeded — includes `Retry-After` header | Yes, after delay |
| `501` | Known intent but no enabled source can serve it (e.g. connector disabled) | No |
| `502` | Every source for the intent failed and no stale cache was available | Yes (transient) |

`422` from request-body validation (smorest) puts field detail under `errors`, e.g.
`{"code":422,"errors":{"json":{"intent":["Missing data for required field."]}}}`.

**Source disabled (machine-detectable).** When a *known* intent's only source is disabled in this
deployment, the `501` carries a structured body so you can branch without reading docs:
```json
{ "detail": "intent 'security.techniques' is unavailable: source(s) disabled in this deployment",
  "code": "source_disabled", "disabled_sources": ["mitre_attack"] }
```
The same disablement is reflected in `GET /v1/ready` (§9). A generic `501` (no source exists at all)
does **not** carry `code: "source_disabled"`.

---

## 6. Rate limiting

- Best-effort, keyed by API key. Default **120 requests/minute** (server-configurable via
  `RATELIMIT_DEFAULT`).
- Responses include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`; `429`
  responses include `Retry-After`.
- On serverless the limiter is per-instance and therefore approximate — do not rely on it as a hard
  quota; implement client-side backoff on `429`.
- **Batch cost:** `POST /v1/research/batch` consumes **one unit per sub-request** (a batch of 8 costs
  8). Size batches with the per-minute limit in mind.

### Caching & ETags
Single-result research responses set `Cache-Control: public, max-age=<cache TTL>` and a strong
`ETag = "sha256(intent + normalized params + meta.version)"`. The ETag is **deterministic** for
identical inputs (it does not depend on the upstream payload), so gateways/CDNs key uniformly; a
contract-version bump rotates every ETag. The batch endpoint is a POST aggregation and is returned
`Cache-Control: no-store`.

---

## 7. Endpoints

### Discovery / health
| Method | Path | Auth | Returns |
|---|---|---|---|
| GET | `/v1/health` | no | `{"status":"ok","version":"v1"}` |
| GET | `/v1/version` | no | `{"version":"1.1.0","api":"v1"}` — response-contract version |
| GET | `/v1/ready` | no | per-source breaker health + disablement (see §9) |
| GET | `/v1/intents` | yes | array of intent specs (name, description, accepts, optional, composite, sources) |

### Research (all return the §4 envelope)
| Method | Path | Maps to intent | Params |
|---|---|---|---|
| POST | `/v1/research` | *any* | body `{"intent","params"}` |
| POST | `/v1/research/batch` | *any* (1–20) | body `{"requests":[{"intent","params"},…]}` (see §7.1) |
| GET | `/v1/concepts/{term}/overview` | `concept.overview` | path `term` |
| GET | `/v1/concepts/{term}/definition` | `concept.definition` | path `term` |
| GET | `/v1/concepts/{term}/examples` | `concept.examples` | path `term` |
| GET | `/v1/security/vulnerabilities` | `security.vulnerabilities` | query `product` (req), `limit` (def 5) |
| GET | `/v1/security/techniques` | `security.techniques` | query `query` (req), `limit` (def 8) |
| GET | `/v1/academic/papers` | `academic.papers` | query `query` (req), `limit` (def 5) |
| GET | `/v1/companies/{name}/profile` | `company.profile` | path `name` (name or ticker) |
| GET | `/v1/roles/{title}/responsibilities` | `role.responsibilities` | path `title` |
| GET | `/v1/compose/slide-outline` | `compose.slide_outline` | query `topic` (req) |
| POST | `/v1/jobs/postings` | `feed.poll` | body `{"source",…}` — caller-supplied source (see §8) |

> Granular `concepts.*` wrappers pass only the path `term`. To pass `limit`/`language`/`tag`, use
> `POST /v1/research`.

### 7.1 Batch — `POST /v1/research/batch`

Run up to **20** requests in one call to cut fan-out and rate-limit pressure.

```jsonc
// request
{ "requests": [
    { "intent": "company.profile",      "params": { "name": "Microsoft" } },
    { "intent": "security.vulnerabilities", "params": { "product": "openssl" } }
] }
// response — results in the SAME order, each a full §4 envelope
{ "results": [ { /* envelope */ }, { /* envelope */ } ] }
```

Semantics:
- **Isolation:** a sub-request that fails/degrades/returns-empty never fails the batch. Each result
  carries its own `degraded`/`warnings`/`cache`/`meta`. A sub-request error becomes a `degraded`
  envelope with the reason in `warnings` (e.g. `"source_disabled: …"`, `"error: unknown intent …"`).
- **Order preserved:** `results[i]` corresponds to `requests[i]`.
- **Cost:** one rate-limit unit per sub-request (§6).
- **`422` only** if the batch envelope itself is malformed or exceeds 20 items — never for an
  individual sub-request's content.

---

## 8. Intent catalog + exact `data` shapes

Each intent accepts one of several **identifier param aliases** (any one is required). `limit` (where
noted) caps result counts. `data` shapes below are exactly what the engine returns; absent/empty
values are omitted.

### `concept.overview` — sources: wikipedia (+ wikidata augment)
Params: one of `term` | `topic` | `query`.
```jsonc
"data": {
  "title": "Transport Layer Security",
  "summary": "TLS is a cryptographic protocol …",
  "description": "cryptographic protocol",
  "thumbnail": "https://…png",          // may be null/absent
  "url": "https://en.wikipedia.org/wiki/Transport_Layer_Security",
  "wikidata_id": "Q…",                  // from wikidata, if matched
  "label": "…", "aliases": ["…"],       // from wikidata
  "facts": { "inception": "1999-01-01T00:00:00Z", "official_website": "https://…" }
}
```

### `concept.definition` — sources: wikipedia
Params: one of `term` | `query`.
```jsonc
"data": { "term": "RSA", "definition": "RSA is a public-key cryptosystem …" }
```

### `concept.examples` — sources: stackexchange + github
Params: one of `term` | `topic` | `query`. Optional: `language`/`tag`, `limit` (≤20).
```jsonc
"data": {
  "questions": [
    { "title": "How does the TLS handshake work?", "url": "https://stackoverflow.com/q/…",
      "score": 42, "is_answered": true, "answer_count": 3, "tags": ["tls","security"] }
  ],
  "site": "stackoverflow",
  "repositories": [
    { "name": "owner/repo", "url": "https://github.com/owner/repo",
      "description": "…", "stars": 39462, "language": "Rust" }
  ]
}
```

### `entity.facts` — sources: wikipedia + wikidata
Params: one of `name` | `term`.
```jsonc
"data": { "title": "…", "summary": "…", "description": "…", "url": "…",
          "wikidata_id": "Q…", "label": "…", "aliases": ["…"],
          "facts": { "inception": "…", "employees": "154000", "official_website": "…" } }
```

### `company.profile` — sources: sec_edgar (authoritative) + wikidata facts
Params: one of `name` | `ticker` | `term`. Normalizer: SEC fields win; only Wikidata `facts` merged.
```jsonc
"data": {
  "name": "MICROSOFT CORP", "ticker": "MSFT", "cik": "0000789019",
  "exchanges": ["Nasdaq"], "industry": "Services-Prepackaged Software", "sic": "7372",
  "entity_type": "operating", "fiscal_year_end": "0630", "state_of_incorporation": "WA",
  "headquarters": { "street": "ONE MICROSOFT WAY", "city": "REDMOND", "state": "WA", "zip": "98052-6399" },
  "facts": { "inception": "…", "employees": "…", "total_revenue": "…", "official_website": "…" }
}
```
Notes: SEC covers **US-listed** companies (resolved by ticker or name). For non-US/private names with
no SEC match, `data` falls back to Wikidata (`{wikidata_id,label,description,aliases,facts}`). Wikidata
`facts` are best-effort (fuzzy entity match) — most reliable when you pass a full **name**.

### `role.responsibilities` — sources: esco
Params: one of `title` | `term` | `query`.
```jsonc
"data": {
  "title": "data scientist",
  "description": "Data scientists find and interpret rich data sources …",
  "essential_skills": ["statistics", "query languages", "…"],   // up to 15
  "optional_skills": ["use Git", "…"],                          // up to 15
  "uri": "http://data.europa.eu/esco/occupation/…"
}
```

### `security.vulnerabilities` — sources: nvd
Params: one of `product` | `keyword` | `term` | `query`. Optional: `limit` (≤20, def 5).
```jsonc
"data": {
  "keyword": "openssl", "total": 1234,
  "cves": [
    { "id": "CVE-2022-0001", "description": "A flaw in openssl …", "published": "2022-01-01T00:00:00",
      "cvss": { "version": "3.1", "base_score": 7.5, "severity": "HIGH" },
      "references": ["https://…"] }
  ]
}
```

### `security.techniques` — sources: mitre_attack
Params: one of `technique` | `tactic` | `term` | `query` | `keyword`. Optional: `limit` (≤25, def 8).
> Disabled on the Vercel deployment (`DISABLED_CONNECTORS=mitre_attack`) → this intent returns
> **501** there. Available when self-hosted.
```jsonc
"data": {
  "query": "phishing",
  "techniques": [
    { "id": "T1566.001", "name": "Spearphishing Attachment", "tactics": ["initial-access"],
      "url": "https://attack.mitre.org/techniques/T1566/001", "description": "…(≤400 chars)" }
  ]
}
```

### `academic.papers` — sources: arxiv
Params: one of `query` | `term` | `topic`. Optional: `limit` (≤20, def 5).
```jsonc
"data": {
  "query": "transformer attention",
  "papers": [
    { "title": "Attention Is All You Need", "summary": "…", "url": "http://arxiv.org/abs/1706.03762",
      "published": "2017-06-12T00:00:00Z", "authors": ["Ashish Vaswani", "…"] }
  ]
}
```

### `company.news` — sources: gdelt  ·  **time-varying (not reproducible)**
Params: one of `name` | `ticker` | `query` | `term`. Optional: `limit` (1–25, def 10),
`since_days` (1–365, def 90), `min_tone` (float, def 0.0 — keep articles at/above this tone),
`sort` (`tone` default | `recency`). **Headline + link + metadata only — never body text.**
```jsonc
"data": {
  "company": "Acme",                  // echoed identifier
  "as_of": "2026-06-16",              // UTC date the query ran
  "articles": [
    { "title": "Acme wins record profit", "source": "reuters.com",
      "url": "https://reuters.com/…", "published": "2026-06-14T12:00:00Z",
      "tone": 4.0, "language": "en" }
  ]
}
```
Notes:
- **`tone` is deterministic** — computed from the headline via a small bundled lexicon (no LLM).
  It is the ranking key and the value you filter on with `min_tone`; "positive" is the caller's
  threshold, not an editorial judgement. Default sort is `tone` desc (recency tiebreak).
- **Volatile:** unlike other intents, results change over time. The response carries `data.as_of`,
  and the cache/ETag are keyed on the **UTC date** in addition to intent+params+version — so within
  a day the ETag is stable and repeats hit the cache, but it rotates daily. Do not treat results as
  reproducible across days.
- Empty result is a normal `200`: `data.articles: []` with `warnings: ["no news found for query"]`.
- Provenance: `sources[]` includes **GDELT** plus each **publisher domain**, each with an
  `attribution` string; `attribution_required` is `true`.
- If `gdelt` is disabled in the deployment, `company.news` returns the structured `501`
  `source_disabled` with `disabled_sources: ["gdelt"]` (see §5).

### `feed.poll` — sources: http_source (caller-supplied)  ·  **time-varying (not reproducible)**
An **incremental stream over a source you provide.** Instead of a built-in upstream, the caller
describes its *own* HTTP JSON source — where to fetch and how to read it — and the engine fetches it,
projects each record into a flat shape, and returns only the records **newer than the caller's
cursor**. You own the poll cadence: call once, or poll continuously by passing each response's
`data.cursor` back as `cursor`. The engine stays stateless — the cursor travels with you. Canonical
use case: job postings.

Params (body of `POST /v1/jobs/postings`, or `params` of `POST /v1/research`):

```jsonc
{
  "source": {
    "url": "https://boards.example.com/api/jobs",  // required, https (see SSRF note below)
    "method": "GET",                                 // GET (default) or POST
    "query":   { "team": "eng" },                    // optional querystring
    "headers": { "Authorization": "Bearer …" },      // optional; your source's auth — MASKED in the echoed query
    "body":    { "...": "..." },                     // optional JSON body (POST only)
    "items_path": "data.jobs",                       // dotted path to the records array (default: response root)
    "map": {                                         // target field <- dotted source path
      "id": "id", "title": "title", "company": "company.name",
      "location": "location.name", "url": "absolute_url",
      "posted_at": "updated_at", "tags": "keywords"
    },
    "cursor_field": "posted_at",                     // which MAPPED field is the high-water mark
    "cursor_type": "datetime",                       // datetime | epoch | number | string
    "license": "© Example Boards"                    // optional; sets sources[].attribution
  },
  "since":  "2026-06-17T08:00:00Z",                  // OR a raw high-water value to poll past
  "cursor": "<opaque token from a prior poll>",      // OR an opaque cursor (takes precedence over `since`)
  "limit":  50                                       // 1–200, default 50
}
```

```jsonc
"data": {
  "source": "boards.example.com",     // resolved host
  "as_of":  "2026-06-17",             // UTC date the poll ran
  "postings": [                       // newest-first by cursor_field; keys follow your `map`
    { "id": "a1b2c3d4e5f6a7b8", "title": "Senior Engineer", "company": "Acme",
      "location": "Remote", "url": "https://…", "posted_at": "2026-06-17T09:42:00Z",
      "tags": ["python","backend"] }
  ],
  "cursor": "eyJ2IjoiMjAyNi0wNi0xN1Q…",  // opaque high-water cursor; pass back as `cursor` next poll
  "count": 1,
  "has_more": false                   // upstream had more than `limit` new items this poll
}
```
Notes:
- **Incremental & stateless.** With a `cursor_field` set, only records strictly newer than `since`/
  `cursor` are returned, and `data.cursor` is the new high-water mark. With nothing new, `postings`
  is `[]`, `data.cursor` **echoes** the supplied cursor (so you can keep polling), and `warnings`
  contains `"no new items since cursor"`. Omit `cursor_field` for a full (non-incremental) fetch each
  poll (`data.cursor` is `null`).
- **`id` for dedup.** If your `map` doesn't produce an `id`, one is derived deterministically from the
  source host + item url/title, so overlapping poll windows are safe to dedup client-side.
- **Volatile:** like `company.news`, results change over time; `data.as_of` is set and the cache/ETag
  are keyed on the UTC date too. Not reproducible across days.
- **Provenance:** `sources[]` carries the resolved host (with your optional `license` →
  `attribution`). No source content is stored; the engine is a pass-through.
- **Security (caller-controlled URL).** The URL is fetched server-side, so it is SSRF-guarded:
  **https-only** and **private/loopback/link-local/cloud-metadata targets are blocked** by default,
  redirects are **not** followed, and the response is size-capped. A deployment may pin fetching to an
  allowlist of hosts (`DYNAMIC_SOURCE_ALLOWLIST`) or disable the source entirely
  (`DISABLED_CONNECTORS=http_source` → `501 source_disabled`). A blocked URL or malformed `source`
  spec is a **422** (client error), not a 502. Your `source.headers` are never logged or echoed back.

### `compose.slide_outline` — composite (overview + examples + papers)
Params: one of `topic` | `term` | `query`. Orchestrates sub-intents; partial sub-failures appear in
`warnings` (not `degraded`). `data.slides` is an ordered list of typed slide objects:
```jsonc
"data": {
  "topic": "RSA encryption",
  "slide_count": 6,
  "slides": [
    { "type": "title",      "title": "RSA", "subtitle": "public-key cryptosystem" },
    { "type": "overview",   "title": "Overview", "bullets": ["…", "…"] },
    { "type": "key_terms",  "title": "Key terms", "items": ["digital signature", "…"] },
    { "type": "key_facts",  "title": "Key facts", "facts": { "inception": "…" } },
    { "type": "examples",   "title": "Q&A and examples", "items": [{ "title": "…", "url": "…" }] },
    { "type": "references", "title": "Further reading",  "items": [{ "title": "…", "url": "…" }] },
    { "type": "sources",    "title": "Sources", "items": ["wikipedia", "arxiv"] }
  ]
}
```
Slide types are optional/variable — render by `type`; not all types appear for every topic.

---

## 9. Source health (`GET /v1/ready`)

```jsonc
{
  "status": "ok",                       // "degraded" if any breaker is open OR a source is disabled
  "connectors": [
    { "name": "wikipedia", "reputation": 0.82, "intents": ["concept.definition","concept.overview","entity.facts"],
      "breaker_open": false, "disabled": false }
  ],
  "disabled_sources": ["mitre_attack"]  // disabled in THIS deployment (see §5 source_disabled)
}
```
Use for monitoring/dashboards. `breaker_open=true` means that source is temporarily isolated after
repeated failures (it auto-recovers); `disabled=true` means it is turned off for this deployment
(permanent until re-enabled), which is what makes the dependent intents return `code:"source_disabled"`.

---

## 10. Integration examples

**Generic (Python / httpx):**
```python
import httpx
r = httpx.post(
    "https://YOUR-HOST/v1/research",
    headers={"X-API-Key": KEY},
    json={"intent": "company.profile", "params": {"name": "Microsoft"}},
    timeout=20,
)
env = r.json()
if r.status_code == 200:
    if not env["data"]:
        ...  # no data found (check env["warnings"])
    elif env["degraded"]:
        ...  # partial — some sources failed (env["warnings"])
    else:
        profile = env["data"]
```

**Generic (JS / fetch):**
```js
const res = await fetch(`${BASE}/v1/research`, {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-API-Key": KEY },
  body: JSON.stringify({ intent: "compose.slide_outline", params: { topic: "TLS" } }),
});
const env = await res.json();
```

**Discovery-driven:** call `GET /v1/intents` to enumerate available intents + their `accepts` params,
then build requests dynamically (the dev console does exactly this).

---

## 11. Operational notes & caveats

- **Stateless / no storage** — no accounts, no usage history; logs are stdout (structured JSON).
  API keys are static env config.
- **Latency** — a request fans out to its sources with a wall-clock deadline (default 12 s) and a
  per-source timeout (default 8 s). Typical responses are 0.5–3 s; set client timeouts ≥ 15 s.
- **MITRE on serverless** — disabled on Vercel (bulk dataset unfit for cold starts); `security.techniques`
  returns `501` there. Self-host to enable it.
- **Provenance & licensing** — you are responsible for honoring `sources[].license` when you reuse
  retrieved content downstream.
- **Dynamic source (`feed.poll`)** — fetches a URL *you* supply, so it is SSRF-guarded: https-only,
  private/internal targets blocked, redirects not followed, response size-capped (knobs:
  `DYNAMIC_SOURCE_BLOCK_PRIVATE`, `DYNAMIC_SOURCE_ALLOW_HTTP`, `DYNAMIC_SOURCE_ALLOWLIST`,
  `DYNAMIC_SOURCE_MAX_BYTES`). Lock it to known hosts with an allowlist, or turn it off with
  `DISABLED_CONNECTORS=http_source`. Credentials you pass in `source.headers` are never logged/echoed.
- **Versioning** — breaking changes will land under a new prefix (`/v2`); `/v1` shapes above are stable.
