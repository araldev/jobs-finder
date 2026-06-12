"""Unit tests for the shared `paginated_search` helper.

Spec: REQ-PAG-001..PAG-004.
The helper is a pure-async, source-agnostic function at
`jobs_finder.infrastructure.pagination.paginated_search` that owns the
auto-pagination loop. Each source (LinkedIn, Indeed, InfoJobs) plugs in
via a `fetch_one_page` closure that captures the source-specific
concerns (URL formula, `_parse_cards` arity, blocked-check, page-0
zero-cards semantic).

This file covers REQ-PAG-001 + REQ-PAG-002 + REQ-PAG-003 with 14
scenarios. The per-source factory integration
(`scraper._make_fetch_one_page(keywords, location)`) is covered by
the existing per-source test suites as the regression check.

Test approach:
- Fake `throttle` (a `CountingThrottle` async CM) so we can assert
  the throttle is acquired exactly once per `search()`-shaped call.
- Fake `fetch_one_page` (a per-test async closure) with a
  configurable return schedule so we can drive the loop's
  control-flow branches deterministically.
- `monkeypatch.setattr("asyncio.sleep", AsyncMock())` to count
  inter-page sleeps without real wall-clock time.
- Test-local exception types (`_TimeoutError`, `_BlockedError`,
  `_ParseError`) keep this file source-agnostic; the helper does
  not import any per-source exception.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.pagination import paginated_search

# NOTE: do NOT import any per-source exception or module here; the
# helper is source-agnostic and so are its tests.


# ---------------------------------------------------------------------------
# Test-local exception types
# ---------------------------------------------------------------------------


class _TimeoutError(Exception):
    """Stand-in for any source's `*TimeoutError` in the helper's contract tests."""


class _BlockedError(Exception):
    """Stand-in for any source's `*BlockedError` — NOT in `timeout_exc_type`."""


class _ParseError(Exception):
    """Stand-in for any source's `*ParseError` — NOT in `timeout_exc_type`."""


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class CountingThrottle:
    """Minimal async context manager that counts `__aenter__` / `__aexit__` calls.

    The real throttles (`AsyncThrottle`, `IndeedAsyncThrottle`,
    `InfoJobsAsyncThrottle`) all implement the same
    `__aenter__` / `__aexit__` shape; the helper treats the
    `throttle` parameter as `Any` and does not import any of them.
    """

    def __init__(self) -> None:
        self.enter_count: int = 0
        self.exit_count: int = 0

    async def __aenter__(self) -> CountingThrottle:
        self.enter_count += 1
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        self.exit_count += 1


def make_job(i: int) -> Job:
    """Build a deterministic `Job` for assertions in this test file.

    All fields are unique by `i` so test assertions can identify
    which job they are looking at. `posted_at` is tz-aware UTC
    (required by `Job.__post_init__`).
    """
    return Job(
        id=str(i),
        title=f"Title {i}",
        company=f"Co {i}",
        location="Madrid",
        url=f"https://example.com/jobs/{i}",
        posted_at=datetime(2026, 5, 1, tzinfo=UTC),
        source="linkedin",
    )


def make_fetcher(
    returns: list[list[Job]] | None = None,
    *,
    raises: type[Exception] | None = None,
    raises_for_page_zero_only: bool = False,
) -> tuple[Callable[[Any, int, int], Awaitable[list[Job]]], list[tuple[Any, int, int]]]:
    """Build a fake `fetch_one_page` closure with a configurable return schedule.

    `returns` is a queue; each call pops the next `list[Job]`. When
    the queue is exhausted the closure returns `[]` (the helper's
    "end of results" signal).

    `raises` is an exception class (NOT an instance) that the
    closure raises on the configured page(s). `raises_for_page_zero_only=True`
    limits the raise to `page_index == 0` (the Indeed/InfoJobs
    page-0 zero-cards semantic: the closure itself raises when the
    parser returns zero cards on the first page).

    Returns `(fetcher, calls)` so tests can both drive the closure
    AND assert the args it was called with.
    """
    queue: list[list[Job]] = list(returns) if returns is not None else []
    calls: list[tuple[Any, int, int]] = []

    async def fetcher(page: Any, page_index: int, remaining: int) -> list[Job]:
        calls.append((page, page_index, remaining))
        if raises is not None and (not raises_for_page_zero_only or page_index == 0):
            raise raises("closure-raised-exception")
        if queue:
            return queue.pop(0)
        return []

    return fetcher, calls


