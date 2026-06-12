# Spec: `background-scheduler` — periodic asyncio background scraper

> **PROMOTED to source of truth on 2026-06-12** from
> `openspec/changes/background-scheduler-persistence/spec.md`
> §"Capability: `background-scheduler`". This is a NEW foundational
> capability spec — no prior `openspec/specs/background-scheduler/spec.md`
> existed. The delta is promoted in full as the foundational spec for
> the capability, capturing the `BackgroundJobScheduler` class, its
> random-interval loop, lock-prevention, graceful lifecycle, and
> multi-query iteration. Source observation IDs for traceability:
> explore #405, proposal (see preflight #404), spec #406, design #407,
> tasks (see apply #409), verify-report #410.

## Purpose

The `background-scheduler` capability is an **asyncio background task**
that periodically scrapes all 3 configured sources at pseudo-random
intervals and persists the results to a job repository. It is
OPT-IN (`SCHEDULER_ENABLED=false` by default) — when disabled, there
is zero behavioral change from the existing on-demand HTTP scraping.

## Requirements

### REQ-SCH-001: Scheduler class

The system MUST define `BackgroundJobScheduler` in
`infrastructure/scheduler.py`. Constructor accepts:

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

#### Scenario: Constructor stores parameters

- GIVEN a `BackgroundJobScheduler(search_fn=..., repo=...,
  queries=[{"keywords": "python", "location": "Madrid"}])`
- WHEN the instance is constructed
- THEN all parameters are stored and no side effects occur

#### Scenario: Constructor accepts retention_days

- GIVEN `BackgroundJobScheduler(search_fn=..., repo=..., queries=[{"keywords": "python", "location": "Madrid"}], retention_days=30)`
- WHEN the instance is constructed
- THEN `retention_days=30` is stored and no side effects occur

### REQ-SCH-002: Random interval

The system MUST sleep `random.uniform(min_interval, max_interval)`
seconds between cycles. Default range 1500–2100s (25–35 min).

#### Scenario: Random delay observed

- GIVEN a scheduler with `min_interval=1.0, max_interval=2.0`
- WHEN a cycle completes
- THEN the next cycle begins after a random delay in `[1.0, 2.0)` seconds

### REQ-SCH-003: No overlapping runs

The system MUST use `asyncio.Lock` to prevent concurrent executions.
If a run is in progress when the next is scheduled, the overlapping
run MUST be skipped with a WARNING log.

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

### REQ-SCH-005: Search queries with retention

Each cycle iterates over `self._queries`. For each query, calls
`search_fn(keywords, location)`. After ALL queries, calls
`repo.upsert_jobs(...)`. After upsert, if `retention_days > 0`,
calls `repo.delete_older_than(days=retention_days, limit=1000)`.

#### Scenario: Multiple queries per cycle

- GIVEN `queries=[{"keywords": "python", "location": "Madrid"},
  {"keywords": "java", "location": "Barcelona"}]`
- WHEN one cycle runs
- THEN `search_fn` is called twice (once per query)
- AND `repo.upsert_jobs` is called once with all results
- AND if `retention_days > 0`, `repo.delete_older_than` is called after upsert

#### Scenario: Search result persists to repo

- GIVEN `queries=[{"keywords": "python", "location": "Madrid"}]`
- WHEN a cycle completes
- THEN `repo.upsert_jobs` is called with the jobs returned by `search_fn`

#### Scenario: Retention deletes old jobs per cycle

- GIVEN a scheduler with `retention_days=30` and jobs with `last_seen_at < now - 30d` in the DB
- WHEN a cycle completes upsert
- THEN `delete_older_than(30, 1000)` is called
- AND rows older than 30 days are deleted

#### Scenario: Retention is skipped when days=0

- GIVEN a scheduler with `retention_days=0`
- WHEN a cycle completes upsert
- THEN `delete_older_than` is NOT called

### REQ-CFG-001 (scheduler fields): Scheduler configuration

The system MUST add 5 fields to `Settings` in
`infrastructure/config.py`:

| Field | Env var | Type | Default |
|-------|---------|------|---------|
| `scheduler_enabled` | `SCHEDULER_ENABLED` / `scheduler_enabled` | `bool` | `False` |
| `scheduler_min_interval_seconds` | `SCHEDULER_MIN_INTERVAL_SECONDS` / `scheduler_min_interval_seconds` | `float` | `1500.0` |
| `scheduler_max_interval_seconds` | `SCHEDULER_MAX_INTERVAL_SECONDS` / `scheduler_max_interval_seconds` | `float` | `2100.0` |
| `scheduler_queries` | `SCHEDULER_QUERIES` / `scheduler_queries` | `list[dict[str, str]]` | `[{"keywords": "desarrollador", "location": "España"}]` |
| `retention_days` | `RETENTION_DAYS` / `retention_days` | `int` | `0` |

The `scheduler_queries` field MUST parse from a JSON env var (same
pattern as `RATE_LIMIT_EXEMPT_PATHS`), using a `mode="before"`
validator.

#### Scenario: JSON env var parsing

- GIVEN `SCHEDULER_QUERIES='[{"keywords":"python","location":"Madrid"}]'`
- WHEN `Settings()` is constructed
- THEN `scheduler_queries` equals `[{"keywords": "python", "location": "Madrid"}]`

#### Scenario: Retention config defaults to 0 (disabled)

- GIVEN no `RETENTION_DAYS` env var
- WHEN `Settings()` is constructed
- THEN `retention_days` equals `0`

#### Scenario: Non-zero enables retention

- GIVEN `RETENTION_DAYS=30`
- WHEN `Settings()` is constructed
- THEN `retention_days` equals `30`

### REQ-ROOT-001: Lifespan wiring

The system MUST wire the repository based on `DB_PATH`, not
`SCHEDULER_ENABLED`. The order:

1. Build `SqliteJobRepository(db_path=settings.db_path)` when `DB_PATH` is non-empty
2. Open it (`__aenter__`) in the lifespan
3. If `settings.scheduler_enabled`: build `BackgroundJobScheduler(...)` with `retention_days` from settings
4. Call `scheduler.start()` if enabled
5. Call `scheduler.stop()` if enabled
6. Close the repository at shutdown end

#### Scenario: Scheduler enabled wires fully

- GIVEN `settings.scheduler_enabled=True, settings.db_path="jobs.db"`
- WHEN `build_app()` constructs the app
- THEN the repository is built and opened
- AND the scheduler is started
- AND at shutdown, scheduler stops then repo closes

#### Scenario: Repo opens even when scheduler disabled

- GIVEN `settings.scheduler_enabled=False, settings.db_path="jobs.db"`
- WHEN `build_app()` constructs the app
- THEN the repository is built and opened in lifespan
- AND no scheduler is started
- AND at shutdown, the repo closes

### REQ-ROOT-002: Dependency

Add `aiosqlite>=0.20,<1.0` to `[project.dependencies]` in
`pyproject.toml`.

### REQ-ROOT-003: .env.example

Add the 4 scheduler env vars + `DB_PATH` to `backend/.env.example`
with sensible defaults and comments.

## New Capabilities

### REQ-RET-001: Retention config

The system MUST define `RETENTION_DAYS` on `Settings` as `int` with
default `0`. Uses `AliasChoices("RETENTION_DAYS", "retention_days")`.
When `0`, retention MUST NOT execute. The DELETE MUST cap at a
`LIMIT 1000` to bound transaction duration.

**Scenario: Config defaults to 0 (disabled)**

- GIVEN no `RETENTION_DAYS` env var
- WHEN `Settings()` is constructed
- THEN `retention_days` equals `0`

**Scenario: Non-zero enables retention**

- GIVEN `RETENTION_DAYS=30`
- WHEN `Settings()` is constructed
- THEN `retention_days` equals `30`

### REQ-RET-002: Retention runs inline after upsert

The system MUST call `repo.delete_older_than(days=retention_days,
limit=1000)` after `repo.upsert_jobs()` in the scheduler loop, inside
the same lock acquisition, when `retention_days > 0`.

**Scenario: Retention deletes old jobs per cycle**

- GIVEN a scheduler with `retention_days=30` and jobs with `last_seen_at < now - 30d` in the DB
- WHEN a cycle completes upsert
- THEN `delete_older_than(30, 1000)` is called
- AND rows older than 30 days are deleted

**Scenario: Retention is skipped when days=0**

- GIVEN a scheduler with `retention_days=0`
- WHEN a cycle completes upsert
- THEN `delete_older_than` is NOT called

### REQ-STATUS-001: SchedulerState dataclass

The system MUST define `SchedulerState` as a dataclass on
`BackgroundJobScheduler` tracking: `enabled`, `running`,
`last_run_start`, `last_run_end`, `last_error`, `cycle_count`,
`total_jobs_collected`, `total_in_db`, `total_per_source`,
`queries`, `min_interval_seconds`, `max_interval_seconds`.
Fields update at each cycle boundary.

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

### REQ-STATUS-002: GET /scheduler/status

The system MUST expose `GET /scheduler/status` returning JSON of the
`SchedulerState`. Returns `200` with full state when scheduler exists.
Graceful degradation when no scheduler or repo unavailable (returns
`{"enabled": false}`).

**Scenario: Status returns scheduler state**

- GIVEN a running scheduler
- WHEN `GET /scheduler/status`
- THEN response is `200` with JSON containing `enabled: true`, `cycle_count`, and all state fields

**Scenario: Degrades gracefully when disabled**

- GIVEN no scheduler (`SCHEDULER_ENABLED=false`)
- WHEN `GET /scheduler/status`
- THEN response is `200` with `{"enabled": false}`

## Scenarios summary

| REQ | Scenarios | Count |
|-----|-----------|-------|
| REQ-SCH-001 | Constructor stores params, accepts retention_days | 2 |
| REQ-SCH-002 | Random interval | 1 |
| REQ-SCH-003 | Lock prevents overlap, sequential runs | 2 |
| REQ-SCH-004 | Start creates task, stop cancels gracefully | 2 |
| REQ-SCH-005 | Multiple queries, result persists, retention deletes, retention skipped | 4 |
| REQ-CFG-001 (scheduler) | JSON env var parsing, retention defaults 0, non-zero enables | 3 |
| REQ-ROOT-001 | Scheduler enabled wires fully, repo opens even when disabled | 2 |
| REQ-RET-001 | Retention config defaults 0, non-zero enables | 2 |
| REQ-RET-002 | Retention deletes per cycle, retention skipped when 0 | 2 |
| REQ-STATUS-001 | State reflects idle scheduler, state updates after cycle | 2 |
| REQ-STATUS-002 | Status returns scheduler state, degrades gracefully when disabled | 2 |
| **Total** | | **24** |
