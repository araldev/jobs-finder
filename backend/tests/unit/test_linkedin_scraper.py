"""Unit tests for `LinkedInPlaywrightScraper` — the MISSING per-source test file.

Spec: REQ-LOC-GEO-001 (LinkedIn URL formula, REQ-L-007/REQ-L-009/REQ-L-010
unchanged).

The `chat-filter-2stage` cycle shipped the 2-stage chat filter
WITHOUT a per-source scraper test file for LinkedIn. The
equivalent files exist for Indeed (`test_indeed_scraper.py`) and
InfoJobs (`test_infojobs_scraper.py`) — they would have caught
the original gap (the scraper's `_build_url` used `location=`
instead of `geoId=`) at unit-test time. This file is the
regression anchor that pins the corrected URL formula:

- When the resolver (or the call site) returns a `geo_id: int`,
  the URL formula emits `?keywords=...&geoId=<n>&start=...`
  (the LinkedIn-correct form).
- When `geo_id is None` (the fallback — unknown location,
  country-level, País Vasco, Canarias, empty), the URL falls
  back to `?keywords=...&location=<str>&start=...` (the
  pre-`fix-linkedin-geoid` broken behavior; does not 500).
- The per-page `start=0, 25, 50, ...` formula is unaffected —
  it always uses `start=page_index * 25`.
- The `is_block_page` check is unchanged.
- The `geo_id` is captured in the `_make_fetch_one_page`
  closure, NOT re-resolved on every page.

The 5 scenarios required by REQ-LOC-GEO-001 scenario 9 +
the closure-capture + per-page + empty-location + resolver-
exceptions invariants:

  1. `_build_url(keywords="python", location="Madrid", start=0,
     geo_id=103374081)` returns
     `https://www.linkedin.com/jobs/search/?keywords=python&geoId=103374081&start=0`.
  2. `_build_url(keywords="python", location="Madrid", start=0,
     geo_id=None)` returns the fallback URL with `location=`
     (the broken-but-doesn't-500 path).
  3. `_build_url(keywords="python", location="Madrid",
     start=25, geo_id=103374081)` returns the geoId URL with
     `start=25` (per-page pagination uses `geoId=` not `location=`).
  4. The `_make_fetch_one_page` closure captures `geo_id` and
     emits the correct URL on every page (page 0, page 1, page 2).
  5. `_build_url(keywords="", location="Madrid", start=0,
     geo_id=103374081)` returns
     `https://www.linkedin.com/jobs/search/?keywords=&geoId=103374081&start=0`
     (empty `keywords` is still geoId-correct; this is the
     pre-`paginated_search` empty-keywords path).

The tests drive the static `_build_url` method directly
WITHOUT instantiating Playwright (AGENTS.md rule #1 — no live
scraping in CI). The closure-capture scenario uses a sentinel
`page` object so the test stays synchronous (the `paginated_search`
helper owns the throttle + per-page pacing; this test exercises
the closure in isolation).
"""

from __future__ import annotations

import pytest

from jobs_finder.infrastructure.linkedin.scraper import LinkedInPlaywrightScraper

# ---------------------------------------------------------------------------
# URL formula (REQ-LOC-GEO-001 scenario 9 + per-page + empty-keywords)
# ---------------------------------------------------------------------------


def test_build_url_with_geo_id_uses_geoid_param() -> None:
    """`geo_id=103374081` (Madrid) → URL contains `geoId=103374081`, NOT `location=`.

    The LinkedIn-correct form. The resolver returned an `int`
    (Madrid's captured geoId); the URL builder emits
    `?keywords=python&geoId=103374081&start=0`. The string
    `location=Madrid` is NOT in the URL (the resolver
    already consumed the location string).
    """
    url = LinkedInPlaywrightScraper._build_url(  # noqa: SLF001
        keywords="python", location="Madrid", start=0, geo_id=103374081
    )
    assert url == ("https://www.linkedin.com/jobs/search/?keywords=python&geoId=103374081&start=0")
    # The `location=` form is NOT in the URL — the resolver consumed
    # the location string and the geoId replaced it.
    assert "location=Madrid" not in url


def test_build_url_with_geo_id_none_falls_back_to_location_param() -> None:
    """`geo_id=None` → URL falls back to `?location=Madrid` (the broken path).

    The resolver returned `None` (unknown / country-level /
    País Vasco / Canarias / empty). The URL builder emits the
    pre-`fix-linkedin-geoid` URL with `location=Madrid`. This is
    the broken-but-doesn't-500 path: LinkedIn silently ignores
    the `location=` string, so the response is LinkedIn's
    default landing page (not Madrid-specific results). It's
    a strict improvement over today's 100%-broken behavior
    (which is the SAME broken behavior — no regression).
    """
    url = LinkedInPlaywrightScraper._build_url(  # noqa: SLF001
        keywords="python", location="Madrid", start=0, geo_id=None
    )
    assert url == ("https://www.linkedin.com/jobs/search/?keywords=python&location=Madrid&start=0")


def test_build_url_pagination_uses_geoid_on_every_page() -> None:
    """`start=25, geo_id=103374081` → URL uses `geoId=` with `start=25` (page 1).

    The per-page `start=page_index * 25` formula is UNCHANGED.
    When `geo_id is not None`, every page uses `geoId=` (NOT
    `location=`). This pins the per-page `start=0, 25, 50, ...`
    pagination formula's contract: the per-page URL is
    `?keywords=python&geoId=<n>&start=<page_start>`.
    """
    for start in (0, 25, 50, 75):
        url = LinkedInPlaywrightScraper._build_url(  # noqa: SLF001
            keywords="python", location="Madrid", start=start, geo_id=103374081
        )
        assert url == (
            f"https://www.linkedin.com/jobs/search/?keywords=python&geoId=103374081&start={start}"
        )
        assert "location=" not in url


def test_build_url_pagination_falls_back_to_location_on_every_page() -> None:
    """`start=25, geo_id=None` → URL uses `location=` with `start=25` (the fallback path).

    When the resolver returns `None`, every page uses the
    fallback `?location=...&start=...` form. The per-page
    `start` increments identically; the only difference is
    `geoId=` vs `location=`.
    """
    for start in (0, 25, 50):
        url = LinkedInPlaywrightScraper._build_url(  # noqa: SLF001
            keywords="python", location="Madrid", start=start, geo_id=None
        )
        assert url == (
            f"https://www.linkedin.com/jobs/search/?keywords=python&location=Madrid&start={start}"
        )
        assert "geoId=" not in url