# ---------------------------------------------------------------------------
# REQ-PAG-001: `paginated_search` is the canonical loop implementation
# ---------------------------------------------------------------------------


async def test_limit_cap_mid_loop_returns_at_most_limit_jobs() -> None:
    """`limit=10` over 5 jobs/call, `max_pages=3` returns at most 10 jobs and stops early.

    REQ-PAG-001 (limit cap mid-loop): when the fetcher returns 5
    jobs per call, two page requests cover the 10-job limit. The
    helper MUST break before the 3rd page so the result is exactly
    10 jobs (no over-fetch).
    """
    fetcher, calls = make_fetcher(returns=[[make_job(i) for i in range(1, 6)]] * 5)
    throttle = CountingThrottle()
    result = await paginated_search(  # helper added in GREEN
        page=None,
        throttle=throttle,
        fetch_one_page=fetcher,
        limit=10,
        max_pages=3,
        inter_page_delay_seconds=0.0,
        timeout_exc_type=_TimeoutError,
    )
    assert len(result) == 10
    # Two fetcher calls (5 + 5 = 10), not three.
    assert len(calls) == 2


async def test_max_pages_cap_caps_fetcher_calls_to_max_pages() -> None:
    """`max_pages=3, limit=100, 5 jobs/page` makes exactly 3 fetcher calls.

    REQ-PAG-001 (max_pages cap): the loop MUST stop at the
    `max_pages` ceiling even if the `limit` was not reached yet. The
    helper never issues more requests than the configured
    `max_pages` per `search()`.
    """
    fetcher, calls = make_fetcher(
        returns=[[make_job(i) for i in range(1, 6)]] * 5,
    )
    throttle = CountingThrottle()
    result = await paginated_search(
        page=None,
        throttle=throttle,
        fetch_one_page=fetcher,
        limit=100,
        max_pages=3,
        inter_page_delay_seconds=0.0,
        timeout_exc_type=_TimeoutError,
    )
    assert len(calls) == 3
    # 3 pages × 5 jobs = 15.
    assert len(result) == 15


# ---------------------------------------------------------------------------
# REQ-PAG-002: Helper owns the loop control flow
# ---------------------------------------------------------------------------


async def test_limit_break_stops_loop_when_first_page_satisfies_limit() -> None:
    """A first page whose result count >= `limit` ends the loop after page 0.

    REQ-PAG-002 (limit break): the closure is expected to cap its
    return to `remaining` (real parsers do this; the helper trusts
    the closure's output). When the capped return brings
    `len(jobs) >= limit`, the next iteration's pre-check breaks
    the loop. The helper MUST NOT issue a 2nd page request.
    """
    calls: list[tuple[Any, int, int]] = []

    async def fetcher(page: Any, page_index: int, remaining: int) -> list[Job]:
        # Parser-style: cap to `remaining` so the closure never returns
        # more jobs than the caller still needs.
        calls.append((page, page_index, remaining))
        return [make_job(i) for i in range(1, min(remaining, 5) + 1)]

    throttle = CountingThrottle()
    result = await paginated_search(
        page=None,
        throttle=throttle,
        fetch_one_page=fetcher,
        limit=2,
        max_pages=10,
        inter_page_delay_seconds=0.0,
        timeout_exc_type=_TimeoutError,
    )
    # The fetcher was called once with `remaining=2`; it returned 2
    # jobs (capped). The helper's top-of-loop check then broke
    # before page 1.
    assert len(calls) == 1
    assert calls[0] == (None, 0, 2)
    assert len(result) == 2


