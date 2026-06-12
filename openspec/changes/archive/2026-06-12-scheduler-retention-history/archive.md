# Archive Report: `scheduler-retention-history`

## Status: CLOSED

**Archived on**: 2026-06-12
**Change**: TTL-based retention + scheduler status endpoint + historical jobs endpoint
**Delivery**: Single PR — 11 requirements, 19 scenarios, 15 tasks, 79 tests
**Verify verdict**: PASS (0 CRITICAL, 0 WARNING, 1 SUGGESTION)

---

## Traceability

| Artifact | Source | Location |
|----------|--------|----------|
| Proposal | `openspec/changes/archive/2026-06-12-scheduler-retention-history/proposal.md` | This archive |
| Spec | `openspec/changes/archive/2026-06-12-scheduler-retention-history/spec.md` | This archive |
| Design | `openspec/changes/archive/2026-06-12-scheduler-retention-history/design.md` | This archive |
| Tasks | `openspec/changes/archive/2026-06-12-scheduler-retention-history/tasks.md` | This archive |
| Archive | `openspec/changes/archive/2026-06-12-scheduler-retention-history/archive.md` | This file |

---

## Capability Promotion Summary

Three new capabilities were promoted to the global specs:

| Capability | Requirements | Promoted To |
|------------|-------------|-------------|
| `scheduler-cleanup` | REQ-RET-001, REQ-RET-002 | `openspec/specs/background-scheduler/spec.md` |
| `scheduler-status` | REQ-STATUS-001, REQ-STATUS-002 | `openspec/specs/background-scheduler/spec.md` |
| `job-history` | REQ-HIST-001, REQ-HIST-002 | `openspec/specs/job-repository/spec.md` |

Two existing capabilities were modified:

| Capability | Modifications | Promoted To |
|------------|--------------|-------------|
| `background-scheduler` | REQ-SCH-001 (+retention_days param), REQ-SCH-005 (+retention call), REQ-CFG-001 (+retention_days field), REQ-ROOT-001 (DB_PATH independence) | `openspec/specs/background-scheduler/spec.md` |
| `job-repository` | REQ-DB-001 (+3 new Protocol methods: delete_older_than, search_jobs_history, count_jobs) | `openspec/specs/job-repository/spec.md` |

**Scenarios promoted**: 24 total in `background-scheduler` spec (+13), 12 total in `job-repository` spec (+5)

---

## Files Created (6)

| File | Purpose |
|------|---------|
| `backend/src/jobs_finder/presentation/routes/scheduler_status.py` | `GET /scheduler/status` endpoint |
| `backend/src/jobs_finder/presentation/routes/history.py` | `GET /jobs/history` endpoint |
| `backend/tests/integration/test_scheduler_status_api.py` | E2E tests for scheduler status |
| `backend/tests/integration/test_history_api.py` | E2E tests for history endpoint |
| (tests) | 79 tests specific to this change, all passing |

## Files Modified (11)

| File | Change |
|------|--------|
| `backend/src/jobs_finder/application/ports.py` | +3 new Protocol methods |
| `backend/src/jobs_finder/infrastructure/config.py` | +`retention_days` field |
| `backend/src/jobs_finder/infrastructure/scheduler.py` | `SchedulerState`, retention, state tracking |
| `backend/src/jobs_finder/infrastructure/persistence/sqlite_job_repository.py` | +3 new repo methods |
| `backend/src/jobs_finder/presentation/app_factory.py` | DB path independence |
| `backend/src/jobs_finder/presentation/schemas.py` | +4 new Pydantic models |
| `backend/.env.example` | +RETENTION_DAYS |
| `backend/README.md` | +3 new docs sections |
| 5 test files | +79 new tests |

## Git History

- `be92bfb` — feat(scheduler): TTL-based retention + scheduler status + history
- `7e82d91` — chore(tests): 79 tests for scheduler-retention-history change

---

## Known Gaps

| Severity | ID | Description |
|----------|----|-------------|
| SUGGESTION | G-001 | `_to_history_response` uses duck typing to adapt `Job` domain objects to `JobResponse` schema. Consider adding an explicit `.to_history_response()` method on the `Job` value object for stronger typing. Cosmetic — no functional impact. |

---

## Next Recommended Changes

1. **Observability**: Add Prometheus metrics for retention deletions (`total_deleted`, `retention_cycle_duration`)
2. **API pagination cursor**: Replace `offset` with cursor-based pagination on `GET /jobs/history` for consistent results under concurrent writes
3. **Retention policy config per source**: Allow different TTL values per job source (e.g., LinkedIn: 30d, Indeed: 14d)
