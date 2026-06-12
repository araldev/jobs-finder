# Spec: `job-repository` — persistent SQLite storage for scraped jobs

> **PROMOTED to source of truth on 2026-06-12** from
> `openspec/changes/background-scheduler-persistence/spec.md`
> §"Capability: `job-repository`". This is a NEW foundational
> capability spec — no prior `openspec/specs/job-repository/spec.md`
> existed. The delta is promoted in full as the foundational spec for
> the capability, capturing the `SqliteJobRepository`, the
> `JobRepositoryPort` Protocol, the Turso-compatible schema with WAL
> mode, and the upsert semantics. Source observation IDs for
> traceability: explore #405, proposal (see preflight #404), spec #406,
> design #407, tasks (see apply #409), verify-report #410.

## Purpose

The `job-repository` capability provides a **persistent storage layer**
for scraped job offers, backed by SQLite with WAL mode and a
Turso-compatible schema. It lives alongside the existing in-memory
TTL cache — the cache serves per-request dedup within TTL; the DB
serves historical persistence and background-scheduler results.

## Requirements

### REQ-DB-001: JobRepositoryPort Protocol

The system MUST define a `JobRepositoryPort` Protocol in
`application/ports.py` with five async methods. Structural subtyping
(NOT `@runtime_checkable`) — matches existing `JobSearchPort`,
`CachePort`, `RateLimitPort` patterns.

Existing methods: `upsert_jobs`, `search_jobs`, `close`.

New methods:

```python
async def delete_older_than(
    self, *, days: int, limit: int = 1000
) -> int: ...

async def search_jobs_history(
    self,
    *,
    sources: list[str] | None = None,
    keywords: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Job]: ...

async def count_jobs(
    self,
    *,
    sources: list[str] | None = None,
    keywords: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> int: ...
```

#### Scenario: Protocol satisfies mypy --strict structural conformance

- GIVEN a class `SqliteJobRepository` with `upsert_jobs`, `search_jobs`,
  `close`, `delete_older_than`, `search_jobs_history`, and `count_jobs`
  methods matching the Protocol signatures
- WHEN mypy --strict checks the assignment
- THEN no type error is reported

#### Scenario: Protocol rejects missing method

- GIVEN a class missing `delete_older_than` but with all other methods
- WHEN mypy --strict checks the assignment
- THEN a type error is reported

### REQ-DB-002: SQLite implementation

The system MUST implement `SqliteJobRepository` in
`infrastructure/persistence/sqlite_job_repository.py`. The class MUST
satisfy `JobRepositoryPort` structurally and MUST use `aiosqlite` as
the async driver. The context manager pattern (`__aenter__`/`__aexit__`)
opens the connection and runs migrations at startup, matching the
existing `PlaywrightScraper` lifecycle precedent.

#### Scenario: Opens DB with context manager on first operation

- GIVEN `SqliteJobRepository(db_path=":memory:")`
- WHEN `upsert_jobs` is called
- THEN the DB is opened via `async with aiosqlite.connect(...)` and
  WAL mode is enabled via `PRAGMA journal_mode=WAL`
- AND migrations run: `CREATE TABLE IF NOT EXISTS` +
  `CREATE INDEX IF NOT EXISTS`

#### Scenario: Supports relative and absolute db_path

- GIVEN `SqliteJobRepository(db_path="jobs.db")`
- WHEN the repository opens the connection
- THEN the path is resolved relative to the process working directory

### REQ-DB-003: Schema

The system MUST create a `jobs` table with the following schema:

```sql
CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL CHECK(source IN ('linkedin','indeed','infojobs')),
    source_id       TEXT NOT NULL,
    title           TEXT NOT NULL,
    company         TEXT NOT NULL,
    location        TEXT NOT NULL,
    url             TEXT NOT NULL,
    description     TEXT,
    posted_at       TEXT NOT NULL,  -- ISO 8601 with timezone
    query_snapshot  TEXT NOT NULL,  -- JSON: {"keywords":"...", "location":"..."}
    first_seen_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    last_seen_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_posted_at ON jobs(posted_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_source_source_id ON jobs(source, source_id);
```

#### Scenario: Table and indexes created

- GIVEN the repository connects to a fresh DB
- WHEN migrations run
- THEN the `jobs` table exists with all columns, constraints, and indexes

