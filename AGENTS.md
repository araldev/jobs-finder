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
| `frontend/` | Next.js 15 · React 19 · TypeScript · Tailwind 3.4 · shadcn/ui (slate) | `frontend/package.json` |

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
| PyJWT            | >= 2.8   | ES256 JWT verification via JWKS (per-user auth).  |

## Stack (frontend)

The tools below are installed in the frontend workspace **right
now** (see `frontend/package.json` for exact pins). All versions
are pinned to an exact number — no `^`, no `*` — to match the
backend's "no floating versions" convention.

| Tool                          | Version  | Purpose                                       |
| ----------------------------- | -------- | --------------------------------------------- |
| Node                          | >= 20    | Runtime.                                      |
| pnpm                          | >= 10    | Package manager.                              |
| Next.js                       | 15.5.19  | App Router, RSC, Route Handlers.              |
| React                         | 19.1.0   | UI runtime.                                   |
| TypeScript                    | 5.9.2    | Strict + `noUncheckedIndexedAccess`.          |
| Tailwind CSS                  | 3.4.17   | PostCSS-based config (`tailwind.config.ts`).  |
| tailwindcss-animate           | 1.0.7    | Tailwind animation utilities (shadcn needs).  |
| shadcn/ui (slate / default)   | —        | Radix-based components in `src/components/ui/`. |
| class-variance-authority      | 0.7.1    | Variant-driven component classes.             |
| clsx                          | 2.1.1    | Conditional class merging.                    |
| tailwind-merge                | 3.6.0    | Tailwind class conflict resolution (`cn()`).  |
| @tanstack/react-query         | 5.101.0  | Server-state cache (GET only — 5min staleTime).|
| framer-motion                 | 11.15.0  | Page transitions, spring animations.          |
| next-themes                   | 0.4.6    | Dark/light mode with `class` strategy.        |
| sonner                        | 2.0.7    | Toasts (`bottom-right`, `richColors`).        |
| lucide-react                  | 1.17.0   | ONLY icon set.                                |
| date-fns                      | 4.1.0    | Relative time formatting.                     |
| Radix UI (via shadcn)         | —        | dialog, dropdown-menu, popover, select, separator, switch, tooltip, avatar, scroll-area |
| vitest                        | 4.1.8    | Test runner with `@testing-library/react`.    |
| @testing-library/react        | 16.3.2   | React component-test utilities.               |
| @testing-library/jest-dom     | 6.6.3    | DOM matchers for vitest.                      |
| jsdom                         | 26.0.0   | Test environment for hooks and DOM logic.     |
| @playwright/test              | —        | E2E tests (config only, no tests yet).        |

