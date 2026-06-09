# AGENTS.md

> Operating manual for humans and AI agents working on `jobs-finder`.
> Read this **first** before running commands, writing code, or making commits.

## Workspaces

This is a monorepo with independent workspaces. Every command that
acts on a workspace is run from **inside that workspace** (usually
`cd backend` or `cd frontend`). The root has no `pyproject.toml` or
`package.json` of its own — there is no "top-level" install.

| Workspace   | Stack                    | Tooling entry point        |
| ----------- | ------------------------ | -------------------------- |
| `backend/`  | Python 3.12 · FastAPI    | `backend/pyproject.toml`   |
| `frontend/` | _not chosen yet_         | _TBD_                      |

## Stack (backend)

The tools below are installed in the backend workspace **right now**
(see `backend/pyproject.toml` for exact pins). Do not claim future
state as if it were shipped — the backend README "Manual
verification" section and the SDD tasks track what is real vs. what
is planned.

| Tool             | Version  | Purpose                                  |
| ---------------- | -------- | ---------------------------------------- |
| Python           | 3.12     | Runtime (see `backend/.python-version`). |
| uv               | >= 0.4   | Package manager and virtualenv.          |
| pytest           | >= 8.0   | Test runner.                             |
| pytest-asyncio   | >= 0.23  | Async test support.                      |
| httpx            | >= 0.27  | In-process API tests.                    |
| Playwright       | >= 1.45  | Headless Chromium driver (scraper).      |
| FastAPI          | >= 0.111 | HTTP framework.                          |
| uvicorn          | >= 0.30  | ASGI server.                             |
| pydantic         | >= 2.7   | Schemas and validation.                  |
| pydantic-settings| >= 2.0   | Env-driven configuration.                |
| mypy             | >= 1.10  | Static type checking (`--strict`).       |
| ruff             | >= 0.5   | Lint + format.                           |

## Project layout

```
jobs-finder/
├── .gitignore
├── AGENTS.md            # this file
├── README.md            # workspace index + Legal Notice
├── backend/             # Python 3.12, FastAPI, Playwright
│   ├── .env.example     # template — copy to `backend/.env` for local dev
│   ├── .python-version
│   ├── pyproject.toml   # PEP 621 metadata + tool config
│   ├── scripts/
│   │   └── check.sh     # local CI: ruff + mypy + pytest
│   ├── src/
│   │   └── jobs_finder/ # src layout, imported as `jobs_finder`
│   │       ├── __init__.py
│   │       ├── main.py                 # composition root + uvicorn entry
│   │       ├── domain/                 # Job value object, base exceptions
│   │       ├── application/            # JobSearchPort, CachePort, use cases, DTOs
│   │       │   └── usecases/           # one use case file per source + cached wrapper
│   │       ├── infrastructure/         # Playwright scrapers, parsers, throttle, cache
│   │       │   ├── linkedin/           # LinkedInPlaywrightScraper + parsers
│   │       │   ├── indeed/             # IndeedPlaywrightScraper + parsers
│   │       │   ├── infojobs/           # InfoJobsPlaywrightScraper + parsers
│   │       │   └── cache/              # InMemoryTTLCache primitive
│   │       └── presentation/           # FastAPI app, routes, middleware, schemas
│   │           └── routes/             # one route file per source (linkedin, indeed, infojobs) + aggregator
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── fixtures/                   # inline HTML for parser tests
│   │   ├── unit/                       # parsers, throttle, use case, scraper, exceptions, cache
│   │   └── integration/                # FastAPI app + composition root + X-Cache headers
│   ├── uv.lock
│   └── README.md        # full backend documentation
└── frontend/            # placeholder; README only for now
```

### Workspace-local `.env` files

Each workspace reads its own env vars from a workspace-local `.env`.
There is no shared `.env` at the repo root because the two
workspaces will (eventually) read different env vars with different
shapes — the backend uses `pydantic-settings` (`backend/.env`),
the frontend will use whatever its framework provides
(`frontend/.env` or `frontend/.env.local`).

- `backend/.env.example` is the **template** for backend env vars.
  Copy it to `backend/.env` to run the backend locally.
  `backend/.env` is git-ignored.
- `frontend/.env.example` will be added when a frontend stack is
  chosen.

The dependency rule is
`presentation → application → domain ← infrastructure`. `application/`
must not import `infrastructure/` or `presentation/`. Each source
(`linkedin`, `indeed`, `infojobs`) has its own sub-package under
`infrastructure/` and its own route file under `presentation/routes/`,
mirrored by per-source fixtures under `tests/fixtures/`.

