# Spec: `infojobs-scraper` — InfoJobs Playwright scraper (URL formula + settings)

> **Promoted to source of truth on 2026-06-10** from
> `openspec/changes/backend-infojobs-provinces/specs/infojobs-scraper/spec.md`
> (archived in `openspec/changes/archive/2026-06-10-backend-infojobs-provinces/`).
>
> This was a MODIFIED delta — no prior
> `openspec/specs/infojobs-scraper/spec.md` existed. The delta is
> promoted in full as the foundational spec for the capability,
> capturing the new behavior on top of the pre-change
> `InfoJobsPlaywrightScraper` contract. Source observation IDs for
> traceability: explore #330, proposal #331, spec #334, design #337,
> tasks #339, apply-progress #341, verify-report #342.

## Purpose

Extend the `InfoJobsPlaywrightScraper` so the URL it navigates to
includes `provinceIds=<id>&countryIds=<id>` when the
`HardcodedLocationResolver.resolve_infojobs(location)` call returns
a non-`None` tuple. When the resolver returns `(None, None)` (no
mapping for the input location, or the resolver is not injected),
the scraper MUST fall back to the v1 `?l=<str>` formula unchanged.
The InfoJobs URL formula is the canonical way to scope the SERP
to a region; without it, InfoJobs returns all-Spain results for
queries like `?q=react&l=malaga` (the pre-change bug).

The `InfoJobsPlaywrightScraper.search(...)` signature is
`async def search(keywords, location, limit=20, geo_id=None) -> list[Job]`
(the `geo_id` kwarg is the LinkedIn-specific arg from `JobSearchPort`;
InfoJobs has always ignored it). The MODIFIED signature extends the
internal contract — NOT the `JobSearchPort` Protocol, which stays
source-agnostic. The new signature is:

```python
async def search(
    keywords: str,
    location: str,
    limit: int = 20,
    geo_id: int | None = None,                                  # existing (ignored)
    infojobs_geo: tuple[int | None, int | None] | None = None, # NEW — scraper-internal
) -> list[Job]:
```

The `infojobs_geo` kwarg is a NON-PORT argument. Aggregators,
use cases, and the cache wrapper do NOT pass it. The InfoJobs
scraper resolves the tuple internally (via the injected
`location_resolver`) when the kwarg is `None`. The `geo_id` kwarg
is kept for `JobSearchPort` structural conformance; InfoJobs
ignores it (the pre-change behavior is unchanged).

## Requirements

### REQ-PROV-002 — InfoJobs scraper URL includes `provinceIds` + `countryIds` when resolved

The `InfoJobsPlaywrightScraper._build_url(...)` method MUST include
`provinceIds=<id>` (when `province_id` is not `None`) and
`countryIds=<id>` (when `country_id` is not `None`) as query
parameters appended to the v1 base URL. When the resolver returns
`(None, None)`, both params are OMITTED (legacy `?l=<str>` fallback).

The URL is built ONCE per `search()` call — the resolver runs
exactly once per call (not once per page in the pagination loop).
The tuple is captured by `_make_fetch_one_page` and forwarded to
`_build_url` on every page (the `page=` param changes per page;
the province/country IDs do not).

#### Scenario: mapped location adds provinceIds + countryIds to the URL

- **GIVEN** the `InfoJobsScraperSettings` is constructed with a `location_resolver` whose `resolve_infojobs("malaga")` returns `(34, 17)`
- **WHEN** `InfoJobsPlaywrightScraper.search("react", "malaga", 20)` builds the URL for the first page
- **THEN** the URL is `https://www.infojobs.net/ofertas-trabajo?q=react&l=malaga&page=1&provinceIds=34&countryIds=17`
- **AND** the test `test_infojobs_scraper.py::test_search_uses_province_country_ids_when_mapped` passes

#### Scenario: country-only mapping adds `countryIds` only (no `provinceIds`)

- **GIVEN** the resolver's `resolve_infojobs("Remote")` returns `(None, 17)`
- **WHEN** `InfoJobsPlaywrightScraper.search("react", "Remote", 20)` builds the URL
- **THEN** the URL is `https://www.infojobs.net/ofertas-trabajo?q=react&l=Remote&page=1&countryIds=17` (NO `provinceIds` param)
- **AND** the test `test_infojobs_scraper.py::test_search_country_only_omits_province_ids` passes

#### Scenario: unmapped location omits both `provinceIds` and `countryIds`

