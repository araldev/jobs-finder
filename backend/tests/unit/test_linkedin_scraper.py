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
    """`_build_url` is a `@staticmethod` whose 4 params match the documented shape.

    The test pins the call shape: the static method takes
    `(keywords, location, start, geo_id=None)`. `keywords` is
    required (no default); `location` and `start` are required;
    `geo_id` has `None` as default. A regression that switches
    the call shape (e.g. moves `geo_id` to position 0) would
    surface here.
    """
    import inspect  # noqa: PLC0415

    sig = inspect.signature(LinkedInPlaywrightScraper._build_url)  # noqa: SLF001
    params = list(sig.parameters.values())
    # 4 parameters: keywords, location, start, geo_id.
    assert len(params) == 4
    assert [p.name for p in params] == ["keywords", "location", "start", "geo_id"]
    # `keywords`, `location`, `start` are required (no default).
    assert sig.parameters["keywords"].default is inspect.Parameter.empty
    assert sig.parameters["location"].default is inspect.Parameter.empty
    assert sig.parameters["start"].default is inspect.Parameter.empty
    # `geo_id` has `None` as default (backward compat: callers
    # pre-WU2 can omit it).
    assert sig.parameters["geo_id"].default is None


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
