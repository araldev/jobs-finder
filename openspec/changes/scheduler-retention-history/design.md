# Design: Scheduler Retention + History

## Technical Approach

Three independent features layered on the existing scheduler + repository: (1) TTL-based retention inline after each scheduler cycle, (2) `SchedulerState` exposed via `GET /scheduler/status`, (3) historical job query endpoint `GET /jobs/history` with pagination and filtering. The repository opens on `DB_PATH` alone (not gated by `SCHEDULER_ENABLED`), so history works even when the scheduler is off.

## Architecture Decisions

### Decision: Retention inline vs separate cleanup task

**Choice**: Inline — call `repo.delete_older_than()` after `repo.upsert_jobs()` inside the same `asyncio.Lock` acquisition.
**Alternatives**: Separate periodic task (more infra, higher isolation).
**Rationale**: Inline is simpler and the DELETE is bounded by `LIMIT 1000`. A long DELETE only blocks the next cycle (which is 25–35 min away). No extra infrastructure needed.

### Decision: Scheduler state polling vs push metrics

**Choice**: Polling via `GET /scheduler/status` returning a JSON representation of a `SchedulerState` dataclass.
**Alternatives**: Prometheus push metrics (adds dependency), SSE push (overengineered).
**Rationale**: The scheduler runs in the same process; state is synchronously accessible. A single dataclass updated at cycle boundaries is trivial to implement and test.

### Decision: History as separate protocol methods vs reuse `search_jobs`

**Choice**: New `search_jobs_history()` + `count_jobs()` on `JobRepositoryPort`.
**Alternatives**: Reuse `search_jobs()` with more optional params (signature bloat).
**Rationale**: Date-based filtering (`posted_at >= date_from AND posted_at <= date_to`) is semantically different from the live-search `search_jobs()`. Separate methods keep each contract narrow and make the `FakeJobRepository` in tests easier to implement (duck typing works per-method).

## Architecture Overview

```
app_factory.build_app()
  │
  ├── repo = SqliteJobRepository(db_path)    ← ALWAYS (not gated by SCHEDULER)
  │     │
  │     ├── app.state.job_repository = repo
  │     │
  │     └── lifespan: open repo → start scheduler (if enabled)
  │                      → serve → stop scheduler → close repo
  │
  ├── if scheduler_enabled:
  │     sched = BackgroundJobScheduler(repo, retention_days, ...)
  │     app.state.scheduler = sched
  │     sched.start()
  │
  └── Routes:
        ├── GET /scheduler/status  → app.state.scheduler (scheduler_status.py)
        └── GET /jobs/history      → app.state.job_repository (history.py)
```

## Data Flow

### Retention (inline in scheduler `_loop()`)
```
_loop() cycle:
  1. for each query: search_fn(kw, loc) → batch
  2. repo.upsert_jobs(all_jobs)   ← lock held
  3. if retention_days > 0:
       repo.delete_older_than(days=retention_days, limit=1000)
       → DELETE FROM jobs WHERE last_seen_at < date('now', '-N days') LIMIT 1000
  4. update SchedulerState fields
```

### History query
```
GET /jobs/history?sources=linkedin,indeed&date_from=2026-01-01&limit=20&offset=0
  │
  ├── repo.search_jobs_history(sources=["linkedin","indeed"], date_from="2026-01-01", limit=20)
  │     → SELECT ... WHERE source IN (?,?) AND posted_at >= ? ORDER BY posted_at DESC LIMIT ? OFFSET ?
  │
  └── repo.count_jobs(sources=["linkedin","indeed"], date_from="2026-01-01")
        → SELECT count(*) FROM jobs WHERE source IN (?,?) AND posted_at >= ?
```

## Component Design Per Feature

### Feature 1: Retention (REQ-RET-001, REQ-RET-002)

| File | Change |
|------|--------|
| `config.py` | Add `retention_days: int = 0`, alias `AliasChoices("RETENTION_DAYS", "retention_days")` |
| `ports.py` | Add `delete_older_than(*, days: int, limit: int = 1000) -> int` to `JobRepositoryPort` |
| `sqlite_job_repository.py` | SQL: `DELETE FROM jobs WHERE last_seen_at < datetime('now', ? || ' days') LIMIT ?` |
| `scheduler.py` | Accept `retention_days` param. In `_loop()` after upsert, call `delete_older_than` if > 0 |
| `app_factory.py` | Forward `retention_days` from settings to scheduler |