### Caching

The composition root (`app_factory.build_app()`) wraps each source's
raw use case in a `CachedJobSearchUseCase` backed by an
`InMemoryTTLCache`. The 3 source caches are independent (the cache
key includes the source name). Each route sets an `X-Cache: HIT|MISS`
response header from the use case's `SearchResult.cache_status.value`.
The TTL is controlled by the `CACHE_TTL_SECONDS` env var (default
`60.0`); setting it to `0` disables the cache. See the README
"Caching" section for the full contract.

### LinkedIn pagination env vars

The LinkedIn scraper auto-paginates `start=0, 25, 50, ...` per
`search()` call (REQ-L-007). The two new env vars
`LINKEDIN_MAX_PAGES` (default `10`) and
`LINKEDIN_INTER_PAGE_DELAY_SECONDS` (default `1.0`) cap the loop
and pace the per-page requests. See the README "LinkedIn pagination"
subsection for the curl smoke test.

### Shared pagination helper

All three source scrapers (LinkedIn, Indeed, InfoJobs) drive the
same auto-pagination loop through a single helper at
`src/jobs_finder/infrastructure/pagination.py` named
`paginated_search`. The helper is a free function (not a base
class) so each scraper remains the source of truth for its own
per-source concerns; the helper owns ONLY the loop control flow.

The signature has **7 keyword-only params**:

```python
async def paginated_search(
    *,
    page: Any,                                              # Playwright page (caller owns lifecycle)
    throttle: Any,                                          # async CM acquired ONCE around the loop
    fetch_one_page: Callable[[Any, int, int], Awaitable[list[Job]]],
    limit: int,
    max_pages: int,
    inter_page_delay_seconds: float,
    timeout_exc_type: type[Exception],
) -> list[Job]:
```

The helper:

- acquires the throttle once around the whole loop
  (`async with throttle:`), so consecutive `search()` calls are
  paced by the throttle's `min_interval_seconds` while the page
  requests within one search are back-to-back;
- caps the loop at `max_pages` and at `len(jobs) >= limit`;
- awaits `asyncio.sleep(inter_page_delay_seconds)` before each
  page > 0 (page 0 is never delayed; `0.0` skips the call);
- catches `timeout_exc_type` (raise on page 0, break on page > 0);
- breaks on any empty `[]` from the closure (end-of-results);
- does **not** catch any other exception (`*BlockedError`,
  `*ParseError`, etc. propagate unchanged).

The helper does NOT import Playwright; the page arg is `Any` so
the helper can stay source-agnostic and the unit tests can drive
it with a sentinel object.

#### Per-source `_make_fetch_one_page(keywords, location)` factory

Each scraper contributes a small private method that returns a
closure capturing the source-specific concerns. The closure
receives `(page, page_index, remaining)` from the helper and
returns the per-page `list[Job]`.

| Source | URL formula | Blocked check | `_parse_cards` arity | Page-0 zero-cards |
|---|---|---|---|---|
| LinkedIn | `start=page_index * 25` | `is_block_page(soup)` | `(soup, remaining)` (2-arg) | **Break silently** |
| Indeed | `start=page_index * 10` | `is_indeed_blocked(soup)` | `(soup, remaining, domain)` (3-arg) | Raise `IndeedParseError("zero_cards_on_first_page")` |
| InfoJobs | `page=page_index + 1` | `is_infojobs_blocked(soup)` | `(soup, remaining, domain)` (3-arg) | Raise `InfoJobsParseError("zero_cards_on_first_page")` |

The factory method pattern (a `Callable` returned from
`_make_fetch_one_page(keywords, location)`) keeps the source's
imports localized: `is_X_blocked`, the source-specific exception
types, and `_parse_cards` arity all live in the closure's
captured scope.

#### How to add a 4th source

Five steps to wire a new source (e.g. `Glassdoor`) into the
shared pagination loop:

1. **Create the source sub-package** under
   `src/jobs_finder/infrastructure/<source>/` with the standard
   layout: `exceptions.py` (3 subclasses of `JobSearchError`:
   `*TimeoutError`, `*BlockedError`, `*ParseError`),
   `parsers.py` (pure functions: `is_<source>_blocked`,
   `parse_<source>_title`, `parse_<source>_company`, etc.),
   `throttle.py` (an `AsyncThrottle` subclass for serialization),
   and `scraper.py` (`<Source>ScraperSettings` with
   `__slots__`/`__eq__`/`__hash__`/`__repr__` +
   `<Source>PlaywrightScraper(JobSearchPort)`).

