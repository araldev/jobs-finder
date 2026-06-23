# =============================================================================
# jobs-finder — Production Docker image
# =============================================================================
#
# Multi-stage build:
#   Stage 1 (base):    Python 3.12-slim + system deps + uv
#   Stage 2 (builder): Install dependencies via uv sync + Playwright Chromium
#   Stage 3 (runtime): Minimal image with everything needed at runtime
#
# Build:
#   docker build -t jobs-finder:latest -f backend/Dockerfile backend/
#
# Run:
#   docker run -p 8000:8000 \
#     -e DATABASE_URL="postgresql://postgres:...@db.XXX.supabase.co:5432/postgres" \
#     -e ENVIRONMENT=production \
#     -e LINKEDIN_CORS_ALLOW_ORIGINS='["https://yourdomain.com"]' \
#     jobs-finder:latest
#
# Required env vars:
#   - DATABASE_URL  (PostgreSQL/Supabase connection string)
#   - ENVIRONMENT   (set to "production")
# =============================================================================

# ── Stage 1: Python base with uv ─────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    PIP_NO_CACHE_DIR=1

# System deps for Playwright (Chromium) + weasyprint (PDF rendering).
# See https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation
# See https://playwright.dev/docs/chromium#install-system-dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    # weasyprint runtime deps
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libfontconfig1 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    # Playwright Chromium runtime deps
    libnspr4 \
    libnss3 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Install uv — the official installer keeps it small (~10 MB).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# ── Stage 2: Install dependencies ────────────────────────────────────────────
FROM base AS builder

WORKDIR /app

# First copy only the lockfile + project metadata for layer caching.
# NOTE: README.md is required by pyproject.toml (readme = "README.md").
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Then copy the source code.
COPY src/ ./src/

# Install the project itself (no dev deps).
RUN uv sync --frozen --no-dev

# Download Playwright Chromium browser into a known location.
ENV PLAYWRIGHT_BROWSERS_PATH=/app/.cache/ms-playwright
RUN uv run playwright install --with-deps chromium 2>&1 | tail -5

# ── Stage 3: Runtime ─────────────────────────────────────────────────────────
FROM base AS runtime

ENV \
    APP_HOME=/app \
    PORT=8000 \
    ENVIRONMENT=production \
    UV_CACHE_DIR=/app/.cache/uv \
    PLAYWRIGHT_BROWSERS_PATH=/app/.cache/ms-playwright

WORKDIR $APP_HOME

# Copy the virtualenv + project + browser cache from builder.
COPY --from=builder /app /app

# Create a non-root user with a writable cache directory.
USER root
RUN addgroup --system app && adduser --system --ingroup app app \
    && chown -R app:app $APP_HOME \
    && mkdir -p $APP_HOME/.cache/uv $APP_HOME/.cache/ms-playwright \
    && chown -R app:app $APP_HOME/.cache
USER app

EXPOSE $PORT

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:$PORT/health')"

CMD ["uv", "run", "uvicorn", "jobs_finder.main:app", "--host", "0.0.0.0", "--port", "8000"]
