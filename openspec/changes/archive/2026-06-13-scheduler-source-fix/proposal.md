# Proposal: `scheduler-source-fix`

## Intent

Fix three production bugs in the scheduler pipeline: (1) `IntegrityError` on every scheduler cycle because `source="aggregator"` violates the DB `CHECK` constraint — the source must travel with each `Job`, not be passed as a separate parameter; (2) scrapers are searching with keywords when location-only Spain queries are desired; (3) the scheduler runs around the clock when it should only run during Madrid business hours.

## Scope

### In Scope
- Add `source: str` field to the `Job` frozen dataclass (`domain/job.py`)
- Update each scraper (`linkedin`, `indeed`, `infojobs`) to set `source=<source_name>` when constructing `Job`
- Remove `source` parameter from `JobRepositoryPort.upsert_jobs` — source travels with each `Job`
- Update `SqliteJobRepository.upsert_jobs` implementation and SQL accordingly
- Change `SCHEDULER_QUERIES` default to empty-keyword Spain locations in `config.py` and `.env.example`
- Add Madrid work-hours gate in `scheduler.py` (22:00 stop, 09:00 start via `zoneinfo.ZoneInfo("Europe/Madrid")`)

### Out of Scope
- Adding new job sources
- Changing the cache key schema
- Modifying the `JobSearchPort` Protocol signature

## Capabilities

### New Capabilities
None — pure bugfix and refactor.

### Modified Capabilities
- `background-scheduler`: Work-hours gate (09:00–22:00 Madrid time) added to the scheduler loop; `SCHEDULER_QUERIES` default changes to location-only Spain queries.
- `job-repository`: `upsert_jobs` signature changes — `source` parameter removed; `Job` now carries `source` directly.
- `linkedin-scraper` / `infojobs-scraper` / `indeed-scraper` (delta specs): Each scraper sets `source` on `Job` construction.

## Approach

**Change 1 — source in Job**: Add `source: str` field to `Job` as a required positional arg (before existing fields to preserve `description=None` default). Each scraper's `_parse_cards` closure sets `source=<source_name>` at construction. Remove `source: str` from `JobRepositoryPort.upsert_jobs` signature; the repository reads `job.source` directly. Update `SqliteJobRepository` SQL to use `excluded.source` in the `ON CONFLICT` clause.

**Change 2 — empty keywords**: Update `SCHEDULER_QUERIES` default in `infrastructure/config.py` to `[{"keywords": "", "location": "España"}, ...]`. Update `.env.example` to reflect the new shape.

**Change 3 — work-hours gate**: In `BackgroundJobScheduler._loop`, before each cycle check `datetime.now(ZoneInfo("Europe/Madrid")).hour`. If outside 09–22, `await asyncio.sleep(300)` and re-check. Uses Python 3.9+ `zoneinfo` (already available).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `domain/job.py` | Modified | Add `source: str` field to `Job` dataclass |
| `application/ports.py` | Modified | Remove `source` from `JobRepositoryPort.upsert_jobs` |
| `infrastructure/persistence/sqlite_job_repository.py` | Modified | Read `job.source`; update upsert SQL |
| `infrastructure/scheduler.py` | Modified | Add Madrid work-hours gate before each cycle |
| `infrastructure/config.py` | Modified | `SCHEDULER_QUERIES` default → empty keywords |
| `backend/.env.example` | Modified | `SCHEDULER_QUERIES` shape |
| `infrastructure/linkedin/scraper.py` | Modified | Set `source="linkedin"` on `Job(...)` |
| `infrastructure/indeed/scraper.py` | Modified | Set `source="indeed"` on `Job(...)` |
| `infrastructure/infojobs/scraper.py` | Modified | Set `source="infojobs"` on `Job(...)` |
| `tests/` | Modified | Update scraper unit tests and repository tests |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `Job` field ordering breaks `description=None` default | Low | Add `source` as first positional arg before existing fields |
| Existing tests pass `source` to `upsert_jobs` | High | Update all call sites in tests and `scheduler.py` |
| `ZoneInfo` import fails on Python < 3.9 | Low | Project requires Python 3.12 per `AGENTS.md` — not an issue |

## Rollback Plan

1. Revert `Job` dataclass: remove `source` field
2. Restore `source: str` parameter on `JobRepositoryPort.upsert_jobs` and `SqliteJobRepository.upsert_jobs`
3. Restore previous `SCHEDULER_QUERIES` default in `config.py`
4. Remove work-hours gate code from `scheduler.py`
5. Revert scrapers to not set `source`
6. All changes are isolated to ~10 files — full revert is straightforward

## Dependencies

- Python 3.9+ `zoneinfo` (built-in; project runs on 3.12)

## Success Criteria

- [ ] Scheduler cycle completes without `IntegrityError` (DB accepts `linkedin`/`indeed`/`infojobs` source values)
- [ ] `SCHEDULER_QUERIES` with empty keywords returns jobs for Spain locations
- [ ] Scheduler skips cycles outside Madrid 09:00–22:00
- [ ] All existing scraper tests pass with `source` field added to `Job`
- [ ] `uv run mypy --strict` passes across all changed files
- [ ] `uv run pytest` passes across all backend tests
