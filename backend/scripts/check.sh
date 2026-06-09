#!/usr/bin/env bash
# Local CI — runs the same checks the orchestrator's verify phase will run.
# Exit non-zero on the first failure. Use `./scripts/check.sh` before
# every commit.

set -euo pipefail

uv run ruff check
uv run ruff format --check
uv run mypy
uv run pytest
