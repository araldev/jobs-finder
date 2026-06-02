"""Unit tests for the InfoJobs-specific `Settings` fields and the shared
InfoJobs conftest fixtures.

Spec: REQ-J-001 (URL pattern, partial — the `_build_url` lands in T-006,
this T-001 only adds the `infojobs_domain` field), REQ-J-003 (inter-page
pacing field, partial — the field is in `Settings` here, the scraper
applies it in T-006), and the conftest fixtures added in T-001 to
unblock T-005 (`SearchJobsUseCase` for InfoJobs).

The `Settings` class is a `pydantic_settings.BaseSettings` whose model
prefix is `LINKEDIN_`. The new InfoJobs-specific fields live in the SAME
`Settings` class (per the InfoJobs design — keep one config object as
the single source of truth), but read from `INFOJOBS_*` env vars
(per-field `validation_alias` overrides the model-level prefix for
those fields), exactly like the `indeed_*` fields that landed in T-001
of the `indeed_platform` change.

This test file is the RED → GREEN → REFACTOR anchor for T-001 of the
`infojobs_platform` change. It must be authored BEFORE the production
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
# Defaults — each of the 6 new `infojobs_*` fields has a documented default.
# ---------------------------------------------------------------------------


def test_infojobs_throttle_seconds_default_is_three() -> None:
    """`infojobs_throttle_seconds` defaults to `3.0` (per the InfoJobs
    design §2 — same default as the Indeed field)."""
    settings = Settings()
    assert settings.infojobs_throttle_seconds == 3.0


def test_infojobs_timeout_ms_default_is_15_000() -> None:
    """`infojobs_timeout_ms` defaults to `15_000` (per the InfoJobs design §2)."""
    settings = Settings()
    assert settings.infojobs_timeout_ms == 15_000


def test_infojobs_domain_default_is_www_infojobs_net() -> None:
    """`infojobs_domain` defaults to `"www.infojobs.net"` (per the InfoJobs
    design §2 and REQ-J-001)."""
    settings = Settings()
    assert settings.infojobs_domain == "www.infojobs.net"


def test_infojobs_max_pages_default_is_ten() -> None:
    """`infojobs_max_pages` defaults to `10` (per the InfoJobs design §2)."""
    settings = Settings()
    assert settings.infojobs_max_pages == 10


def test_infojobs_inter_page_delay_seconds_default_is_one_point_five() -> None:
    """`infojobs_inter_page_delay_seconds` defaults to `1.5` (per the
    InfoJobs design §2 — stricter than the Indeed default `1.0` because
    InfoJobs anti-bot (Distil + Geetest) is more aggressive than
    Cloudflare)."""
    settings = Settings()
    assert settings.infojobs_inter_page_delay_seconds == 1.5


def test_infojobs_user_agent_default_matches_linkedin_default() -> None:
    """`infojobs_user_agent` shares the same stealth desktop Chrome UA
    default as the LinkedIn `user_agent` field (per the InfoJobs design
    §2 — `_DEFAULT_USER_AGENT` is shared across sources)."""
    settings = Settings()
    assert settings.infojobs_user_agent == settings.user_agent
    # The shared default is a plausible stealth desktop Chrome string.
    assert "Mozilla" in settings.infojobs_user_agent
    assert "AppleWebKit" in settings.infojobs_user_agent
    assert "Chrome" in settings.infojobs_user_agent
    assert "Safari" in settings.infojobs_user_agent


# ---------------------------------------------------------------------------
# Env-var overrides — each `INFOJOBS_*` env var overrides its field via the
# per-field `validation_alias` (which overrides the model `env_prefix=
# "LINKEDIN_"` for the InfoJobs fields).
# ---------------------------------------------------------------------------


def test_infojobs_throttle_seconds_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`INFOJOBS_THROTTLE_SECONDS=6.0` overrides the default `3.0`."""
    monkeypatch.setenv("INFOJOBS_THROTTLE_SECONDS", "6.0")
    settings = Settings()
    assert settings.infojobs_throttle_seconds == 6.0


def test_infojobs_timeout_ms_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`INFOJOBS_TIMEOUT_MS=30000` overrides the default `15000`."""
    monkeypatch.setenv("INFOJOBS_TIMEOUT_MS", "30000")
    settings = Settings()
    assert settings.infojobs_timeout_ms == 30_000


def test_infojobs_domain_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`INFOJOBS_DOMAIN=br.infojobs.net` overrides the default `www.infojobs.net`."""
    monkeypatch.setenv("INFOJOBS_DOMAIN", "br.infojobs.net")
    settings = Settings()
    assert settings.infojobs_domain == "br.infojobs.net"


def test_infojobs_max_pages_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`INFOJOBS_MAX_PAGES=5` overrides the default `10`."""
    monkeypatch.setenv("INFOJOBS_MAX_PAGES", "5")
    settings = Settings()
    assert settings.infojobs_max_pages == 5


def test_infojobs_inter_page_delay_seconds_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`INFOJOBS_INTER_PAGE_DELAY_SECONDS=2.5` overrides the default `1.5`."""
    monkeypatch.setenv("INFOJOBS_INTER_PAGE_DELAY_SECONDS", "2.5")
    settings = Settings()
    assert settings.infojobs_inter_page_delay_seconds == 2.5