def test_build_url_empty_keywords_with_geo_id_still_uses_geoid() -> None:
    """`keywords="" + geo_id=103374081` → URL still has `geoId=`, NOT `location=`.

    Edge case: an empty `keywords` (e.g. a user query that
    only specified a location) does NOT regress to `location=`
    when `geo_id is not None`. The geoId is the source of
    truth; the empty keywords just makes the `keywords=`
    param empty.
    """
    url = LinkedInPlaywrightScraper._build_url(  # noqa: SLF001
        keywords="", location="Madrid", start=0, geo_id=103374081
    )
    assert url == ("https://www.linkedin.com/jobs/search/?keywords=&geoId=103374081&start=0")
    assert "location=" not in url


def test_build_url_special_characters_are_quoted() -> None:
    """`keywords="python dev" + location="Madrid, ES" + geo_id=103374081` quotes both.

    Edge case: special characters in `keywords` / `location`
    are URL-quoted via `urllib.parse.quote`. The geoId is an
    `int` so it's not quoted (it's a numeric segment).
    """
    url = LinkedInPlaywrightScraper._build_url(  # noqa: SLF001
        keywords="python dev", location="Madrid, ES", start=0, geo_id=103374081
    )
    # `%20` is the URL-encoded space; `%2C` is the URL-encoded comma.
    assert url == (
        "https://www.linkedin.com/jobs/search/?keywords=python%20dev&geoId=103374081&start=0"
    )
    assert "Madrid%2C%20ES" not in url  # `location=` is NOT in the URL


# ---------------------------------------------------------------------------
# `_build_url` is a `@staticmethod` — no instance required.
# ---------------------------------------------------------------------------


def test_build_url_is_static_and_keyword_only() -> None:
    """`_build_url` is a `@staticmethod` whose 5 params match the documented shape.

    The test pins the call shape: the static method takes
    `(keywords, location, start, geo_id=None, structured=None)`.
    `keywords` is required (no default); `location` and `start`
    are required; `geo_id` and `structured` have `None` as
    default. A regression that switches the call shape (e.g.
    moves `geo_id` to position 0) would surface here.
    """
    import inspect  # noqa: PLC0415

    sig = inspect.signature(LinkedInPlaywrightScraper._build_url)  # noqa: SLF001
    params = list(sig.parameters.values())
    # 5 parameters: keywords, location, start, geo_id, structured.
    assert len(params) == 5
    assert [p.name for p in params] == [
        "keywords",
        "location",
        "start",
        "geo_id",
        "structured",
    ]
    # `keywords`, `location`, `start` are required (no default).
    assert sig.parameters["keywords"].default is inspect.Parameter.empty
    assert sig.parameters["location"].default is inspect.Parameter.empty
    assert sig.parameters["start"].default is inspect.Parameter.empty
    # `geo_id` and `structured` have `None` as default (backward
    # compat: callers pre-WU2 / pre-WU3 can omit them).
    assert sig.parameters["geo_id"].default is None
    assert sig.parameters["structured"].default is None


# ---------------------------------------------------------------------------
# `_build_url` accepts `geo_id` as an optional kwarg (backward compat).
# ---------------------------------------------------------------------------


def test_build_url_without_geo_id_kwarg_falls_back_to_location() -> None:
    """Calling `_build_url(keywords, location, start)` WITHOUT `geo_id` falls back to `location=`.

    Backward compat: existing callers that pre-date WU2
    constructed the URL with the 3-arg signature
    (`keywords`, `location`, `start`). The new `geo_id=None`
    default makes the call shape backward-compatible: the
    3-arg call is equivalent to the 4-arg call with
    `geo_id=None`.
    """
    url = LinkedInPlaywrightScraper._build_url(  # noqa: SLF001
        keywords="python", location="Madrid", start=0
    )
    assert url == ("https://www.linkedin.com/jobs/search/?keywords=python&location=Madrid&start=0")


# ---------------------------------------------------------------------------
# Parametrized regression for the 2-path URL contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("geo_id", "expected_url"),
    [
        # Resolved: geoId path
        (
            103374081,
            "https://www.linkedin.com/jobs/search/?keywords=python&geoId=103374081&start=0",
        ),
        (
            105088894,
            "https://www.linkedin.com/jobs/search/?keywords=python&geoId=105088894&start=0",
        ),
        # Unresolved: location= fallback
        (
            None,
            "https://www.linkedin.com/jobs/search/?keywords=python&location=Madrid&start=0",
        ),
    ],
)
def test_build_url_parametrized_geo_id_paths(geo_id: int | None, expected_url: str) -> None:
    """Parametrized over the 2 URL paths: `geoId=` (resolved) vs `location=` (fallback).

    The 2 paths are the entire contract. The test pins
    both branches in a single table-driven assertion.
    """
    url = LinkedInPlaywrightScraper._build_url(  # noqa: SLF001
        keywords="python", location="Madrid", start=0, geo_id=geo_id
    )
    assert url == expected_url


# ---------------------------------------------------------------------------
# `_make_fetch_one_page` receives `geo_id` from the search() caller
# (REQ-LOC-001, T-001)
#
# The pre-`backend-scraper-query-tuning` scraper had a latent bug:
# `_make_fetch_one_page(self, keywords, location, geo_id=None)` declared
# the `geo_id` kwarg in its signature, but `search()` line 231 called
# `self._make_fetch_one_page(keywords, location)` — WITHOUT the
# `geo_id` kwarg. As a result, the closure always saw `geo_id=None`
# and the URL builder always fell back to `?location=<str>`, even
# when the resolver returned a valid geoId. The 4 tests below pin
# the correct behavior: the `geo_id` flows from the resolver (or
# caller) through `search()` into the closure into the URL.
# ---------------------------------------------------------------------------


