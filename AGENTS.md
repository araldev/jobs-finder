# AGENTS.md

> Operating manual for humans and AI agents working on `jobs-finder`.
> Read this **first** before running commands, writing code, or making commits.

## Stack

The tools below are installed in the project **right now** (see
`pyproject.toml` for exact pins). Do not claim future state as if it were
shipped — the README "Manual verification" section and the SDD tasks
track what is real vs. what is planned.

| Tool             | Version  | Purpose                                  |
| ---------------- | -------- | ---------------------------------------- |
| Python           | 3.12     | Runtime (see `.python-version`).         |
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
├── .python-version
├── AGENTS.md            # this file
├── README.md            # Legal Notice is the FIRST section
├── pyproject.toml       # PEP 621 metadata + tool config
├── scripts/
│   └── check.sh         # local CI: ruff + mypy + pytest
├── src/
│   └── jobs_finder/     # src layout, imported as `jobs_finder`
│       ├── __init__.py
│       ├── main.py                 # composition root + uvicorn entry
│       ├── domain/                 # Job value object, base exceptions
│       ├── application/            # JobSearchPort, CachePort, use cases, DTOs
│       │   └── usecases/           # one use case file per source + cached wrapper
│       ├── infrastructure/         # Playwright scrapers, parsers, throttle, cache
│       │   ├── linkedin/           # LinkedInPlaywrightScraper + parsers
│       │   ├── indeed/             # IndeedPlaywrightScraper + parsers
│       │   ├── infojobs/           # InfoJobsPlaywrightScraper + parsers
│       │   └── cache/              # InMemoryTTLCache primitive
│       └── presentation/           # FastAPI app, routes, middleware, schemas
│           └── routes/             # one route file per source (linkedin, indeed, infojobs) + aggregator
└── tests/
    ├── conftest.py
    ├── fixtures/                   # inline HTML for parser tests
    │   ├── linkedin_search.py
    │   ├── indeed_search.py
    │   └── infojobs_search.py
    ├── unit/                       # parsers, throttle, use case, scraper, exceptions, cache
    └── integration/                # FastAPI app + composition root + X-Cache headers
```

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

## How to run

All commands are run from the project root and use `uv` (NOT `pip`, NOT
`poetry`).

```bash
# Install dependencies into a project-local virtualenv
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

Run `./scripts/check.sh` before every commit. CI runs the same commands
(`ruff check`, `ruff format --check`, `mypy`, `pytest`). Do not commit
if any check fails.

## Conventions

1. **No live scraping in tests — covers LinkedIn, Indeed, AND InfoJobs.**
   The end-to-end live paths are documented in the README "Manual
   verification" sections (one per source), but they are **never**
   executed in CI or in the automated test suite. Parser tests use
   inline HTML fixtures (`tests/fixtures/linkedin_search.py` and
   `tests/fixtures/indeed_search.py`). The only sanctioned exception
   is the one-time Playwright capture of `es.indeed.com` performed
   manually during a follow-up test- fixture refresh — that capture
   is NEVER run in CI; the captured HTML is committed to the fixture
   file and the rest of the suite re-runs offline against the new
   capture.
2. **Use `uv`, not `pip` or `poetry`.** All Python dependency operations
   go through `uv sync` and `uv run ...`.
3. **Src layout only.** Production code lives under `src/jobs_finder/`.
   Never add modules at the repo root.
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