### Feature 2: Scheduler Status (REQ-STATUS-001, REQ-STATUS-002)

| File | Change |
|------|--------|
| `scheduler.py` | Add `SchedulerState` dataclass. Instrument `_loop()` to update fields at entry/exit/error |
| `app_factory.py` | Expose `app.state.scheduler = _scheduler_instance` (may be `None`) |
| `routes/scheduler_status.py` | **New**: `GET /scheduler/status` reads `app.state.scheduler`, returns JSON state |
| `schemas.py` | **New**: `SchedulerStatusResponse(BaseModel)` |

`SchedulerState` fields: `enabled`, `running`, `last_run_start`, `last_run_end`, `last_error: str | None`, `cycle_count`, `total_jobs_collected`, `total_in_db`, `total_per_source`, `queries`, `min_interval_seconds`, `max_interval_seconds`. Updated at each cycle boundary.

### Feature 3: Historical Jobs (REQ-HIST-001, REQ-HIST-002)

| File | Change |
|------|--------|
| `ports.py` | Add `search_jobs_history()` + `count_jobs()` to `JobRepositoryPort` |
| `sqlite_job_repository.py` | Implement both with `posted_at` range, source IN, keyword LIKE filters |
| `routes/history.py` | **New**: `GET /jobs/history` with query params, returns `{"items": [...], "total": N}` |
| `schemas.py` | **New**: `HistoryJobQuery(BaseModel)`, `HistoryJobResponse(items: list[JobResponse], total: int)` |

### Cross-cutting: DB Path Independence (REQ-SCH-ROOT-001)

- `app_factory.py`: Build `SqliteJobRepository(db_path=settings.db_path)` when `db_path` is non-empty, regardless of `scheduler_enabled`. Open in lifespan. Build + start scheduler only when `scheduler_enabled`. Stop + close only if scheduler was built.

## Interface Contracts

### JobRepositoryPort additions (keyword-only params)
```python
async def delete_older_than(self, *, days: int, limit: int = 1000) -> int: ...
async def search_jobs_history(self, *, sources=None, keywords=None,
    date_from=None, date_to=None, limit=50, offset=0) -> list[Job]: ...
async def count_jobs(self, *, sources=None, keywords=None,
    date_from=None, date_to=None) -> int: ...
```

### API contracts
- `GET /scheduler/status` → `200` with `SchedulerState` JSON; graceful `{"enabled": false}` when scheduler is `None`
- `GET /jobs/history?sources=&keywords=&date_from=&date_to=&limit=&offset=` → `200: {"items": [JobResponse], "total": int}`

## Test Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | `delete_older_than` | In-memory SQLite, insert rows with varying `last_seen_at`, assert deleted count |
| Unit | `search_jobs_history` + `count_jobs` | In-memory, vary source/keyword/date filters |
| Unit | Scheduler calls retention | `FakeJobRepository` with `delete_older_than` spy, assert call after upsert |
| Unit | Retention skipped when 0 | Same spy — assert NO call when `retention_days=0` |
| Unit | SchedulerState tracking | Assert state fields after one `_loop()` cycle |
| Unit | Protocol conformance | `repo: JobRepositoryPort = SqliteJobRepository(...)` assignment check |
| Integration | `GET /scheduler/status` | Test app with scheduler, assert JSON shape. Test without, assert `{"enabled": false}` |
| Integration | `GET /jobs/history` | In-memory DB, insert fixtures, query with filters, assert items + total shape |
| Integration | History without scheduler | `build_app(scheduler_enabled=False, db_path=":memory:")`, assert history returns 200 |

## Migration / Rollout

No migration required. All columns (`last_seen_at`, `posted_at`, `source`, `source_id`) already exist. Retention is opt-in (`RETENTION_DAYS=0` default = off). Rollback: set `RETENTION_DAYS=0`, revert route/task files.

## Open Questions

None. All requirements are well-specified.
