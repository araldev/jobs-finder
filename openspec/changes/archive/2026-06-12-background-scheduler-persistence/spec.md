# Change Spec: Background Scheduler + Job Persistence

## Capability: job-repository

Persistent storage layer for scraped jobs, backed by SQLite with WAL mode and a Turso-compatible schema.

| REQ ID | Requirement | Strength | Scenarios |
|--------|-------------|----------|-----------|
| REQ-DB-001 | `JobRepositoryPort` Protocol in `application/ports.py` | MUST | 2 |
| REQ-DB-002 | `SqliteJobRepository` via `aiosqlite` | MUST | 2 |
| REQ-DB-003 | Schema with `jobs` table, constraints, indexes | MUST | 1 |
| REQ-DB-004 | Upsert via `ON CONFLICT(source, source_id) DO UPDATE` | MUST | 2 |

### REQ-DB-001: JobRepositoryPort Protocol

The system MUST define a `JobRepositoryPort` Protocol in `application/ports.py` with three async methods. Structural subtyping (NOT `@runtime_checkable`) — matches existing `JobSearchPort`, `CachePort`, `RateLimitPort` patterns.

#### Scenario: Protocol satisfies mypy --strict structural conformance

- GIVEN a class `SqliteJobRepository` with `upsert_jobs`, `search_jobs`, and `close` methods matching the Protocol signatures
- WHEN mypy --strict checks the assignment
- THEN no type error is reported

#### Scenario: Protocol rejects missing method

- GIVEN a class missing `close()` but with `upsert_jobs` and `search_jobs`
- WHEN mypy --strict checks the assignment
- THEN a type error is reported

### REQ-DB-002: SQLite implementation

The system MUST implement `SqliteJobRepository` in `infrastructure/persistence/sqlite_job_repository.py`. The class MUST satisfy `JobRepositoryPort` structurally and MUST use `aiosqlite` as the async driver.

#### Scenario: Opens DB with context manager on first operation

- GIVEN `SqliteJobRepository(db_path=":memory:")`
- WHEN `upsert_jobs` is called
- THEN the DB is opened via `async with aiosqlite.connect(...)` and WAL mode is enabled via `PRAGMA journal_mode=WAL`
- AND migrations run: `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`

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

- GIVEN the repository connects to a fresh DB
- WHEN migrations run
- THEN the `jobs` table exists with all columns, constraints, and indexes

### REQ-DB-004: Upsert semantics

The system MUST upsert jobs via `INSERT ... ON CONFLICT(source, source_id) DO UPDATE SET title=excluded.title, company=excluded.company, location=excluded.location, url=excluded.url, description=excluded.description, posted_at=excluded.posted_at, last_seen_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')`. The method MUST return the count of affected rows.

#### Scenario: New job inserts a row

- GIVEN a repository with an empty `jobs` table
- WHEN `upsert_jobs([job_1], source="linkedin", query_snapshot={"keywords": "python", "location": "Madrid"})` is called
- THEN 1 row is inserted
- AND `first_seen_at` equals `last_seen_at`

#### Scenario: Existing job updates on conflict

- GIVEN a repository with a row for `(source="linkedin", source_id="123")` with `title="Old Title"`
- WHEN `upsert_jobs([updated_job], source="linkedin", ...)` is called with `title="New Title"` and the same `source_id`
- THEN the row's `title` is updated to `"New Title"`
- AND `last_seen_at` is updated but `first_seen_at` is unchanged

---

## Capability: background-scheduler

Asyncio background task that periodically scrapes all 3 sources and persists results to the repository.

| REQ ID | Requirement | Strength | Scenarios |
|--------|-------------|----------|-----------|
| REQ-SCH-001 | `BackgroundJobScheduler` class | MUST | 1 |
| REQ-SCH-002 | Random interval between cycles | MUST | 1 |
| REQ-SCH-003 | No overlapping runs via `asyncio.Lock` | MUST | 2 |
| REQ-SCH-004 | Graceful `start()` / `stop()` lifecycle | MUST | 2 |
| REQ-SCH-005 | Iterates over configured queries each cycle | MUST | 2 |

### REQ-SCH-001: Scheduler class

The system MUST define `BackgroundJobScheduler` in `infrastructure/scheduler.py`. Constructor accepts: `search_fn: Callable[[str, str], Awaitable[list[Job]]]`, `repo: JobRepositoryPort`, `min_interval: float = 1500.0`, `max_interval: float = 2100.0`, `queries: list[dict[str, str]]`.

- GIVEN a `BackgroundJobScheduler(search_fn=..., repo=..., queries=[{"keywords": "python", "location": "Madrid"}])`
- WHEN the instance is constructed
- THEN all parameters are stored and no side effects occur

### REQ-SCH-002: Random interval

The system MUST sleep `random.uniform(min_interval, max_interval)` seconds between cycles. Default range 1500–2100s (25–35 min).

- GIVEN a scheduler with `min_interval=1.0, max_interval=2.0`
- WHEN a cycle completes
- THEN the next cycle begins after a random delay in `[1.0, 2.0)` seconds

### REQ-SCH-003: No overlapping runs

The system MUST use `asyncio.Lock` to prevent concurrent executions. If a run is in progress when the next is scheduled, the overlapping run MUST be skipped with a WARNING log.

#### Scenario: Lock prevents concurrent execution

