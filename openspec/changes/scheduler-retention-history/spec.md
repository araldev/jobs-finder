# Delta Spec: scheduler-retention-history

## Overview

Adds three capabilities: TTL-based job retention inline in the scheduler, a scheduler runtime status endpoint, and a historical jobs query endpoint with pagination. Modifies `background-scheduler` to track runtime state and run retention after each cycle. Extends `job-repository` Protocol with `delete_older_than()`, `search_jobs_history()`, and `count_jobs()`. The repository opens on `DB_PATH` alone, no longer gated by `SCHEDULER_ENABLED`.

---

## New Capabilities

### Capability: `scheduler-cleanup`

#### REQ-RET-001: Retention config

The system MUST define `RETENTION_DAYS` on `Settings` as `int` with default `0`. Uses `AliasChoices("RETENTION_DAYS", "retention_days")`. When `0`, retention MUST NOT execute. The DELETE MUST cap at a `LIMIT 1000` to bound transaction duration.

**Scenario: Config defaults to 0 (disabled)**

- GIVEN no `RETENTION_DAYS` env var
- WHEN `Settings()` is constructed
- THEN `retention_days` equals `0`

**Scenario: Non-zero enables retention**

- GIVEN `RETENTION_DAYS=30`
- WHEN `Settings()` is constructed
- THEN `retention_days` equals `30`

#### REQ-RET-002: Retention runs inline after upsert

The system MUST call `repo.delete_older_than(days=retention_days, limit=1000)` after `repo.upsert_jobs()` in the scheduler loop, inside the same lock acquisition, when `retention_days > 0`.

**Scenario: Retention deletes old jobs per cycle**

- GIVEN a scheduler with `retention_days=30` and jobs with `last_seen_at < now - 30d` in the DB
- WHEN a cycle completes upsert
- THEN `delete_older_than(30, 1000)` is called
- AND rows older than 30 days are deleted

**Scenario: Retention is skipped when days=0**

- GIVEN a scheduler with `retention_days=0`
- WHEN a cycle completes upsert
- THEN `delete_older_than` is NOT called

---

### Capability: `scheduler-status`

#### REQ-STATUS-001: SchedulerState dataclass

The system MUST define `SchedulerState` as a dataclass on `BackgroundJobScheduler` tracking: `enabled`, `running`, `last_run_start`, `last_run_end`, `last_error`, `cycle_count`, `total_jobs_collected`, `total_in_db`, `total_per_source`, `queries`, `min_interval_seconds`, `max_interval_seconds`. Fields update at each cycle boundary.

**Scenario: State reflects idle scheduler**

- GIVEN a scheduler that has not run yet
- WHEN state is read
- THEN `running` is `False`, `cycle_count` is `0`

**Scenario: State updates after cycle**

- GIVEN a running scheduler
- WHEN one cycle completes
- THEN `cycle_count` is `1`
- AND `last_run_end` is set
- AND `last_error` is `None`

#### REQ-STATUS-002: GET /scheduler/status

The system MUST expose `GET /scheduler/status` returning JSON of the `SchedulerState`. Returns `200` with full state when scheduler exists. Graceful degradation when no scheduler or repo unavailable (returns `{"enabled": false}`).

**Scenario: Status returns scheduler state**

- GIVEN a running scheduler
- WHEN `GET /scheduler/status`
- THEN response is `200` with JSON containing `enabled: true`, `cycle_count`, and all state fields

**Scenario: Degrades gracefully when disabled**

- GIVEN no scheduler (`SCHEDULER_ENABLED=false`)
- WHEN `GET /scheduler/status`
- THEN response is `200` with `{"enabled": false}`

---

### Capability: `job-history`

#### REQ-HIST-001: search_jobs_history and count_jobs on Protocol

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

#### REQ-HIST-002: GET /jobs/history endpoint

The system MUST expose `GET /jobs/history` with query params: `sources` (comma-separated), `keywords`, `date_from`, `date_to`, `limit` (max 200, default 50), `offset` (default 0). Returns JSON with `items: list[Job]` and `total: int`.

**Scenario: Full-featured query**

- GIVEN jobs in the DB
- WHEN `GET /jobs/history?sources=linkedin,indeed&keywords=python&date_from=2026-01-01&limit=20&offset=0`
- THEN response is `200` with paginated results and `total` count

**Scenario: Works without scheduler**

- GIVEN `SCHEDULER_ENABLED=false` but `DB_PATH` set
- WHEN `GET /jobs/history`
- THEN response is `200` with results from the persisted DB

---

## Modified Capabilities