async def test_max_pages_cap_stops_loop_at_ceiling_even_when_limit_unreached() -> None:
    """`max_pages=3, limit=100, 1+ job/page` → exactly 3 calls; loop stops on the ceiling.

    REQ-PAG-002 (max-pages cap / budget-exhaustion): the helper
    MUST terminate on the `max_pages` ceiling even when the
    `limit` was not reached AND no early-break branch fired.
    The closure returns 1 job per call (enough to avoid the
    zero-cards break) so the loop runs to the ceiling.

    NOTE: a closure that returns `[]` per call would trigger the
    zero-cards break after page 0 (1 call, NOT 3) — that
    scenario is already covered by `test_zero_cards_break_...`
    below. This test exercises the "I exhausted my budget"
    stop, not the empty-result stop.
    """
    fetcher, calls = make_fetcher(
        returns=[[make_job(1)], [make_job(2)], [make_job(3)]],
    )
    throttle = CountingThrottle()
    result = await paginated_search(
        page=None,
        throttle=throttle,
        fetch_one_page=fetcher,
        limit=100,
        max_pages=3,
        inter_page_delay_seconds=0.0,
        timeout_exc_type=_TimeoutError,
    )
    assert len(calls) == 3
    assert len(result) == 3


async def test_zero_delay_skips_sleep_call_entirely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`inter_page_delay_seconds=0.0` does NOT call `asyncio.sleep` at all.

    REQ-PAG-002 (delay `0.0` skips sleep): the `> 0` guard makes
    the call vanish — no event-loop yield, no wall-clock wait.
    Tests monkeypatch `asyncio.sleep` (already imported by the
    helper) and assert `await_count == 0`.
    """
    sleep_mock = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", sleep_mock)

    fetcher, _ = make_fetcher(
        returns=[[make_job(1)], [make_job(2)]],  # forces 2 fetcher calls
    )
    throttle = CountingThrottle()
    await paginated_search(
        page=None,
        throttle=throttle,
        fetch_one_page=fetcher,
        limit=100,
        max_pages=2,
        inter_page_delay_seconds=0.0,
        timeout_exc_type=_TimeoutError,
    )
    assert sleep_mock.await_count == 0


async def test_positive_delay_fires_exactly_n_minus_one_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`inter_page_delay_seconds=1.0, max_pages=3` calls `asyncio.sleep(1.0)` exactly twice.

    REQ-PAG-002 (delay `>0` fires N-1 times): the sleep fires
    BEFORE the next page request, never after the last one. Three
    page requests → exactly 2 sleeps, each `(1.0,)`.
    """
    sleep_mock = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", sleep_mock)

    fetcher, _ = make_fetcher(
        returns=[[make_job(1)], [make_job(2)], [make_job(3)]],
    )
    throttle = CountingThrottle()
    await paginated_search(
        page=None,
        throttle=throttle,
        fetch_one_page=fetcher,
        limit=100,
        max_pages=3,
        inter_page_delay_seconds=1.0,
        timeout_exc_type=_TimeoutError,
    )
    # 3 page requests → 2 inter-page sleeps.
    assert sleep_mock.await_count == 2
    assert sleep_mock.await_args_list[0].args == (1.0,)
    assert sleep_mock.await_args_list[1].args == (1.0,)


async def test_page_zero_timeout_propagates_to_caller() -> None:
    """A `timeout_exc_type` raised on page 0 propagates (no catch).

    REQ-PAG-002 (page-0 timeout raises): the first page is the
    "real" page — a timeout there is a real error
    (Cloudflare block, zero results, network failure). The helper
    MUST NOT swallow it.
    """
    fetcher, _ = make_fetcher(raises=_TimeoutError)
    throttle = CountingThrottle()
    with pytest.raises(_TimeoutError, match="closure-raised-exception"):
        await paginated_search(
            page=None,
            throttle=throttle,
            fetch_one_page=fetcher,
            limit=100,
            max_pages=3,
            inter_page_delay_seconds=0.0,
            timeout_exc_type=_TimeoutError,
        )