The frontend talks to the backend **only** through Next.js Route
Handlers in `src/app/api/`. The browser never calls
`BACKEND_URL` directly. See the project layout below for the
contract.

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
│   ├── supabase/         # local Supabase config + migrations/
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
└── frontend/                # Next.js 15, React 19, shadcn/ui (slate)
    ├── .env.example         # template — copy to `frontend/.env.local`
    ├── .gitignore
    ├── components.json      # shadcn config (style: default, baseColor: slate)
    ├── e2e/                 # Playwright E2E (config only, no tests yet)
    ├── eslint.config.mjs
    ├── next-env.d.ts
    ├── next.config.ts
    ├── package.json
    ├── playwright.config.ts
    ├── postcss.config.mjs
    ├── tailwind.config.ts
    ├── tsconfig.json
    ├── vitest.config.ts
    ├── vitest.setup.ts
    ├── public/
    └── src/
        ├── app/             # App Router (RSC + Route Handlers)
        │   ├── api/         # server-side proxies (jobs, jobs/[id], stats, health)
        │   ├── globals.css  # Tailwind + CSS vars (light/dark) + Google Fonts + shimmer
        │   ├── layout.tsx   # Root layout with Providers + AppShell
        │   ├── loading.tsx  # Root loading skeleton
        │   ├── error.tsx    # Global error boundary
        │   ├── not-found.tsx
        │   ├── page.tsx     # Dashboard (stats + search + job list + right sidebar)
        │   ├── providers.tsx  # ThemeProvider > QueryClientProvider > Toaster
        │   ├── jobs/
        │   │   ├── page.tsx          # Jobs listing
        │   │   └── [id]/
        │   │       ├── page.tsx      # Job detail (2-col layout)
        │   │       └── loading.tsx
        │   ├── search/
        │   │   ├── page.tsx          # Search with filters + results grid
        │   │   └── loading.tsx
        │   └── settings/
        │       ├── page.tsx          # Platform config + notification prefs
        │       └── loading.tsx
        ├── components/
        │   ├── ui/           # shadcn primitives (button, card, input, badge, …)
        │   ├── layout/       # AppShell, Sidebar, Header, ThemeToggle, PageTransition
        │   ├── dashboard/    # StatCard, StatsCardsRow, PlatformDistribution, RightSidebar
        │   ├── jobs/         # JobCard, JobList, JobDetailContent, JobDetailAside, PlatformBadge, SalaryBadge
        │   ├── search/       # SearchBar, FilterPanel
        │   ├── settings/     # PlatformConfigCard, NotificationSettings
        │   └── shared/       # EmptyState, ErrorState, ExportButton
        ├── hooks/            # useStats, useJobs, useJobsInfinite, useJobDetail, useDebounce
        ├── lib/              # utils (cn), api-client (server-only), formatters, types
        └── types/            # job.ts, stats.ts, settings.ts
