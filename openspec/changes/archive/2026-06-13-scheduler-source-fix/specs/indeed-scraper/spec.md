# Spec: `indeed-scraper` — Indeed Playwright scraper

## Purpose

`IndeedPlaywrightScraper` (in `infrastructure/indeed/scraper.py`) is the
adapter of Playwright for the Indeed job-search portal. Its
responsibility is to:

1. Build the search URL with the correct query parameters.
2. Open a fresh browser context + page.
3. Drive the auto-pagination loop via the shared `paginated_search` helper.
4. Detect blocking variants and raise appropriate errors.
5. Parse each page into a `list[Job]`.

## Requirements

### Requirement: REQ-SOURCE-002 — Indeed scraper sets source="indeed" on Job construction

The `IndeedPlaywrightScraper._parse_cards` closure MUST set
`source="indeed"` when constructing each `Job` instance. The source
value MUST exactly match `"indeed"` to satisfy the DB `CHECK` constraint
`source IN ('linkedin','indeed','infojobs')`.

#### Scenario: Indeed scraper sets source="indeed" on Job construction

- GIVEN the Indeed scraper has parsed job cards from a search result page
- WHEN `_parse_cards` constructs `Job` instances
- THEN each `Job` is constructed with `source="indeed"`

#### Scenario: Source is testable via job.source field

- GIVEN a `FakeBrowser` returning valid Indeed HTML with 3 job cards
- WHEN `IndeedPlaywrightScraper.search("python", "Madrid", limit=20)` is called
- THEN the returned `list[Job]` has all 3 jobs with `source="indeed"`

### Requirement: REQ-QUERY-003 — Indeed scraper handles empty keywords without error

The scraper MUST pass `keywords=""` (empty string) verbatim to the URL
builder when the scheduler passes empty keywords. The scraper MUST NOT
raise an error or skip the search when keywords are empty.

#### Scenario: Empty keywords passed to URL builder as-is

- GIVEN `keywords=""` passed to `search()`
- WHEN the URL is built
- THEN the URL contains the empty keywords parameter without error
- AND the search executes against Indeed with an empty query string

## Out of scope

- The pagination loop internals (`paginated_search` helper, inter-page delay,
  max-pages cap) — owned by the shared helper.
- The URL formula, blocking detection, and parser selectors — covered by
  existing scraper tests.
- The `JobSearchPort` Protocol — source-agnostic, unchanged.
