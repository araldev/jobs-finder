# jobs-finder

> Monorepo for the jobs-finder project. **Educational / personal use
> only.** Read the Legal Notice below before running anything.

## Workspaces

| Path | Stack | Status |
| --- | --- | --- |
| [`backend/`](backend/) | Python 3.12 · FastAPI · Playwright · uv | **Active.** On-demand LinkedIn + Indeed + InfoJobs job search HTTP endpoints. |
| [`frontend/`](frontend/) | _not chosen yet_ | **Empty placeholder.** Will host the web client that consumes the backend API. |

See each workspace's own `README.md` for setup, scripts, and per-workspace
documentation. The backend README is the source of truth for the HTTP API
(headers, endpoints, env vars, manual verification procedures).

## Repository layout

```
jobs-finder/
├── backend/                 # Python 3.12, FastAPI, Playwright
│   ├── src/jobs_finder/     # src layout, imported as `jobs_finder`
│   ├── tests/
│   ├── pyproject.toml       # uv-managed project
│   ├── scripts/check.sh     # local CI: ruff + mypy + pytest
│   └── README.md            # full backend documentation
├── frontend/                # placeholder; README only for now
├── AGENTS.md                # operating manual for humans + AI agents
├── .gitignore               # ignores for Python AND Node
└── README.md                # this file
```

## Quick start

Each workspace is independent — `cd` into the one you want to work on.

```bash
# Backend
cd backend
uv sync
uv run pytest
./scripts/check.sh
```

```bash
# Frontend (once a stack is chosen)
cd frontend
# TBD
```

## Legal Notice

> **STOP. Read this before running anything.**

This project scrapes LinkedIn's, Indeed's, and InfoJobs's public job
search pages. **Scraping any of these services may violate their Terms
of Service** and may expose the operator to civil and/or criminal
liability depending on jurisdiction (including but not limited to the
EU's GDPR, Spain's AEPD/LOPDGDD, and the United States' CFAA).

By downloading, building, running, or otherwise using this software,
**you acknowledge and accept the following**:

- You assume **all** legal risk. The authors and contributors of this
  project accept **no** liability for misuse, account bans, IP blocks,
  or legal action taken against you.
- This is **not** a production-grade job aggregator. It is an
  educational exercise that demonstrates how to combine FastAPI,
  Playwright, and hexagonal architecture. There is no SLA, no support,
  no reliability guarantee, and no warranty of any kind.
- Do not use this software to redistribute LinkedIn, Indeed, or
  InfoJobs data; to bypass rate limits; to evade anti-bot measures; or
  for any commercial purpose.
- If you are unsure whether your use case is legal, **consult a
  lawyer** in your jurisdiction before running this code.

If you are not willing to accept these terms, **do not run this
software**. Per-source warnings (with each provider's specific terms)
are documented in [`backend/README.md`](backend/README.md).
