# Archive Report: `scheduler-source-fix`

**Status:** CLOSED
**Archived:** 2026-06-13
**Delivery:** Single PR — 5 commits on `main`

---

## Traceability

| Artifact | Path |
|----------|------|
| Proposal | `openspec/changes/archive/2026-06-13-scheduler-source-fix/proposal.md` |
| Spec (delta) | `openspec/changes/archive/2026-06-13-scheduler-source-fix/specs/` |
| Design | `openspec/changes/archive/2026-06-13-scheduler-source-fix/design.md` |
| Tasks | `openspec/changes/archive/2026-06-13-scheduler-source-fix/tasks.md` |
| Archive (this) | `openspec/changes/archive/2026-06-13-scheduler-source-fix/archive.md` |

---

## Capability Changes Summary

| Capability | Action | Details |
|------------|--------|---------|
| `job-domain` | **MODIFIED** | Added `source: str` field as first positional arg to `Job` frozen dataclass. Preserves `description=None` default. Scapers now set `source=<name>` at construction. |
| `job-repository` | **MODIFIED** | Removed `source` parameter from `JobRepositoryPort.upsert_jobs`. Each `Job` now carries `source`; SQL `ON CONFLICT` uses `excluded.source`. 4 scenarios (new insert, update, mixed-source grouping, TypeError on old call signature). |
| `background-scheduler` | **MODIFIED** | `SCHEDULER_QUERIES` default changed to 3 Spain locations with empty keywords. Added Madrid work-hours gate (`09:00–22:00`) via `ZoneInfo("Europe/Madrid")`; sleeps 300s outside window. 9 new scenarios added. |

### Git Commits

```
b857218 fix(Phase1): add source field to Job dataclass and update scrapers
fe7b81e fix(Phase2): remove source param from upsert_jobs and use job.source per-row
bffb2c4 fix(scheduler): phase 3 — empty-keyword Spain queries for scheduler
247399c fix(scheduler-source-fix): Phase 4 — Madrid work hours gate 09:00-22:00 + test fixes
8cc4a71 fix(tests): add source field to all Job() constructors across integration tests
```

### Verification Results

- **14** requirements verified PASS
- **88** scheduler-specific tests pass
- **1402** total tests pass
- `uv run mypy --strict` ✅
- `uv run ruff check` ✅
- `uv run ruff format --check` ✅

---

## Known Gaps / Next Recommended Changes

| # | Gap | Recommended Change |
|---|-----|-------------------|
| 1 | Scheduler cycle still uses `source="aggregator"` for the aggregator's own job | After Phase 1 fix, aggregator jobs should carry their own `source`; clarify aggregator role in `job-domain` spec |
| 2 | Madrid work-hours gate does not persist across process restarts | Consider a lightweight cron or external timer that restarts the scheduler process at 09:00 Madrid |
| 3 | No scheduler cycle jitter outside business hours (sleep is fixed 300s) | Could randomize the 300s sleep slightly to avoid thundering-herd on wake |
| 4 | `.env.example` documents but does not validate `SCHEDULER_QUERIES` JSON shape at startup | Add validation in `Settings` to reject malformed JSON with a clear error message |
| 5 | No integration test for full scheduler cycle with real DB (only unit tests) | Add `test_scheduler_integration.py` with real `aiosqlite` DB and mock scrapers |

---

## Rollback Plan (archived for reference)

1. Revert `Job` dataclass: remove `source` field
2. Restore `source: str` parameter on `JobRepositoryPort.upsert_jobs` and `SqliteJobRepository.upsert_jobs`
3. Restore previous `SCHEDULER_QUERIES` default in `config.py`
4. Remove work-hours gate code from `scheduler.py`
5. Revert scrapers to not set `source`
6. All changes isolated to ~10 files — full revert is straightforward