### Capability: `background-scheduler`

#### REQ-SCH-001 (MODIFIED): Scheduler class

The system MUST define `BackgroundJobScheduler` in `infrastructure/scheduler.py`. Constructor accepts:

```python
def __init__(
    self,
    search_fn: Callable[[str, str], Awaitable[list[Job]]],
    repo: JobRepositoryPort,
    queries: list[dict[str, str]],
    min_interval: float = 1500.0,
    max_interval: float = 2100.0,
    retention_days: int = 0,
) -> None: ...
```
(Previously: 5 params, no `retention_days`)

**Scenario: Constructor stores parameters**

- GIVEN `BackgroundJobScheduler(search_fn=..., repo=..., queries=[{"keywords": "python", "location": "Madrid"}], retention_days=30)`
- WHEN the instance is constructed
- THEN all parameters are stored and no side effects occur

#### REQ-SCH-005 (MODIFIED): Search queries with retention

Each cycle iterates over `self._queries`. For each query, calls `search_fn(keywords, location)`. After ALL queries, calls `repo.upsert_jobs(...)`. After upsert, if `retention_days > 0`, calls `repo.delete_older_than(days=retention_days, limit=1000)`.
(Previously: no retention call after upsert)

**Scenario: Multiple queries per cycle**

- GIVEN `queries=[{"keywords": "python", "location": "Madrid"}, {"keywords": "java", "location": "Barcelona"}]`
- WHEN one cycle runs
- THEN `search_fn` is called twice (once per query)
- AND `repo.upsert_jobs` is called once with all results
- AND if `retention_days > 0`, `repo.delete_older_than` is called after upsert

**Scenario: Search result persists to repo**

- GIVEN `queries=[{"keywords": "python", "location": "Madrid"}], retention_days=30`
- WHEN a cycle completes
- THEN `repo.upsert_jobs` is called with the jobs returned by `search_fn`
- AND `repo.delete_older_than` is called after upsert

#### REQ-CFG-001 (scheduler) (MODIFIED): Scheduler configuration

Add `retention_days` to the scheduler config fields:

| Field | Env var | Type | Default |
|-------|---------|------|---------|
| `retention_days` | `RETENTION_DAYS` / `retention_days` | `int` | `0` |

(Previously: 4 fields, no retention field)

#### REQ-ROOT-001 (MODIFIED): Lifespan wiring

The system MUST wire the repository based on `DB_PATH`, not `SCHEDULER_ENABLED`. The order:

1. Build `SqliteJobRepository(db_path=settings.db_path)` when `DB_PATH` is non-empty
2. Open it (`__aenter__`) in the lifespan
3. If `settings.scheduler_enabled`: build `BackgroundJobScheduler(...)` with `retention_days` from settings
4. Call `scheduler.start()` if enabled
5. Call `scheduler.stop()` if enabled
6. Close the repository at shutdown end

(Previously: repository was only built when scheduler enabled; no step 3 and 4 were inside a single enabled gate)

**Scenario: Scheduler enabled wires fully**

- GIVEN `settings.scheduler_enabled=True, settings.db_path="jobs.db"`
- WHEN `build_app()` constructs the app
- THEN the repository is built and opened
- AND the scheduler is started
- AND at shutdown, scheduler stops then repo closes

**Scenario: Repo opens even when scheduler disabled**

- GIVEN `settings.scheduler_enabled=False, settings.db_path="jobs.db"`
- WHEN `build_app()` constructs the app
- THEN the repository is built and opened in lifespan
- AND no scheduler is started
- AND at shutdown, the repo closes

---

### Capability: `job-repository`

#### REQ-DB-001 (MODIFIED): JobRepositoryPort Protocol

The system MUST define `JobRepositoryPort` Protocol in `application/ports.py` with **five** async methods. Structural subtyping (NOT `@runtime_checkable`).

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

(Previously: 3 methods — `upsert_jobs`, `search_jobs`, `close`)

**Scenario: Protocol satisfies mypy --strict**

- GIVEN `SqliteJobRepository` implementing all 5 methods
- WHEN mypy --strict checks conformance
- THEN no type error is reported

**Scenario: Protocol rejects missing method**

- GIVEN a class missing `delete_older_than`
- WHEN mypy --strict checks the assignment
- THEN a type error is reported

---

## Out of Scope

- Separate cleanup task/worker (retention inline only)
- Scheduled reports, exports, or notifications
- Prometheus or OpenTelemetry metrics
- Authentication/authorization on history or status endpoints
- Schema migrations (all required columns already exist)
- Full-text search or fuzzy matching on history queries
