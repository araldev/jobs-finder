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

The `X-Cache` header is additive — the JSON response body is unchanged.
A `HIT` collapses a 2-15s Playwright round-trip into a sub-millisecond
dict lookup; see "Caching" below.

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
`CachedJobSearchUseCase` backed by an in-memory `InMemoryTTLCache` with
absolute TTL semantics. The first call invokes the Playwright scraper
and stores the result (`X-Cache: MISS`); every subsequent identical
query within the TTL window returns the cached `list[Job]` without
launching a browser (`X-Cache: HIT`).

The TTL is controlled by the `CACHE_TTL_SECONDS` env var (default `60.0`).
Set `CACHE_TTL_SECONDS=0` to disable caching (every call is a miss).
The 3 source caches are independent (a LinkedIn HIT does not affect
Indeed or InfoJobs) — the cache key includes the source name.

```bash
# Default: 60s TTL. A frontend SPA refreshing every 5s collapses
# 12 requests into 1.
uv run uvicorn jobs_finder.main:app --port 8000

# 5-minute cache (longer absorption window, more stale-data risk).
CACHE_TTL_SECONDS=300 uv run uvicorn jobs_finder.main:app --port 8000

# Cache disabled (every call hits the upstream source).
CACHE_TTL_SECONDS=0 uv run uvicorn jobs_finder.main:app --port 8000
```

Caveats: the cache is in-memory (no cross-process / cross-host sharing,
no survival of process restart) and best-effort (two concurrent misses
for the same key can cause two scraper calls; a future change can add
`asyncio.Lock`-per-key for single-flight). Errors (502) are NOT cached
so a transient Distil/Cloudflare block doesn't poison the cache.

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

```bash
# 1. Install dependencies into a project-local virtualenv
uv sync

# 2. Run the test suite (no network, no Chromium)
uv run pytest

# 3. Static type check
uv run mypy

# 4. Lint
uv run ruff check

# 5. Format check
uv run ruff format --check
```

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

### Examples

```bash
# Default: aggregate all 3 sources, deduped
curl -i "http://localhost:8000/jobs?q=python&location=madrid&limit=20"
# X-Cache: MISS,MISS,MISS (first call)
# X-Aggregator-Sources: linkedin,indeed,infojobs
# X-Aggregator-Errors: (absent)

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
      "posted_at": "2026-06-02T17:00:00+00:00"
    }
  ]
}
```

The first call returns `X-Cache: MISS` (Playwright invoked). Repeating
the same query within the TTL window returns `X-Cache: HIT` without a
browser launch. The Indeed cache is independent of the LinkedIn +
InfoJobs caches.

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