2. **Implement the source's `search()` method** by mirroring
   the Indeed / InfoJobs pattern: open a fresh context + page
   in the source's `search()`, then `return await
   paginated_search(page=page, throttle=self._throttle,
   fetch_one_page=self._make_fetch_one_page(keywords, location),
   limit=limit, max_pages=self._settings.max_pages,
   inter_page_delay_seconds=self._settings.inter_page_delay_seconds,
   timeout_exc_type=<Source>TimeoutError)`. The helper acquires
   the throttle (no outer `async with self._throttle:` in
   `search()`).

3. **Implement `_make_fetch_one_page(self, keywords, location)
   -> Callable[[Any, int, int], Awaitable[list[Job]]]`** as a
   closure that captures the source's URL formula,
   `is_<source>_blocked`, `_parse_cards(soup, remaining[, domain])`,
   and the page-0 zero-cards raise semantic. If the source
   should "break silently" on page-0 zero-cards (LinkedIn's
   contract), omit the page-0 zero-cards check; if it should
   raise (Indeed / InfoJobs's contract), raise the source's
   `*ParseError`.

4. **Add the source's settings fields** to
   `src/jobs_finder/infrastructure/config.py` with
   `validation_alias=AliasChoices("<SOURCE>_MAX_PAGES",
   "<source>_max_pages")` (and the same for
   `inter_page_delay_seconds`). Wire the new fields through
   `app_factory.build_app()` into `<Source>ScraperSettings(...)`.

5. **Add the source's per-page test suite** under
   `tests/unit/test_<source>_scraper.py` covering the URL
   formula, the blocked check, the page-0 zero-cards semantic
   (raise vs break), the inter-page delay, and the max_pages /
   limit cap. The shared `paginated_search` is exercised by
   `tests/unit/test_pagination.py`; the per-source tests are
   the regression check for the per-source closure.

Do NOT re-implement the pagination loop inline; the helper is
the canonical implementation. If a source needs behavior the
helper doesn't support (e.g. backoff, retry, concurrency), open
a follow-up change to extend the helper — don't bypass it.

## How to run

All backend commands are run from `backend/` and use `uv` (NOT `pip`,
NOT `poetry`).

```bash
# Install dependencies into a project-local virtualenv
cd backend
uv sync

# Run the test suite
uv run pytest

# Static type check (strict)
uv run mypy

# Lint
uv run ruff check

# Format check
uv run ruff format --check
```

## Pre-commit

Run `backend/scripts/check.sh` before every commit. CI runs the same
commands (`ruff check`, `ruff format --check`, `mypy`, `pytest`). Do
not commit if any check fails.

## Conventions

1. **No live scraping in tests — covers LinkedIn, Indeed, AND InfoJobs.**
   The end-to-end live paths are documented in the backend README
   "Manual verification" sections (one per source), but they are
   **never** executed in CI or in the automated test suite. Parser
   tests use inline HTML fixtures
   (`backend/tests/fixtures/linkedin_search.py`,
   `backend/tests/fixtures/indeed_search.py`, and
   `backend/tests/fixtures/infojobs_search.py`). The only sanctioned
   exception is the one-time Playwright capture of `es.indeed.com`
   performed manually during a follow-up test- fixture refresh — that
   capture is NEVER run in CI; the captured HTML is committed to the
   fixture file and the rest of the suite re-runs offline against the
   new capture.
2. **Use `uv`, not `pip` or `poetry`.** All Python dependency operations
   go through `cd backend && uv sync` and `cd backend && uv run ...`.
3. **Src layout only — within `backend/`.** Production code lives
   under `backend/src/jobs_finder/`. Never add modules at the repo
   root or at `backend/` directly (no loose `.py` files next to
   `pyproject.toml`).
4. **No business logic in `__init__.py`.** `__init__.py` files may
   contain a module docstring and nothing else.
   Domain/application/infrastructure code goes in its own module.
5. **One commit per work unit.** A commit represents a deliverable
   behavior, not a file type. Tests and docs ship with the code they
   verify or describe.
6. **Conventional commits.** Format: `<type>(<scope>): <subject>`. Do
   **not** add `Co-Authored-By:` or any AI attribution trailer.
7. **No secrets in the repo.** `li_at` cookies, proxy credentials, or
   any LinkedIn / Indeed authentication material are explicitly
   forbidden by the spec.
