# jobs-finder

> On-demand **LinkedIn** + **Indeed** job search HTTP endpoints, built with
> FastAPI + Playwright. **Educational / personal use only.** Read the Legal
> Notices below before running anything.

## Sources

| Endpoint | Source | Backed by |
| --- | --- | --- |
| `GET /jobs/linkedin` | `linkedin.com/jobs/search` | `LinkedInPlaywrightScraper` (closed source) |
| `GET /jobs/indeed`   | `es.indeed.com/jobs`     | `IndeedPlaywrightScraper` (closed source) |

Each source has its own Legal Notice and Manual Verification procedure —
read them both before running.

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

## What this is

`jobs-finder` is a multi-source job-search engine. On each request, the
relevant route launches a headless Chromium browser via Playwright,
navigates to the upstream source's public job search, parses the result
cards, and returns structured JSON. It is bootstrapped as a hexagonal
Python project (domain / application / infrastructure / presentation) so
additional job sources (InfoJobs, etc.) and a frontend can be added in
follow-up changes without rewrites.

### CORS — development default is `*`; override for production

`Settings.cors_allow_origins` defaults to `["*"]` so a browser-based dev
client can call the API without extra wiring. **This is NOT safe for
production.** Set the `LINKEDIN_CORS_ALLOW_ORIGINS` env var to a
comma-separated allowlist before exposing the service publicly, e.g.

```bash
LINKEDIN_CORS_ALLOW_ORIGINS="https://app.example.com,https://admin.example.com" \
  uv run uvicorn jobs_finder.main:app --port 8000
```

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
#    the live path is blocked from your IP — the suite cannot bypass
#    this by design. Try from a residential IP, or skip the live
#    verify and rely on the parser unit tests (which run against
#    a captured HTML fixture).
curl -i "http://localhost:8000/jobs/indeed?keywords=python&l=madrid&limit=20"
```

```http
HTTP/1.1 200 OK
content-type: application/json
x-request-id: <uuid-or-your-trace-id>

{
  "jobs": [
    {
      "id": "100000001",
      "title": "Senior Python Developer",
      "company": "Acme Corp",
      "location": "Madrid, Spain",
      "url": "https://es.indeed.com/viewjob?jk=100000001",
      "posted_at": "2026-05-01T00:00:00+00:00"
    }
  ]
}
```

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
manual procedure can. **Future work**: consider adding
`playwright-stealth` as a follow-up change to reduce Cloudflare
challenge frequency — the v1 scraper intentionally does not include
it (REQ-I-016) so the live failure mode is observable.