async def test_subsequent_page_timeout_breaks_gracefully() -> None:
    """A `timeout_exc_type` raised on page > 0 breaks the loop and returns partial jobs.

    REQ-PAG-002 (page-`>0` timeout break): a timeout on page 1 is
    "end of results" or an anti-bot re-challenge. The helper
    breaks gracefully and returns whatever it collected on page 0
    (no raise).
    """

    async def fetcher(page: Any, page_index: int, remaining: int) -> list[Job]:
        if page_index == 0:
            return [make_job(1)]
        raise _TimeoutError("page-1-timed-out")

    throttle = CountingThrottle()
    result = await paginated_search(
        page=None,
        throttle=throttle,
        fetch_one_page=fetcher,
        limit=100,
        max_pages=3,
        inter_page_delay_seconds=0.0,
        timeout_exc_type=_TimeoutError,
    )
    # Helper returned page 0's job, did NOT raise.
    assert len(result) == 1
    assert result[0].id == "1"
    # Throttle still released (acquired once, exited once) despite the break.
    assert throttle.enter_count == 1
    assert throttle.exit_count == 1


async def test_zero_cards_break_ends_loop_on_empty_result() -> None:
    """An empty `[]` from the fetcher ends the loop (no `max_pages` exhaustion).

    REQ-PAG-002 (zero-cards break): a single empty page at any
    `page_index` is the universal "end of results" signal. The
    helper breaks BEFORE the next iteration's `max_pages` cap.
    """
    fetcher, calls = make_fetcher(
        returns=[[make_job(1)], []],
    )
    throttle = CountingThrottle()
    result = await paginated_search(
        page=None,
        throttle=throttle,
        fetch_one_page=fetcher,
        limit=100,
        max_pages=5,
        inter_page_delay_seconds=0.0,
        timeout_exc_type=_TimeoutError,
    )
    assert len(calls) == 2
    assert len(result) == 1
    assert result[0].id == "1"


async def test_throttle_is_acquired_exactly_once_around_the_loop() -> None:
    """`throttle.__aenter__` is called exactly once for the whole `paginated_search` call.

    REQ-PAG-002 (throttle acquired once): the helper wraps the
    entire loop in `async with throttle:` so consecutive
    `search()` calls are paced by the throttle's
    `min_interval_seconds`, while back-to-back page requests
    inside one search are NOT.

    `max_pages=5` with always-non-empty pages exercises the full
    loop body without relying on any early-break branch.
    """
    fetcher, _ = make_fetcher(
        returns=[[make_job(i)] for i in range(1, 6)],  # 5 pages, 1 job each
    )
    throttle = CountingThrottle()
    await paginated_search(
        page=None,
        throttle=throttle,
        fetch_one_page=fetcher,
        limit=100,
        max_pages=5,
        inter_page_delay_seconds=0.0,
        timeout_exc_type=_TimeoutError,
    )
    assert throttle.enter_count == 1
    assert throttle.exit_count == 1


async def test_non_timeout_exception_propagates_to_caller() -> None:
    """An exception NOT in `timeout_exc_type` is NOT caught — it reaches the caller.

    REQ-PAG-002 (non-timeout exception propagates): the helper
    only catches the configured `timeout_exc_type`. A closure
    raising `BlockedError` (or any other exception type) MUST
    propagate unchanged. This is the guard that prevents the
    helper from accidentally swallowing source-specific errors
    like `LinkedInBlockedError` / `IndeedParseError`.
    """
    fetcher, _ = make_fetcher(raises=_BlockedError)
    throttle = CountingThrottle()
    with pytest.raises(_BlockedError, match="closure-raised-exception"):
        await paginated_search(
            page=None,
            throttle=throttle,
            fetch_one_page=fetcher,
            limit=100,
            max_pages=3,
            inter_page_delay_seconds=0.0,
            timeout_exc_type=_TimeoutError,  # does NOT match _BlockedError
        )


