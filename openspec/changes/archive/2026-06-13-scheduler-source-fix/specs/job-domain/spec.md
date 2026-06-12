# Delta for `job-domain`

## ADDED Requirements

### Requirement: REQ-SOURCE-001 — Job dataclass carries source

The `Job` frozen dataclass in `domain/job.py` MUST include a
required `source: str` field as a positional argument placed before
existing fields to preserve the `description=None` default. The field
MUST be set by the caller at construction time and MUST NOT be
modifiable after instantiation.

#### Scenario: Job construction with source field

- GIVEN a `Job` constructor call with `source="linkedin"`
- WHEN the instance is created
- THEN `job.source` equals `"linkedin"`
- AND `job.source` is immutable (frozen dataclass)

#### Scenario: source is required at construction

- GIVEN a `Job` constructor call missing the `source` argument
- WHEN the instance is created
- THEN a `TypeError` is raised for the missing required argument

---

### Requirement: REQ-SOURCE-002 — Scrapers set source on Job construction

Each scraper's `_parse_cards` closure MUST set `source=<source_name>`
when constructing `Job` instances:
`linkedin` → `"linkedin"`, `indeed` → `"indeed"`, `infojobs` → `"infojobs"`.

The source string MUST match the values permitted by the DB
`CHECK(source IN ('linkedin','indeed','infojobs'))` constraint.

#### Scenario: LinkedIn scraper sets source="linkedin"

- GIVEN the LinkedIn scraper parses job cards from a search result page
- WHEN each `Job` is constructed in `_parse_cards`
- THEN `source="linkedin"` is passed to the `Job(...)` constructor

#### Scenario: Indeed scraper sets source="indeed"

- GIVEN the Indeed scraper parses job cards from a search result page
- WHEN each `Job` is constructed in `_parse_cards`
- THEN `source="indeed"` is passed to the `Job(...)` constructor

#### Scenario: InfoJobs scraper sets source="infojobs"

- GIVEN the InfoJobs scraper parses job cards from a search result page
- WHEN each `Job` is constructed in `_parse_cards`
- THEN `source="infojobs"` is passed to the `Job(...)` constructor

## Out of scope

- Changing any other `Job` fields (title, company, location, url, description, posted_at, etc.)
- The `JobRepositoryPort` Protocol signature (handled by `job-repository` delta)
- Adding new job sources