- **GIVEN** the resolver's `resolve_infojobs("Berlin")` returns `(None, None)`
- **WHEN** `InfoJobsPlaywrightScraper.search("react", "Berlin", 20)` builds the URL
- **THEN** the URL is `https://www.infojobs.net/ofertas-trabajo?q=react&l=Berlin&page=1` (NO `provinceIds`, NO `countryIds` — exact v1 fallback)
- **AND** the test `test_infojobs_scraper.py::test_search_omits_province_country_ids_when_unmapped` passes

#### Scenario: empty `location` omits both params (the v1 path is unchanged)

- **GIVEN** the resolver's `resolve_infojobs("")` returns `(None, None)` (empty short-circuit)
- **WHEN** `InfoJobsPlaywrightScraper.search("react", "", 20)` builds the URL
- **THEN** the URL is `https://www.infojobs.net/ofertas-trabajo?q=react&l=&page=1` (no province/country IDs)
- **AND** the test `test_infojobs_scraper.py::test_search_empty_location_omits_province_country_ids` passes

#### Scenario: resolver is called exactly once per `search()` (not per page)

- **GIVEN** a 3-page search via the `paginated_search` helper (the canonical loop)
- **WHEN** the search is executed
- **THEN** the resolver's `resolve_infojobs()` method is called exactly 1 time (the test uses a recording fake that counts calls; the count is asserted to be 1, not 3)
- **AND** the URL built for each of the 3 pages differs ONLY in the `page=` param (`page=1`, `page=2`, `page=3`); the `provinceIds=` + `countryIds=` are byte-identical across pages
- **AND** the test `test_infojobs_scraper.py::test_resolver_called_once_per_search` passes

#### Scenario: legacy wiring without resolver keeps the v1 URL formula

- **GIVEN** the `InfoJobsScraperSettings` is constructed WITHOUT a `location_resolver` (`location_resolver=None` — the default)
- **WHEN** `InfoJobsPlaywrightScraper.search("react", "malaga", 20)` builds the URL
- **THEN** the URL is `https://www.infojobs.net/ofertas-trabajo?q=react&l=malaga&page=1` (NO `provinceIds`, NO `countryIds` — legacy behavior, byte-identical to the pre-change scraper)
- **AND** a `DeprecationWarning` is logged ONCE per `search()` call (NOT raised — the legacy path is still valid, just suboptimal) to nudge operators to inject the resolver
- **AND** the test `test_infojobs_scraper.py::test_legacy_wiring_without_resolver_logs_warning` passes

#### Scenario: explicit `infojobs_geo` kwarg bypasses the resolver

- **GIVEN** the caller passes `infojobs_geo=(34, 17)` to `search(...)` directly (the kwarg is a non-public, scraper-internal argument; aggregators and use cases do NOT pass it)
- **WHEN** the URL is built
- **THEN** the resolver is NOT called (the explicit tuple wins; the `infojobs_geo` arg is forwarded to `_make_fetch_one_page` directly)
- **AND** the test `test_infojobs_scraper.py::test_explicit_infojobs_geo_kwarg_skips_resolver` passes

### REQ-PROV-002-MOD — `search()` resolution semantics

(Previously: `search()` had no resolver plumb; the URL builder always
fell back to `?l=<str>`, returning all-Spain results for any
`location=` value.)

The `InfoJobsPlaywrightScraper.search()` method MUST resolve the
`(province_id, country_id)` tuple at the START of the call
(before the pagination loop), then forward the captured tuple
to `_make_fetch_one_page(keywords, location, infojobs_geo=tuple)`
so the URL builder can emit the province/country params on
every page.

#### Scenario: resolver called once at `search()` start

- **GIVEN** the `InfoJobsScraperSettings` is wired with a recording fake resolver
- **WHEN** `InfoJobsPlaywrightScraper.search("react", "malaga", 20)` is called
- **THEN** the resolver's `resolve_infojobs("malaga")` is called exactly once
- **AND** the captured tuple `(34, 17)` is forwarded to `_make_fetch_one_page` (the test asserts the closure was called with the tuple)
- **AND** the test `test_infojobs_scraper.py::test_search_resolves_tuple_once` passes

#### Scenario: explicit `infojobs_geo` arg skips the resolver call

- **GIVEN** the caller passes `infojobs_geo=(34, 17)` to `search(...)`
- **WHEN** the method is called
- **THEN** the resolver is NOT called (the explicit tuple wins)
- **AND** the URL is built with `provinceIds=34&countryIds=17` from the explicit tuple
- **AND** the test `test_infojobs_scraper.py::test_explicit_infojobs_geo_skips_resolver` passes

#### Scenario: tuple forwarded to the closure (per-page URL uses it)

