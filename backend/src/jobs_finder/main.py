"""Composition root for the jobs-finder service.

Spec: REQ-005, REQ-006.

`app` is a module-level `FastAPI` instance so `uv run uvicorn
jobs_finder.main:app --reload` works out of the box.

The `__main__` guard runs `uvicorn` only when the file is invoked
directly (e.g. `python -m jobs_finder.main`). The `cli()` function is
the entry point declared in `[project.scripts]` so `jobs-finder` works
as a console script after `uv sync`.
"""

from __future__ import annotations

import uvicorn

from jobs_finder.presentation.app_factory import build_app

app = build_app()


def cli() -> None:
    """Console-script entry point (`jobs-finder` command)."""
    uvicorn.run(
        "jobs_finder.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    cli()
