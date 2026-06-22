# Development Guide

How to run the full stack locally for development.

## TL;DR

The stack has **two services**: a FastAPI backend (port 8000) and a Next.js
frontend (port 3000). The project is wired to a **cloud Supabase instance**
(`https://<your-project>.supabase.co`) — there is NO local Supabase stack to
start. All env vars for the cloud instance live in `backend/.env` (already
gitignored, already populated).

```bash
# Terminal 1 — backend
cd backend
uv sync
uv run uvicorn jobs_finder.main:app --port 8000 --reload

# Terminal 2 — frontend
cd frontend
pnpm install
pnpm run dev
```

That's it. Visit <http://localhost:3000>. The frontend talks to the backend at
`http://localhost:8000` via Next.js Route Handlers in `frontend/src/app/api/`,
and the backend talks to the cloud Supabase via `SUPABASE_URL` /
`SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY` from `backend/.env`.

If both are already running from a previous session, no setup needed — just
check the ports:

```bash
ss -tlnp 2>/dev/null | grep -E ":3000|:8000"
```

## Detailed setup

### Prerequisites

| Tool  | Version | Install |
|-------|---------|---------|
| Python | 3.12 (see `backend/.python-version`) | `pyenv install 3.12` or system Python |
| uv     | >= 0.4 | `pip install uv` |
| Node   | >= 20  | `nvm install 20` |
| pnpm   | >= 10  | `npm install -g pnpm` |

### First-time setup

```bash
# Clone the repo
git clone git@github.com:araldev/jobs-finder.git
cd jobs-finder

# Backend
cd backend
uv sync                       # creates .venv, installs deps from uv.lock
cp .env.example .env          # template; edit values if needed
                               # (the committed .env already has the cloud
                               # Supabase values, so you can skip this if
                               # you're an existing contributor)
uv run uvicorn jobs_finder.main:app --port 8000 --reload

# Frontend (separate terminal)
cd ../frontend
pnpm install
cp .env.example .env.local    # template; the BACKEND_URL default is
                               # http://localhost:8000 which matches the
                               # backend above
pnpm run dev
```

Visit:

- Frontend: <http://localhost:3000>
- Backend Swagger: <http://localhost:8000/docs>
- Backend OpenAPI JSON: <http://localhost:8000/openapi.json>

### Environment variables

#### `backend/.env`

The committed `backend/.env` already has the cloud Supabase credentials
configured for the team instance. **Do not edit it unless you know what you're
doing.** The `.env.example` template documents every variable and its purpose.

The 46 env vars are read via `pydantic-settings` (`backend/src/jobs_finder/
infrastructure/config.py`). Missing vars will fail with a clear error
message at startup.

Key vars:

| Var | Purpose |
|-----|---------|
| `SUPABASE_URL` | Cloud Supabase project URL |
| `SUPABASE_ANON_KEY` | Public anon key (browser-safe) |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-side key (admin) — never expose to browser |
| `BACKEND_API_KEYS` | Comma-separated list of valid API keys for `/api/*` proxy auth |
| `CACHE_TTL_SECONDS` | In-memory TTL for source caches (default 60.0, set 0 to disable) |
| `LLM_API_KEY` | Optional — required for the `/api/jobs/chat/stream` route |
| `LLM_FILTER_ENABLED` | Set `true` to register the chat route (default false) |

#### `frontend/.env.local`

```bash
BACKEND_URL=http://localhost:8000        # the FastAPI backend
BACKEND_API_KEY=<match one of BACKEND_API_KEYS in backend/.env>

# Supabase (cloud) — same project as the backend
NEXT_PUBLIC_SUPABASE_URL=<your-project-url>
NEXT_PUBLIC_SUPABASE_ANON_KEY=<your-anon-key>

# i18n escape hatch — flips the entire intl middleware off
NEXT_PUBLIC_I18N_ENABLED=true             # default true; set false to bypass i18n
```

## Verifying it works

Once both services are up, run the smoke tests:

```bash
# Backend health
curl -s http://localhost:8000/api/health | head -3

# Backend swagger
open http://localhost:8000/docs

# Frontend root
curl -s -o /dev/null -w "GET / → HTTP %{http_code}\n" http://localhost:3000

# Frontend with cookie-driven locale switch
curl -s -o /dev/null -w "GET / (en cookie) → HTTP %{http_code}\n" \
  --cookie "NEXT_LOCALE=en" http://localhost:3000

# The <html lang> attribute should match the cookie
curl -s --cookie "NEXT_LOCALE=en" http://localhost:3000/ | grep '<html lang=' | head -1
```

## Running tests

