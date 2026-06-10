# jobs-finder

> On-demand **LinkedIn** + **Indeed** + **InfoJobs** job search HTTP endpoints,
> built with FastAPI + Playwright. **Educational / personal use only.** Read
> the Legal Notices below before running anything.

## Sources

| Endpoint | Source | Backed by |
| --- | --- | --- |
| `GET /jobs/linkedin` | `linkedin.com/jobs/search` | `LinkedInPlaywrightScraper` (closed source) |
| `GET /jobs/indeed`   | `es.indeed.com/jobs`     | `IndeedPlaywrightScraper` (closed source) |
| `GET /jobs/infojobs` | `www.infojobs.net/ofertas-trabajo` | `InfoJobsPlaywrightScraper` |
| `GET /jobs`          | aggregator over all 3 sources (dedup by `(title, company, location)`) | `SearchAllSourcesUseCase` |

Each source has its own Legal Notice and Manual Verification procedure —
read them both before running. The aggregator is a thin composition
layer — see "Aggregator endpoint" below.

## Response headers

Every `GET /jobs/<source>` response carries these headers:

| Header | Value | Purpose |
| --- | --- | --- |
| `X-Request-Id` | UUID (or the value of the request's `X-Request-Id` header, if present) | Correlation id for logs + 502 bodies. |
| `X-Cache` | `HIT` or `MISS` | Whether the response was served from the in-memory TTL cache. `MISS` means the Playwright scraper was invoked; `HIT` means the cached `list[Job]` was returned without a browser launch. |
| `X-RateLimit-Limit` | int | The bucket capacity (= max burst). From `RATE_LIMIT_REQUESTS` (default 20). Absent on exempt paths. |
| `X-RateLimit-Remaining` | int | Tokens left in the bucket after this request. Absent on exempt paths. |
| `X-RateLimit-Reset` | int (seconds) | Seconds until the bucket is full again. Absent on exempt paths. |
| `Retry-After` | int (seconds) | Seconds until the next token is available. **ONLY on 429 responses** (RFC 6585). |

The `X-Cache` header is additive — the JSON response body is unchanged.
A `HIT` collapses a 2-15s Playwright round-trip into a sub-millisecond
dict lookup; see "Caching" below. The 3 `X-RateLimit-*` headers are
additive on every non-exempt response; see "Rate limiting" below.

## Legal Notice

> **STOP. Read this before running anything.**

This project scrapes LinkedIn's public job search pages. **Scraping LinkedIn
may violate LinkedIn's Terms of Service** and may expose the operator to
civil and/or criminal liability depending on jurisdiction (including but not
limited to the EU's GDPR, Spain's AEPD/LOPDGDD, and the United States' CFAA).

By downloading, building, running, or otherwise using this software, **you
acknowledge and accept the following**:

- You assume **all** legal risk. The authors and contributors of this project
  accept **no** liability for misuse, account bans, IP blocks, or legal
  action taken against you.
- This is **not** a production-grade job aggregator. It is an educational
  exercise that demonstrates how to combine FastAPI, Playwright, and
  hexagonal architecture. There is no SLA, no support, no reliability
  guarantee, and no warranty of any kind.
- Do not use this software to redistribute LinkedIn data, to bypass rate
  limits, to evade anti-bot measures, or for any commercial purpose.
- If you are unsure whether your use case is legal, **consult a lawyer** in
  your jurisdiction before running this code.

If you are not willing to accept these terms, **do not run this software**.

## Legal Notice — Indeed

> **STOP. Indeed's Terms of Service also prohibit scraping.** This
> section is a separate warning because the legal exposure to Indeed
> scraping is distinct from LinkedIn's.

This project scrapes Indeed's public job search pages. **Scraping Indeed
may violate Indeed's Terms of Service and/or their `robots.txt` policy**
and may expose the operator to civil and/or criminal liability depending
on jurisdiction (including but not limited to the EU's GDPR, Spain's
AEPD/LOPDGDD, and the United States' CFAA). Indeed also serves a
Cloudflare anti-bot challenge to suspected scrapers; the live procedure
below may break at any time without notice.

By using the `/jobs/indeed` endpoint you additionally acknowledge and
accept the following:

- You assume **all** legal risk. The authors and contributors of this
  project accept **no** liability for misuse, account bans, IP blocks,
  Cloudflare challenges, or legal action taken against you.
- This software does **not** log in to Indeed. It does **not** send
  `li_at` cookies, credentials, proxies, or any other authentication
  material. It only requests the public, unauthenticated
  `https://es.indeed.com/jobs?...` endpoint.
- The captured data — title, company, location, URL, and posting date —
  are fields Indeed renders publicly to anonymous users. The scraper
  does not bypass any paywall, anti-bot measure, or authentication
  gate. (A Cloudflare challenge IS treated as a hard stop: the
  scraper returns 502 and does not retry, solve, or evade.)
- Do not use this software to redistribute Indeed data, to bypass rate
  limits, to evade anti-bot measures, or for any commercial purpose.
- If you are unsure whether your use case is legal, **consult a lawyer**
  in your jurisdiction before running this code.

If you are not willing to accept these terms, **do not call
`/jobs/indeed`**.

## Legal Notice — InfoJobs

> **STOP. InfoJobs's Terms of Service also prohibit scraping, and the
> service is protected by Distil Networks + Geetest.** This section
> is a separate warning because the legal and technical exposure to
> InfoJobs scraping is distinct from LinkedIn's and Indeed's.

This project scrapes InfoJobs's public job search pages. **Scraping
InfoJobs may violate InfoJobs's Terms of Service and/or their
`robots.txt` policy** and may expose the operator to civil and/or
criminal liability depending on jurisdiction (including but not limited
to the EU's GDPR, Spain's AEPD/LOPDGDD, and the United States' CFAA).
InfoJobs is also protected by **Distil Networks** (browser
fingerprinting) and **Geetest** (captcha challenge) — many datacenter
and VPS IP ranges are blocked at the first request. The live procedure
below may break at any time without notice.

By using the `/jobs/infojobs` endpoint you additionally acknowledge
and accept the following:

- You assume **all** legal risk. The authors and contributors of this
  project accept **no** liability for misuse, account bans, IP blocks,
  Distil/Geetest challenges, or legal action taken against you.
- This software does **not** log in to InfoJobs. It does **not** send
  credentials, proxies, or any other authentication material. It only
  requests the public, unauthenticated
  `https://www.infojobs.net/ofertas-trabajo?q=...&l=...` endpoint. The
  path-based form (`/ofertas-trabajo/{keyword}-en-{location}`) is NOT
  used by this project because Distil blocks it.
- The captured data — title, company, location, URL — are fields
  InfoJobs renders publicly to anonymous users. The scraper does not
  bypass any paywall, anti-bot measure, or authentication gate. A
  Distil/Geetest challenge IS treated as a hard stop: the scraper
  returns 502 and does not retry, solve, or evade.
- `playwright-stealth` is wired in production to reduce the
  frequency of anti-bot challenges, but it is not a guarantee. From
  some IP ranges the live path will return 502 every time; this is
  the expected failure mode, not a bug.
- Do not use this software to redistribute InfoJobs data, to bypass
  rate limits, to evade anti-bot measures, or for any commercial
  purpose.
- If you are unsure whether your use case is legal, **consult a
  lawyer** in your jurisdiction before running this code.

If you are not willing to accept these terms, **do not call
`/jobs/infojobs`**.

## What this is

`jobs-finder` is a multi-source job-search engine. On each request, the
relevant route launches a headless Chromium browser via Playwright,
navigates to the upstream source's public job search, parses the result
cards, and returns structured JSON. It is bootstrapped as a hexagonal
Python project (domain / application / infrastructure / presentation) so
additional job sources can be added in follow-up changes without
rewrites.

### CORS — development default is `*`; override for production

`Settings.cors_allow_origins` defaults to `["*"]` so a browser-based dev
client can call the API without extra wiring. **This is NOT safe for
production.** Set the `LINKEDIN_CORS_ALLOW_ORIGINS` env var to a
comma-separated allowlist before exposing the service publicly, e.g.

```bash
LINKEDIN_CORS_ALLOW_ORIGINS="https://app.example.com,https://admin.example.com" \
  uv run uvicorn jobs_finder.main:app --port 8000
```

### Caching

Each `GET /jobs/<source>` route wraps the source's `JobSearchPort` in a
`CachedJobSearchUseCase` backed by a `CachePort` implementation. The
first call invokes the Playwright scraper and stores the result
(`X-Cache: MISS`); every subsequent identical query within the TTL
window returns the cached `list[Job]` without launching a browser
(`X-Cache: HIT`).

Two cache backends are supported, selected by the `CACHE_BACKEND`
env var (default `memory`):

| Backend | Use case | Survives restart | Multi-worker / multi-host | State location |
| --- | --- | --- | --- | --- |
| `memory` (default) | single-process dev / laptop | no | no | per-process `dict` + `threading.Lock` |
| `redis` | production / multi-worker | yes | yes (shared cache) | external `redis.asyncio` server |

Both backends satisfy the same `CachePort` Protocol, set the same
`X-Cache: HIT|MISS` response header, and honor the per-source key
isolation (a LinkedIn HIT never satisfies an Indeed query).

#### Local Redis (Docker one-liner)

```bash
# Start a local Redis on :6379 (one-time, persists across restarts
# of the API; stop with `docker stop jobs-finder-redis`).
docker run -d -p 6379:6379 --name jobs-finder-redis redis:7-alpine

# Run the API against Redis. The lifespan pings the server on
# startup; if Redis is unreachable, the app exits with a
# RuntimeError BEFORE serving any request.
CACHE_BACKEND=redis \
  CACHE_REDIS_URL=redis://localhost:6379/0 \
  uv run uvicorn jobs_finder.main:app --port 8000
```

#### Remote Redis (managed services)

Point `CACHE_REDIS_URL` at any reachable Redis. The factory uses
`redis.asyncio.from_url(url, db=...)` so a `rediss://` URL (TLS) or
a username/password are supported via the standard `redis://`
syntax (`redis://:password@host:port/db`).

```bash
# Upstash (HTTP / TLS edge Redis — works with the free tier).
CACHE_BACKEND=redis \
  CACHE_REDIS_URL=rediss://default:<password>@<host>.upstash.io:6379 \
  CACHE_REDIS_NAMESPACE=jobs-finder-prod \
  uv run uvicorn jobs_finder.main:app --port 8000

# AWS ElastiCache (cluster-mode disabled, single node).
CACHE_BACKEND=redis \
  CACHE_REDIS_URL=redis://my-cluster.xxxxx.use1.cache.amazonaws.com:6379/0 \
  CACHE_REDIS_NAMESPACE=jobs-finder-prod \
  uv run uvicorn jobs_finder.main:app --port 8000

# Redis Cloud (managed Redis Enterprise).
CACHE_BACKEND=redis \
  CACHE_REDIS_URL=redis://default:<password>@<host>.redis.cloud:6379/0 \
  CACHE_REDIS_NAMESPACE=jobs-finder-prod \
  uv run uvicorn jobs_finder.main:app --port 8000
```

The `CACHE_REDIS_NAMESPACE` env var is the per-deployment key
prefix. Set it to your environment (e.g. `jobs-finder-prod`,
`jobs-finder-staging`) so two deployments sharing the same Redis
instance don't collide. The validator at startup rejects empty
or `:`-containing namespaces (the runtime key is
`{namespace}:{source}:{hash}` — a `:` in the namespace would let
two deployments share a key prefix).

#### Disable the cache

Set `CACHE_TTL_SECONDS=0` to disable the cache for either backend:

```bash
# Memory backend, cache disabled (every call hits the upstream).
CACHE_TTL_SECONDS=0 uv run uvicorn jobs_finder.main:app --port 8000

# Redis backend, cache disabled (every call hits the upstream;
# the Redis connection is still created on startup for ping).
CACHE_BACKEND=redis CACHE_TTL_SECONDS=0 \
  uv run uvicorn jobs_finder.main:app --port 8000
```

A `ttl=0` cache issues NO write commands (in-memory: every entry
is already expired by the time it's read; Redis: no `SET` issued).
Subsequent `get`s are always a miss, so the scraper is invoked
on every call.

#### `query_tokens` field (REQ-CACHE-001)

The 6th field of `JobSearchCacheKey` is `query_tokens: tuple[str, ...]`,
the normalized query tokens (lowercased, punctuation-stripped, sorted,
deduped) used by the aggregator's InfoJobs client-side filter and
the opt-in `keyword_score` sort. Two calls with the same
`(source, keywords, location, limit, geo_id)` but different
`query_tokens` are byte-distinct cache entries (different jobs are
returned; cache HITs would silently corrupt the wrong response). The
field is optional with a default `()` for backward compat: pre-change
callers that construct `JobSearchCacheKey` with 5 positional args get
`query_tokens=()` and the v1 cache-key behavior.

#### Cache env-var table

| Env var | Type | Default | Effect |
| --- | --- | --- | --- |
| `CACHE_BACKEND` | `memory` \| `redis` | `memory` | Selects the backend. `redis` requires a reachable `redis.asyncio` server (the lifespan pings it on startup; if unreachable, the app exits with `RuntimeError`). |
| `CACHE_TTL_SECONDS` | float | `60.0` | Absolute TTL (last-write-wins). `0.0` disables the cache. Sub-second values use PEX (millisecond precision) on the Redis backend. |
| `CACHE_REDIS_URL` | str | `redis://localhost:6379/0` | The `redis://` URL passed to `redis.asyncio.from_url`. Use `rediss://` for TLS, or `redis://:password@host:port/db` for auth. |
| `CACHE_REDIS_NAMESPACE` | str | `jobs-finder` | The per-deployment key prefix. Validated at startup: empty and `:`-containing values are rejected. The runtime key is `{namespace}:{source}:{sha256(key)[:32]}`. |
| `CACHE_REDIS_DB` | int | `0` | The integer db index passed to `redis.asyncio.from_url(..., db=...)`. |

The `X-Cache: HIT|MISS` response header is unchanged by the
backend: the route reads `SearchResult.cache_status.value` from
the `CachedJobSearchUseCase` and emits the exact same header
shape. The 3 source caches (LinkedIn + Indeed + InfoJobs) are
always independent — a LinkedIn HIT never satisfies an Indeed
query — regardless of backend.

#### Caveats

- **In-memory backend** is per-process: 4 uvicorn workers = 4
  independent caches (no cross-worker sharing, no survival of
  process restart). The 553 pre-existing tests assume this mode
  (the conftest's `app` fixture builds a default `app = build_app()`
  which uses `InMemoryTTLCache`).
- **Redis backend** is best-effort: a `redis.exceptions.RedisError`
  on a `get`/`set`/`delete` logs a WARNING and returns the no-op
  sentinel (None for `get`, no exception for the rest). The
  request continues as a cache miss — a Redis outage degrades to
  a slower but functional API, not a 502.
- **JSON serialization**: values are stored as `json.dumps(value,
  default=str)`. A `Job` (frozen dataclass) round-trips to a
  `dict` — callers should consume the cached value via the
  response schema (`JobResponse`), not by `isinstance(..., Job)`.
- **Stampede**: two concurrent misses for the same key can
  cause two scraper calls. A future change can add
  `asyncio.Lock`-per-key for single-flight. Not in v1.
- **Error caching**: errors (502) are NOT cached (REQ-C-006),
  so a transient Distil/Cloudflare block doesn't poison the
  cache. The next request after a failure retries the scraper.

### Rate limiting

A token-bucket rate limiter at the HTTP layer protects against a
single client IP hammering the API and fanning out to 3 Playwright
sessions per request. The default is 20 requests per 60 seconds
per client IP, aligned with the per-source `AsyncThrottle` pace
(`min_interval_seconds=3.0` → 20 req/min/source). With the
in-memory backend, the rate limiter is a coarse top layer that
matches the per-source throttles; with the Redis backend, the
bucket is shared across workers and hosts.

**Bucket keys are SHA256 hashes of the resolved client IP**
(truncated to 16 hex chars) — no PII at rest. The raw client IP
is NEVER written to the `InMemoryTokenBucket._buckets` dict or
the `RedisTokenBucket` Redis key. This applies to both `memory`
and `redis` backends.

The per-route cost map: `GET /jobs` (the aggregator) costs 1
token; the 3 parallel scraper calls inside the aggregator are
paced by each source's own `AsyncThrottle` (20 req/min/source),
so the HTTP rate limiter does NOT double-count the fan-out.
Each `GET /jobs/{source}` costs 1 token. A 429 short-circuits
`call_next`, so the cache and scraper are NEVER reached from a
429 path.

Two backends are supported, selected by the `RATE_LIMIT_BACKEND`
env var (default `memory`):

| Backend | Use case | Survives restart | Multi-worker / multi-host | State location |
| --- | --- | --- | --- | --- |
| `memory` (default) | single-process dev / laptop | no | no | per-process `dict` + per-key `asyncio.Lock` |
| `redis` | production / multi-worker | yes | yes (shared bucket) | external `redis.asyncio` server (atomic Lua `EVAL`) |

Both backends satisfy the same `RateLimitPort` Protocol, set the
same `X-RateLimit-*` response headers, and short-circuit the
route on a 429 (no cache pollution, no scraper call). The Redis
backend is **fail-open** by design: a `redis.exceptions.RedisError`
on `try_acquire` logs a WARNING and returns `allowed=True` (no
throttling), so a rate-limiter Redis outage degrades to "no
throttling", never 5xx. This is asymmetric to the cache's
fail-fast Redis ping — the rate limiter is OPTIONAL, the cache
is not.

#### Exempt paths

The exempt list defaults to `{/health}` (k8s liveness probes MUST
NOT 429 the pod) and `app_factory` additionally exempts FastAPI's
docs surface (`/docs`, `/openapi.json`, `/redoc`). Override via
`RATE_LIMIT_EXEMPT_PATHS='["/health", "/internal/ping"]'` (a
JSON list per the spec OQ-B). Exempt responses carry no
`X-RateLimit-*` / `Retry-After` headers — exempt is
observability-agnostic by design.

#### Trusted proxies

The default is to **ignore** `X-Forwarded-For` entirely (security
default — an attacker who sets the header on a direct connection
should not be able to spoof their client_id). To enable proxy
trust, set `RATE_LIMIT_TRUSTED_PROXIES` to a JSON list of CIDR
strings — the trusted proxy CIDRs:

```bash
# A single trusted reverse proxy in front of the API:
RATE_LIMIT_TRUSTED_PROXIES='["10.0.0.0/8"]' \
  uv run uvicorn jobs_finder.main:app --port 8000
```

With this config and a request from socket IP `10.0.0.1` (in the
trusted CIDR) carrying `X-Forwarded-For: 1.2.3.4`, the
rightmost-untrusted walk returns `"1.2.3.4"` as the client_id.
A request from socket IP `203.0.113.5` (NOT in the trusted CIDR)
with the same `X-Forwarded-For` header is **ignored** — the
middleware uses the socket IP `203.0.113.5` as the client_id
(direct connection from an untrusted IP cannot claim a proxy
chain).

Quick smoke test of the trusted-proxy path:

```bash
# Start the API with a trusted proxy CIDR (the 127.0.0.1/32 covers
# the ASGITransport `client=("127.0.0.1", 50000)` default).
RATE_LIMIT_TRUSTED_PROXIES='["127.0.0.1/32"]' \
  RATE_LIMIT_REQUESTS=20 RATE_LIMIT_WINDOW_SECONDS=60 \
  uv run uvicorn jobs_finder.main:app --port 8000

# A request with a spoofed X-Forwarded-For lands in a different
# bucket from the socket-IP bucket (the spoofed IP is the rightmost-
# untrusted hop from the trusted chain):
curl -is -H "X-Forwarded-For: 1.2.3.4" \
  "http://localhost:8000/jobs/linkedin?keywords=python&location=madrid" \
  | grep -E '^(HTTP/1\.1|X-RateLimit-Remaining)'

# Two curls with DIFFERENT X-Forwarded-For values land in
# DIFFERENT buckets (their X-RateLimit-Remaining values start at
# 19 independently, NOT sharing the socket-IP bucket).
```

Invalid CIDRs in `RATE_LIMIT_TRUSTED_PROXIES` (e.g.
`'["not-a-cidr"]'`) fail at app startup with a `pydantic.ValidationError`,
not silently at request time. Malformed JSON fails similarly.

#### Manual verification

The fastest way to confirm the rate limiter is working end-to-end
is to start the API with a small limit and curl-loop until a 429
fires. With the new defaults (`RATE_LIMIT_REQUESTS=20`), the
expected response sequence: requests 1-20 → `200` with
`X-RateLimit-Remaining` decrementing from 19 to 0; request 21 →
`429` with `Retry-After: 3` (`X-RateLimit-Reset: 60` — the
full-refill time) and the documented body shape. Run from a
separate terminal after the API is up:

```bash
# Start with the default 20 req/min so a 429 is reachable in <10s.
RATE_LIMIT_REQUESTS=20 RATE_LIMIT_WINDOW_SECONDS=60 \
  uv run uvicorn jobs_finder.main:app --port 8000

# Loop 21 requests, inspect X-RateLimit-* + Retry-After.
for i in $(seq 1 21); do
  echo "--- request $i ---"
  curl -is "http://localhost:8000/jobs/linkedin?keywords=python&location=madrid" \
    | grep -E '^(HTTP/1\.1|X-RateLimit|Retry-After|X-Request-Id)'
done

# Expected:
#   requests 1-20 → HTTP 200, X-RateLimit-Remaining: 19,18,...,0
#   request 21   → HTTP 429, Retry-After: 3, X-RateLimit-Reset: 60, X-RateLimit-Remaining: 0
#   429 body: {"detail":"rate limit exceeded","request_id":"<uuid>"}

# Verify the /health exempt path.
curl -is http://localhost:8000/health
# Expected: HTTP 200, NO X-RateLimit-* headers (exempt is observability-agnostic).
```

#### Rate-limit env-var table

| Env var | Type | Default | Effect |
| --- | --- | --- | --- |
| `RATE_LIMIT_ENABLED` | bool | `true` | Kill-switch: `false` makes the middleware a no-op (no headers, no rejection). |
| `RATE_LIMIT_BACKEND` | `memory` \| `redis` | `memory` | Selects the backend. `redis` requires a reachable `redis.asyncio` server (used for the atomic Lua `EVAL`; if unreachable, the middleware fails OPEN with a WARNING — no startup ping). |
| `RATE_LIMIT_REQUESTS` | int | `20` | Bucket capacity (= max burst). Aligned to the per-source `AsyncThrottle.min_interval_seconds=3.0` pace: 1 req / 3 sec = 20 req/min. |
| `RATE_LIMIT_WINDOW_SECONDS` | float | `60.0` | Refill period. The refill rate is `capacity / window_seconds` tokens/sec (20 / 60 = 1/3 tokens/sec at the new default). |
| `RATE_LIMIT_REDIS_URL` | str | (falls back to `CACHE_REDIS_URL`) | The `redis://` URL for the optional Redis backend. |
| `RATE_LIMIT_REDIS_NAMESPACE` | str | `rate-limiter` | The per-deployment key prefix. The runtime key is `{namespace}:{sha256(client_id)[:16]}` (hash, not raw IP — see "Trusted proxies" below). |
| `RATE_LIMIT_REDIS_DB` | int | (falls back to `CACHE_REDIS_DB`) | The integer db index passed to `redis.asyncio.from_url(..., db=...)`. |
| `RATE_LIMIT_EXEMPT_PATHS` | JSON list | `["/health"]` | Paths that bypass the limiter (no headers, no rejection). FastAPI docs paths are appended at app-factory wiring time. |
| `RATE_LIMIT_TRUSTED_PROXIES` | JSON list of CIDR strings | `[]` | Trusted proxy CIDRs. When the socket IP is in any trusted CIDR, `X-Forwarded-For` is parsed right-to-left and the first untrusted hop is the client_id. When empty (the default), `X-Forwarded-For` is IGNORED. |
| `RATE_LIMIT_AGGREGATOR_PATH_COST` | int | `1` | Cost of `GET /jobs` (the aggregator). The 3 parallel scraper calls are paced by each source's own `AsyncThrottle` (20 req/min/source), so the HTTP rate limiter charges 1× per aggregator call (NOT 3× — that would double-count). |
| `RATE_LIMIT_PER_SOURCE_PATH_COST` | int | `1` | Cost of `GET /jobs/{linkedin,indeed,infojobs}`. |

#### Disable the rate limiter

Set `RATE_LIMIT_ENABLED=false` to make the middleware a true
no-op (no `X-RateLimit-*` headers, no rejection, no log noise).
The middleware is not added to the stack at all, so the app's
behavior is byte-identical to the pre-rate-limiting baseline.

```bash
RATE_LIMIT_ENABLED=false uv run uvicorn jobs_finder.main:app --port 8000
```

#### Caveats

- **In-memory backend** is per-process: 4 uvicorn workers = 4
  independent buckets (no cross-worker sharing, no survival of
  process restart). For multi-worker throttling, use the Redis
  backend.
- **Bucket keys are SHA256 hashes, not raw IPs**: the resolved
  client IP (after `_resolve_client_id`) is hashed via
  `hash_client_id()` (SHA256, truncated to 16 hex chars) before
  being passed to the limiter. The raw IP NEVER appears in the
  `InMemoryTokenBucket._buckets` dict or the `RedisTokenBucket`
  Redis key. This is PII-sanitization at the HTTP boundary.
- **Default trusted-proxies = empty** (security default): the
  middleware IGNORES `X-Forwarded-For` when
  `RATE_LIMIT_TRUSTED_PROXIES=[]`. A deployment behind a reverse
  proxy that forwards the original client IP MUST set
  `RATE_LIMIT_TRUSTED_PROXIES` to a JSON list of CIDR strings
  (e.g. `'["10.0.0.0/8"]'`) for per-client throttling to work
  correctly. See the "Trusted proxies" subsection above.
- **`X-RateLimit-Remaining` rounds DOWN** to the nearest integer
  (a `float` decision's `remaining` field is `int(math.floor(...))`).
  Clients should treat the value as an approximation under heavy
  fractional-cost loads.
- **Cache invariant preserved**: the 429 short-circuits
  `call_next`, so `CachedJobSearchUseCase.search` is never
  reached from a 429 path. No `CachePort.set` happens, so the
  cache namespace stays clean.
- **Asymmetric fail-open**: the rate-limiter Redis is fail-open
  (a Redis outage degrades to "no throttling"), while the cache
  Redis is fail-fast (a Redis outage prevents startup). The
  asymmetry is intentional — the rate limiter is OPTIONAL
  (`memory` is the default), the cache is not.

### Structured JSON logs (with `request_id`)

Log lines are emitted as single-line JSON to stderr with the field set
locked to `{timestamp, level, name, message, request_id}`. The
`request_id` field is filled from the `X-Request-Id` request header
(generated if absent) so a single grep can join a request, its
response, and any error logged during processing. Set
`LINKEDIN_LOG_FORMAT=plain` for a human-readable fallback.

## Stack

- **Python** 3.12
- **FastAPI** + **uvicorn** (HTTP layer)
- **Playwright** + Chromium (scraper)
- **httpx** (in-process API tests)
- **pydantic-settings** (env-driven configuration)
- **uv** (package manager and virtualenv)
- **mypy --strict** (type checking)
- **ruff** (lint + format)
- **pytest** + **pytest-asyncio** (test runner)

## Quick start

Three ways to start the API, depending on whether you want the
default in-memory cache, a Redis-backed cache, or no cache at all.

### Environment variables — `.env` workflow

The service reads **46 environment variables** (LinkedIn / Indeed /
InfoJobs scrapers, cache, rate limiter, aggregator ranking, LLM chat
filter). The full annotated list lives in **`.env.example`** (committed
to the repo). Your local overrides go in **`.env`** (gitignored, never
committed).

**First-time setup**:

```bash
# 1. Copy the template.
cp .env.example .env

# 2. Edit the values you want to override. The minimum for the
#    chat filter to work is LLM_API_KEY (set it) and LLM_FILTER_ENABLED
#    (set to `true` to register the /jobs/chat route).
$EDITOR .env

# 3. Start the API. pydantic-settings reads `.env` automatically
#    (see SettingsConfigDict in src/jobs_finder/infrastructure/config.py).
uv run uvicorn jobs_finder.main:app --port 8000
```

**Precedence** (standard pydantic-settings order):

1. **Shell env vars** — `export LLM_API_KEY=sk-...` wins over everything
2. **`.env` file** — your local overrides
3. **Code defaults** in `src/jobs_finder/infrastructure/config.py::Settings`

So you can keep `.env` minimal (just `LLM_API_KEY=` and the overrides
you actively tweak) and use shell exports for one-off experiments.

**Per-source / per-feature env-var tables** appear in the relevant
sections below (Caching, Rate limiting, Aggregator, AI Chat Filter).
Use those for context on what each var does — `.env.example` is the
canonical template.

### Default: in-memory cache

```bash
# 1. Install dependencies into a project-local virtualenv
uv sync

# 2. (Optional) copy the env template and edit values.
cp .env.example .env

# 3. Start the API. The default CACHE_BACKEND=memory uses
#    InMemoryTTLCache (60s TTL, per-process, no external deps).
uv run uvicorn jobs_finder.main:app --port 8000
```

### With Redis (persistent, multi-worker-safe)

```bash
# 1. Start a local Redis (one-time; persists across API restarts).
docker run -d -p 6379:6379 --name jobs-finder-redis redis:7-alpine

# 2. Start the API against Redis. The lifespan pings the server
#    on startup and exits with a RuntimeError if unreachable.
CACHE_BACKEND=redis \
  CACHE_REDIS_URL=redis://localhost:6379/0 \
  uv run uvicorn jobs_finder.main:app --port 8000
```

For remote Redis (Upstash, ElastiCache, Redis Cloud), see
the "Caching" section above for the exact env-var block.

### Cache disabled

```bash
# Every request hits the upstream source (no caching, no Redis
# connection). Useful for forcing a fresh scrape during
# development or for benchmarking the scraper directly.
CACHE_TTL_SECONDS=0 uv run uvicorn jobs_finder.main:app --port 8000
```

### Quality gates

```bash
# Run the test suite (no network, no Chromium).
uv run pytest

# Static type check (--strict).
uv run mypy

# Lint.
uv run ruff check

# Format check.
uv run ruff format --check
```

### Coverage

Coverage is informational, not a build gate. To measure coverage:

```bash
uv run pytest --cov=jobs_finder --cov-report=term-missing
```

This prints a per-module coverage report to the terminal. For an HTML
report, use:

```bash
uv run pytest --cov=jobs_finder --cov-report=html
```

No `fail_under` threshold is configured — coverage is a signal, not a
gate. Add one only when the team sets a target.

## Aggregator endpoint

`GET /jobs` is a thin composition layer over the 3 per-source routes.
It accepts `q`, `location`, `limit`, and a comma-separated `sources`
parameter (default `linkedin,indeed,infojobs`), invokes the
selected cached use cases in parallel via `asyncio.gather`,
deduplicates identical job postings across sources, and returns a
single aggregated `list[AggregatedJobResponse]`.

**The aggregator automatically inherits the cache-ttl behavior**
(REQ-C-001..REQ-C-006) — it calls the same 3 cached use cases that
the per-source routes use, so a cache hit on LinkedIn from a prior
`/jobs/linkedin?keywords=python&location=madrid` call is ALSO a cache
hit when the aggregator invokes LinkedIn. Two aggregator calls
within the TTL window do N+1=3 → 1 scraper round-trip.

**Dedup is by `(title, company, location)` heuristic** (case-insensitive,
whitespace-stripped). A job from 2+ sources is returned once with
`sources: list[str]` listing where it appeared (in source-priority
order: `linkedin` > `indeed` > `infojobs`).

**Per-source error isolation** (REQ-A-003) — a `JobSearchError`
from one source is caught and logged; the aggregator continues with
the other sources' results. A 502 from one source does NOT take down
the aggregator. The `X-Aggregator-Errors` response header lists
the errored sources.

### Result ordering

Deduped results are **ranked** after the dedup step (REQ-AR-002,
`jobs-aggregator-ranking` change). The default ranking is
**`posted_at` DESC** (most recent first) with a deterministic
tie-breaker chain: source-priority ASC, then `job.id` ASC. This
means a LinkedIn job from yesterday appears BEFORE an Indeed job
from last week — the default behavior is freshness-ordered, not
source-priority-ordered. The ranking is post-cache: changing the
strategy does not invalidate the cache.

The strategy is configurable via 2 env vars (see the
"Aggregator env vars" table below):

- `AGGREGATOR_RANKING_STRATEGY=posted_at` (default): sort by
  `posted_at` DESC, with the source-priority + `job.id`
  tie-breaker. Most useful for a job search.
- `AGGREGATOR_RANKING_STRATEGY=priority`: sort by source-priority
  alone (LinkedIn > Indeed > InfoJobs), ignoring freshness.
  Useful for "I trust LinkedIn more than Indeed" deployments.
- `AGGREGATOR_RANKING_STRATEGY=none`: preserve the pre-change
  source-priority + scrape-order behavior. **The escape hatch**
  for clients depending on the pre-change order.
- `AGGREGATOR_PRIORITY_MAP='{"linkedin":0,"indeed":1,"infojobs":2}'`
  (default): the source-priority map used as the primary sort
  key for `priority` AND as the tie-breaker for `posted_at`.
  Sources not in the map are treated as priority `999` (last).
  Invalid JSON raises a Pydantic `ValidationError` at startup.
- `ENABLE_KEYWORD_SCORING=false` (default): opt-in `keyword_score`
  relevance ranking. When `true`, the aggregator sorts by
  `keyword_score desc, posted_at desc` (per-job match rate
  against the query tokens, with title match weighted `0.6` +
  description match weighted `0.4`, capped at `1.0`). The v1
  `posted_at` sort is preserved when `false`. The setting is
  opt-in (not the default) because the `keyword_score` heuristic
  is a best-effort signal — a v1 deployment that depends on
  the freshness-first order is not affected unless the operator
  flips the switch. See "InfoJobs client-side filter" below for
  the always-active `filter_infojobs_results` step that the
  `keyword_score` sort complements (the filter discards 0-overlap
  jobs; the sort orders the survivors).

**None `posted_at` defensive branch**: the ranking function
places `posted_at=None` jobs at the bottom (REQ-AR-007). This
is a future-proofing safety net — all 3 scrapers fall back to
`datetime.now(UTC)` when the parser returns `None`, so in
practice every `posted_at` is non-`None`.

### InfoJobs client-side filter (REQ-FILTER-001)

The `SearchAllSourcesUseCase` applies a post-scrape filter to
the InfoJobs slice of the aggregated results. The filter is a
pure function `filter_infojobs_results(jobs, query_tokens)`
in `infrastructure/aggregator_filters.py` that discards any
`Job` whose `title` has zero token overlap with the query
tokens (lowercased, punctuation-stripped, deduped). A job
is kept iff `len(tokenize(job.title) & query_tokens) > 0`.
The filter is applied AFTER the per-source dedup step
(post-cache, post-scrape). LinkedIn and Indeed results are
NOT filtered (their server-side search is more accurate;
only InfoJobs's broad keyword match needs a client-side
narrowing). The `query_tokens` is the tokenized `q` query
parameter from the `GET /jobs` route; an empty `query_tokens`
(the v1 default) is a no-op (every job is kept). A
`tokenize()` Unicode-safe accent is preserved: a query for
`"Málaga"` matches `"Ingeniero Málaga"` (U+00E1) but does
NOT match `"Ingeniero Malaga"` (no accent).

### Defensive partial results (REQ-DEFENSIVE-001)

The aggregator's per-source error isolation extends the
v1 contract: when at least 1 source returns jobs, the
aggregator returns 200 with the successful sources' jobs
plus an `X-Aggregator-Errors` header listing the failed
sources. The pre-`backend-scraper-query-tuning` v1
behavior (return 200 + empty `jobs` when all 3 sources
failed) was a silent failure mode that misled clients;
the new spec maps `success_count == 0` to
`AllSourcesFailedError` → HTTP 502 (the same status as
any individual source failure). The response body is
`{"detail": "upstream source unavailable",
"request_id": "..."}` (the registered
`JobSearchError` handler masks the original exception
type). Per-source failures emit a WARNING log with
`extra={source, error_type}` so ops can spot failure
patterns (the log is emitted ONCE per failed source, not
once per job the source would have returned).

### Response shape

```json
{
  "jobs": [
    {
      "id": "dd6cc0f5b0f0cfc9",
      "title": "Senior Python Developer",
      "company": "Acme Corp",
      "location": "Madrid, Spain",
      "url": "https://es.indeed.com/viewjob?jk=dd6cc0f5b0f0cfc9",
      "posted_at": "2026-06-01T00:00:00+00:00",
      "sources": ["linkedin", "indeed"]
    },
    {
      "id": "i53515057515712074971181024164219803726",
      "title": "Senior Python",
      "company": "Acme",
      "location": "Madrid",
      "url": "https://www.infojobs.net/acme/em-i53515057515712074971181024164219803726",
      "posted_at": "2026-06-01T00:00:00+00:00",
      "sources": ["infojobs"]
    }
  ]
}
```

The `sources` field is a sorted list in source-priority order
(`linkedin` > `indeed` > `infojobs`). The 6 other fields are the
canonical `JobResponse` shape (identical to the per-source routes).

### Aggregator response headers (in addition to `X-Request-Id`)

| Header | Description |
| --- | --- |
| `X-Cache` | Comma-separated per-source cache status in the caller's `sources` order. E.g. `MISS,MISS,HIT` for a 3-source call where Indeed was a cache hit. **Note**: the values are in the caller's order, not source-priority order, so a request with `sources=indeed,linkedin` returns `MISS,HIT` (Indeed first, then LinkedIn). The route preserves caller order in the joined header for transparency. |
| `X-Aggregator-Sources` | The sources that were queried, in the caller's `sources` order. E.g. `linkedin,infojobs` when only those 2 are queried. |
| `X-Aggregator-Errors` | ABSENT when all sources succeed; set to the comma-separated list of errored sources (in caller order) when at least one fails. E.g. `indeed` if only Indeed raised a `JobSearchError`. |

### Aggregator env vars

| Env var | Type | Default | Effect |
| --- | --- | --- | --- |
| `AGGREGATOR_RANKING_STRATEGY` | `posted_at` \| `priority` \| `none` | `posted_at` | Ranking strategy applied AFTER the dedup step. `posted_at` (default) sorts by `posted_at` DESC with source-priority + `job.id` tie-breakers; `priority` sorts by source-priority alone (ignores freshness); `none` preserves the pre-change source-priority + scrape-order behavior (the escape hatch for clients depending on the old order). Unknown values raise `pydantic.ValidationError` at startup. |
| `AGGREGATOR_PRIORITY_MAP` | JSON object | `{"linkedin": 0, "indeed": 1, "infojobs": 2}` | The source-priority map. Used as the primary sort key for `strategy="priority"` AND as the tie-breaker for `strategy="posted_at"`. Lower number = higher priority; sources not in the map are treated as priority `999` (last). Invalid JSON raises `pydantic.ValidationError` at startup. |

### Examples

```bash
# Default: aggregate all 3 sources, deduped, ordered by posted_at DESC
curl -i "http://localhost:8000/jobs?q=python&location=madrid&limit=20"
# X-Cache: MISS,MISS,MISS (first call)
# X-Aggregator-Sources: linkedin,indeed,infojobs
# X-Aggregator-Errors: (absent)
# Body: jobs ordered by posted_at DESC (most recent first);
#       the first 6 jobs from 3 sources with the same posted_at
#       are tied-broken by source-priority (LinkedIn > Indeed > InfoJobs).

# 1-source: only LinkedIn
curl -i "http://localhost:8000/jobs?q=python&location=madrid&sources=linkedin"
# X-Cache: MISS (no commas)
# X-Aggregator-Sources: linkedin

# 2 sources: LinkedIn + InfoJobs (Indeed skipped)
curl -i "http://localhost:8000/jobs?q=python&location=madrid&sources=linkedin,infojobs"
# X-Cache: MISS,MISS (only 2 values)
# X-Aggregator-Sources: linkedin,infojobs

# Invalid source
curl -i "http://localhost:8000/jobs?q=python&location=madrid&sources=glassdoor"
# HTTP/1.1 422
# {"detail": "unknown sources: ['glassdoor']; valid: ['indeed', 'infojobs', 'linkedin']"}
```

## AI Chat Filter

> **Optional feature.** Code merged with `LLM_FILTER_ENABLED=false` (the
> default). The chat endpoint is **OFF** until an operator sets
> `LLM_FILTER_ENABLED=true` AND `LLM_API_KEY=<key>` in production.
> See "Rollout" below for the 2-stage rollout.

`POST /jobs/chat` is an additive, **Spanish-natural-language** intent
filter on top of the 3-source aggregator. The user types a free-form
request (e.g. "solo remoto, junior Python, Madrid"); the server runs
a **2-stage LLM flow** that drives a directed aggregator scrape with
the extracted `q` / `location`, then filters the result with the v1
LLM filter. Strict ID-subset validation drops any hallucinated IDs
before they reach the response.

The chat endpoint is **read-only and additive** — it does not modify
`/jobs`, `/jobs/linkedin`, `/jobs/indeed`, or `/jobs/infojobs`, and it
does NOT introduce an LLM result cache (the 60s per-source aggregator
cache is the only cache layer; two identical chat payloads within
60s trigger ONE full re-aggregation and TWO LLM calls when the
2-stage path is active, or ONE aggregator + ONE LLM call when the
v1 fallback path runs).

### 2-stage flow

The 2-stage flow replaces the v1 "blind scrape + LLM filter" with a
**structured intent extraction** call that drives a **directed
aggregator scrape**:

```
  ┌──────────────────────────────────────────────────────────────┐
  │  POST /jobs/chat  { message: "ingeniero python, Madrid, 3y" }│
  └──────────────────────────────────────────────────────────────┘
                              ↓
  ┌─ STAGE 1 (NEW): IntentExtractor.extract(message) ──────────┐
  │  LLM call #1 (INTENT_EXTRACTION_SYSTEM_PROMPT)              │
  │  - Security boundary: no inventes, null for absent,         │
  │    no malformed JSON, si dudas baja confidence              │
  │  - Strict Pydantic `extra="forbid"` on Intent schema        │
  │  - RETRY ONCE with corrective prompt on parse failure       │
  │  Returns: Intent(q="ingeniero python", location="Madrid",   │
  │            experience_years=3, remote=None,                  │
  │            employment_type=None, confidence=0.95,           │
  │            notes=None)                                      │
  └──────────────────────────────────────────────────────────────┘
                              ↓
              ┌─ Confidence gate ─┐
              │ confidence < 0.7? │ ← INTENT_EXTRACTION_CONFIDENCE_THRESHOLD
              └──────┬────────────┘
                YES   │   NO
       ┌──────────┘         └──────────┐
       ↓                              ↓
  v1 fallback path              2-stage path
  (used_fallback=True)          (used_fallback=False)
       │                              │
       ↓                              ↓
  Aggregator.search(          Aggregator.search(
    q="", location="",          q="ingeniero python",
    limit=20)                   location="Madrid",
       │                        limit=100)        ← INTENT_MAX_RESULTS
       │                              │
       └──────────────┬───────────────┘
                      ↓
  ┌─ STAGE 3 (v1 LLM filter) ──────────────────────────────────┐
  │  LLM call #2 (SYSTEM_PROMPT + security boundary at END)     │
  │  - Same v1 prompt as before; security boundary APPENDED     │
  │    at the end (REQ-LLM-SEC-001 — no renames, backward compat)│
  │  - Returns: LLMSelection(matching_ids=[...], explanation)   │
  │  - Strict-subset validation: hallucinated ids dropped + WARN │
  └──────────────────────────────────────────────────────────────┘
                      ↓
  ChatResponse { jobs, explanation, total_considered,
                 total_matched, used_fallback }
```

The v1 fallback runs when:
- `INTENT_EXTRACTION_ENABLED=false` (the master switch / kill switch)
- `intent.confidence < INTENT_EXTRACTION_CONFIDENCE_THRESHOLD` (default 0.7)
- Stage-1 `LLMResponseParseError` after retry exhaustion

The `used_fallback: bool` field in the `ChatResponse` tells the
client which path served the request (`True` = v1, `False` = 2-stage).

LinkedIn queries with a specific `intent.location` (e.g. "Madrid")
are translated to a LinkedIn `geoId` (e.g. `103374081`) via the
**location resolver** (`HardcodedLocationResolver`) so the
scraper builds the correct `?geoId=<n>` URL. See the "Location
resolver" section below for the full contract, coverage, and
partial-coverage behavior.

### Curl smoke test

```bash
# Start the app with the chat filter ENABLED (operator-supplied key).
export LLM_API_KEY="<your-minimax-key>"
export LLM_FILTER_ENABLED=true
uv run python -m jobs_finder.main
# In another terminal:
curl -X POST http://localhost:8000/jobs/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"ingeniero < 2 anos en Malaga"}'
# HTTP/1.1 200
# {"jobs": [...3 of 5...], "explanation": "...",
#  "total_considered": 5, "total_matched": 3,
#  "used_fallback": false}
```

### Chat env vars

The 2-stage flow adds 6 NEW env vars on top of the v1 9 env vars.
All 15 are documented here; the v1 vars are unchanged.

| Env var | Default | Purpose |
| --- | --- | --- |
| `LLM_API_KEY` | `None` (route OFF) | MiniMax API key (`SecretStr` in the Settings). The chat route is NOT registered when this is `None`. |
| `LLM_BASE_URL` | `https://api.minimax.io` | OpenAI-compatible base URL. |
| `LLM_MODEL` | `MiniMax-M3` | Pinned to M3 + `thinking: {type: disabled}` (the only model that honors the disabled flag). |
| `LLM_TEMPERATURE` | `0.0` | Deterministic filter. |
| `LLM_MAX_TOKENS` | `1024` | Upper bound on the stage-3 response size. |
| `LLM_REQUEST_TIMEOUT_SECONDS` | `15.0` | Per-request timeout for the `httpx.AsyncClient`. |
| `LLM_MAX_MESSAGE_CHARS` | `1000` | Hard cap on the user `message` length. Exceeding it returns `400 {"detail": "message exceeds 1000 chars (got N)"}`. |
| `LLM_FILTER_ENABLED` | `false` | Feature flag. `true` + key set → route is registered; otherwise the route returns 404. |
| `LLM_FILTER_RATE_LIMIT_RPM` | `20` | Per-user chat bucket (default 20 req/min, matches the main `RATE_LIMIT_REQUESTS`). |
| **`INTENT_EXTRACTION_ENABLED`** | `true` | **Master switch for the 2-stage flow.** `false` reverts to v1 behavior (no stage-1 call, no extra cost). The kill switch. REQ-CHAT-INT-005. |
| **`INTENT_EXTRACTION_CONFIDENCE_THRESHOLD`** | `0.7` | **Confidence gate.** Below this, the use case falls back to v1 (`used_fallback=True`). Tune with production data; calibration is model + prompt specific. REQ-CHAT-INT-004. |
| **`INTENT_MAX_RESULTS`** | `100` | **Per-source cap for the stage-2 aggregator scrape.** Higher than the v1 `limit=20` to give the LLM more recall. 100 jobs × 200 tokens = 20K, well under the 128K window. REQ-CHAT-INT-001. |
| **`LLM_STAGE1_MAX_TOKENS`** | `256` | **Stage-1 response size cap.** The Intent schema is small (7 fields); 256 is enough headroom. REQ-CHAT-INT-001. |
| **`LLM_STAGE1_TEMPERATURE`** | `0.0` | **Stage-1 sampling temperature.** 0.0 = deterministic intent extraction. |
| **`INTENT_EXTRACTION_RETRY`** | `1` | **Number of stage-1 retries on parse failure.** Default 1 = retry once with the corrective system prompt. Set to 0 to disable retry; max 3. REQ-LLM-SEC-002. |

### Cost

**2-stage cost is 2× v1 for Indeed and InfoJobs**: ~$0.005/req (one
stage-1 intent call + one stage-3 filter call). At 1000 queries/day,
~$5/day.

**2-stage cost is 2× v1 for LinkedIn** (since `fix-linkedin-geoid`):
the LinkedIn source now correctly honors `intent.location` via
the `HardcodedLocationResolver` (translates to `geoId=`). The
stage-1 LLM call + stage-3 filter call + directed LinkedIn scrape
(typically a cache hit within 60s) → ~$0.005/req. The benefit is
the same as Indeed + InfoJobs: a directed scrape with the
extracted `q` AND `location`.

**v1 fallback cost is unchanged**: ~$0.0025/req (one stage-3 filter
call only). The fallback is automatic when confidence is low or
the 2-stage flow is disabled.

**Worst case** is bounded by `LLM_FILTER_RATE_LIMIT_RPM` (default 20)
per IP per minute. The shared `httpx.AsyncClient` is built in the
app's lifespan and reuses the connection pool across requests.

**Latency**: the 2-stage flow takes ~5-8s end-to-end (stage 1 LLM
call + directed aggregator scrape + stage 3 LLM call), vs ~3-4s for
v1. The aggregator's 60s per-source cache reuses results within the
window so the "directed" scrape is typically a cache hit. LinkedIn
queries with a specific location now hit the correct geoId
cache entry (the `JobSearchCacheKey` 5th field `geo_id` is part
of the key).

### Security boundaries

Both stage-1 and stage-3 LLM calls receive a system prompt with an
**explicit security boundary** (REQ-LLM-SEC-001):

- **Stage 1** (`INTENT_EXTRACTION_SYSTEM_PROMPT`): the prompt lists
  the 6 `Intent` field names (`q`, `location`, `experience_years`,
  `remote`, `employment_type`, `confidence`) plus 4 invariants:
  1. **No inventes** — never invent fields the user did not mention
  2. **Null for absent** — return `null` for fields the user did not
     mention, never default
  3. **No malformed JSON** — output must be valid JSON, no markdown
     fences, no surrounding prose
  4. **Si dudas, baja confidence** — if uncertain, lower `confidence`
     and let the dispatcher fall back to v1

- **Stage 3** (the v1 `SYSTEM_PROMPT`, with the security boundary
  APPENDED at the END per REQ-LLM-SEC-001 scenario 1): the boundary
  lists the 2 stage-3 field names (`matching_ids`, `explanation`) plus
  the same 4 invariants (no inventes IDs, no inventes ubicaciones,
  null for absent, no malformed JSON, si dudas no inventes). The v1
  prompt NAME is preserved (no rename); the boundary is a STRING
  APPEND, not a replacement.

- **Pydantic `extra="forbid"`** (REQ-LLM-SEC-002) is enforced on
  every LLM response. The stage-1 parser rejects unknown fields,
  type mismatches, and out-of-range `confidence` (`Field(ge=0.0,
  le=1.0)`). The stage-3 parser is the v1 defensive 3-tier parser
  (pinned unchanged by 14 unit tests in `test_llm_parser.py`).

- **Retry once with corrective prompt** (REQ-LLM-SEC-002): on stage-1
  parse failure, the `IntentExtractor` retries ONCE with the
  corrective system prompt (schema-explicit + one-line example). On
  retry failure, the use case falls back to v1 — a misbehaving model
  that fails twice will not succeed on a third try, and a runaway
  retry loop would multiply the cost.

### Running the live tests

The 2 live tests in `tests/integration/test_chat_live.py` are gated
by `LLM_LIVE_TESTS=1` and NEVER run in CI (AGENTS.md rule #1). To
run them locally, use the `direnv` pattern so the API key auto-loads
on `cd`:

```bash
# 1. Install direnv: https://direnv.net/

# 2. Create .envrc in the project root (gitignored):
export LLM_API_KEY=<your-minimax-key>

# 3. Allow the file:
direnv allow

# 4. `cd` into the project dir auto-loads LLM_API_KEY. Now run:
LLM_LIVE_TESTS=1 uv run pytest tests/integration/test_chat_live.py -v
```

The 2 live tests cover:
- `test_live_chat_2stage_high_confidence`: canned
  "ingeniero Python en Madrid, 3+ años, remoto" → 2-stage path,
  asserts `used_fallback=False` + non-empty explanation.
- `test_live_chat_2stage_low_confidence_fallback`: canned "asdf"
  (gibberish) → v1 fallback, asserts `used_fallback=True`.

### Rollout

The chat filter follows a **2-stage rollout** (the rollout, distinct
from the LLM 2-stage flow):

1. **Stage 1 (default)**: code merged with `LLM_FILTER_ENABLED=false`
   (the default). The chat route is **NOT** registered; the chat
   middleware is **NOT** mounted; the LLM client is **NOT** built.
   `GET /jobs`, `GET /jobs/linkedin`, `GET /jobs/indeed`,
   `GET /jobs/infojobs` behave identically to the pre-feature baseline.
2. **Stage 2 (ops enables in prod)**: set
   `LLM_API_KEY=<key>` + `LLM_FILTER_ENABLED=true` in the prod env.
   The chat route is registered; the LLM client is constructed; the
   chat middleware is mounted. No redeploy is required to disable —
   flip `LLM_FILTER_ENABLED=false` and the route returns 404 again.

**The `INTENT_EXTRACTION_ENABLED` kill switch** is a separate,
**runtime** toggle. When the chat filter is ON but
`INTENT_EXTRACTION_ENABLED=false`, the route is still registered
but the use case reverts to the v1 single-stage flow (no stage-1
LLM call, no extra cost). This is the per-deployment lever for
operators who want the chat filter but not the 2-stage LLM cost.

### Known limitations

- **`test_aggregator_settings::test_programmatic_construction_still_works`**
  was a v1 pre-existing bug (the .env + pydantic-settings `deep_update`
  merged the user's programmatic dict with the .env value). It was
  deselected at the v1 baseline of `chat-filter-2stage` and is now
  GREEN again (commit `77b610f` on `main`, fix is a 3-line override
  of `BaseSettings._settings_build_values`).

### Location resolver

LinkedIn's public search uses `geoId=` (numeric) rather than
`location=` (string). The 2-stage chat filter extracts
`intent.location` as a free-form string ("Madrid", "Barcelona",
"cdmx") and the **location resolver** (`HardcodedLocationResolver`)
translates it to a LinkedIn `geoId` (e.g. `103374081` for Madrid)
so the LinkedIn scraper builds the correct URL.

- **Implementation**: `HardcodedLocationResolver` (in
  `src/jobs_finder/infrastructure/location/hardcoded_resolver.py`).
  A pure in-process dict lookup — no I/O, no network call, no
  runtime dependency. Alias normalization chain:
  `unicodedata.normalize("NFC", s).casefold().strip()` + remove
  combining accent marks + alias-to-canonical recurse (e.g.
  `cdmx` → `ciudad de mexico`).
- **Coverage**: 34 canonical entries (8 Spanish cities + 16
  Spanish autonomous communities + 9 LATAM cities + 1 remote).
  Sources from `tests/fixtures/linkedin_geo_ids.csv` (43 captured
  geoIds; 9 country-level + País Vasco + Canarias excluded).
- **Hierarchical fallback**: city > region > country. Country-level
  ("España", "México") and unknown cities return `None` with a
  WARNING log. The use case forwards `geo_id=None` to the
  aggregator; the LinkedIn scraper falls back to broken
  `?location=<str>` (a strict improvement over today's
  100%-broken behavior).
- **Partial coverage**: País Vasco + Canarias + country-level +
  any city NOT in the dict returns `None` → scraper falls back to
  `?location=<str>`. The WARNING log on unresolvable inputs is
  observable for ops; the `scripts/capture_linkedin_geo_ids.py`
  capture script can be re-run to refresh the mapping.
- **Runtime kill switch**: out of scope for this change. The
  resolver is always on; a future env var can disable it without
  code changes. The `LOCATION_RESOLVER_ENABLED=false` is the
  proposed follow-up.
- **Wired in the 2-stage chat filter only**: the v1 path
  (`_execute_v1` with `INTENT_EXTRACTION_ENABLED=false` or
  `confidence < threshold`) does NOT call the resolver. The
  per-source `GET /jobs/linkedin?location=Madrid` route also does
  NOT call the resolver (the scraper is responsible for its own
  `geo_id` resolution per the design).
- **Test coverage**: 51 scenarios in
  `tests/unit/test_hardcoded_location_resolver.py` (alias
  normalization + every entry + None semantic) + 9 scenarios
  in `tests/unit/test_linkedin_scraper.py` (URL formula) + 7
  scenarios in `tests/unit/test_filter_use_case.py` (resolver
  injection + v1 path isolation) + 1 end-to-end integration
  test (`test_2stage_geo_id_end_to_end_with_real_resolver`)
  that pins the full chain from `intent.location` →
  `HardcodedLocationResolver` → LinkedIn port `geo_id=103374081`.
- **Cache key impact**: the `JobSearchCacheKey` 5th field
  (`geo_id`) isolates resolved queries (`geo_id=103374081`) from
  unresolved ones (`geo_id=None`). A query with a resolved
  `geoId` is byte-distinct from the same query with an
  unresolved `geoId` — they return different results, so a
  cache HIT on one would silently corrupt the other. The 60s
  cache flush is invisible to users (60s is short).

### LinkedIn description: empirical finding (Branch B)

The `parse_linkedin_description` function was a skeleton in the
`ai-chat-filter` PR1 (returned `None` for every card). The sanctioned
one-time Playwright capture (AGENTS.md rule #1) was performed on
2026-06-07 and the captured HTML is committed at
`tests/fixtures/linkedin_search_with_description.py`. The
selector was pinned: `div.show-more-less-html__markup`.

**Empirical finding** (the result that shaped Branch B):

LinkedIn's public search results page does **NOT** expose
description text on the individual job cards in the results list.
Each `<div class="base-search-card">` card carries only title,
company, location, and date. The full description is only visible
in a separate **detail panel** that the page renders when a user
clicks a card:

```html
<section class="show-more-less-html">
  <div class="show-more-less-html__markup ...">
    <the actual description text, with <br> separators and <li> bullets>
  </div>
</section>
```

The captured page had the detail panel open for the "active" card,
so the fixture contains 3 cards + 1 detail panel. The parser
`parse_description` is "detail-panel aware":

- Given a search-result card → returns `None` (cards don't carry
  descriptions).
- Given the detail panel element (the section OR its inner div) →
  returns the text content with `separator=" "` and `strip=True`.

**Chat filter behavior**: the chat filter (POST /jobs/chat) handles
`description=None` for LinkedIn rows gracefully via the
no-assumption rule in the system prompt (REQ-LLM-004). The LLM
matches on `title + company + location` for LinkedIn rows (vs the
full 5-field match for Indeed + InfoJobs rows that DO have
descriptions). Quality is acceptable for v1.

**Future work**: scraping each job's detail page individually would
yield descriptions for all 3 sources at 5-10× the request cost.
Tracked as a separate potential change (`linkedin-job-detail`,
not yet scheduled).

### CORS — POST is now advertised

The CORS middleware was widened (in the `chat-streaming`
change) to advertise **both `GET` and `POST`** in
`Access-Control-Allow-Methods`. The widening is strictly
additive — the v1 GET routes (`/jobs`, `/jobs/linkedin`,
`/jobs/indeed`, `/jobs/infojobs`) are unchanged. A
browser-based client at any origin can now `fetch` POST
to `/jobs/chat` and `/jobs/chat/stream` without a CORS
preflight failure.

## AI Chat Filter — streaming endpoint

`POST /jobs/chat/stream` is a **streaming sibling** of the
JSON `/jobs/chat` endpoint. The client (a browser
`EventSource` or a `fetch` with `ReadableStream`) opens
an SSE connection; the server emits a sequence of events
in real time, then closes. The endpoint is the
recommended choice for any UI that wants a "typewriter"
rendering of the LLM's explanation (the JSON endpoint
returns the full response in 5-8s; the streaming
endpoint pushes the first `text` event in ~1s).

### Event types

The SSE stream emits 4 event types in this order:

| Event     | When                              | Payload                                                  |
| --------- | --------------------------------- | -------------------------------------------------------- |
| `meta`    | 2-stage path only (first event)   | `{"intent": <Intent JSON>}`                              |
| `text`    | One per LLM token                 | `{"delta": "<chunk>"}`                                   |
| `done`    | Terminal (always exactly one)     | `{"jobs":[...], "explanation":"...", "total_considered":N, "total_matched":M, "used_fallback":bool, "request_id":"..."}` |
| `error`   | Mid-stream failure (terminal)     | `{"code": "<machine>", "message": "<reason>"}`           |

The 4 stable `code` values for `error` events are:
`llm_unavailable`, `llm_stream`, `llm_parse`, `llm_timeout`.

The `done.jobs` list is in the **aggregator's** order (NOT
the LLM's emission order — the LLM's order is meaningful
for `text` events only).

### curl example

```bash
curl -N -X POST http://localhost:8000/jobs/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "ingeniero python, Madrid, 3 años"}'

# Output (one event per line; the `:` prefix on a line is an SSE comment):
#
# event: text
# data: {"delta": "He "}
#
# event: text
# data: {"delta": "encontrado "}
#
# event: text
# data: {"delta": "3 ofertas."}
#
# event: done
# data: {"jobs":[...], "explanation": "3 ofertas en Madrid", "total_considered":42, "total_matched":3, "used_fallback":false, "request_id":"abc-123"}
#
```

The response headers include `Content-Type:
text/event-stream`, `Cache-Control: no-cache`,
`Connection: keep-alive`, and `X-Accel-Buffering: no` (the
last disables nginx buffering — see the section below).

### Keepalive

During the stage-2 aggregator wait (typically 2-5s), the
server emits a `: keepalive\n\n` SSE comment every
`SSE_KEEPALIVE_SECONDS` seconds (default 15.0, max 60.0).
Set `SSE_KEEPALIVE_SECONDS=0` to disable keepalives
entirely. Keepalives are NOT emitted between consecutive
`text` events at the LLM's normal emission rate (the
events themselves keep the connection alive).

### v1 path

When `INTENT_EXTRACTION_ENABLED=false` (or no
`IntentExtractor` is injected), the `meta` event is
omitted. The stream is just `text × N → done` — the v1
single-stage behavior, streamed.

## Streaming behind nginx

The streaming endpoint REQUIRES `proxy_buffering off;`
on the nginx location. Without it, nginx buffers the
SSE response and the client sees nothing until the
buffer fills (kilobytes of text), then sees a burst of
`text` events. The `X-Accel-Buffering: no` response
header the server sets is the upstream-side signal
that nginx should respect, but the `proxy_buffering
off;` directive is the canonical configuration.

```nginx
location /jobs/chat/stream {
    proxy_pass http://backend_upstream;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;                # <-- REQUIRED for SSE
    proxy_cache off;
    proxy_read_timeout 600s;            # long LLM calls
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

`proxy_buffering off;` is the critical line. The other
directives are the standard nginx reverse-proxy
configuration. See the [nginx `proxy_buffering`
docs](http://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_buffering)
for the full semantics.

## Manual verification

> **Re-read the Legal Notice above before proceeding.** Scraping LinkedIn
> violates LinkedIn's Terms of Service. This procedure exists to confirm
> the implementation works on a real page; it is **never** executed in
> CI or in the automated test suite. By running it you accept the legal
> risk documented at the top of this README.

The automated test suite is hermetic — it never contacts LinkedIn and
never launches a real browser. The procedure below is the only signal
that the live code path works against a real page, and it is **expected
to break** when LinkedIn changes their DOM or anti-bot surface. The
test suite is not a substitute for this procedure; they verify
different things.

### Prerequisites

- Python 3.12, `uv` installed.
- Network access to `linkedin.com` from the host running the service.

### Procedure

```bash
# 1. Install project dependencies (no Playwright browser yet).
uv sync

# 2. One-time: download the Chromium binary used by Playwright.
#    Skipped by the test suite; required only for the live path.
uv run playwright install chromium

# 3. Start the API. Defaults to 0.0.0.0:8000.
uv run uvicorn jobs_finder.main:app --reload --port 8000
```

In a second terminal, exercise the endpoints:

```bash
# 4. Liveness probe — must return 200 with `{"status":"ok"}` and
#    MUST NOT trigger a browser launch.
curl -i "http://localhost:8000/health"
```

```http
HTTP/1.1 200 OK
content-type: application/json
{"status":"ok"}
```

```bash
# 5. Happy path — must return 200 with `{"jobs": [...]}` and a
#    `X-Request-Id` response header.
#
#    NOTE on the `location` parameter: for accurate geo filtering
#    (no Washington when you search Málaga), use the structured
#    "city, region, country" format that LinkedIn's canonical URL
#    uses. The free-form `location=madrid` returns a noisy mix
#    because LinkedIn falls back to keyword matching.
#
#    Free-form (noisy, but supported):
curl -i "http://localhost:8000/jobs/linkedin?keywords=python&location=madrid"
#
#    Structured (recommended for production clients):
curl -i --get "http://localhost:8000/jobs/linkedin" \
    --data-urlencode "keywords=python" \
    --data-urlencode "location=Málaga, Andalucía, Spain"
```

```http
HTTP/1.1 200 OK
content-type: application/json
x-cache: MISS
x-request-id: <uuid-or-your-trace-id>

{
  "jobs": [
    {
      "id": "3850000001",
      "title": "Senior Python Developer",
      "company": "Acme Corp",
      "location": "Madrid, Spain",
      "url": "https://www.linkedin.com/jobs/view/3850000001/",
      "posted_at": "2026-05-01T00:00:00+00:00"
    }
  ]
}
```

The first call returns `X-Cache: MISS` (the Playwright scraper was
invoked). Repeating the exact same query within the TTL window
(default 60s) returns `X-Cache: HIT` and the cached `list[Job]`
without launching a browser. See the "Caching" section above.

```bash
# 6. Trigger a 502. Two reproducible ways to do it:
#
#    a) Temporarily point the scraper at a URL that always returns
#       the auth wall (e.g. by setting LINKEDIN_REQUEST_TIMEOUT_MS=1
#       so the wait-for-selector times out and the scraper raises
#       LinkedInTimeoutError, which is a JobSearchError → 502).
LINKEDIN_REQUEST_TIMEOUT_MS=1 uv run uvicorn jobs_finder.main:app --port 8000
curl -i "http://localhost:8000/jobs/linkedin?keywords=python&location=madrid"
```

```http
HTTP/1.1 502 Bad Gateway
content-type: application/json
x-request-id: <uuid-or-your-trace-id>

{
  "detail": "upstream source unavailable",
  "request_id": "<same-uuid-as-x-request-id>"
}
```

The body's `request_id` MUST equal the `X-Request-Id` response header.
The body's `detail` MUST be the literal string
`"upstream source unavailable"` — the underlying exception type
(`LinkedInTimeoutError`, `LinkedInBlockedError`, ...) is masked.

### LinkedIn pagination

`GET /jobs/linkedin` auto-paginates `start=0, 25, 50, ...` per page
up to `max_pages` total requests (REQ-L-007). The default
`max_pages=10` and `inter_page_delay_seconds=1.0` are mirrored from
the Indeed scraper so all three sources behave consistently.

| Env var | Type | Default | Effect |
| --- | --- | --- | --- |
| `LINKEDIN_MAX_PAGES` | int | `10` | Hard cap on pages per `search()`. Set to `1` for the v0 single-page behavior; raise it to drain longer result streams. |
| `LINKEDIN_INTER_PAGE_DELAY_SECONDS` | float | `1.0` | Pacing between pages to reduce the chance of LinkedIn's anti-bot re-challenging the 2nd+ request. Set to `0.0` to skip the sleep entirely. |

#### `geoId` plumb (REQ-LOC-001)

The LinkedIn scraper resolves `location="malaga"` (free-form
string) to `geoId=104401670` (the captured LinkedIn numeric ID)
via the `HardcodedLocationResolver` injected into the
`LinkedInScraperSettings` at composition time. The URL builder
emits `?keywords=...&geoId=<n>&start=...` (the LinkedIn-correct
form) instead of `?keywords=...&location=<str>&start=...`
(the v0 broken-but-doesn't-500 form LinkedIn silently ignores).
The resolver is a read-only in-process dict lookup; the
34-entry `_CANONICAL_MAPPING` in
`infrastructure/location/_mapping.py` lists every supported
location. Unknown locations (country-level, País Vasco, Canarias,
empty string) return `None` and the scraper falls back to
`?location=<str>` — a strict improvement over the v0
100%-broken behavior (no regression for unknown locations).

#### LinkedIn structured location fallback (REQ-STR-LOC-001)

For cities NOT in the 34-entry `_CANONICAL_MAPPING` (no captured
`geoId`), the v0 path falls back to `?location=<raw_string>` —
which LinkedIn silently ignores, returning globally-distributed
results. The user captured a real LinkedIn URL showing a third
supported format: `?location=<city>,<province>,<country>`. The
scraper consults a second method on the resolver
(`resolve_structured()`) and uses the structured triplet when
the city has a mapping. **The HTTP contract is unchanged**: the
frontend sigue enviando `location=<raw>`; el resolver convierte
internamente.

##### Priority order

```
1. geo_id is not None    → ?keywords=...&geoId=<n>&start=...    (LinkedIn-preferred)
2. structured is not None → ?keywords=...&location=quote(city,province,country)&start=...  (NEW)
3. both None             → ?keywords=...&location=<raw>&start=...  (legacy fallback)
```

##### The 10-city `_STRUCTURED_MAPPING` (v1)

| City | Province | Country | Status |
|------|----------|---------|--------|
| `antequera` | Andalucía | Spain | **VERIFIED** (LIVE test gated `LLM_LIVE_TESTS=1`) |
| `fuengirola` | Málaga | Spain | SPECULATIVE (pending LIVE test) |
| `marbella` | Málaga | Spain | SPECULATIVE |
| `toledo` | Castilla-La Mancha | Spain | SPECULATIVE |
| `salamanca` | Castilla y León | Spain | SPECULATIVE |
| `cadiz` | Cádiz / Andalucía | Spain | SPECULATIVE |
| `granada` | Andalucía | Spain | SPECULATIVE |
| `gijon` | Asturias | Spain | SPECULATIVE |
| `leon` | Castilla y León | Spain | SPECULATIVE |
| `vigo` | Galicia | Spain | SPECULATIVE |

**Important**: `Madrid` is in `_CANONICAL_MAPPING` (geoId) and
is intentionally EXCLUDED from `_STRUCTURED_MAPPING` — the
geoId is LinkedIn's preferred form and always wins
(`geoId > structured > raw`).

##### Live test gate

The structured format is validated by a gated LIVE test in
`tests/integration/test_linkedin_live.py`. The test is SKIPPED
in CI per AGENTS.md rule #1 ("no live scraping in tests").
To run the LIVE probe manually:

```bash
LLM_LIVE_TESTS=1 uv run pytest tests/integration/test_linkedin_live.py -v
```

If a SPECULATIVE city fails the LIVE test, remove it from
`_STRUCTURED_MAPPING` (1-line change, 0 LOC). The scraper
falls back to the legacy `?location=<raw>` path — no code
changes required.

#### Curl smoke test

After `uv run uvicorn jobs_finder.main:app --port 8000` is running,
exercise the paginated path against a real page (LinkedIn is the
only source for which a live smoke test is in the spec):

```bash
# Start the server first (in another terminal):
uv run uvicorn jobs_finder.main:app --host 0.0.0.0 --port 8000 &

# Body curl — must return >= 25 jobs (one full page, ~25 cards).
curl -sS 'http://localhost:8000/jobs/linkedin?keywords=python&location=madrid&limit=30' | head -c 4000

# Header curl — first call MUST carry `X-Cache: MISS` (cache is cold).
curl -sSI 'http://localhost:8000/jobs/linkedin?keywords=python&location=madrid&limit=30' | grep -i x-cache

# Second call MUST carry `X-Cache: HIT` (cache layer + pagination
# coexist correctly — the cached first-page result is returned
# without re-navigating).
curl -sSI 'http://localhost:8000/jobs/linkedin?keywords=python&location=madrid&limit=30' | grep -i x-cache

# Kill the server when done:
kill %1
```

If the body returns 0 jobs OR the headers lack `X-Cache: MISS`, the
live path is broken from your IP (LinkedIn anti-bot, rate limit, or
DOM drift). See "When the live path breaks" below.

### When the live path breaks

If step 5 returns `200 {"jobs": []}` and the HTML is the auth wall, the
live page structure has changed from the fixture. The maintenance
burden is yours from this point on:

1. Open `src/jobs_finder/infrastructure/linkedin/parsers.py` and update
   the private selector constants (`_TITLE_SELECTOR`,
   `_COMPANY_SELECTOR`, etc.) and any per-field parser that depends on
   the old DOM.
2. Open `tests/fixtures/linkedin_search.py` and replace the inline
   `SEARCH_PAGE_HTML` and `BLOCK_PAGE_HTML` literals with a fresh
   recording from a real browser session.
3. Re-run `uv run pytest` — every parser and scraper test must pass
   against the new fixture.
4. Retry step 5 above.

The automated test suite cannot catch a live DOM drift; only this
manual procedure can.

## Manual verification — Indeed

> **Re-read the Legal Notice — Indeed above before proceeding.**
> Scraping Indeed violates Indeed's Terms of Service. This procedure
> exists to confirm the implementation works on a real page; it is
> **never** executed in CI or in the automated test suite. By running
> it you accept the legal risk documented at the top of this README.

The automated test suite is hermetic — it never contacts Indeed and
never launches a real browser. The procedure below is the only signal
that the live code path works against a real page, and it is **expected
to break** when Indeed changes their DOM, swaps the card class name,
or serves a Cloudflare challenge to your IP. The test suite is not a
substitute for this procedure; they verify different things.

### Prerequisites

- Python 3.12, `uv` installed.
- Network access to `es.indeed.com` (or the configured `INDEED_DOMAIN`)
  from the host running the service. Indeed serves a Cloudflare
  anti-bot challenge to many datacenter / VPS IP ranges; if you hit
  one, the live path returns 502 and there is no in-software bypass
  by design (see REQ-I-016).

### Procedure

```bash
# 1. Install project dependencies (no Playwright browser yet).
uv sync

# 2. One-time: download the Chromium binary used by Playwright.
#    Skipped by the test suite; required only for the live path.
#    The same browser binary is shared with the LinkedIn live path.
uv run playwright install chromium

# 3. Start the API. Defaults to 0.0.0.0:8000.
#    The composition root builds BOTH the LinkedIn and the Indeed
#    scrapers in the default branch; the lifespan opens BOTH browsers
#    on startup. To point at a different locale, set INDEED_DOMAIN
#    (e.g. INDEED_DOMAIN=uk.indeed.com for the UK SERP).
uv run uvicorn jobs_finder.main:app --reload --port 8000
```

In a second terminal, exercise the endpoint:

```bash
# 4. Liveness probe — must return 200 with `{"status":"ok"}` and
#    MUST NOT trigger an Indeed browser launch.
curl -i "http://localhost:8000/health"
```

```http
HTTP/1.1 200 OK
content-type: application/json
{"status":"ok"}
```

```bash
# 5. Happy path — must return 200 with `{"jobs": [...]}` and a
#    `X-Request-Id` response header. Indeed uses `l` (lowercase L) as
#    the location query parameter, NOT `location`. The example below
#    mirrors Indeed's canonical URL pattern.
#
#    If the live page returns a Cloudflare challenge (you'll see a
#    502 with `{"detail":"upstream source unavailable"}` and no jobs),
#    the live path is blocked from your IP — `playwright-stealth`
#    reduces the challenge frequency but is not a guarantee (see
#    the stealth note at the end of this section). Try from a
#    residential IP, or skip the live verify and rely on the parser
#    unit tests (which run against a captured HTML fixture).
curl -i "http://localhost:8000/jobs/indeed?keywords=python&l=madrid&limit=20"
```

```http
HTTP/1.1 200 OK
content-type: application/json
x-cache: MISS
x-request-id: <uuid-or-your-trace-id>

{
  "jobs": [
    {
      "id": "dd6cc0f5b0f0cfc9",
      "title": "Desarrollador Python Junior (Madrid) | Sigma AI",
      "company": "Sigma Group",
      "location": "Madrid, Madrid provincia",
      "url": "https://es.indeed.com/viewjob?jk=dd6cc0f5b0f0cfc9",
      "posted_at": "2025-09-24T05:00:00+00:00"
    }
  ]
}
```

The first call returns `X-Cache: MISS` (Playwright invoked). Repeating
the same query within the TTL window returns `X-Cache: HIT` without a
browser launch. The Indeed cache is independent of the LinkedIn +
InfoJobs caches.

`posted_at` is read from the document-level
`mosaic-provider-jobcards` JSON blob (epoch-ms `pubDate` per
result), matched by the card's `data-jk`. The legacy
`span.date` relative-time grammar is preserved as a fallback
for older fixtures and any future DOM that re-renders inline
dates. Indeed cards that do not have a matching record in the
JSON fall back to `datetime.now(UTC)` (the scrape second).

```bash
# 6. Trigger a 502. Two reproducible ways to do it:
#
#    a) Force a timeout so the scraper's `wait_for_selector` expires
#       (the scraper raises `IndeedTimeoutError`, which the
#       exception handler maps to 502).
INDEED_TIMEOUT_MS=1 uv run uvicorn jobs_finder.main:app --port 8000
curl -i "http://localhost:8000/jobs/indeed?keywords=python&l=madrid"
```

```http
HTTP/1.1 502 Bad Gateway
content-type: application/json
x-request-id: <uuid-or-your-trace-id>

{
  "detail": "upstream source unavailable",
  "request_id": "<same-uuid-as-x-request-id>"
}
```

The body's `request_id` MUST equal the `X-Request-Id` response header.
The body's `detail` MUST be the literal string
`"upstream source unavailable"` — the underlying exception type
(`IndeedTimeoutError`, `IndeedBlockedError`, `IndeedParseError`) is
masked.

### When the live path breaks

If step 5 returns `200 {"jobs": []}` and the HTML is the Cloudflare
challenge page, or if the page structure has changed from the fixture,
the maintenance burden is yours from this point on:

1. Open `src/jobs_finder/infrastructure/indeed/parsers.py` and update
   the private selector constants (`_TITLE_SELECTOR`,
   `_COMPANY_SELECTOR`, `_DATE_SELECTOR`, etc.) and any per-field
   parser that depends on the old DOM.
2. Open `tests/fixtures/indeed_search.py` and replace the inline
   `SEARCH_PAGE_HTML` literal with a fresh recording from a real
   browser session. The `BLOCKED_PAGE_HTML` constant should be
   kept (it's a synthetic Cloudflare challenge for the
   `is_indeed_blocked` tests).
3. Re-run `uv run pytest tests/unit/test_indeed_parsers.py` —
   every parser test must pass against the new fixture. If a
   relative-time string the parser doesn't recognise appears in
   the capture, extend the grammar in `_parse_relative_date`
   (the parser is intentionally narrow so unknown shapes fail
   closed).
4. Retry step 5 above.

The automated test suite cannot catch a live DOM drift; only this
manual procedure can. The scraper uses
[`playwright-stealth`](https://pypi.org/project/playwright-stealth/)
to bypass Cloudflare's bot detection; ensure Chromium is installed
via `uv run playwright install chromium`. The capture script used to
refresh the parser fixture lives in `/tmp/capture_indeed.py` (NOT
committed) and is regenerated from a residential IP when the live
DOM drifts.

## Manual verification — InfoJobs

> **Re-read the Legal Notice — InfoJobs above before proceeding.**
> Scraping InfoJobs violates InfoJobs's Terms of Service. This
> procedure exists to confirm the implementation works on a real
> page; it is **never** executed in CI or in the automated test
> suite. By running it you accept the legal risk documented at the
> top of this README.

The automated test suite is hermetic — it never contacts InfoJobs
and never launches a real browser. The procedure below is the only
signal that the live code path works against a real page, and it is
**expected to break** when InfoJobs changes their DOM, swaps the
card class name, or serves a Distil/Geetest challenge to your IP.
The test suite is not a substitute for this procedure; they verify
different things.

### Prerequisites

- Python 3.12, `uv` installed.
- Network access to `www.infojobs.net` from the host running the
  service. InfoJobs is protected by **Distil Networks** (browser
  fingerprinting) and **Geetest** (captcha challenge); many
  datacenter and VPS IP ranges are blocked at the first request.
  If you hit one, the live path returns 502 and there is no
  in-software bypass by design (see REQ-J-002 + REQ-J-005).
- The same Chromium binary is shared with the LinkedIn + Indeed
  live paths.

### Procedure

```bash
# 1. Install project dependencies (no Playwright browser yet).
uv sync

# 2. One-time: download the Chromium binary used by Playwright.
#    Skipped by the test suite; required only for the live path.
uv run playwright install chromium

# 3. Start the API. Defaults to 0.0.0.0:8000.
#    The composition root builds ALL THREE scrapers in the default
#    branch (LinkedIn + Indeed + InfoJobs); the lifespan opens all
#    three browsers on startup. Stealth is wired for the InfoJobs
#    scraper (unlike the LinkedIn one).
uv run uvicorn jobs_finder.main:app --reload --port 8000
```

In a second terminal, exercise the endpoint:

```bash
# 4. Liveness probe — must return 200 with `{"status":"ok"}` and
#    MUST NOT trigger an InfoJobs browser launch.
curl -i "http://localhost:8000/health"
```

```http
HTTP/1.1 200 OK
content-type: application/json
{"status":"ok"}
```

```bash
# 5. Happy path — must return 200 with `{"jobs": [...]}` and a
#    `X-Request-Id` response header. InfoJobs's public SERP uses
#    query-string parameters: `?q=<keywords>&l=<location>&page=<N>`
#    (1-indexed). The path-based form is blocked by Distil.
#
#    If the live page returns a Distil/Geetest challenge (you'll
#    see a 502 with `{"detail":"upstream source unavailable"}` and
#    no jobs), the live path is blocked from your IP. `Stealth()`
#    is already wired in production but it's not a guarantee.
#    Try from a residential IP, or skip the live verify and rely
#    on the parser unit tests (which run against a captured HTML
#    fixture).
curl -i "http://localhost:8000/jobs/infojobs?keywords=python&location=madrid&limit=20"
```

```http
HTTP/1.1 200 OK
content-type: application/json
x-cache: MISS
x-request-id: <uuid-or-your-trace-id>

{
  "jobs": [
    {
      "id": "abc123def",
      "title": "Desarrollador/a Python",
      "company": "Empresa Demo S.L.",
      "location": "Madrid, Madrid provincia",
      "url": "https://www.infojobs.net/ofertas-trabajo/oferta-abc123def",
      "posted_at": "2026-06-02T17:00:00+00:00"
    }
  ]
}
```

The first call returns `X-Cache: MISS` (Playwright invoked). Repeating
the same query within the TTL window returns `X-Cache: HIT` without a
browser launch. The InfoJobs cache is independent of the LinkedIn +
Indeed caches.

```bash
# 6. Trigger a 502 (Distil/Geetest challenge is also a valid
#    trigger). Two reproducible ways:
#
#    a) Force a timeout so the scraper's `wait_for_selector` expires
#       (the scraper raises `InfoJobsTimeoutError`, which the
#       exception handler maps to 502).
INFOJOBS_TIMEOUT_MS=1 uv run uvicorn jobs_finder.main:app --port 8000
curl -i "http://localhost:8000/jobs/infojobs?keywords=python&location=madrid"
```

```http
HTTP/1.1 502 Bad Gateway
content-type: application/json
x-request-id: <uuid-or-your-trace-id>

{
  "detail": "upstream source unavailable",
  "request_id": "<same-uuid-as-x-request-id>"
}
```

The body's `request_id` MUST equal the `X-Request-Id` response header.
The body's `detail` MUST be the literal string
`"upstream source unavailable"` — the underlying exception type
(`InfoJobsTimeoutError`, `InfoJobsBlockedError`, `InfoJobsParseError`)
is masked.

### When the live path breaks

If step 5 returns `200 {"jobs": []}` and the HTML is a Distil/Geetest
challenge (page title `"No podemos identificar tu navegador"`), the
request is being blocked from your IP. The maintenance burden is
yours from this point on:

1. Open `src/jobs_finder/infrastructure/infojobs/parsers.py` and
   update the private selector constants (`_CARD_SELECTOR`,
   `_TITLE_SELECTOR`, etc.) and any per-field parser that depends
   on the old DOM.
2. Open `tests/fixtures/infojobs_search.py` and replace the inline
   `SEARCH_PAGE_HTML` literal with a fresh recording from a real
   browser session. The `BLOCKED_PAGE_HTML` constant should be
   kept (it's a synthetic Distil/Geetest challenge for the
   `is_infojobs_blocked` tests).
3. Re-run `uv run pytest tests/unit/test_infojobs_parsers.py` —
   every parser test must pass against the new fixture.
4. Retry step 5 above.

The automated test suite cannot catch a live DOM drift; only this
manual procedure can. The scraper uses
[`playwright-stealth`](https://pypi.org/project/playwright-stealth/)
to bypass Distil/Geetest; ensure Chromium is installed via
`uv run playwright install chromium`. The capture script used to
refresh the parser fixture lives in `/tmp/capture_infojobs.py` (NOT
committed) and is regenerated from a residential IP when the live
DOM drifts.
