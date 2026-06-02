"""Unit tests for the Indeed-specific `Settings` fields and the shared
Indeed conftest fixtures.

Spec: REQ-I-011 (Settings extension) and REQ-I-017 (conftest extension —
`sample_indeed_jobs` and `fake_indeed_port` fixtures are added here so
the T-005 use-case test can consume them without duplicating
infrastructure).

The `Settings` class is a `pydantic_settings.BaseSettings` whose model
prefix is `LINKEDIN_`. The new Indeed-specific fields live in the SAME
`Settings` class (per REQ-I-011 — keep one config object as the single
source of truth), but read from `INDEED_*` env vars (per-field
`validation_alias` overrides the model-level prefix for those fields).

This test file is the RED → GREEN → REFACTOR anchor for T-001 of the
`indeed_platform` change. It must be authored BEFORE the production
fields are added, run to confirm it fails (RED), then the production
fields are added, then the test passes (GREEN), then any cleanup
(REFACTOR) happens.
"""

from __future__ import annotations

import inspect

import pytest

from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.config import Settings
from tests.conftest import FakeJobSearchPort

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_indeed_throttle_seconds_default_is_three() -> None:
    """`indeed_throttle_seconds` defaults to `3.0` (per REQ-I-011)."""
    settings = Settings()
    assert settings.indeed_throttle_seconds == 3.0


def test_indeed_timeout_ms_default_is_15_000() -> None:
    """`indeed_timeout_ms` defaults to `15_000` (per REQ-I-011)."""
    settings = Settings()
    assert settings.indeed_timeout_ms == 15_000


def test_indeed_domain_default_is_es_indeed_com() -> None:
    """`indeed_domain` defaults to `"es.indeed.com"` (per REQ-I-011)."""
    settings = Settings()
    assert settings.indeed_domain == "es.indeed.com"


def test_indeed_max_pages_default_is_ten() -> None:
    """`indeed_max_pages` defaults to `10` (per REQ-I-011)."""
    settings = Settings()
    assert settings.indeed_max_pages == 10


def test_indeed_inter_page_delay_seconds_default_is_one() -> None:
    """`indeed_inter_page_delay_seconds` defaults to `1.0` (follow-up to fd51ea1).

    The 1.0-second default is a sweet spot: short enough that a typical
    search of 2-3 pages adds only 1-2 seconds of latency, long enough
    that Cloudflare's anti-bot heuristics don't re-challenge the second
    request. Set to `0.0` via `INDEED_INTER_PAGE_DELAY_SECONDS=0` to
    disable (NOT recommended in production).
    """
    settings = Settings()
    assert settings.indeed_inter_page_delay_seconds == 1.0


def test_indeed_user_agent_default_is_a_modern_chrome_fingerprint() -> None:
    """`indeed_user_agent` defaults to the same stealth desktop Chrome UA
    the LinkedIn field uses (per REQ-I-011).
    """
    settings = Settings()
    assert isinstance(settings.indeed_user_agent, str)
    assert len(settings.indeed_user_agent) > 0
    assert "Mozilla" in settings.indeed_user_agent
    # A modern Chrome fingerprint includes the WebKit/KHTML/Safari tokens.
    assert "AppleWebKit" in settings.indeed_user_agent
    assert "Chrome" in settings.indeed_user_agent
    assert "Safari" in settings.indeed_user_agent


def test_indeed_user_agent_default_matches_linkedin_default() -> None:
    """`indeed_user_agent` and `user_agent` share the same default value
    (per REQ-I-011 — Indeed uses the same stealth UA as LinkedIn).
    """
    settings = Settings()
    assert settings.indeed_user_agent == settings.user_agent


# ---------------------------------------------------------------------------
# Env-var overrides (per-field `validation_alias` overrides the model
# `env_prefix="LINKEDIN_"` for the Indeed fields)
# ---------------------------------------------------------------------------


def test_indeed_throttle_seconds_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`INDEED_THROTTLE_SECONDS=6.0` overrides the default `3.0`."""
    monkeypatch.setenv("INDEED_THROTTLE_SECONDS", "6.0")
    settings = Settings()
    assert settings.indeed_throttle_seconds == 6.0


def test_indeed_domain_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`INDEED_DOMAIN=fr.indeed.com` overrides the default `es.indeed.com`."""
    monkeypatch.setenv("INDEED_DOMAIN", "fr.indeed.com")
    settings = Settings()
    assert settings.indeed_domain == "fr.indeed.com"


def test_indeed_timeout_ms_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`INDEED_TIMEOUT_MS=30000` overrides the default `15000`."""
    monkeypatch.setenv("INDEED_TIMEOUT_MS", "30000")
    settings = Settings()
    assert settings.indeed_timeout_ms == 30_000


def test_indeed_max_pages_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`INDEED_MAX_PAGES=5` overrides the default `10`."""
    monkeypatch.setenv("INDEED_MAX_PAGES", "5")
    settings = Settings()
    assert settings.indeed_max_pages == 5