- **GIVEN** the resolver returns `(34, 17)` for `"malaga"`
- **WHEN** the pagination loop iterates over 3 pages
- **THEN** `_make_fetch_one_page` is called with the tuple captured once at the start
- **AND** the URLs built for pages 1, 2, 3 all carry `provinceIds=34&countryIds=17` (only `page=` changes)
- **AND** the test `test_infojobs_scraper.py::test_tuple_forwarded_to_closure_across_pages` passes

### REQ-PROV-003 — `InfoJobsScraperSettings` accepts the resolver

The `InfoJobsScraperSettings` MUST add an optional
`location_resolver: LocationResolverPort | None = None` field.
The field defaults to `None` (backward-compatible: the pre-change
test suite + the legacy `app_factory` path keep working unchanged).
The field MUST participate in `__eq__` and `__hash__` so the
settings object is hashable in cache wrappers (mirrors the
existing `LinkedInScraperSettings.location_resolver` pattern at
`infrastructure/linkedin/scraper.py`).

#### Scenario: settings accept the resolver

- **GIVEN** the `InfoJobsScraperSettings` is constructed with `location_resolver=HardcodedLocationResolver()`
- **WHEN** the settings are validated
- **THEN** the field is accepted without error and the resolver is stored
- **AND** the test `test_infojobs_settings.py::test_settings_accept_resolver` passes

#### Scenario: settings default `location_resolver=None` (backward-compat)

- **GIVEN** the `InfoJobsScraperSettings` is constructed WITHOUT a `location_resolver` kwarg (legacy wiring)
- **WHEN** the settings are validated
- **THEN** the field defaults to `None` and the settings object is valid
- **AND** the existing legacy tests in `test_infojobs_settings.py` continue to pass (the field is OPTIONAL with a `None` default)

#### Scenario: settings with resolver are hashable and `==` to identical settings

- **GIVEN** two `InfoJobsScraperSettings` instances constructed with the SAME `location_resolver` (the SAME Python object)
- **WHEN** they are compared with `==` and `hash()`
- **THEN** they are equal and have the same hash (mirrors the `LinkedInScraperSettings.__eq__/__hash__` pattern)
- **AND** two settings with DIFFERENT resolver instances are NOT equal (the resolver identity is the comparison key — the same pattern the `LinkedInScraperSettings` uses)
- **AND** the test `test_infojobs_settings.py::test_settings_equality_includes_resolver` passes

## New requirements (added 2026-06-13 from `scheduler-source-fix` archive)

### REQ-SOURCE-002 — InfoJobs scraper sets source="infojobs" on Job construction

The `InfoJobsPlaywrightScraper._parse_cards` closure MUST set
`source="infojobs"` when constructing each `Job` instance. The source
value MUST exactly match `"infojobs"` to satisfy the DB `CHECK` constraint
`source IN ('linkedin','indeed','infojobs')`.

#### Scenario: InfoJobs scraper sets source="infojobs" on Job construction

- GIVEN the InfoJobs scraper has parsed job cards from a search result page
- WHEN `_parse_cards` constructs `Job` instances
- THEN each `Job` is constructed with `source="infojobs"`

#### Scenario: Source is testable via job.source field

- GIVEN a `FakeBrowser` returning valid InfoJobs HTML with 3 job cards
- WHEN `InfoJobsPlaywrightScraper.search("python", "Madrid", limit=20)` is called
- THEN the returned `list[Job]` has all 3 jobs with `source="infojobs"`

### REQ-QUERY-003 — InfoJobs scraper handles empty keywords without error

The scraper MUST pass `keywords=""` (empty string) verbatim to the URL
builder when the scheduler passes empty keywords. The scraper MUST NOT
raise an error or skip the search when keywords are empty.

#### Scenario: Empty keywords passed to URL builder as-is

- GIVEN `keywords=""` passed to `search()`
- WHEN the URL is built
- THEN the URL contains the empty keywords parameter without error
- AND the search executes against InfoJobs with an empty query string

## Out of scope

- Adding `sortBy=RELEVANCE`, `sinceDate=ANY`, `segmentId=` to the URL (separate change; the 2 new params are the minimum to fix the bug).
- Changing the `JobSearchPort` Protocol — the `infojobs_geo` kwarg is scraper-internal, not on the Port.
- Changing the `JobSearchCacheKey` NamedTuple — the 5th field is LinkedIn-specific; the InfoJobs tuple travels via the closure kwarg, not the cache key (the cache wrapper's key still uses `geo_id=None` for InfoJobs, which is correct).
- Changing the HTTP shape — the frontend still sends `location=...`; the resolver runs internally.
- Adding more sources (the change is InfoJobs-specific).
