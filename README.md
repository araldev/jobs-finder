# jobs-finder

> On-demand LinkedIn job search HTTP endpoint, built with FastAPI + Playwright.
> **Educational / personal use only.** Read the Legal Notice below.

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

## What this is

`jobs-finder` is the first slice of a multi-source job-search engine. It
exposes a single HTTP endpoint that, on each request, launches a headless
Chromium browser via Playwright, navigates to LinkedIn's public job search,
parses the result cards, and returns structured JSON. It is bootstrapped
as a hexagonal Python project (domain / application / infrastructure /
presentation) so additional job sources (InfoJobs, etc.) and a frontend can
be added in follow-up changes without rewrites.

## Stack

- **Python** 3.12
- **FastAPI** + **uvicorn** (HTTP layer, planned for T-008/T-009)
- **Playwright** + Chromium (scraper, planned for T-006)
- **httpx** (in-process API tests, planned for T-008)
- **uv** (package manager and virtualenv)
- **mypy --strict** (type checking)
- **ruff** (lint + format)
- **pytest** + **pytest-asyncio** (test runner)

## Quick start

```bash
# 1. Install dependencies into a project-local virtualenv
uv sync

# 2. Run the bootstrap test suite
uv run pytest

# 3. Static type check
uv run mypy

# 4. Lint
uv run ruff check

# 5. (Planned for T-010) Install the Chromium binary used by Playwright.
#    Not run automatically — the project does not hit LinkedIn during tests.
uv run playwright install chromium
```

## Manual verification

<!-- TODO: T-010 will fill this -->
The manual live-verification procedure (curl examples, expected 200/422/502
responses, Playwright install step) will be filled in by task T-010 once the
HTTP endpoint is implemented. For now, this section is intentionally a
placeholder.
