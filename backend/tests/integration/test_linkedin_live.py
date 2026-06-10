"""LIVE integration test for the LinkedIn structured location fallback.

Spec: `backend-linkedin-location-fallback` REQ-STR-LOC-001.

This test is GATED by the `LLM_LIVE_TESTS` env var per
AGENTS.md rule #1 ("No live scraping in tests"). When
`LLM_LIVE_TESTS` is NOT set to `"1"`, the test is SKIPPED
in CI. To run the LIVE probe manually:

    LLM_LIVE_TESTS=1 uv run pytest tests/integration/test_linkedin_live.py -v

The test:
  1. Builds the real composition root (`build_app()`).
  2. Invokes the LinkedIn scraper's `search()` with
     `?keywords=react&location=Antequera,Andalucía,Spain` (the
     structured URL captured by the user in the explore phase).
  3. Asserts that at least 1 of the first 5 results has a
     `location` field containing `"Antequera"`, `"Málaga"`, or
     `"Andalucía"`.

The test confirms the VERIFIED entry (`antequera`) works
end-to-end against real LinkedIn. The 9 SPECULATIVE entries
are validated by the same test in a follow-up change (one
test per city, gated on `LLM_LIVE_TESTS=1`).

If the test fails because LinkedIn returned 0 results: the
structured URL format may not be honored for that city, OR
LinkedIn's anti-bot blocked the request from this IP. The
fallback is `?location=<raw_string>` (the legacy v1
broken-but-doesn't-500 path) — no regression.
"""

from __future__ import annotations

import os

import pytest

# Skip the LIVE test by default (AGENTS.md rule #1).
_LIVE_TESTS_ENABLED = os.environ.get("LLM_LIVE_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not _LIVE_TESTS_ENABLED,
    reason="Live LinkedIn test, gated by LLM_LIVE_TESTS=1 (per AGENTS.md rule #1)",
)


@pytest.mark.asyncio
async def test_live_antequera_returns_actual_antequera_jobs() -> None:
    """`?location=Antequera,Andalucía,Spain` returns ≥1 real Antequera / Málaga / Andalucía job.

    This is the ONLY VERIFIED entry in `_STRUCTURED_MAPPING`.
    The LIVE test confirms the URL format `?location=<city>,
    <province>,<country>` (URL-encoded as
    `?location=Antequera%2CAndaluc%C3%ADa%2CSpain`) returns
    real jobs in Antequera / Málaga / Andalucía when invoked
    against real LinkedIn.

    Spec: REQ-STR-LOC-001, the `LLM_LIVE_TESTS=1` gate from
    the README's "LinkedIn structured location fallback"
    section. The 9 SPECULATIVE entries (Fuengirola, Marbella,
    Toledo, etc.) are validated in a follow-up change with
    one test per city.
    """
    # Build the real composition root.
    from jobs_finder.infrastructure.linkedin.scraper import (  # noqa: PLC0415
        LinkedInPlaywrightScraper,
    )
    from jobs_finder.main import app  # noqa: PLC0415

    # The composition root exposes the LinkedIn use case on
    # `app.state.job_search_port`. We unwrap the cache wrapper
    # to get to the raw scraper (the raw scraper is the one
    # that actually navigates to LinkedIn).
    port = getattr(app.state, "job_search_port", None)
    assert port is not None
    # Unwrap the cache wrapper to reach the raw `LinkedInPlaywrightScraper`.
    raw = port
    if hasattr(raw, "_port"):
        raw = raw._port  # noqa: SLF001
    if not isinstance(raw, LinkedInPlaywrightScraper):
        pytest.skip("Composition root is using a non-LinkedIn scraper (test config differs)")

    # Enter the scraper's async context manager (launches a
    # headless Chromium).
    async with raw:
        jobs = await raw.search(
            keywords="react",
            location="Antequera",
            limit=5,
        )

    # The structured URL MUST return at least 1 real
    # Antequera-area job. LinkedIn's fuzzy match is
    # permissive (matches city, province, OR country).
    antequera_keywords = ("Antequera", "Málaga", "Andalucía")
    matching = [job for job in jobs if any(kw in (job.location or "") for kw in antequera_keywords)]
    assert len(matching) >= 1, (
        f"Expected ≥1 Antequera / Málaga / Andalucía job in the first 5 results, "
        f"got: {[j.location for j in jobs]}. The structured URL format may not be "
        f"honored by LinkedIn, or the IP is blocked."
    )