def test_indeed_inter_page_delay_seconds_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`INDEED_INTER_PAGE_DELAY_SECONDS=2.5` overrides the default `1.0`."""
    monkeypatch.setenv("INDEED_INTER_PAGE_DELAY_SECONDS", "2.5")
    settings = Settings()
    assert settings.indeed_inter_page_delay_seconds == 2.5


def test_indeed_user_agent_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`INDEED_USER_AGENT=...` overrides the default stealth UA."""
    monkeypatch.setenv("INDEED_USER_AGENT", "CustomIndeed/1.0")
    settings = Settings()
    assert settings.indeed_user_agent == "CustomIndeed/1.0"


# ---------------------------------------------------------------------------
# Regression: the existing LinkedIn fields are unchanged.
# ---------------------------------------------------------------------------


def test_existing_linkedin_throttle_seconds_default_is_unchanged() -> None:
    """Regression: `throttle_seconds` still defaults to `3.0`."""
    settings = Settings()
    assert settings.throttle_seconds == 3.0


def test_existing_linkedin_user_agent_default_is_unchanged() -> None:
    """Regression: `user_agent` is still a non-empty modern Chrome UA."""
    settings = Settings()
    assert isinstance(settings.user_agent, str)
    assert "Mozilla" in settings.user_agent


def test_existing_linkedin_request_timeout_ms_default_is_unchanged() -> None:
    """Regression: `request_timeout_ms` still defaults to `10_000`."""
    settings = Settings()
    assert settings.request_timeout_ms == 10_000


def test_existing_linkedin_headless_default_is_unchanged() -> None:
    """Regression: `headless` still defaults to `True`."""
    settings = Settings()
    assert settings.headless is True


def test_linkedin_env_vars_still_override_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: `LINKEDIN_*` env vars still override LinkedIn fields.

    Setting `INDEED_*` env vars must NOT bleed into the LinkedIn fields,
    and vice versa.
    """
    monkeypatch.setenv("LINKEDIN_THROTTLE_SECONDS", "7.5")
    monkeypatch.setenv("INDEED_THROTTLE_SECONDS", "6.0")
    settings = Settings()
    assert settings.throttle_seconds == 7.5
    assert settings.indeed_throttle_seconds == 6.0


# ---------------------------------------------------------------------------
# Conftest fixtures (REQ-I-017) — exercised here so the T-001 batch proves
# the conftest is ready for T-005.
# ---------------------------------------------------------------------------


def test_sample_indeed_jobs_fixture_returns_three_jobs(
    sample_indeed_jobs: list[Job],
) -> None:
    """`sample_indeed_jobs` returns exactly 3 `Job` instances."""
    assert len(sample_indeed_jobs) == 3
    for job in sample_indeed_jobs:
        assert isinstance(job, Job)


def test_sample_indeed_jobs_have_source_agnostic_shape(
    sample_indeed_jobs: list[Job],
) -> None:
    """Each `sample_indeed_jobs` entry has all 6 `Job` fields populated
    and `posted_at` is tz-aware (per the domain invariant)."""
    for job in sample_indeed_jobs:
        assert isinstance(job.id, str) and job.id
        assert isinstance(job.title, str) and job.title
        assert isinstance(job.company, str) and job.company
        assert isinstance(job.location, str) and job.location
        assert isinstance(job.url, str) and job.url
        assert job.posted_at.tzinfo is not None
        assert job.posted_at.tzinfo.utcoffset(job.posted_at) is not None


def test_sample_indeed_jobs_use_canonical_indeed_viewjob_urls(
    sample_indeed_jobs: list[Job],
) -> None:
    """Each `sample_indeed_jobs` entry's `url` is a canonical Indeed
    `viewjob?jk=<id>` URL (not a SERP `/rc/clk` or `vjk=`-pinned URL).
    """
    for job in sample_indeed_jobs:
        assert job.url.startswith("https://")
        assert "/viewjob?jk=" in job.url
        # The id from the URL must match the Job.id (the canonical source).
        assert f"jk={job.id}" in job.url


def test_fake_indeed_port_fixture_is_a_callable_search_port(
    fake_indeed_port: object,
) -> None:
    """`fake_indeed_port` exposes an async `search` method, satisfying
    the structural `JobSearchPort` Protocol (cite REQ-I-003)."""
    assert callable(getattr(fake_indeed_port, "search", None))
    assert inspect.iscoroutinefunction(fake_indeed_port.search)  # type: ignore[attr-defined]


async def test_fake_indeed_port_fixture_returns_sample_indeed_jobs(
    fake_indeed_port: object,
    sample_indeed_jobs: list[Job],
) -> None:
    """Awaiting `fake_indeed_port.search(keywords, location, limit)`
    returns the `sample_indeed_jobs` list."""
    port = fake_indeed_port
    result = await port.search("python", "madrid", 20)  # type: ignore[attr-defined]
    assert result == sample_indeed_jobs


async def test_fake_indeed_port_records_calls() -> None:
    """`FakeJobSearchPort` (the class behind the `fake_indeed_port`
    fixture) records every call's `(keywords, location, limit)` so tests
    can assert the route/use case forwarded the input correctly.
    """
    port = FakeJobSearchPort()
    await port.search("python", "barcelona", 5)
    await port.search("rust", "valencia", 3)
    assert port.calls == [
        ("python", "barcelona", 5),
        ("rust", "valencia", 3),
    ]
