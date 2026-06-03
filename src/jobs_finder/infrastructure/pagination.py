"""Canonical auto-pagination loop used by LinkedIn, Indeed, and InfoJobs.

Spec: REQ-PAG-001, REQ-PAG-002, REQ-PAG-003.

The 3 source scrapers (`LinkedInPlaywrightScraper`,
`IndeedPlaywrightScraper`, `InfoJobsPlaywrightScraper`) all
implement the same loop shape:

    for page_index in range(max_pages):
        if len(jobs) >= limit: break
        if page_index > 0 and inter_page_delay_seconds > 0: sleep
        try: new_jobs = await fetch_one_page(...)
        except timeout_exc_type: if page_index == 0: raise else: break
        if not new_jobs: break
        jobs.extend(new_jobs)

This module hoists that loop into a single async helper that
each source calls from its own `search()`. The source-specific
concerns (URL formula, exception types, blocked-check fn,
`_parse_cards` arity, page-0 zero-cards semantic) are absorbed
by the `fetch_one_page` closure the source builds and passes
in. The helper does NOT import Playwright; the caller owns the
page lifecycle and passes the page in.

Design choices (mirror `sdd/shared-pagination-helper/design`):
- Free function, not a base class — keeps each source as the
  source of truth for its own fetcher.
- Throttle acquisition lives INSIDE the helper so the "throttle
  once per `search()`" contract is preserved by the helper,
  not duplicated in each scraper.
- `timeout_exc_type` is the ONLY exception caught. All other
  exceptions (`*BlockedError`, `*ParseError`, etc.) propagate
  unchanged to the caller.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from jobs_finder.domain.job import Job

# The shape the source's per-page closure MUST satisfy. The page
# arg is `Any` because the helper does not import Playwright; the
# caller owns the page lifecycle. The `int` is `page_index` (0-based);
# the trailing `int` is `remaining = limit - len(jobs)` so the
# closure can cap the parser to "jobs I still need".
Fetcher = Callable[[Any, int, int], Awaitable[list[Job]]]


async def paginated_search(
    *,
    page: Any,
    throttle: Any,
    fetch_one_page: Fetcher,
    limit: int,
    max_pages: int,
    inter_page_delay_seconds: float,
    timeout_exc_type: type[Exception],
) -> list[Job]:
    """Drive the canonical auto-pagination loop and return the collected jobs.

    Args:
        page: The Playwright `Page` (or any duck-typed page-like
            object the closure navigates with). The helper does NOT
            import Playwright; lifecycle is the caller's
            responsibility (`new_page` / `close`).
        throttle: An async context manager acquired ONCE around the
            whole loop so consecutive `search()` calls are paced by
            the throttle's `min_interval_seconds` while back-to-back
            page requests inside one search are NOT.
        fetch_one_page: A closure `(page, page_index, remaining)
            -> Awaitable[list[Job]]` that navigates the page,
            checks for blocks, parses the cards, and returns the
            per-page job list. Returns `[]` to signal
            "end of results" (zero cards or page-`>0` timeout). May
            raise `timeout_exc_type` on page 0 to propagate a
            first-page failure; may raise any other exception
            (e.g. `*BlockedError`, `*ParseError`) which the helper
            will NOT catch.
        limit: The caller's request size. The loop stops as soon
            as `len(jobs) >= limit`.
        max_pages: The hard ceiling on the number of page
            requests. The loop stops at `max_pages` even if the
            limit was not reached.
        inter_page_delay_seconds: The wall-clock sleep between
            page requests. Page 0 is never delayed. A value of
            `0.0` skips the `asyncio.sleep` call entirely (no
            event-loop yield, no wall-clock wait).
        timeout_exc_type: The exception class the helper MUST
            catch and treat as a per-page timeout (page 0 → raise
            to caller; page > 0 → break gracefully). Any other
            exception type is NOT caught and propagates.

    Returns:
        The collected `list[Job]`, capped at `limit`. May be
        shorter if a page-`>0` timeout, zero-cards page, or
        `max_pages` ceiling ended the loop early.
    """
    jobs: list[Job] = []
    async with throttle:
        for page_index in range(max_pages):
            # Top-of-loop limit cap: stop as soon as we have enough.
            if len(jobs) >= limit:
                break
            # Inter-page pacing: page 0 is never delayed; `0.0`
            # skips the call entirely.
            if page_index > 0 and inter_page_delay_seconds > 0:
                await asyncio.sleep(inter_page_delay_seconds)
            try:
                new_jobs = await fetch_one_page(
                    page,
                    page_index,
                    limit - len(jobs),
                )
            except timeout_exc_type:
                if page_index == 0:
                    # First page timing out is a real error
                    # (auth-wall, zero results, network failure).
                    # Let the caller decide what HTTP status to map.
                    raise
                # Subsequent page timed out: end of results or
                # anti-bot re-challenge. Return what we have.
                break
            # Empty page is the universal "end of results" signal —
            # works for both LinkedIn (silent) and Indeed/InfoJobs
            # (where the closure's `[]` is also the break trigger;
            # the per-source page-0 zero-cards raise happens
            # INSIDE the closure, not as a `[]` here).
            if not new_jobs:
                break
            jobs.extend(new_jobs)
    return jobs