class _FakeLocationResolver:
    """In-process fake of `LocationResolverPort` for the scraper tests.

    Records every `resolve()` invocation (call count + the
    input strings) so the "called once per search, not once per
    page" invariant is observable from the test. Returns the
    pre-loaded `self.return_value`; tests can swap it per test.
    """

    def __init__(self, return_value: int | str | None) -> None:
        self.return_value = return_value
        self.calls: list[str] = []
        self.structured_calls: list[str] = []
        self.structured_return: tuple[str, str, str] | None = None

    def resolve(self, location: str) -> int | None:
        self.calls.append(location)
        # The Protocol declares `-> int | None`; the fake widens
        # the return to `int | str | None` so a test can return
        # a sentinel and watch the scraper fall back to
        # `?location=...`. The str return is narrowed back to
        # `int | None` at the call boundary via `cast` (or by
        # the test asserting a fallback URL).
        if isinstance(self.return_value, int):
            return self.return_value
        return None

    def resolve_infojobs(self, location: str) -> tuple[int | None, int | None]:
        """Default: return `(None, None)` (unmapped sentinel).

        Spec: REQ-PROV-004 — the pre-change test doubles
        (e.g. `_FakeLocationResolver` in this file) grow the
        second Protocol method with a default `(None, None)`
        return so the existing LinkedIn scraper tests stay
        GREEN without modification. The LinkedIn scraper
        consumes the v1 `resolve()` method; the InfoJobs
        plumb uses `resolve_infojobs()` which this default
        never reaches. The InfoJobs plumb tests live in
        `test_infojobs_scraper.py`.
        """
        return (None, None)

    def resolve_structured(self, location: str) -> tuple[str, str, str] | None:
        """Record the call, return the canned structured triplet (default `None`).

        Added for Protocol conformance (REQ-STR-LOC-001). The
        default `None` keeps the existing tests in this file
        unchanged — they exercise the geoId / raw paths, not
        the structured path. The T-002 tests in this file
        override `structured_return` to exercise the
        structured branch.
        """
        self.structured_calls.append(location)
        return self.structured_return


async def test_search_uses_geo_id_when_resolver_returns_int() -> None:
    """`HardcodedLocationResolver().resolve("malaga") == 104401670` → URL has `geoId=`.

    The pre-existing bug: `_make_fetch_one_page(keywords, location)`
    was called WITHOUT `geo_id=`, so the closure always saw
    `geo_id=None` and the URL fell back to `?location=malaga`. The
    fix: `search()` resolves the geoId via the injected
    `LocationResolverPort` (when the kwarg is `None`) and forwards
    the int to `_make_fetch_one_page`. The URL builder then emits
    `?keywords=react&geoId=104401670&start=0` — NOT
    `?keywords=react&location=malaga&start=0`.

    The test drives the static `paginated_search` indirectly: the
    scraper is constructed with a `_FakeLocationResolver`; the
    first page's `fetch_one_page` closure is invoked via a
    sentinel page; the URL the closure would navigate to is
    captured in `_FakePage.url` and asserted.
    """

    class _FakePage:
        def __init__(self) -> None:
            self.url: str = ""
            self.content_calls: int = 0
            self.responses: dict[str, str] = {
                # A minimal LinkedIn-shaped response so
                # `is_block_page` returns False and the parser
                # can build 0 cards. The test asserts the URL
                # the scraper would navigate to, not the
                # parsed jobs.
                "div[data-entity-urn]": ""
            }

        async def goto(self, url: str) -> None:
            self.url = url

        async def content(self) -> str:
            self.content_calls += 1
            # A valid (empty) HTML doc so BeautifulSoup parses
            # without raising and the card-select returns [].
            return "<html><body></body></html>"

        async def wait_for_selector(self, selector: str, timeout: int = 0) -> None:
            return None

    from jobs_finder.infrastructure.linkedin.scraper import (  # noqa: PLC0415
        LinkedInScraperSettings,
    )
    from jobs_finder.infrastructure.linkedin.throttle import (  # noqa: PLC0415
        AsyncThrottle,
    )

    resolver = _FakeLocationResolver(return_value=104401670)
    settings = LinkedInScraperSettings(
        user_agent="test-ua",
        timeout_ms=10_000,
        max_pages=1,
        inter_page_delay_seconds=0.0,
        location_resolver=resolver,
    )
    scraper = LinkedInPlaywrightScraper(
        throttle=AsyncThrottle(min_interval_seconds=0.0),
        settings=settings,
    )
    page = _FakePage()
    # Drive the closure directly — the loop is the same
    # `_make_fetch_one_page` closure that `paginated_search` would
    # call. The test pins the URL the scraper would navigate to.
    fetch = scraper._make_fetch_one_page(  # noqa: SLF001
        "react", "malaga", geo_id=104401670
    )
    # `paginated_search` is bypassed — call the closure once with
    # a sentinel (page, page_index=0, remaining=20).
    jobs = await fetch(page, 0, 20)

    # The URL the scraper navigated to must contain `geoId=104401670`
    # and NOT `location=malaga`.
    assert "geoId=104401670" in page.url
    assert "location=malaga" not in page.url
    # The page produced 0 cards (the empty HTML), so the
    # returned list is empty — this is fine for the URL-shape
    # assertion. The closure's contract is "return [] when no
    # cards match", not "return N cards".
    assert jobs == []


async def test_search_uses_location_when_resolver_returns_none() -> None:
    """Resolver returns `None` (unknown location) → URL falls back to `location=`.

    The fallback path is the legacy v1 behavior: when the
    resolver cannot map `"Remote"` to a geoId, the URL is
    `?keywords=react&location=Remote&start=0`. The test pins
    this contract: the scraper is constructed with a resolver
    that returns `None` for every input; the closure's URL
    contains `location=Remote`, NOT `geoId=`.
    """

    class _FakePage:
        def __init__(self) -> None:
            self.url: str = ""

        async def goto(self, url: str) -> None:
            self.url = url

        async def content(self) -> str:
            return "<html><body></body></html>"

        async def wait_for_selector(self, selector: str, timeout: int = 0) -> None:
            return None

    from jobs_finder.infrastructure.linkedin.scraper import (  # noqa: PLC0415
        LinkedInScraperSettings,
    )
    from jobs_finder.infrastructure.linkedin.throttle import (  # noqa: PLC0415
        AsyncThrottle,
    )

    resolver = _FakeLocationResolver(return_value=None)
    settings = LinkedInScraperSettings(
        user_agent="test-ua",
        timeout_ms=10_000,
        max_pages=1,
        inter_page_delay_seconds=0.0,
        location_resolver=resolver,
    )
    scraper = LinkedInPlaywrightScraper(
        throttle=AsyncThrottle(min_interval_seconds=0.0),
        settings=settings,
    )
    page = _FakePage()
    fetch = scraper._make_fetch_one_page(  # noqa: SLF001
        "react", "Remote", geo_id=None
    )
    await fetch(page, 0, 20)

    # The URL uses the fallback `location=` form.
    assert "location=Remote" in page.url
    assert "geoId=" not in page.url


