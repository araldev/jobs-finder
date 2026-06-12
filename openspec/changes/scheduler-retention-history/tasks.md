# Tasks: Scheduler Retention + History

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~550 (13 files: 8 production + 5 test) |
| 5000-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR (features share scheduler.py + ports.py) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

```
Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low
```

## Phase 1: Retention — Protocol + Repo (TDD)

- [ ] 1.1 **RED**: Write `test_retention_settings.py` — assert `retention_days` defaults `0`, reads `RETENTION_DAYS=30`. **GREEN**: Add field to `Settings` in `config.py` with `AliasChoices("RETENTION_DAYS", "retention_days")`
- [ ] 1.2 **RED**: Write tests for `delete_older_than` in `test_sqlite_job_repository.py` — insert rows with varying `last_seen_at`, assert deleted count, LIMIT cap, zero-delete for fresh rows. **GREEN**: Add `delete_older_than(*, days, limit=1000) -> int` to `JobRepositoryPort` in `ports.py` + implement in `SqliteJobRepository` with `DELETE WHERE last_seen_at < datetime('now', ? || ' days') LIMIT ?`
- [ ] 1.3 **GREEN**: Update `FakeJobRepository` in `test_scheduler.py` with `delete_older_than` spy (tracks call count + args). Verify protocol conformance: `repo: JobRepositoryPort = FakeJobRepository()` passes mypy

## Phase 2: Retention — Scheduler + Wiring (TDD)

- [ ] 2.1 **RED**: Extend `test_scheduler.py` — add `test_retention_called_after_upsert` (spy asserts call when `retention_days>0`) + `test_retention_skipped_when_zero` (assert no call). **GREEN**: Add `retention_days` param to `BackgroundJobScheduler.__init__`, call `self._repo.delete_older_than(days=..., limit=1000)` in `_loop()` after upsert when `> 0`
- [ ] 2.2 **RED**: Write one-shot scheduler cycle test — assert `repo.upsert_jobs` called before `delete_older_than`. **GREEN**: Verify lock-held ordering in `_loop()`
- [ ] 2.3 **RED**: Integration test — `build_app` with `RETENTION_DAYS=30`, exercise lifespan, assert scheduler constructed with retention. **GREEN**: Wire `retention_days=effective_settings.retention_days` through `app_factory` scheduler construction

## Phase 3: Scheduler Status (TDD)

- [x] 3.1 **RED**: Add `test_scheduler_state_tracks_cycle` — start scheduler, run one cycle, assert `cycle_count==1`, `last_run_end` set, `last_error` is None, `running` is false after cycle. **GREEN**: Add `SchedulerState` dataclass to `scheduler.py` with fields: `running`, `last_run_start`, `last_run_end`, `last_error`, `cycle_count`, `total_jobs_collected`. Static/config fields (`enabled`, `queries`, `min_interval_seconds`, `max_interval_seconds`) and DB stats (`total_in_db`, `per_source`) live in `SchedulerStatusResponse` schema. Instrument `_loop()` to update fields at cycle entry/exit/error
- [x] 3.2 **RED**: Integration test `test_scheduler_status_api.py` — `GET /scheduler/status` returns 200 with all state fields when scheduler exists, returns `{"enabled": false}` when scheduler is None (disabled). **GREEN**: Create `routes/scheduler_status.py` with `GET /scheduler/status` reading `app.state.scheduler`. Add `SchedulerStatusResponse(BaseModel)` to `schemas.py`. Expose `app.state.scheduler` in `app_factory` lifespan

## Phase 4: Historical Jobs — Repo (TDD)

- [x] 4.1 **RED**→**GREEN**: Tests written first (11 tests covering empty, all, source filter, multi-source filter, keyword title, keyword company, date range, pagination, count empty, count total, count filtered). Implemented `search_jobs_history` + `count_jobs` on `JobRepositoryPort` Protocol + `SqliteJobRepository`. Refactored: extracted `_build_history_clauses` helper.
- [x] 4.2 **GREEN**: Updated `FakeJobRepository` with `search_jobs_history` + `count_jobs` stubs. All 47 tests pass. MyPy --strict clean. Ruff format clean.

## Phase 5: Historical Jobs — Route + Wiring (TDD)

- [x] 5.1 **RED**: Integration test `test_history_api.py` — `GET /jobs/history` with source/keywords/date filters returns 200 + `{"items": [...], "total": N}`. **GREEN**: Create `routes/history.py` with query params `sources`, `keywords`, `date_from`, `date_to`, `limit` (default 50, max 200), `offset` (default 0). Add `HistoryJobQuery(BaseModel)` + `HistoryJobResponse(items: list[JobResponse], total: int)` to `schemas.py`
- [x] 5.2 **RED**: Integration test — history works when `SCHEDULER_ENABLED=false` but `DB_PATH` is set. **GREEN**: Refactor `app_factory` lifespan — build `SqliteJobRepository` when `db_path` non-empty (NOT gated by `scheduler_enabled`), expose `app.state.job_repository`. Build scheduler ONLY when `scheduler_enabled`. Register `history.router` always. Update `test_scheduler_wiring.py` assertions
- [x] 5.3 **GREEN**: Register both new routers in `app_factory`. `history.router` always; `scheduler_status.router` always (graceful degradation when scheduler is None). Run `mypy --strict`, `ruff check`, `ruff format --check`, full `pytest` suite

## Phase 6: Cleanup + Verification

- [x] 6.1 Update backend `README.md` — document `RETENTION_DAYS`, `GET /scheduler/status`, `GET /jobs/history`
- [x] 6.2 Run full check suite: `uv run mypy && uv run ruff check && uv run ruff format --check && uv run pytest`

## Implementation Order

Phase 1 → 2 → 3 → 4 → 5 → 6. Each phase is additive and independently verifiable. Phase 1+2 (retention) must land before Phase 3 (status touches same scheduler file). Phase 4+5 (history) is independent of scheduler state changes but shares ports.py with Phase 1. All three features merge as a single PR since they share `ports.py`, `scheduler.py`, and `app_factory.py`.

## Summary

| Phase | Tasks | Focus |
|-------|-------|-------|
| 1 | 3 | Protocol + config + repo impl (retention) |
| 2 | 3 | Scheduler retention + app_factory wiring |
| 3 | 2 | SchedulerState + status endpoint |
| 4 | 2 | search_jobs_history + count_jobs repo impl |
| 5 | 3 | History route + DB_PATH wiring |
| 6 | 2 | Docs + final verification |
| **Total** | **15** | |

### Next Step

Ready for implementation (sdd-apply). Since `400-line budget risk: Low` and `review_budget_lines: 5000`, no chained PRs are recommended. Proceed with single PR implementation.
