"""Integration tests for the Indeed FastAPI route.

Spec: REQ-I-012, REQ-I-013, REQ-I-017.
Drives the FastAPI app in-process with `httpx.AsyncClient` over
`ASGITransport`. The Indeed use case is constructed against a
`FakeJobSearchPort` (the shared one from `tests/conftest.py`) so the
suite never launches a browser and never contacts Indeed.

The scenarios mirror the LinkedIn integration tests where the contracts
are 1:1 (200 happy, 422 missing/invalid, 502 with masked detail,
`X-Request-Id` echo, `/health` independence).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import httpx
import pytest
from bs4 import BeautifulSoup
from fastapi import FastAPI

from jobs_finder.infrastructure.indeed.exceptions import IndeedBlockedError
from jobs_finder.infrastructure.indeed.scraper import _parse_cards
from tests.conftest import FakeJobSearchPort
from tests.fixtures.indeed_search import SEARCH_PAGE_HTML

JOB_FIELDS: set[str] = {
    "id",
    "title",
    "company",
    "location",
    "url",
    "description",
    "posted_at",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """An `httpx.AsyncClient` bound to the in-process ASGI app.

    Uses the conftest `app` fixture (which wires BOTH use cases to
    fake ports) so Indeed and LinkedIn routes are both reachable.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# REQ-I-012 — happy path
# ---------------------------------------------------------------------------


async def test_get_jobs_indeed_returns_three_jobs_with_all_six_fields(
    client: httpx.AsyncClient, fake_indeed_port: FakeJobSearchPort
) -> None:
    """The 200 response has `jobs: [...]` with exactly the 6 spec fields per job."""
    response = await client.get("/jobs/indeed?keywords=python&location=madrid")

    assert response.status_code == 200
    body = response.json()
    assert "jobs" in body
    assert len(body["jobs"]) == 3

    for job in body["jobs"]:
        assert set(job.keys()) == JOB_FIELDS

    first = body["jobs"][0]
    assert first["id"] == "100000001"
    assert first["title"] == "Indeed Title 1"
    assert first["company"] == "Indeed Co 1"
    assert first["location"] == "Madrid, Spain"
    assert first["url"] == "https://es.indeed.com/viewjob?jk=100000001"
    assert first["posted_at"] is not None


async def test_get_jobs_indeed_forwards_keywords_location_and_default_limit(
    client: httpx.AsyncClient, fake_indeed_port: FakeJobSearchPort
) -> None:
    """The default `limit=20` from the Pydantic schema reaches the port."""
    response = await client.get("/jobs/indeed?keywords=python&location=madrid")

    assert response.status_code == 200
    assert fake_indeed_port.calls == [("python", "madrid", 20)]


async def test_get_jobs_indeed_forwards_explicit_limit(
    client: httpx.AsyncClient, fake_indeed_port: FakeJobSearchPort
) -> None:
    """`limit=5` is forwarded to the port unchanged."""
    response = await client.get("/jobs/indeed?keywords=python&location=madrid&limit=5")

    assert response.status_code == 200
    assert fake_indeed_port.calls == [("python", "madrid", 5)]


# ---------------------------------------------------------------------------
# REQ-I-013 — missing required query params -> 422
# ---------------------------------------------------------------------------


async def test_missing_keywords_returns_422(client: httpx.AsyncClient) -> None:
    """A request without `keywords` returns 422 mentioning `keywords`."""
    response = await client.get("/jobs/indeed?location=madrid")

    assert response.status_code == 422
    assert "keywords" in str(response.json())


async def test_missing_location_returns_422(client: httpx.AsyncClient) -> None:
    """A request without `location` returns 422 mentioning `location`."""
    response = await client.get("/jobs/indeed?keywords=python")

    assert response.status_code == 422
    assert "location" in str(response.json())


# ---------------------------------------------------------------------------
# REQ-I-013 — limit out of range -> 422
# ---------------------------------------------------------------------------


async def test_limit_zero_returns_422(client: httpx.AsyncClient) -> None:
    """`limit=0` is below `ge=1` and returns 422."""
    response = await client.get("/jobs/indeed?keywords=python&location=madrid&limit=0")
    assert response.status_code == 422


async def test_limit_101_returns_422(client: httpx.AsyncClient) -> None:
    """`limit=101` is above `le=100` and returns 422."""
    response = await client.get("/jobs/indeed?keywords=python&location=madrid&limit=101")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# REQ-I-017 — scraper failure -> 502 with masked detail
# ---------------------------------------------------------------------------


async def test_indeed_blocked_returns_502_with_masked_detail(
    app: FastAPI, fake_indeed_port: FakeJobSearchPort
) -> None:
    """`IndeedBlockedError` becomes 502 with masked detail + request_id.

    The body MUST NOT leak the `IndeedBlockedError` type or message
    (the upstream source name is internal information).
    """
    fake_indeed_port._error = IndeedBlockedError("cloudflare challenge")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/jobs/indeed?keywords=python&location=madrid")

    assert response.status_code == 502
    body = response.json()
    assert body["detail"] == "upstream source unavailable"
    # The original exception type and message MUST NOT leak.
    assert "IndeedBlockedError" not in str(body)
    assert "cloudflare" not in str(body)
    # `request_id` is present and non-empty.
    assert isinstance(body.get("request_id"), str)
    assert body["request_id"]