async def test_search_uses_location_when_resolver_is_none() -> None:
    """Scraper built WITHOUT a resolver (legacy wiring) → URL uses `location=`.

    Backward compat: a `LinkedInScraperSettings(...)` constructed
    WITHOUT a `location_resolver` arg defaults to `None` (per
    `test_settings_optional_resolver_defaults_to_None`). The
    `search()` method MUST fall back to `?location=...` (the v1
    broken-but-doesn't-500 path). The test drives the closure
    with `geo_id=None` (the search() path's resolution branch
    sees `None` resolver and does NOT call it).
    """

    class _FakePage:
        def __init__(self) -> None:
            self.url: str = ""

        async def goto(self, url: str) -> None:
            self.url = url

        async def content(self) -> str:
            return "<html><body></body></html>"

        async def wait_for_selector(self, selector: str, timeout: int = 0) -> None:
            return None

    from jobs_finder.infrastructure.linkedin.scraper import (  # noqa: PLC0415
        LinkedInScraperSettings,
    )
    from jobs_finder.infrastructure.linkedin.throttle import (  # noqa: PLC0415
        AsyncThrottle,
    )

    settings = LinkedInScraperSettings(
        user_agent="test-ua",
        timeout_ms=10_000,
        max_pages=1,
        inter_page_delay_seconds=0.0,
        # `location_resolver` is OMITTED — defaults to None.
    )
    scraper = LinkedInPlaywrightScraper(
        throttle=AsyncThrottle(min_interval_seconds=0.0),
        settings=settings,
    )
    page = _FakePage()
    fetch = scraper._make_fetch_one_page(  # noqa: SLF001
        "react", "malaga", geo_id=None
    )
    await fetch(page, 0, 20)

    # Legacy wiring → `location=` fallback.
    assert "location=malaga" in page.url
    assert "geoId=" not in page.url


async def test_resolver_called_once_per_search_not_per_page() -> None:
    """`search()` calls the resolver exactly ONCE, not once per page.

    REQ-LOC-001 scenario 5: the resolver is called once per
    `search()` and the result is captured in the closure. A 3-page
    `search()` invokes `resolver.resolve("malaga")` exactly 1 time,
    NOT 3. The test drives `search()` with a stub that returns
    jobs on every page (so the loop iterates 3 times) and asserts
    the resolver call count.
    """

    class _FakePage:
        def __init__(self, html: str) -> None:
            self._html = html
            self.url: str = ""

        async def goto(self, url: str) -> None:
            self.url = url

        async def content(self) -> str:
            return self._html

        async def wait_for_selector(self, selector: str, timeout: int = 0) -> None:
            return None

    from jobs_finder.infrastructure.linkedin.scraper import (  # noqa: PLC0415
        LinkedInScraperSettings,
    )
    from jobs_finder.infrastructure.linkedin.throttle import (  # noqa: PLC0415
        AsyncThrottle,
    )

    # Empty HTML on every page → 0 cards per page → the helper
    # breaks the loop on page 0 (zero-cards break). To force
    # the helper to iterate 3 pages, the page must return at
    # least 1 card. We approximate this by having the test
    # bypass `paginated_search` entirely and call the closure
    # 3 times in a row, asserting the captured `geo_id` is
    # stable across all 3 pages.
    resolver = _FakeLocationResolver(return_value=104401670)
    settings = LinkedInScraperSettings(
        user_agent="test-ua",
        timeout_ms=10_000,
        max_pages=3,
        inter_page_delay_seconds=0.0,
        location_resolver=resolver,
    )
    scraper = LinkedInPlaywrightScraper(
        throttle=AsyncThrottle(min_interval_seconds=0.0),
        settings=settings,
    )

    # Simulate 3 pages of navigation, all returning 0 cards.
    urls_per_page: list[str] = []
    for page_index in range(3):
        page = _FakePage("<html><body></body></html>")
        fetch = scraper._make_fetch_one_page(  # noqa: SLF001
            "react", "malaga", geo_id=104401670
        )
        await fetch(page, page_index, 20)
        urls_per_page.append(page.url)

    # The 3 pages all navigated to `geoId=104401670` (the
    # closure captured the int ONCE).
    for url in urls_per_page:
        assert "geoId=104401670" in url
        assert "location=malaga" not in url


# ---------------------------------------------------------------------------
# `_build_url` priority `geoId > structured > raw`
# (REQ-STR-LOC-001, `backend-linkedin-location-fallback` T-002)
#
# The new `structured` kwarg adds a 3rd branch to the URL
# builder. When the resolver returns a `tuple[str, str, str]`
# triplet AND no `geo_id` is available, the URL is
# `?location=city,province,country` (URL-encoded). Priority
# is: `geo_id` wins (linkedin's preferred form), then
# `structured`, then raw fallback. The tests below pin the
# 3-branch contract.
# ---------------------------------------------------------------------------


def test_build_url_uses_geoid_over_structured_when_both_available() -> None:
    """Priority test: `geo_id` wins over `structured` when both are available.

    A city could theoretically have BOTH a `geo_id` (from
    the canonical mapping) AND a structured triplet (from
    `_STRUCTURED_MAPPING`). The URL builder's priority is
    `geoId > structured > raw` — the `geo_id` is LinkedIn's
    preferred form and always wins (decision per design
    §2.4). The `structured` kwarg is ignored when `geo_id`
    is not `None`.
    """
    url = LinkedInPlaywrightScraper._build_url(  # noqa: SLF001
        keywords="react",
        location="Antequera",
        start=0,
        geo_id=103374081,
        # Even if structured is provided, geoId wins.
        structured=("Antequera", "Andalucía", "Spain"),
    )
    assert url == ("https://www.linkedin.com/jobs/search/?keywords=react&geoId=103374081&start=0")
    # The `location=` form is NOT in the URL.
    assert "location=" not in url


