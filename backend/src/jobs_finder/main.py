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
    """Console-script entry point (`jobs-finder` command).

    ``log_config=None`` defers all logging configuration to our own
    ``configure_logging()`` (called inside ``build_app()``). Without
    this, uvicorn's internal ``logging.config.dictConfig()`` overrides
    our JSON formatter with its default plain-text config, and logs
    from sub-loggers (e.g. ``jobs_finder.infrastructure.scheduler``)
    are silently dropped.
    """
    uvicorn.run(
        "jobs_finder.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_config=None,
    )


if __name__ == "__main__":
    # Entry point for `python -m jobs_finder.main` (and `uv run
    # python -m jobs_finder.main`). This runs `cli()` which calls
    # `uvicorn.run(..., log_config=None)` so our own
    # `configure_logging()` (called inside `build_app()`) is the
    # ONLY logging configuration — uvicorn won't override it.
    #
    # Prefer this over `uv run uvicorn jobs_finder.main:app`:
    # the latter skips `cli()` so uvicorn's built-in dictConfig
    # replaces our JSON formatter with its plain-text config.
    cli()
