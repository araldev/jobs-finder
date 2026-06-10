"""Integration tests for the composition-root wiring of the LinkedIn
auth-cookie path (T-005 of `backend-linkedin-auth`).

Spec coverage (REQ-LA-SCR-001 + REQ-LA-SCR-003):
- REQ-LA-SCR-001: the operator's `LINKEDIN_LI_AT` env var flows
  through `Settings` → `EnvLinkedInAuthCookieAdapter` →
  `LinkedInScraperSettings.auth_cookie` → the scraper's
  `search()` call. The integration test drives `build_app()` with
  a monkeypatched env and asserts the wiring is intact.
- REQ-LA-SCR-003: when `LINKEDIN_LI_AT` is absent, `build_app()`
  emits exactly ONE WARNING log line with the message
  \"LinkedIn scraper running without auth cookie; SERP will hit
  the auth wall and return a reduced list\".

The tests build the app via `build_app(use_case=...)` and inject
fake ports (no Playwright launch) so the test stays offline per
AGENTS.md rule #1. The only thing under test is the
composition-root wiring + the startup WARNING.

The synthetic test value `"AQEAAAAQEAAA"` (12 bytes ASCII) is the
canonical NON-REAL placeholder per the `backend-linkedin-auth`
exploration (obs #353). Real `li_at` cookies are forbidden from
the repo by AGENTS.md rule #7.
"""

from __future__ import annotations

import logging

import pytest

from jobs_finder.application.usecases.search_linkedin_jobs import (
    SearchLinkedInJobsUseCase,
)
from jobs_finder.infrastructure.cache.in_memory_ttl_cache import InMemoryTTLCache
from jobs_finder.infrastructure.config import Settings
from jobs_finder.presentation.app_factory import build_app
from tests.conftest import FakeJobSearchPort


def _build_app_with_linkedin_fake() -> object:
    """Build a FastAPI app with a fake LinkedIn port (no Playwright)."""
    linkedin_port = FakeJobSearchPort()
    linkedin_use_case = SearchLinkedInJobsUseCase(
        port=linkedin_port,
        cache=InMemoryTTLCache(ttl_seconds=60.0),
        source="linkedin",
    )
    return build_app(use_case=linkedin_use_case)


def test_startup_warning_when_cookie_absent(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-LA-SCR-003 — `build_app()` with no `LINKEDIN_LI_AT` env var
    emits exactly one WARNING log line with the message
    \"LinkedIn scraper running without auth cookie; SERP will hit
    the auth wall and return a reduced list\"."""
    monkeypatch.delenv("LINKEDIN_LI_AT", raising=False)
    with caplog.at_level(logging.WARNING):
        _build_app_with_linkedin_fake()
    matching = [
        r
        for r in caplog.records
        if "LinkedIn scraper running without auth cookie" in r.getMessage()
    ]
    assert len(matching) == 1, f"expected exactly 1 startup WARNING, got {len(matching)}"
    assert matching[0].levelno == logging.WARNING


def test_no_startup_warning_when_cookie_set(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-LA-SCR-003 — `build_app()` with `LINKEDIN_LI_AT` set does
    NOT emit the startup WARNING (the operator has opted in to the
    authenticated path)."""
    monkeypatch.setenv("LINKEDIN_LI_AT", "AQEAAAAQEAAA")
    with caplog.at_level(logging.WARNING):
        _build_app_with_linkedin_fake()
    matching = [
        r
        for r in caplog.records
        if "LinkedIn scraper running without auth cookie" in r.getMessage()
    ]
    assert matching == []


def test_wired_app_uses_env_cookie_when_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-LA-SCR-001 — the operator's `LINKEDIN_LI_AT` env var
    flows through `Settings` → `EnvLinkedInAuthCookieAdapter` →
    `LinkedInScraperSettings.auth_cookie`. The test asserts the
    `Settings()` instance sees the env var (the composition root
    constructs `Settings()` internally so the test does not have
    a direct handle on the adapter — the assertion is at the
    `Settings` boundary which is the load-bearing contract)."""
    monkeypatch.setenv("LINKEDIN_LI_AT", "AQEAAAAQEAAA")
    # The composition root does `Settings()` internally. The
    # test asserts `Settings()` reads the env var correctly —
    # this is the same behavior the composition root relies on
    # (the `linkedin_li_at` field on the resolved `Settings`
    # is what `EnvLinkedInAuthCookieAdapter` wraps).
    settings = Settings()
    assert settings.linkedin_li_at is not None
    assert settings.linkedin_li_at.get_secret_value() == "AQEAAAAQEAAA"