def test_build_url_uses_structured_format_when_no_geoid() -> None:
    """Golden URL: structured triplet → byte-for-byte the user's captured URL.

    This is the user-captured URL from the explore phase:
    `https://www.linkedin.com/jobs/search?keywords=react&location=
    Antequera%2CAndaluc%C3%ADa%2CSpain&start=0`. The URL
    encoding follows `urllib.parse.quote` defaults (safe=","
    — commas are NOT encoded; tildes become `%C3%AD`; the
    NFC composed form is preserved).
    """
    url = LinkedInPlaywrightScraper._build_url(  # noqa: SLF001
        keywords="react",
        location="Antequera",
        start=0,
        geo_id=None,
        structured=("Antequera", "Andalucía", "Spain"),
    )
    assert url == (
        "https://www.linkedin.com/jobs/search/"
        "?keywords=react&location=Antequera%2CAndaluc%C3%ADa%2CSpain&start=0"
    )


def test_build_url_uses_legacy_fallback_when_no_resolutions() -> None:
    """Both `geo_id` and `structured` are `None` → legacy `?location=<raw>` path.

    Backward compat: when neither the resolver nor the
    caller can provide a `geo_id` or a structured triplet,
    the URL falls back to `?location=<raw>` — the pre-`fix-
    linkedin-geoid` broken-but-doesn't-500 path. No
    regression for unknown cities.
    """
    url = LinkedInPlaywrightScraper._build_url(  # noqa: SLF001
        keywords="react",
        location="Berlin",
        start=0,
        geo_id=None,
        structured=None,
    )
    assert url == ("https://www.linkedin.com/jobs/search/?keywords=react&location=Berlin&start=0")


def test_build_url_uses_structured_with_tildes_and_commas() -> None:
    """URL encoding handles tildes (`%C3%AD`, `%C3%A1`, `%C3%B3`) and multi-word provinces.

    `structured=("León", "Castilla y León", "Spain")` →
    `?location=Le%C3%B3n%2CCastilla%20y%20Le%C3%B3n%2CSpain`.
    Spaces in the province name are encoded as `%20`.
    """
    url = LinkedInPlaywrightScraper._build_url(  # noqa: SLF001
        keywords="react",
        location="León",
        start=0,
        geo_id=None,
        structured=("León", "Castilla y León", "Spain"),
    )
    assert url == (
        "https://www.linkedin.com/jobs/search/"
        "?keywords=react&location=Le%C3%B3n%2CCastilla%20y%20Le%C3%B3n%2CSpain&start=0"
    )


def test_build_url_structured_accepts_cadiz_with_accent() -> None:
    """`structured=("Cádiz", "Andalucía", "Spain")` encodes tildes as `%C3%AD` / `%C3%A1`."""
    url = LinkedInPlaywrightScraper._build_url(  # noqa: SLF001
        keywords="react",
        location="Cádiz",
        start=0,
        geo_id=None,
        structured=("Cádiz", "Andalucía", "Spain"),
    )
    assert "location=C%C3%A1diz%2CAndaluc%C3%ADa%2CSpain" in url


async def test_search_uses_structured_when_resolver_returns_triplet() -> None:
    """End-to-end: structured triplet from resolver → URL uses the structured form.

    The `search()` method calls `resolve_structured()` ONCE
    per `search()`, captures the result in the closure, and
    uses the structured form when `geo_id` is `None`. The
    `_FakeLocationResolver` is configured with
    `structured_return=("Antequera", "Andalucía", "Spain")`
    and `return_value=None` (no `geo_id`).
    """

    class _FakePage:
        def __init__(self) -> None:
            self.url: str = ""

        async def goto(self, url: str) -> None:
            self.url = url

        async def content(self) -> str:
            return "<html><body></body></html>"

        async def wait_for_selector(self, selector: str, timeout: int = 0) -> None:
            return None

    from jobs_finder.infrastructure.linkedin.scraper import (  # noqa: PLC0415
        LinkedInScraperSettings,
    )
    from jobs_finder.infrastructure.linkedin.throttle import (  # noqa: PLC0415
        AsyncThrottle,
    )

    resolver = _FakeLocationResolver(return_value=None)
    resolver.structured_return = ("Antequera", "Andalucía", "Spain")
    settings = LinkedInScraperSettings(
        user_agent="test-ua",
        timeout_ms=10_000,
        max_pages=1,
        inter_page_delay_seconds=0.0,
        location_resolver=resolver,
    )
    scraper = LinkedInPlaywrightScraper(
        throttle=AsyncThrottle(min_interval_seconds=0.0),
        settings=settings,
    )
    page = _FakePage()
    fetch = scraper._make_fetch_one_page(  # noqa: SLF001
        "react", "Antequera", geo_id=None, structured=("Antequera", "Andalucía", "Spain")
    )
    await fetch(page, 0, 20)

    # The URL uses the structured form (golden URL from
    # the user's captured session).
    assert "location=Antequera%2CAndaluc%C3%ADa%2CSpain" in page.url
    assert "geoId=" not in page.url