```

### Workspace-local `.env` files

Each workspace reads its own env vars from a workspace-local `.env`.
There is no shared `.env` at the repo root because the two
workspaces will (eventually) read different env vars with different
shapes — the backend uses `pydantic-settings` (`backend/.env`),
the frontend reads its env vars via `process.env.BACKEND_URL`
inside the Node server runtime (Next.js Route Handlers).

- `backend/.env.example` is the **template** for backend env vars.
  Copy it to `backend/.env` to run the backend locally.
  `backend/.env` is git-ignored.
- `frontend/.env.example` is the **template** for frontend env
  vars. Copy it to `frontend/.env.local` to run the frontend
  locally. `frontend/.env.local` is git-ignored (the `.gitignore`
  has an `!.env.example` exception so the template ships with
  the repo).

The dependency rule for the backend is
`presentation → application → domain ← infrastructure`. `application/`
must not import `infrastructure/` or `presentation/`. Each source
(`linkedin`, `indeed`, `infojobs`) has its own sub-package under
`infrastructure/` and its own route file under `presentation/routes/`,
mirrored by per-source fixtures under `tests/fixtures/`.

For the frontend, the rule is
`app (server) ← lib (server-only) | app (client) ← lib (browser-safe)`.
`src/lib/api-client.ts` carries `import "server-only"` so any
accidental client import fails the build. The browser always
talks to the same-origin `/api/*` endpoints, never to
`BACKEND_URL` directly.

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

Backend commands are run from `backend/` and use `uv` (NOT `pip`,
NOT `poetry`). Frontend commands are run from `frontend/` and
use `pnpm` (NOT `npm`, NOT `yarn`, NOT `bun` — the lockfile is
`pnpm-lock.yaml` and `pnpm-workspace.yaml` configures the
workspace).

```bash
# Backend
cd backend
uv sync
uv run pytest
uv run mypy
uv run ruff check
uv run ruff format --check

# Frontend
cd frontend
pnpm install
pnpm run dev            # http://localhost:3000 (desarrollo)
pnpm run typecheck      # tsc --noEmit (strict + noUncheckedIndexedAccess)
pnpm run lint           # next lint
pnpm run test           # vitest run --passWithNoTests
pnpm run build          # build de producción (next build)
pnpm run start          # servidor de producción (next start, requiere build previo)
```

### Running the backend as a daemon (surviving shell exit)

The backend is a long-running FastAPI + uvicorn + BackgroundScheduler
process that scrapes job sites every ~15 minutes. Launching it from
a terminal or an AI tool session requires special care so the process
survives when the launching shell exits.

**DO NOT** use `nohup` — it only ignores SIGHUP but does NOT prevent
the process from being killed when its parent shell terminates.
Instead, use `setsid` to create a new session that is fully independent
of the launching shell:

```bash
cd backend

# Start (survives shell exit)
setsid uv run python -m jobs_finder.main > backend.log 2>&1 &

# Verify
curl http://localhost:8000/health

# Stop
kill $(lsof -ti :8000) 2>/dev/null
```

**How it works**: `setsid` creates a new process session with no
controlling terminal. Unlike `nohup` (which only masks SIGHUP), the
new session receives NO signals from the parent shell — even if the
launching shell is killed, the backend continues running. This is
required when launching from AI tool sessions (OpenCode, Copilot,
etc.) where the shell environment has unpredictable lifecycle.

**Legacy note**: The original deployment used `nohup` and a `setsid`
wrapper script. The current canonical entry point is the `uv run`
command above. No `scripts/` wrapper exists because the `setsid`
built-in is available on every Linux distribution (coreutils).

### Accessing from other devices on the local network

Both services bind to `0.0.0.0` by default (all network interfaces),
so they are accessible from any device on the same LAN.

```bash
# 1. Find your machine's LAN IP
hostname -I | awk '{print $1}'
# e.g. 192.168.1.42

# 2. Start the backend (port 8000)
cd backend
setsid uv run python -m jobs_finder.main > backend.log 2>&1 &

# 3. Start the frontend dev server (port 3000, binds to 0.0.0.0)
cd frontend
pnpm dev

# 4. Access from another device on the LAN:
#    http://192.168.1.42:3000
#
#    The backend CORS allows any origin in development mode
#    (ENVIRONMENT=development, the default). The frontend
#    Route Handlers proxy API calls server-side, so the
#    browser never calls the backend directly.
```

If you need CORS for a specific origin (e.g. a deployed staging
site), set `LINKEDIN_CORS_ALLOW_ORIGINS` in `backend/.env`:

```bash
# backend/.env — comma-separated list of allowed origins
LINKEDIN_CORS_ALLOW_ORIGINS=["https://app.mydomain.com","https://staging.mydomain.com"]
```

When `ENVIRONMENT=production`, CORS MUST be explicitly configured
(the app will refuse to start otherwise).

## Pre-commit

Run the workspace's check commands before every commit.

- **Backend** — `cd backend && bash scripts/check.sh` runs `ruff
  check`, `ruff format --check`, `mypy`, `pytest`.
- **Frontend** — `cd frontend && pnpm run typecheck && pnpm run
  lint && pnpm run test && pnpm run build` runs the four gates
  this project uses.

CI runs the same commands. Do not commit if any check fails.

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
   forbidden by the spec. Backup files (`.env.bak`, `*.bak`) are also
   forbidden — add `*.bak` to `.gitignore` if you encounter any.
23. **Secrets use `SecretStr`.** Any env var that holds a credential
    (`SUPABASE_SERVICE_KEY`, `LLM_API_KEY`, `DATABASE_URL`, etc.)
    MUST be declared as `SecretStr | None` in
    `backend/src/jobs_finder/infrastructure/config.py` so the
    credential is masked in `repr()`, `str()`, log lines, and
    tracebacks. Use `field_validator(mode="before")` to normalize
    empty strings to `None` (mirrors the existing
    `_normalize_empty_secret` validator for `llm_api_key`).
    **JWT verification uses asymmetric ES256 via JWKS** — the backend
    holds NO signing key, only the public key fetched from
    Supabase's JWKS endpoint.
24. **Don't leak exception details to clients.** Route handlers MUST
    NOT interpolate `f"...{exc}"` into `HTTPException.detail` or
    SSE error payloads. Log the full exception server-side with
    `_logger.warning(...)` or `_logger.error(..., exc_info=True)`
    and return a STATIC user-facing message. Internal API
    structure, LLM provider names, and library internals are
    NOT for client consumption.
25. **Per-user rate limiting** is automatically applied when a
    valid Supabase JWT is present (the `JWTUserMiddleware` sets
    `request.state.current_user` BEFORE `RateLimitMiddleware`
    runs). Authenticated users get their own bucket keyed by
    `user:{user_id_hash}`. Anonymous users fall back to the IP
    hash. See `RateLimitMiddleware.dispatch()` for the priority
    chain: **user JWT > API key > IP address**.
26. **Auth-required routes** MUST use
    `Depends(get_current_user)` (raises 401 when JWT is missing).
    For routes that want JWT identification without blocking
    anonymous access (job search, stats, history), use
    `Depends(get_optional_user)` instead — this lets the
    per-user rate limiter see the user without breaking the
    current public-data behavior.
27. **Sensitive endpoints** (`/scheduler/status`, anything
    exposing internal state, queries, error traces) MUST require
    `Depends(get_current_user)`. The scheduler/status endpoint
    leaks runtime config + last_error + cycle internals — never
    public.
28. **File uploads MUST be validated.** Any `UploadFile = File(...)`
    parameter MUST have:
    - `content_type` whitelist check (e.g. `application/pdf` only)
    - `max_length` cap (current default for CV: 10 MB)
    - Generic error messages (don't echo file contents or library
      internals back to the client).
8. **Use `pnpm`, not `npm` or `yarn`** (frontend). All Node
   dependency operations go through `cd frontend && pnpm install`
   and `cd frontend && pnpm run ...`. The lockfile is
   `pnpm-lock.yaml` (committed); `pnpm-workspace.yaml` configures
   the workspace.
9. **Src layout only — within `frontend/`.** Production code lives
   under `frontend/src/`. Never add modules at the repo root or at
   `frontend/` directly (no loose `.ts`/`.tsx` files next to
   `package.json`).
10. **Pin every dep, no `^`.** Every dependency in
    `frontend/package.json` is an exact version. If a transitive
    upgrade is needed, open a separate change and pin the new
    version explicitly.
11. **No business logic in `__init__.ts`.** Same rule as Python.
12. **The browser never talks to the backend directly.** All
    backend traffic goes through a Next.js Route Handler in
    `frontend/src/app/api/`. Adding `fetch(${BACKEND_URL}…)` to a
    client component is a build-time architectural violation.
13. **No bg-white or pure black.** Always use `bg-background` (which resolves via CSS variables for light/dark mode). Cards use `bg-card`.
14. **No hardcoded colors.** Use CSS variable tokens: `text-muted-foreground` (never `text-gray-500`), `border-border`, `bg-muted`, etc.
15. **Typography rules:** headings use `font-display` (DM Sans via `font-feature-settings`), body uses `font-sans` (Inter), important numbers use `font-mono` (JetBrains Mono).
16. **Shadows:** `shadow-sm` base, `shadow-md` hover. Never `shadow-lg` or heavier.
17. **Borders:** always 1px `border-border`. Never 2px.
18. **Border radius:** `rounded-xl` for cards/panels, `rounded-lg` for buttons/inputs/badges. Never `rounded-md` or `rounded-sm` for containers.
19. **Loading states:** per-component skeletons with `skeleton-shimmer` class. NEVER a global spinner.
20. **Page transitions:** framer-motion `AnimatePresence` via `PageTransition` wrapper, keyed by `usePathname`.
21. **Job card animations:** spring `bounce:0.1`, delay `index * 0.06s`, `layout` enabled.
22. **Data fetching:** React Query with `staleTime: 5 * 60 * 1000`, `refetchOnWindowFocus: true`. Use `useInfiniteQuery` for paginated lists (IntersectionObserver-based infinite scroll).