def test_infojobs_user_agent_env_var_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`INFOJOBS_USER_AGENT=...` overrides the default stealth UA."""
    monkeypatch.setenv("INFOJOBS_USER_AGENT", "CustomInfoJobs/1.0")
    settings = Settings()
    assert settings.infojobs_user_agent == "CustomInfoJobs/1.0"


# ---------------------------------------------------------------------------
# Regression: the existing LinkedIn + Indeed fields are unchanged.
# ---------------------------------------------------------------------------


def test_existing_linkedin_throttle_seconds_default_is_unchanged() -> None:
    """Regression: `throttle_seconds` (LinkedIn) still defaults to `3.0`."""
    settings = Settings()
    assert settings.throttle_seconds == 3.0


def test_existing_indeed_throttle_seconds_default_is_unchanged() -> None:
    """Regression: `indeed_throttle_seconds` still defaults to `3.0`."""
    settings = Settings()
    assert settings.indeed_throttle_seconds == 3.0


def test_existing_indeed_domain_default_is_unchanged() -> None:
    """Regression: `indeed_domain` still defaults to `es.indeed.com`."""
    settings = Settings()
    assert settings.indeed_domain == "es.indeed.com"


def test_linkedin_and_indeed_env_vars_dont_cross_bleed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: setting `INFOJOBS_*` env vars does NOT bleed into
    LinkedIn or Indeed fields, and vice versa.

    Each source's env var maps to its own field only.
    """
    monkeypatch.setenv("LINKEDIN_THROTTLE_SECONDS", "7.5")
    monkeypatch.setenv("INDEED_THROTTLE_SECONDS", "6.0")
    monkeypatch.setenv("INFOJOBS_THROTTLE_SECONDS", "4.5")
    settings = Settings()
    assert settings.throttle_seconds == 7.5
    assert settings.indeed_throttle_seconds == 6.0
    assert settings.infojobs_throttle_seconds == 4.5


# ---------------------------------------------------------------------------
# Conftest fixtures — `sample_infojobs_jobs` and `fake_infojobs_port`.
#
# The InfoJobs fixtures are added in T-001 of `infojobs_platform` to
# unblock T-005 (`SearchJobsUseCase` for InfoJobs) without re-defining
# the `FakeJobSearchPort` class. The `FakeJobSearchPort` class itself
# was added in T-001 of `indeed_platform` and is reused here.
# ---------------------------------------------------------------------------


def test_sample_infojobs_jobs_returns_three_jobs_with_canonical_urls(
    sample_infojobs_jobs: list[Job],
) -> None:
    """`sample_infojobs_jobs` returns exactly 3 `Job` instances, each with
    all 6 `Job` fields populated and a canonical InfoJobs URL.

    The URL pattern is a placeholder for the T-010 real-capture step
    (the exact format will be confirmed by the real InfoJobs DOM). For
    T-001, the test only asserts the URL is rooted at the InfoJobs
    domain and embeds the Job id (so a route that builds URLs from
    the Job.id source can find it).
    """
    assert len(sample_infojobs_jobs) == 3
    for job in sample_infojobs_jobs:
        assert isinstance(job, Job)
        # All 6 fields are populated.
        assert isinstance(job.id, str) and job.id
        assert isinstance(job.title, str) and job.title
        assert isinstance(job.company, str) and job.company
        assert isinstance(job.location, str) and job.location
        assert isinstance(job.url, str) and job.url
        # `posted_at` is tz-aware per the domain invariant.
        assert job.posted_at.tzinfo is not None
        assert job.posted_at.tzinfo.utcoffset(job.posted_at) is not None
        # The URL is a canonical InfoJobs URL.
        assert job.url.startswith("https://www.infojobs.net")
        # The id from the URL must match the Job.id (the canonical source).
        assert job.id in job.url


def test_fake_infojobs_port_fixture_is_callable(
    fake_infojobs_port: object,
) -> None:
    """`fake_infojobs_port` exposes an async `search` method, satisfying
    the structural `JobSearchPort` Protocol (cite REQ-I-003 analog).

    The fixture reuses the `FakeJobSearchPort` class added in T-001 of
    `indeed_platform`; this test confirms the InfoJobs fixture wires
    it correctly.
    """
    assert callable(getattr(fake_infojobs_port, "search", None))
    assert inspect.iscoroutinefunction(fake_infojobs_port.search)  # type: ignore[attr-defined]


async def test_fake_infojobs_port_records_calls() -> None:
    """`FakeJobSearchPort` (the class behind the `fake_infojobs_port`
    fixture) records every call's `(keywords, location, limit)` so tests
    can assert the route/use case forwarded the input correctly.

    This test instantiates the class directly (via the conftest import)
    to exercise the `calls` list independently of the fixture wiring.
    The class is the same one used by the `fake_indeed_port` fixture
    (added in T-001 of `indeed_platform`).
    """
    port = FakeJobSearchPort()
    await port.search("python", "barcelona", 5)
    await port.search("rust", "valencia", 3)
    assert port.calls == [
        ("python", "barcelona", 5),
        ("rust", "valencia", 3),
    ]