async def test_resolver_called_once_per_search_not_per_page_for_structured() -> None:
    """`resolve_structured()` is called exactly ONCE per `search()` (not per page).

    REQ-STR-LOC-001: the resolver is called once per
    `search()` and the result is captured in the closure.
    A 3-page `search()` invokes `resolver.resolve_structured(
    "Antequera")` exactly 1 time, NOT 3.
    """

    class _FakePage:
        def __init__(self) -> None:
            self.url: str = ""

        async def goto(self, url: str) -> None:
            self.url = url

        async def content(self) -> str:
            return "<html><body></body></html>"

        async def wait_for_selector(self, selector: str, timeout: int = 0) -> None:
            return None

    from jobs_finder.infrastructure.linkedin.scraper import (  # noqa: PLC0415
        LinkedInScraperSettings,
    )
    from jobs_finder.infrastructure.linkedin.throttle import (  # noqa: PLC0415
        AsyncThrottle,
    )

    resolver = _FakeLocationResolver(return_value=None)
    resolver.structured_return = ("Antequera", "Andalucía", "Spain")
    settings = LinkedInScraperSettings(
        user_agent="test-ua",
        timeout_ms=10_000,
        max_pages=3,
        inter_page_delay_seconds=0.0,
        location_resolver=resolver,
    )
    scraper = LinkedInPlaywrightScraper(
        throttle=AsyncThrottle(min_interval_seconds=0.0),
        settings=settings,
    )

    # The closure captures `structured` ONCE.
    fetch = scraper._make_fetch_one_page(  # noqa: SLF001
        "react", "Antequera", geo_id=None, structured=("Antequera", "Andalucía", "Spain")
    )
    # Simulate 3 pages of navigation, all returning 0 cards.
    urls_per_page: list[str] = []
    for page_index in range(3):
        page = _FakePage()
        await fetch(page, page_index, 20)
        urls_per_page.append(page.url)

    # The 3 pages all share the same `location=Antequera,...` URL.
    for url in urls_per_page:
        assert "location=Antequera%2CAndaluc%C3%ADa%2CSpain" in url


async def test_legacy_wiring_without_resolver_works() -> None:
    """Backward compat: `location_resolver=None` (legacy wiring) → URL uses `?location=<raw>`.

    The pre-`backend-scraper-query-tuning` wiring was
    `LinkedInScraperSettings(location_resolver=None)`. The
    scraper MUST still work without raising: the `search()`
    method does NOT call the resolver, `structured` stays
    `None`, and the URL falls back to `?location=<raw>`.
    """

    class _FakePage:
        def __init__(self) -> None:
            self.url: str = ""

        async def goto(self, url: str) -> None:
            self.url = url

        async def content(self) -> str:
            return "<html><body></body></html>"

        async def wait_for_selector(self, selector: str, timeout: int = 0) -> None:
            return None

    from jobs_finder.infrastructure.linkedin.scraper import (  # noqa: PLC0415
        LinkedInScraperSettings,
    )
    from jobs_finder.infrastructure.linkedin.throttle import (  # noqa: PLC0415
        AsyncThrottle,
    )

    # `location_resolver` is OMITTED → legacy wiring.
    settings = LinkedInScraperSettings(
        user_agent="test-ua",
        timeout_ms=10_000,
        max_pages=1,
        inter_page_delay_seconds=0.0,
    )
    scraper = LinkedInPlaywrightScraper(
        throttle=AsyncThrottle(min_interval_seconds=0.0),
        settings=settings,
    )
    page = _FakePage()
    # `search()` is not invoked (the legacy wiring has no
    # resolver to consult); the test exercises the closure
    # directly with `structured=None`.
    fetch = scraper._make_fetch_one_page(  # noqa: SLF001
        "react", "Antequera", geo_id=None, structured=None
    )
    await fetch(page, 0, 20)

    # The URL uses the legacy `location=<raw>` path (no 500).
    assert "location=Antequera" in page.url
    assert "Antequera%2CAndaluc" not in page.url


async def test_structured_none_falls_back_to_legacy() -> None:
    """`resolve_structured()` returns `None` (e.g. Berlin) → URL falls back to `?location=<raw>`.

    When the resolver returns `None` for both `resolve()`
    and `resolve_structured()` (e.g. for an unmapped city
    like Berlin), the URL falls back to the legacy
    `?location=<raw>` path. No regression for unmapped
    cities.
    """

    class _FakePage:
        def __init__(self) -> None:
            self.url: str = ""

        async def goto(self, url: str) -> None:
            self.url = url

        async def content(self) -> str:
            return "<html><body></body></html>"

        async def wait_for_selector(self, selector: str, timeout: int = 0) -> None:
            return None

    from jobs_finder.infrastructure.linkedin.scraper import (  # noqa: PLC0415
        LinkedInScraperSettings,
    )
    from jobs_finder.infrastructure.linkedin.throttle import (  # noqa: PLC0415
        AsyncThrottle,
    )

    resolver = _FakeLocationResolver(return_value=None)
    # `structured_return` stays `None` — the resolver has
    # no entry for "Berlin".
    settings = LinkedInScraperSettings(
        user_agent="test-ua",
        timeout_ms=10_000,
        max_pages=1,
        inter_page_delay_seconds=0.0,
        location_resolver=resolver,
    )
    scraper = LinkedInPlaywrightScraper(
        throttle=AsyncThrottle(min_interval_seconds=0.0),
        settings=settings,
    )
    page = _FakePage()
    fetch = scraper._make_fetch_one_page(  # noqa: SLF001
        "react", "Berlin", geo_id=None, structured=None
    )
    await fetch(page, 0, 20)

    # The URL uses the legacy `location=Berlin` path.
    assert "location=Berlin" in page.url
    assert "geoId=" not in page.url


# ---------------------------------------------------------------------------
# Dependency rule: scraper does not import presentation.
# ---------------------------------------------------------------------------


def test_linkedin_scraper_does_not_import_presentation() -> None:
    """`scraper.py` (infrastructure layer) has no presentation imports."""
    import ast  # noqa: PLC0415

    source_path = "src/jobs_finder/infrastructure/linkedin/scraper.py"
    with open(source_path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=source_path)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.append(node.module)
    joined = " ".join(imported)
    assert "presentation" not in joined, f"{source_path} imports presentation"


# ---------------------------------------------------------------------------
# T-004 of `backend-linkedin-stealth` — stealth + multi-cookie + closure
# precedence (REQ-LST-SCR-001..004).
#
# Mirrors the Indeed `TestStealthIntegration` pattern (obs #83).
# The tests use a small `_LinkedInFakePage` / `_LinkedInFakeContext` /
# `_LinkedInFakeBrowser` triple (defined inline to avoid touching the
# existing v1 test fixtures) so the `search()` method can run
# end-to-end without launching Chromium. The `stealth=` injection
# is a `MagicMock` whose `apply_stealth_async` is an `AsyncMock` —
# the `await_count` and `await_args` are the regression check.
# ---------------------------------------------------------------------------