### REQ-DB-004: Upsert semantics

The system MUST upsert jobs via:

```sql
INSERT INTO jobs (...)
ON CONFLICT(source, source_id) DO UPDATE SET
    title=excluded.title, company=excluded.company,
    location=excluded.location, url=excluded.url,
    description=excluded.description, posted_at=excluded.posted_at,
    last_seen_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
```

The method MUST return the count of affected rows.

#### Scenario: New job inserts a row

- GIVEN a repository with an empty `jobs` table
- WHEN `upsert_jobs([job_1], source="linkedin",
  query_snapshot={"keywords": "python", "location": "Madrid"})`
  is called
- THEN 1 row is inserted
- AND `first_seen_at` equals `last_seen_at`

#### Scenario: Existing job updates on conflict

- GIVEN a repository with a row for `(source="linkedin", source_id="123")`
  with `title="Old Title"`
- WHEN `upsert_jobs([updated_job], source="linkedin", ...)` is called
  with `title="New Title"` and the same `source_id`
- THEN the row's `title` is updated to `"New Title"`
- AND `last_seen_at` is updated but `first_seen_at` is unchanged

### REQ-CFG-001 (db_path): Database path configuration

| Field | Env var | Type | Default |
|-------|---------|------|---------|
| `db_path` | `DB_PATH` / `db_path` | `str` | `"jobs.db"` |

The `db_path` field is part of the `Settings` class in
`infrastructure/config.py`, using `AliasChoices("DB_PATH", "db_path")`
so env-var and programmatic construction both work.

## Scenarios summary

| REQ | Scenarios | Count |
|-----|-----------|-------|
| REQ-DB-001 | Protocol conformance (5 methods), rejection of missing method | 2 |
| REQ-DB-002 | DB open with WAL, relative/absolute path | 2 |
| REQ-DB-003 | Schema and indexes | 1 |
| REQ-DB-004 | New row insert, existing row update | 2 |

## New Capabilities

### REQ-HIST-001: search_jobs_history and count_jobs on Protocol

The system MUST define on `JobRepositoryPort`:

- `search_jobs_history(*, sources=None, keywords=None, date_from=None, date_to=None, limit=50, offset=0) -> list[Job]` with `limit` max `200`
- `count_jobs(*, sources=None, keywords=None, date_from=None, date_to=None) -> int`

Both return results filtered by the provided criteria.

**Scenario: Filters by source**

- GIVEN jobs from linkedin, indeed, infojobs in the DB
- WHEN `search_jobs_history(sources=["linkedin"])`
- THEN only linkedin jobs are returned

**Scenario: Date range filters correctly**

- GIVEN a job with `posted_at="2026-01-15"`
- WHEN `search_jobs_history(date_from="2026-01-01", date_to="2026-01-31")`
- THEN the job is included

**Scenario: Limit caps at 200**

- GIVEN 500 matching jobs
- WHEN `search_jobs_history(limit=200)`
- THEN at most 200 jobs are returned

### REQ-HIST-002: GET /jobs/history endpoint

The system MUST expose `GET /jobs/history` with query params:
`sources` (comma-separated), `keywords`, `date_from`, `date_to`,
`limit` (max 200, default 50), `offset` (default 0). Returns JSON
with `items: list[Job]` and `total: int`.

**Scenario: Full-featured query**

- GIVEN jobs in the DB
- WHEN `GET /jobs/history?sources=linkedin,indeed&keywords=python&date_from=2026-01-01&limit=20&offset=0`
- THEN response is `200` with paginated results and `total` count

**Scenario: Works without scheduler**

- GIVEN `SCHEDULER_ENABLED=false` but `DB_PATH` set
- WHEN `GET /jobs/history`
- THEN response is `200` with results from the persisted DB

## Scenarios summary

| REQ | Scenarios | Count |
|-----|-----------|-------|
| REQ-DB-001 | Protocol conformance (5 methods), rejection of missing method | 2 |
| REQ-DB-002 | DB open with WAL, relative/absolute path | 2 |
| REQ-DB-003 | Schema and indexes | 1 |
| REQ-DB-004 | New row insert, existing row update | 2 |
| REQ-HIST-001 | Filters by source, date range, limit caps at 200 | 3 |
| REQ-HIST-002 | Full-featured query, works without scheduler | 2 |
| **Total** | | **12** |