```bash
# Backend (FastAPI / pytest)
cd backend
uv run pytest                  # full suite
uv run pytest -k <pattern>     # single test or pattern
uv run mypy                    # static type check
bash scripts/check.sh          # ruff + mypy + pytest (CI gate)

# Frontend (vitest + RTL)
cd frontend
pnpm run typecheck             # tsc --noEmit (strict + noUncheckedIndexedAccess)
pnpm run lint                  # next lint
pnpm run test                  # vitest run --passWithNoTests
pnpm run lint:i18n             # CI grep audit for hardcoded user-facing strings
pnpm run build                 # production build (also catches type errors)
```

The pre-commit gates per workspace (CI runs all of them):

- **Backend**: `cd backend && bash scripts/check.sh` → ruff + mypy + pytest
- **Frontend**: `cd frontend && pnpm run typecheck && pnpm run lint && pnpm run test && pnpm run build`

## Common pitfalls

| Symptom | Cause | Fix |
|---------|-------|-----|
| Backend exits immediately with `ValidationError` | Missing or invalid env vars in `backend/.env` | Check the error message; fix the offending var; restart |
| Frontend returns 500 on `/api/jobs` | Backend API key mismatch | `BACKEND_API_KEYS` (backend) and `BACKEND_API_KEY` (frontend) must match one entry |
| Frontend shows "Invalid login credentials" on every page | Supabase anon key or URL is wrong in `frontend/.env.local` | Copy values from a teammate's working `.env.local` |
| `<html lang>` stays `es` even after switching to English | `NEXT_PUBLIC_I18N_ENABLED=false` | Flip to `true` in `.env.local` and restart the dev server |
| `pnpm run build` fails with "Cannot find module '@/...'" | tsconfig path alias not picked up | `rm -rf .next && pnpm run build` to clear stale cache |
| Backend `422 Unprocessable Entity` on scraper endpoints | Rate limiter rejecting the request | Increase `RATE_LIMIT_*` values in `backend/.env` or wait |
| LinkedIn scraper returns 401 / CAPTCHA | `li_at` cookie expired or invalid | Refresh cookies via `backend/scripts/extract_linkedin_cookies.py` and update `LINKEDIN_LI_AT` in `.env` |
| `supabase start` errors with "config.toml missing" | Someone tried to run a local Supabase stack — don't | **There is no local Supabase stack.** Use the cloud instance. See top of this file. |

## Architecture overview

```
Browser (port 3000)
       │
       ▼
Next.js frontend  ←  cloud Supabase (auth, DB)
       │
       │ (Browser → /api/* Route Handler → backend)
       ▼
FastAPI backend (port 8000)
       │
       ├─→  cloud Supabase (DB, auth verify)
       ├─→  LinkedIn / Indeed / InfoJobs (Playwright scrapers)
       └─→  MiniMax LLM (chat filter — optional)
```

The browser NEVER talks to the backend directly. All backend traffic goes
through `frontend/src/app/api/*` Route Handlers, which proxy to the backend at
`BACKEND_URL`. This is enforced architecturally — see `frontend/src/lib/api-client.ts`
which carries `import "server-only"`.

The backend's `BACKEND_API_KEYS` is the only authentication between the
frontend Route Handlers and the backend. The frontend's `BACKEND_API_KEY`
must match one entry.

The browser talks to Supabase directly for auth (sign-in, sign-up, session
cookies, etc.) using the public `NEXT_PUBLIC_SUPABASE_ANON_KEY`. The backend
uses `SUPABASE_SERVICE_ROLE_KEY` (admin) for server-side DB queries.

## Why no local Supabase?

The project uses a shared cloud Supabase instance so the team works against
the same DB. Local Supabase stacks were evaluated and rejected because:

- They drift from cloud state (schema, migrations, RLS policies)
- They require Docker + ~10 GB of image pulls
- They don't help catch real Supabase-specific bugs (RLS, JWT, RPCs)

The cloud instance is the source of truth. Migrations under
`backend/supabase/migrations/` are applied via the Supabase dashboard SQL
editor or `supabase db push` against the cloud project.

## CI

GitHub Actions runs all 4 backend + 4 frontend gates on every PR. PRs that
fail any gate cannot merge. See `.github/workflows/` for the full pipeline.

## Where to look next

- `backend/README.md` — full backend documentation (scraper config, scheduler,
  rate limiting, aggregator ranking, LLM chat filter)
- `frontend/README.md` — frontend documentation (i18n architecture, app routes,
  state management, data fetching)
- `AGENTS.md` — operating manual (conventions, pre-commit gates, scratch rules)
- `openspec/specs/` — capability specs (single source of truth for what each
  feature MUST do)
- `openspec/changes/<change-id>/` — per-change SDD artifacts (explore,
  proposal, design, tasks, archive-report)