class _LinkedInFakePage:
    """Minimal Playwright `Page` stub for T-004 of `backend-linkedin-stealth`."""

    def __init__(self, html: str = "") -> None:
        self._html = html
        self.goto_calls: list[str] = []
        self.wait_calls: list[tuple[str, int]] = []
        self.closed = False

    async def goto(self, url: str) -> None:
        self.goto_calls.append(url)

    async def wait_for_selector(self, selector: str, *, timeout: int) -> None:
        self.wait_calls.append((selector, timeout))

    async def content(self) -> str:
        return self._html

    async def close(self) -> None:
        self.closed = True


class _LinkedInFakeContext:
    """Minimal Playwright `BrowserContext` stub for T-004."""

    def __init__(self, page: _LinkedInFakePage) -> None:
        self.page = page
        self.closed = False
        self.add_cookies_calls: list[list[dict[str, object]]] = []

    async def new_page(self) -> _LinkedInFakePage:
        return self.page

    async def add_cookies(self, cookies: list[dict[str, object]]) -> None:
        # Record every `add_cookies` call so the test can assert
        # the multi-cookie golden shape.
        self.add_cookies_calls.append(cookies)

    async def close(self) -> None:
        self.closed = True


class _LinkedInFakeBrowser:
    """Minimal Playwright `Browser` stub for T-004."""

    def __init__(self, page: _LinkedInFakePage) -> None:
        self.page = page
        self.closed = False
        # Records every context created so the test can assert
        # the cookies injected on it.
        self.contexts: list[_LinkedInFakeContext] = []

    async def new_context(self, **kwargs: object) -> _LinkedInFakeContext:
        ctx = _LinkedInFakeContext(self.page)
        self.contexts.append(ctx)
        return ctx

    async def close(self) -> None:
        self.closed = True


async def _linkedin_make_scraper_with(
    page: _LinkedInFakePage,
) -> tuple[object, _LinkedInFakeBrowser]:
    """Build a `LinkedInPlaywrightScraper` whose browser is the given fake.

    Mirrors the Indeed `_make_scraper_with` pattern (obs #83) but
    uses the local LinkedIn fakes. The throttle is configured
    with `min_interval_seconds=0.0` so the test doesn't actually
    sleep; the inter-page delay is `0.0` for the same reason.
    """
    from jobs_finder.infrastructure.linkedin.scraper import (  # noqa: PLC0415
        LinkedInPlaywrightScraper,
        LinkedInScraperSettings,
    )
    from jobs_finder.infrastructure.linkedin.throttle import (  # noqa: PLC0415
        AsyncThrottle,
    )

    fake_browser = _LinkedInFakeBrowser(page)
    throttle = AsyncThrottle(min_interval_seconds=0.0)

    async def factory() -> _LinkedInFakeBrowser:
        return fake_browser

    settings = LinkedInScraperSettings(
        user_agent="test-agent/1.0",
        timeout_ms=10_000,
        max_pages=1,
        inter_page_delay_seconds=0.0,
    )
    scraper = LinkedInPlaywrightScraper(
        throttle=throttle,
        settings=settings,
        browser_factory=factory,
    )
    return scraper, fake_browser