# ---------------------------------------------------------------------------
# REQ-PAG-003: Per-source `_make_fetch_one_page` factory
# ---------------------------------------------------------------------------


async def test_closure_returning_empty_on_page_zero_does_not_raise() -> None:
    """A LinkedIn-style closure that returns `[]` on page 0 produces `[]` (no raise).

    REQ-PAG-003 (LinkedIn page-0 zero-cards does NOT raise):
    LinkedIn's current contract is "break silently when the first
    page has zero cards" — the closure returns `[]` and the
    helper's zero-cards break returns `[]` to the caller. The
    helper MUST NOT introduce a `*ParseError` raise on page 0
    zero-cards (that would be a behavior change for LinkedIn).
    """
    fetcher, calls = make_fetcher(returns=[[]])  # page 0 returns []
    throttle = CountingThrottle()
    result = await paginated_search(
        page=None,
        throttle=throttle,
        fetch_one_page=fetcher,
        limit=100,
        max_pages=3,
        inter_page_delay_seconds=0.0,
        timeout_exc_type=_TimeoutError,
    )
    assert result == []
    assert len(calls) == 1


async def test_closure_raising_on_page_zero_propagates() -> None:
    """An Indeed/InfoJobs-style closure that raises `ParseError` on page 0 propagates.

    REQ-PAG-003 (Indeed page-0 zero-cards raises): the Indeed
    and InfoJobs closures translate "first page has zero cards"
    into a `*ParseError("zero_cards_on_first_page")` raise
    INSIDE the closure. Because the raise happens in the
    closure (not via `wait_for_selector`), it's NOT a
    `timeout_exc_type` — and the helper MUST propagate it
    (scenario 10 above already covers the "non-timeout
    propagates" branch; this test pins the per-source factory
    shape on top of it).
    """
    fetcher, _ = make_fetcher(
        raises=_ParseError,
        raises_for_page_zero_only=True,
    )
    throttle = CountingThrottle()
    with pytest.raises(_ParseError, match="closure-raised-exception"):
        await paginated_search(
            page=None,
            throttle=throttle,
            fetch_one_page=fetcher,
            limit=100,
            max_pages=3,
            inter_page_delay_seconds=0.0,
            timeout_exc_type=_TimeoutError,
        )


async def test_closure_receives_page_page_index_remaining_per_call() -> None:
    """The helper invokes the closure with `(page, page_index, remaining)` per call.

    REQ-PAG-003 (factory returns closure) — proven functionally:
    the helper calls the closure with the right args. The
    closure receives the SAME `page` the helper was given
    (so it can navigate) and the per-iteration
    `remaining = limit - len(jobs)` so the closure can cap the
    parser to "jobs I still need".
    """
    sentinel_page = object()
    fetcher, calls = make_fetcher(
        returns=[[make_job(1)]] * 3,  # 3 pages, 1 job each
    )
    throttle = CountingThrottle()
    await paginated_search(
        page=sentinel_page,
        throttle=throttle,
        fetch_one_page=fetcher,
        limit=5,  # jobs grow 1, 2, 3 → remaining 5, 4, 3
        max_pages=3,
        inter_page_delay_seconds=0.0,
        timeout_exc_type=_TimeoutError,
    )
    # The helper passes the same `page` each call (identity check).
    # The third arg is the per-iteration `limit - len(jobs)`.
    assert calls == [
        (sentinel_page, 0, 5),
        (sentinel_page, 1, 4),
        (sentinel_page, 2, 3),
    ]
    # All three calls received the SAME page object.
    assert calls[0][0] is calls[1][0] is calls[2][0] is sentinel_page