- GIVEN a scheduler whose `search_fn` takes 10 seconds
- WHEN `min_interval=0.1` (faster than execution time)
- THEN the second scheduled cycle logs a WARNING and skips
- AND only one `search_fn` invocation runs at a time

#### Scenario: Sequential runs succeed

- GIVEN a scheduler whose `search_fn` takes 0.1 seconds
- WHEN `min_interval=60.0`
- THEN each cycle completes fully before the next starts
- AND all cycles invoke `search_fn`

### REQ-SCH-004: Graceful lifecycle

#### Scenario: Start creates background task

- GIVEN a scheduler instance
- WHEN `start()` is called
- THEN an `asyncio.Task` is created that runs `_loop()`

#### Scenario: Stop cancels gracefully

- GIVEN a running scheduler
- WHEN `stop()` is called mid-cycle
- THEN the task is cancelled
- AND `CancelledError` is caught without propagating

### REQ-SCH-005: Search queries

Each cycle iterates over `self._queries`. For each query, calls `search_fn(keywords, location)`. After ALL queries, calls `repo.upsert_jobs(...)`.

#### Scenario: Multiple queries per cycle

- GIVEN `queries=[{"keywords": "python", "location": "Madrid"}, {"keywords": "java", "location": "Barcelona"}]`
- WHEN one cycle runs
- THEN `search_fn` is called twice (once per query)
- AND `repo.upsert_jobs` is called once with all results

#### Scenario: Search result persists to repo

- GIVEN `queries=[{"keywords": "python", "location": "Madrid"}]`
- WHEN a cycle completes
- THEN `repo.upsert_jobs` is called with the jobs returned by `search_fn`

---

## Configuration

### REQ-CFG-001: New env vars

The system MUST add 5 new fields to `Settings` in `infrastructure/config.py`:

| Field | Env var | Type | Default |
|-------|---------|------|---------|
| `db_path` | `DB_PATH` / `db_path` | `str` | `"jobs.db"` |
| `scheduler_enabled` | `SCHEDULER_ENABLED` / `scheduler_enabled` | `bool` | `False` |
| `scheduler_min_interval_seconds` | `SCHEDULER_MIN_INTERVAL_SECONDS` / `scheduler_min_interval_seconds` | `float` | `1500.0` |
| `scheduler_max_interval_seconds` | `SCHEDULER_MAX_INTERVAL_SECONDS` / `scheduler_max_interval_seconds` | `float` | `2100.0` |
| `scheduler_queries` | `SCHEDULER_QUERIES` / `scheduler_queries` | `list[dict[str, str]]` | `[{"keywords": "desarrollador", "location": "España"}]` |

The `scheduler_queries` field MUST parse from a JSON env var (same pattern as `RATE_LIMIT_EXEMPT_PATHS`).

- GIVEN `SCHEDULER_QUERIES='[{"keywords":"python","location":"Madrid"}]'`
- WHEN `Settings()` is constructed
- THEN `scheduler_queries` equals `[{"keywords": "python", "location": "Madrid"}]`

---

## Wiring

### REQ-ROOT-001: Lifespan wiring

The system MUST wire the scheduler in `app_factory.build_app()` when `settings.scheduler_enabled` and the aggregator use case are available. The order:

1. Build `SqliteJobRepository(db_path=settings.db_path)`
2. Open it (`__aenter__`) in the lifespan
3. Build `BackgroundJobScheduler(search_fn=aggregator.search, repo=repo, queries=settings.scheduler_queries, min_interval=..., max_interval=...)`
4. Call `scheduler.start()` after scrapers are open
5. Call `scheduler.stop()` before scrapers close
6. Close the repository at shutdown end

#### Scenario: Scheduler enabled wires in lifespan

- GIVEN `settings.scheduler_enabled=True`
- WHEN `build_app()` constructs the app
- THEN the lifespan creates the repository, opens it, starts the scheduler, stops it, and closes the repository

#### Scenario: Scheduler disabled is no-op

- GIVEN `settings.scheduler_enabled=False` (default)
- WHEN `build_app()` constructs the app
- THEN no repository or scheduler is built
- AND the lifespan is unchanged from prior behavior

### REQ-ROOT-002: Dependency

Add `aiosqlite>=0.20,<1.0` to `[project.dependencies]` in `pyproject.toml`.

### REQ-ROOT-003: .env.example

Add the 5 new env vars to `backend/.env.example` with sensible defaults and comments:

```
DB_PATH=jobs.db
SCHEDULER_ENABLED=false
SCHEDULER_MIN_INTERVAL_SECONDS=1500.0
SCHEDULER_MAX_INTERVAL_SECONDS=2100.0
SCHEDULER_QUERIES=[{"keywords":"desarrollador","location":"España"}]
```

---

## Specs Written

**Change**: `background-scheduler-persistence`

| Domain | Type | Requirements | Scenarios |
|--------|------|-------------|-----------|
| `job-repository` | New | 4 (DB-001..DB-004) | 7 |
| `background-scheduler` | New | 5 (SCH-001..SCH-005) | 8 |
| Configuration | N/A | 1 (CFG-001) | 1 |
| Wiring | N/A | 3 (ROOT-001..ROOT-003) | 2 |
| **Total** | | **13** | **18** |

### Coverage
- Happy paths: covered
- Edge cases: covered (lock contention, disabled toggle, empty queries)
- Error states: covered (cancelled task, protocol mismatch)

### Next Step
Ready for design (sdd-design). If design already exists, ready for tasks (sdd-tasks).