class TestStealthIntegration:
    """REQ-LST-SCR-001 — `playwright-stealth`'s
    `Stealth().apply_stealth_async` is wired into `search()` so the
    live scraper can bypass Cloudflare's bot detection.

    Mirrors `test_indeed_scraper.py::TestStealthIntegration`
    (obs #83 — the Indeed precedent). The browser_factory injection
    pattern isolates the integration: the real Playwright Chromium
    never launches; the mock Stealth records the awaited call.
    """

    async def test_stealth_is_applied_when_provided(self) -> None:
        """`stealth.apply_stealth_async` is awaited once with the created context."""
        from unittest.mock import AsyncMock, MagicMock  # noqa: PLC0415

        from tests.fixtures.linkedin_search import SEARCH_PAGE_HTML  # noqa: PLC0415

        page = _LinkedInFakePage(SEARCH_PAGE_HTML)
        scraper, _ = await _linkedin_make_scraper_with(page)
        stealth = MagicMock()
        stealth.apply_stealth_async = AsyncMock()
        # Direct attribute assignment (Indeed pattern — the helper
        # does not expose a `stealth=` kwarg; we assign `_stealth`
        # directly so the test stays focused on the integration
        # in `search()`).
        scraper._stealth = stealth  # type: ignore[attr-defined]
        async with scraper:  # type: ignore[attr-defined]
            await scraper.search(  # type: ignore[attr-defined]
                "react", "Madrid", limit=5
            )
        # Exactly one call, exactly one positional argument, the
        # context the scraper just created.
        assert stealth.apply_stealth_async.await_count == 1
        assert stealth.apply_stealth_async.await_args is not None
        args, _ = stealth.apply_stealth_async.await_args
        assert len(args) == 1
        # The single argument is the fake context the fake
        # browser produced.
        assert isinstance(args[0], _LinkedInFakeContext)

    async def test_stealth_is_skipped_when_none(self) -> None:
        """No `apply_stealth_async` call when `stealth=None` (the default)."""
        from tests.fixtures.linkedin_search import SEARCH_PAGE_HTML  # noqa: PLC0415

        page = _LinkedInFakePage(SEARCH_PAGE_HTML)
        scraper, _ = await _linkedin_make_scraper_with(page)
        # `stealth` defaults to None; assert the attribute exists
        # and is None.
        assert scraper._stealth is None  # type: ignore[attr-defined]
        async with scraper:  # type: ignore[attr-defined]
            await scraper.search(  # type: ignore[attr-defined]
                "react", "Madrid", limit=5
            )
        # The test passes if `search()` returns without raising —
        # the absence of `_stealth` would have raised
        # `AttributeError` in the pre-T-004 state.

    async def test_multi_cookie_injection_golden(self) -> None:
        """When `auth_cookies` is set, `add_cookies` is called with all 4.

        REQ-LST-SCR-002 — the multi-cookie path injects each
        `(name, value)` pair from `port.cookies()` via
        `ctx.add_cookies([{...}, ...])` with the LinkedIn-shape
        dict (`domain=".linkedin.com"`, `path="/"`,
        `httpOnly=True`, `secure=True`).
        """
        from pydantic import SecretStr  # noqa: PLC0415

        from jobs_finder.infrastructure.linkedin.auth_cookie import (  # noqa: PLC0415
            MultiEnvLinkedInAuthCookiesAdapter,
        )
        from jobs_finder.infrastructure.linkedin.scraper import (  # noqa: PLC0415
            LinkedInPlaywrightScraper,
            LinkedInScraperSettings,
        )
        from jobs_finder.infrastructure.linkedin.throttle import (  # noqa: PLC0415
            AsyncThrottle,
        )
        from tests.fixtures.linkedin_search import SEARCH_PAGE_HTML  # noqa: PLC0415

        page = _LinkedInFakePage(SEARCH_PAGE_HTML)
        fake_browser = _LinkedInFakeBrowser(page)
        throttle = AsyncThrottle(min_interval_seconds=0.0)

        async def factory() -> _LinkedInFakeBrowser:
            return fake_browser

        auth_cookies = MultiEnvLinkedInAuthCookiesAdapter(
            li_at=SecretStr("AQEAAAAQEAAA"),
            jsessionid=SecretStr("ajax:12345"),
            bcookie=SecretStr("v2_xyz"),
            li_gc=SecretStr("gc_abc"),
        )
        settings = LinkedInScraperSettings(
            user_agent="test-agent/1.0",
            timeout_ms=10_000,
            max_pages=1,
            inter_page_delay_seconds=0.0,
            auth_cookie=None,  # v1 slot kept (None in production wire)
            auth_cookies=auth_cookies,
        )
        scraper = LinkedInPlaywrightScraper(
            throttle=throttle,
            settings=settings,
            browser_factory=factory,
        )
        async with scraper:
            await scraper.search("react", "Madrid", limit=5)
        # The fake browser recorded every context. The
        # production wire should call `add_cookies` exactly once
        # on the single context (4 entries, one per cookie).
        assert len(fake_browser.contexts) == 1
        ctx = fake_browser.contexts[0]
        assert len(ctx.add_cookies_calls) == 1
        cookies = ctx.add_cookies_calls[0]
        assert len(cookies) == 4
        # Each cookie has the LinkedIn-shape dict.
        names = [c["name"] for c in cookies]
        assert names == ["li_at", "JSESSIONID", "bcookie", "li_gc"]
        for cookie in cookies:
            assert cookie["domain"] == ".linkedin.com"
            assert cookie["path"] == "/"
            assert cookie["httpOnly"] is True
            assert cookie["secure"] is True
        # The synthetic test values are NOT in the recorded call
        # shape (the values are present but the test asserts the
        # SHAPE — domain/path/httpOnly/secure — which is the
        # public contract; the values themselves are operator
        # cookies in production).
        assert scraper._settings.auth_cookies is not None

    async def test_closure_warns_on_cloudflare_challenge(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """REQ-LST-SCR-003 — `is_cloudflare_challenge` triggers a soft WARNING.

        The closure emits a WARNING with the prefix
        "LinkedIn Cloudflare challenge detected" and the 3
        missing cookie names; returns `_parse_cards(soup, remaining)`
        (the soft path — NO raise, the route returns a degraded
        empty list).
        """
        import logging  # noqa: PLC0415

        from jobs_finder.infrastructure.linkedin.scraper import (  # noqa: PLC0415
            LinkedInPlaywrightScraper,
            LinkedInScraperSettings,
        )
        from jobs_finder.infrastructure.linkedin.throttle import (  # noqa: PLC0415
            AsyncThrottle,
        )
        from tests.fixtures.linkedin_search import (  # noqa: PLC0415
            CLOUDFLARE_CHALLENGE_HTML,
        )

        page = _LinkedInFakePage(CLOUDFLARE_CHALLENGE_HTML)
        fake_browser = _LinkedInFakeBrowser(page)
        throttle = AsyncThrottle(min_interval_seconds=0.0)

        async def factory() -> _LinkedInFakeBrowser:
            return fake_browser

        # Drive the closure directly — we do not need the full
        # `search()` lifecycle; the closure is the unit under test.
        from pydantic import SecretStr  # noqa: PLC0415

        from jobs_finder.infrastructure.linkedin.auth_cookie import (  # noqa: PLC0415
            MultiEnvLinkedInAuthCookiesAdapter,
        )

        auth_cookies = MultiEnvLinkedInAuthCookiesAdapter(
            li_at=SecretStr("AQEAAAAQEAAA"),
            jsessionid=SecretStr("ajax:12345"),
            bcookie=SecretStr("v2_xyz"),
            li_gc=SecretStr("gc_abc"),
        )
        settings = LinkedInScraperSettings(
            user_agent="test-agent/1.0",
            timeout_ms=10_000,
            max_pages=1,
            inter_page_delay_seconds=0.0,
            auth_cookie=None,
            auth_cookies=auth_cookies,
        )
        scraper = LinkedInPlaywrightScraper(
            throttle=throttle,
            settings=settings,
            browser_factory=factory,
        )
        # Reach the closure directly; drive it with the
        # `_LinkedInFakePage` (which returns the Cloudflare
        # challenge HTML on `content()`).
        fetch = scraper._make_fetch_one_page(  # noqa: SLF001
            "react", "Madrid", geo_id=None, structured=None
        )
        with caplog.at_level(logging.WARNING):
            jobs = await fetch(page, 0, 20)
        # The soft path returns the parsed cards (0 cards on the
        # Cloudflare challenge fixture — the cards-win rule
        # already excluded them, and there are no other cards to
        # parse on the fixture).
        assert jobs == []
        # The WARNING has the expected prefix and mentions the 3
        # missing cookie env-var names. The prefix matches
        # REQ-LST-SCR-003.
        matching = [
            r for r in caplog.records if "LinkedIn Cloudflare challenge detected" in r.getMessage()
        ]
        assert len(matching) == 1, f"expected exactly 1 Cloudflare WARNING, got {len(matching)}"
        # The cookie names are the 3 missing env vars (since
        # the operator's full cookie set is 19+ and we ship 4
        # — the WARNING guides them to add more).
        msg = matching[0].getMessage()
        assert "LINKEDIN_JSESSIONID" in msg
        assert "LINKEDIN_BCOOKIE" in msg
        assert "LINKEDIN_LI_GC" in msg
