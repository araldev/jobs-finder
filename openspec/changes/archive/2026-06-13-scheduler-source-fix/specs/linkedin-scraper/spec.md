# Delta for `linkedin-scraper`

## ADDED Requirements

### Requirement: REQ-SOURCE-002 — LinkedIn scraper sets source="linkedin" on Job construction

The `LinkedInPlaywrightScraper._parse_cards` closure MUST set
`source="linkedin"` when constructing each `Job` instance. The source
value MUST exactly match `"linkedin"` to satisfy the DB `CHECK` constraint
`source IN ('linkedin','indeed','infojobs')`.

#### Scenario: LinkedIn scraper sets source="linkedin" on Job construction

- GIVEN the LinkedIn scraper has parsed job cards from a search result page
- WHEN `_parse_cards` constructs `Job` instances
- THEN each `Job` is constructed with `source="linkedin"`

#### Scenario: Source is testable via job.source field

- GIVEN a `FakeBrowser` returning valid LinkedIn HTML with 3 job cards
- WHEN `LinkedInPlaywrightScraper.search("python", "Madrid", limit=20)` is called
- THEN the returned `list[Job]` has all 3 jobs with `source="linkedin"`

### Requirement: REQ-QUERY-003 — LinkedIn scraper handles empty keywords without error

The scraper MUST pass `keywords=""` (empty string) verbatim to the URL
builder when the scheduler passes empty keywords. The scraper MUST NOT
raise an error or skip the search when keywords are empty.

#### Scenario: Empty keywords passed to URL builder as-is

- GIVEN `keywords=""` passed to `search()`
- WHEN the URL is built
- THEN the URL contains the empty keywords parameter without error
- AND the search executes against LinkedIn with an empty query string
