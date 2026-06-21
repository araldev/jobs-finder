"""LIVE tests for the InfoJobs province/country resolution (T-005).

Spec: REQ-PROV-001 scenario "USER-VERIFIED" + the LIVE test gate
documented in `README.md` "InfoJobs province/country resolution".

These tests verify the v3 InfoJobs URL plumb against the REAL
InfoJobs SERP. The 4 speculative province IDs (Madrid=28,
Barcelona=8, Valencia=46, Sevilla=41) are gated by `LLM_LIVE_TESTS=1`
so a future operator can run them on a residential IP
(distinct from the v1 capture) and confirm the IDs are
correct. A failing ID is REMOVED from the dict (1-line
change) and the scraper transparently degrades to the v1
`?l=<str>` path (graceful degradation, no 500).

**Live tests are NEVER run in CI** (AGENTS.md rule #1).
They require:

  1. The `LLM_LIVE_TESTS=1` env var set so the
     `pytest.mark.skipif` gating lets the test run.
  2. Outbound network access to `www.infojobs.net` (the
     real InfoJobs domain the scraper drives).

To run the live tests locally:

    LLM_LIVE_TESTS=1 uv run pytest tests/integration/test_infojobs_live.py -v

The 1 test is:

  - `test_live_malaga_returns_actual_malaga_jobs`: the v1
    canonical smoke-test case (the user's 2026-06-10 capture).
    A query for `?q=react&location=malaga` with the v3
    plumb (`provinceIds=34&countryIds=17`) returns jobs
    whose `location` field is "Málaga" (or starts with
    "Málaga" — InfoJobs sometimes appends the province to
    the city). The test asserts AT LEAST 1 result and that
    EVERY result's location is in the Málaga area. A
    failure here is the canonical "the URL plumb is wrong"
    signal — the operator investigates whether the
    provinceId (34) or countryId (17) is stale.

The 4 speculative IDs (Madrid, Barcelona, Valencia, Sevilla)
are NOT exercised by this test (the captured sample set is
small; the test focuses on the 1 ID the user has already
smoke-tested). A follow-up change can add
`test_live_madrid_returns_actual_madrid_jobs` etc. with
the same shape; the LIVE test gate is the seam.
"""

from __future__ import annotations

import os

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from jobs_finder.presentation.app_factory import build_app

# Gating: the live test runs ONLY when `LLM_LIVE_TESTS=1` is
# in the environment. The default `pytest` run (and CI) SKIPS
# it — AGENTS.md rule #1: live tests are NEVER run in CI.
_LIVE_GATE = pytest.mark.skipif(
    not os.getenv("LLM_LIVE_TESTS"),
    reason=(
        "Live InfoJobs test, gated by LLM_LIVE_TESTS=1 "
        "(per AGENTS.md rule #1: live tests are never run in CI)"
    ),
)


@_LIVE_GATE
async def test_live_malaga_returns_actual_malaga_jobs() -> None:
    """End-to-end smoke test: `?q=react&location=malaga` returns actual Málaga jobs.

    The v3 URL plumb appends `&provinceIds=34&countryIds=17`
    to the v1 URL when the `HardcodedLocationResolver`
    resolves `malaga` → `(34, 17)`. The test drives the REAL
    InfoJobs SERP via the InfoJobs use case (NOT a fake
    port) and asserts:

        1. The HTTP response is 200.
        2. The response body has `>= 1` job.
        3. EVERY returned job's `location` field contains
           the substring "Málaga" (case-insensitive). The
           test is strict about substring (NOT exact-match)
           because InfoJobs appends the province name in
           some SERP variations (`"Málaga, Andalucía"`,
           `"Málaga, Spain"`, etc.).

    A failure of assertion 3 (jobs from other regions) is
    the canonical "the URL plumb is wrong" signal — the
    operator investigates whether `provinceId=34` is stale
    (InfoJobs may have changed the internal namespace) and
    either fixes the dict entry or removes it (graceful
    fallback to `?l=malaga`).
    """
    app = build_app()
    async with (
        LifespanManager(app, startup_timeout=30, shutdown_timeout=30),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        response = await client.get(
            "/jobs/infojobs",
            params={"keywords": "react", "location": "malaga", "limit": 10},
        )

    assert response.status_code == 200, (
        f"Expected 200 from /jobs/infojobs, got {response.status_code}: {response.text[:200]}"
    )
    body = response.json()
    jobs = body.get("jobs", [])
    assert len(jobs) >= 1, (
        "Expected >= 1 Málaga job from "
        "/jobs/infojobs?keywords=react&location=malaga, got 0. "
        "The v3 URL plumb may be wrong (provinceId=34 or countryId=17 "
        "may be stale); verify the URL in the InfoJobs route logs."
    )
    for job in jobs:
        location = job.get("location", "")
        assert "málaga" in location.lower() or "malaga" in location.lower(), (
            f"Job {job.get('id')!r} has location {location!r} which is NOT in "
            f"the Málaga area. The v3 URL plumb may have returned jobs from "
            f"the wrong region. Investigate provinceId=34 and countryId=17."
        )
