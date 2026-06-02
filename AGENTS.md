# AGENTS.md

> Operating manual for humans and AI agents working on `jobs-finder`.
> Read this **first** before running commands, writing code, or making commits.

## Stack

This bootstrap is intentionally narrow. Only the tools that exist in the
project **right now** are listed here. Do not claim future state as if it were
shipped — the README "Manual verification" section and the SDD tasks track
what is real vs. what is planned.

| Tool       | Version  | Purpose                                  |
| ---------- | -------- | ---------------------------------------- |
| Python     | 3.12     | Runtime (see `.python-version`).         |
| uv         | >= 0.4   | Package manager and virtualenv.          |
| pytest     | >= 8.0   | Test runner.                             |
| pytest-asyncio | >= 0.23 | Async test support.                    |
| httpx      | >= 0.27  | (Planned) in-process API tests.          |
| Playwright | >= 1.45  | (Planned) headless Chromium driver.      |
| FastAPI    | >= 0.111 | (Planned) HTTP framework.                |
| uvicorn    | >= 0.30  | (Planned) ASGI server.                   |
| mypy       | >= 1.10  | Static type checking (`--strict`).       |
| ruff       | >= 0.5   | Lint + format.                           |

## Project layout

```
jobs-finder/
├── .gitignore
├── .python-version
├── AGENTS.md            # this file
├── README.md            # Legal Notice is the FIRST section
├── pyproject.toml       # PEP 621 metadata + tool config
├── src/
│   └── jobs_finder/     # src layout, imported as `jobs_finder`
│       └── __init__.py  # intentionally empty (module docstring only)
└── tests/
    ├── conftest.py
    └── smoke_test.py
```

The hexagonal layers (`domain/`, `application/`, `infrastructure/`,
`presentation/`) will be added in later apply tasks (T-002..T-008). The
dependency rule will be `presentation → application → domain ← infrastructure`.

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

# Format check (will be added in T-011)
uv run ruff format --check
```

## Conventions

1. **No live LinkedIn scraping in tests.** The end-to-end live path is
   documented in the README "Manual verification" section, but it is
   **never** executed in CI or in the automated test suite. Parser tests
   use an inline HTML fixture.
2. **Use `uv`, not `pip` or `poetry`.** All Python dependency operations go
   through `uv sync` and `uv run ...`.
3. **Src layout only.** Production code lives under `src/jobs_finder/`. Never
   add modules at the repo root.
4. **No business logic in `__init__.py`.** `__init__.py` files may contain a
   module docstring and nothing else. Domain/application/infrastructure code
   goes in its own module.
5. **One commit per work unit.** A commit represents a deliverable behavior,
   not a file type. Tests and docs ship with the code they verify or describe.
6. **Conventional commits.** Format: `<type>(<scope>): <subject>`. Do **not**
   add `Co-Authored-By:` or any AI attribution trailer.
7. **No secrets in the repo.** `li_at` cookies, proxy credentials, or any
   LinkedIn authentication material are explicitly forbidden by the spec.
