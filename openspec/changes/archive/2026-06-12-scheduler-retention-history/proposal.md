# Proposal: Scheduler Retention + History

## Intent

The scheduler persists jobs indefinitely with no observability or cleanup. This adds TTL-based retention, a scheduler status endpoint, and a historical jobs endpoint.

## Scope

### In Scope
- Retention: `repo.delete_older_than(cutoff)` inline in scheduler, opt-in via `RETENTION_DAYS`.
- Scheduler state: `SchedulerState` as `GET /scheduler/status`.
- History: `GET /jobs/history` with source/keywords/date-range/limit-offset + count.
- DB path: open repo on `DB_PATH` alone, not gated by `SCHEDULER_ENABLED`.

### Out of Scope
- Separate cleanup task (inline only). No scheduled reports/export. No Prometheus metrics.

## Capabilities

### New Capabilities
- `scheduler-cleanup`: TTL-based retention policy for the job repository.
- `scheduler-status`: HTTP endpoint exposing scheduler runtime state.
- `job-history`: HTTP endpoint for querying historical persisted jobs.

### Modified Capabilities
- `background-scheduler`: add retention call after upsert + `SchedulerState` tracking.
- `job-repository`: add `delete_older_than()` and `search_jobs_history()` to the Protocol.

## Approach

1. **Retention** — `delete_older_than(days, limit)` on `JobRepositoryPort`. Call after upsert when `retention_days > 0`. New env `RETENTION_DAYS` (default `0` = never).
2. **State** — `SchedulerState` dataclass, instrument `_loop()`, expose as `app.state.scheduler`. Route `GET /scheduler/status`.
3. **History** — `search_jobs_history()` on port. New `routes/history.py` with `GET /jobs/history`. Open repo on `DB_PATH` alone.
4. **Order**: 1 → 2 → 3. No migration needed.

## Affected Areas

| Area | Impact |
|------|--------|
| `application/ports.py` | 2 new methods on `JobRepositoryPort` |
| `infrastructure/persistence/*.py` | Implement both |
| `infrastructure/scheduler.py` | Retention + `SchedulerState` |
| `presentation/app_factory.py` | Open on DB_PATH, wire routes |
| `infrastructure/config.py` | +`RETENTION_DAYS` field |
| `presentation/routes/history.py` | New: `GET /jobs/history` |
| `presentation/routes/scheduler_status.py` | New: `GET /scheduler/status` |
| `tests/unit/test_scheduler.py` | State + retention |
| `tests/unit/test_sqlite_job_repository.py` | New method coverage |
| `tests/integration/test_history_api.py` | New E2E |
| `tests/integration/test_scheduler_status_api.py` | New E2E |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| DELETE blocks loop | Low | Inside lock but after upsert; LIMIT caps per-cycle |
| History broken when scheduler off | Low | Open on DB_PATH, not SCHEDULER_ENABLED |
| Schema migration needed | None | All columns exist in `jobs` table |

## Rollback Plan

1. Set `RETENTION_DAYS=0` (default) to disable cleanup.
2. Revert `history.py` and `scheduler_status.py` route files.
3. Revert `JobRepositoryPort` additions (old callers unaffected).
4. Revert `app_factory.py` wiring.

## Dependencies

- None. All required columns already exist in the `jobs` schema.

## Success Criteria

- [ ] `repo.delete_older_than(days=30)` removes only rows with `last_seen_at < cutoff`
- [ ] `SchedulerState` fields update correctly across cycles
- [ ] `GET /scheduler/status` returns 200 with JSON state
- [ ] `GET /jobs/history?sources=linkedin,indeed&date_from=...&limit=20` returns paginated results + total count
- [ ] History works when `SCHEDULER_ENABLED=false` but `DB_PATH` is set
- [ ] MyPy strict + all existing tests pass