# ---------------------------------------------------------------------------
# REQ-I-017 — X-Request-Id echo + correlation
# ---------------------------------------------------------------------------


async def test_x_request_id_propagates_through_502_body_and_header(
    app: FastAPI, fake_indeed_port: FakeJobSearchPort
) -> None:
    """A client-provided `X-Request-Id` is echoed in BOTH header and 502 body."""
    fake_indeed_port._error = IndeedBlockedError("cloudflare challenge")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/jobs/indeed?keywords=python&location=madrid",
            headers={"X-Request-Id": "indeed-trace-1"},
        )

    assert response.status_code == 502
    body = response.json()
    assert response.headers.get("X-Request-Id") == "indeed-trace-1"
    assert body["request_id"] == "indeed-trace-1"


async def test_x_request_id_is_echoed_on_successful_200(
    client: httpx.AsyncClient,
) -> None:
    """A client-provided `X-Request-Id` is echoed on success too."""
    response = await client.get(
        "/jobs/indeed?keywords=python&location=madrid",
        headers={"X-Request-Id": "ok-trace-indeed"},
    )
    assert response.status_code == 200
    assert response.headers.get("X-Request-Id") == "ok-trace-indeed"


# ---------------------------------------------------------------------------
# REQ-I-017 — /health independence
# ---------------------------------------------------------------------------


async def test_health_returns_ok_without_calling_indeed_port(
    client: httpx.AsyncClient, fake_indeed_port: FakeJobSearchPort
) -> None:
    """`GET /health` is 200, body `{"status":"ok"}`, and the Indeed port is NEVER called.

    The test must confirm the Indeed route AND the `/health` route
    coexist on the same app without one calling the other.
    """
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert fake_indeed_port.calls == []


# ---------------------------------------------------------------------------
# indeed-date-fix — end-to-end scraper→parser integration (REQ-I-009 delta)
# ---------------------------------------------------------------------------


def test_parse_cards_end_to_end_returns_distinct_posted_at() -> None:
    """`_parse_cards(SEARCH_PAGE_HTML, 15, "es.indeed.com")` returns 15
    non-`None` `posted_at` values with at least 13 distinct
    timestamps, and the first equals
    `datetime(2025, 9, 24, 5, 0, 0, tzinfo=UTC)`.

    Defense-in-depth: this drives the module-level `_parse_cards`
    (called by the scraper) against the committed 2026-06-02
    real capture and asserts the JSON path wired through
    `parse_indeed_posted_at(card, soup)` returns the real
    `pubDate` for every card with a matching `jobkey`. The
    legacy `datetime.now(UTC)` fallback would FAIL this test
    (it would collapse all 15 timestamps to the scrape second,
    yielding 1 distinct value, not 13+).

    The 2026-06-02 capture has 15 records in
    `mosaicProviderJobCardsModel/results/` with 14 unique
    `pubDate` values (2 records share `pubDate=1780030800000`).
    Of the 15 cards, 14 have a JSON match (distinct real
    `pubDate`s) and 1 (`789abcdef0123456`) has no JSON record
    and falls back to `datetime.now(UTC)`. The total distinct
    count is therefore 14 — 13 unique JSON `pubDate`s + 1
    shared `pubDate` (counted once) + 1 `datetime.now(UTC)`
    fallback. The lower bound 13 (well above the 1 the
    fallback would produce) is sufficient to prove the JSON
    path is wired through.

    The first card's `pubDate=1758690000000` → the pinned
    `datetime(2025, 9, 24, 5, 0, 0, tzinfo=UTC)`. If this test
    fails, the JSON wire-through in `scraper.py` regressed.
    """
    soup = BeautifulSoup(SEARCH_PAGE_HTML, "html.parser")
    jobs = _parse_cards(soup, remaining=15, domain="es.indeed.com")

    assert len(jobs) == 15
    posted_at_values = [job.posted_at for job in jobs]
    # No None: every card got a real posted_at (14 from the
    # JSON, 1 from the `datetime.now(UTC)` fallback).
    assert all(p is not None for p in posted_at_values), (
        f"all 15 jobs must have non-None posted_at; got {posted_at_values}"
    )
    # Many distinct values: the JSON has 14 unique pubDates,
    # the legacy `datetime.now(UTC)` fallback would collapse
    # all 15 jobs to 1 distinct value. The lower bound 13
    # proves the JSON path is wired through.
    assert len(set(posted_at_values)) >= 13, (
        f"expected at least 13 distinct posted_at values; got "
        f"{len(set(posted_at_values))} distinct — the JSON path "
        f"may have regressed to the datetime.now(UTC) fallback"
    )
    # First job's posted_at is the exact pubDate=1758690000000.
    assert posted_at_values[0] == datetime(2025, 9, 24, 5, 0, 0, tzinfo=UTC)
    # All are tz-aware UTC.
    assert all(p.tzinfo == UTC for p in posted_at_values)
