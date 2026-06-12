# Design: `scheduler-source-fix`

## Technical Approach

Three independent bugfixes sharing the same PR:
1. **Change 1 — `source` in `Job`**: Eliminate the `IntegrityError` by making `source` a first-class field of `Job`. Scraper closures set `source=<name>` at construction; `upsert_jobs` reads it from each `Job` instead of a separate parameter. The DB CHECK constraint `CHECK(source IN ('linkedin','indeed','infojobs'))` is satisfied per-row.
2. **Change 2 — empty keywords**: Update `SCHEDULER_QUERIES` default in `config.py` and `.env.example` to use `""` keywords with 3 Spain locations.
3. **Change 3 — work-hours gate**: Guard the scheduler loop with a Madrid-time check (09:00–22:00) using `zoneinfo.ZoneInfo("Europe/Madrid")`.

## Architecture Decisions

### Decision: `source` as a positional field before `description`

**Choice**: Add `source: str` as the **first** positional argument of the `Job` dataclass.
**Alternatives considered**: Add it as the last field, or as `source: str = "aggregator"` default.
**Rationale**: `description: str | None = None` has a default; adding a required field after a field with a default is a Python syntax error. Adding `source` at the start keeps the existing default intact and preserves all call sites that pass `description=None` positionally. Using a default of `"aggregator"` would be wrong — the whole point is that scrapers set the real source name.

### Decision: `source` removed from `JobRepositoryPort.upsert_jobs` entirely

**Choice**: Remove the `source: str` parameter; `Job` carries its own source.
**Alternatives considered**: Keep `source` as an optional parameter with a default; pass `job.source` at every call site.
**Rationale**: The protocol should not accept a `source` that contradicts the `Job` objects being passed. Removing it is cleaner and makes the interface match the DB schema (where `source` lives on the row, not on a separate param).

### Decision: Work-hours gate uses a pre-lock while loop

**Choice**: Before acquiring the scheduler lock, check Madrid hour; if outside 09–22, sleep 300s and re-check.
**Alternatives considered**: Check inside the lock; check once at startup.
**Rationale**: Checking inside the lock would block the lock unnecessarily. Checking once at startup would let a scheduler started at 23:00 run immediately. The pre-lock loop with 300s sleep is correct: the scheduler is effectively paused outside business hours without holding any resources.

## Data Flow

```
Scheduler._loop()
  ├── is_within_active_hours()  ← ZoneInfo("Europe/Madrid"), hour ∈ [9, 22)
  │       └── False → sleep(300), re-check
  └── lock.acquire()
        ├── for query in queries:
        │     search_fn(keywords, location) → list[Job]  (each Job.source = "<source>")
        └── repo.upsert_jobs(jobs=list[Job])  ← NO source param
              └── INSERT INTO jobs (source, ...) VALUES (job.source, ...)
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/jobs_finder/domain/job.py` | Modify | Add `source: str` as first positional field before `description` |
| `src/jobs_finder/application/ports.py` | Modify | Remove `source: str` from `JobRepositoryPort.upsert_jobs` signature |
| `src/jobs_finder/infrastructure/persistence/sqlite_job_repository.py` | Modify | Remove `source` param from `upsert_jobs`; read `job.source` in loop; update `_UPSERT_SQL` to use `excluded.source`; update `_row_to_job` to reconstruct `source` |
| `src/jobs_finder/infrastructure/scheduler.py` | Modify | Remove `source="aggregator"` from `upsert_jobs` call; add `ZoneInfo` import; add `_is_within_active_hours()` helper; add pre-lock while gate |
| `src/jobs_finder/infrastructure/config.py` | Modify | `scheduler_queries` default → `[{"keywords": "", "location": "Madrid"}, {"keywords": "", "location": "Barcelona"}, {"keywords": "", "location": "España"}]` |
| `backend/.env.example` | Modify | Update `SCHEDULER_QUERIES` example to use empty keywords + 3 Spain locations |
| `src/jobs_finder/infrastructure/linkedin/scraper.py` | Modify | Add `source="linkedin"` to `Job(...)` in `_parse_cards` |
| `src/jobs_finder/infrastructure/indeed/scraper.py` | Modify | Add `source="indeed"` to `Job(...)` in `_parse_cards` |
| `src/jobs_finder/infrastructure/infojobs/scraper.py` | Modify | Add `source="infojobs"` to `Job(...)` in `_parse_cards` |
| `tests/unit/test_scheduler.py` | Modify | Remove `source="aggregator"` from `upsert_jobs` mock assertions; add work-hours test |
| `tests/unit/test_linkedin_scraper.py` | Modify | Update `Job(...)` assertions to include `source="linkedin"` |
| `tests/unit/test_indeed_scraper.py` | Modify | Update `Job(...)` assertions to include `source="indeed"` |
| `tests/unit/test_infojobs_scraper.py` | Modify | Update `Job(...)` assertions to include `source="infojobs"` |
| `tests/unit/test_sqlite_job_repository.py` | Modify | Update `upsert_jobs` calls to remove `source` param; update `_row_to_job` assertions |

## Interfaces / Contracts

### `Job` dataclass (domain/job.py)

```python
@dataclass(frozen=True, slots=True)
class Job:
    id: str
    title: str
    company: str
    location: str
    url: str
    posted_at: datetime
    source: str                           # NEW — required, no default
    description: str | None = None
```

### `JobRepositoryPort.upsert_jobs` (application/ports.py)

```python
# BEFORE
async def upsert_jobs(self, jobs: list[Job], source: str, query_snapshot: dict[str, str]) -> int: ...

# AFTER
async def upsert_jobs(self, jobs: list[Job], query_snapshot: dict[str, str]) -> int: ...
```

### `BackgroundJobScheduler._is_within_active_hours` (infrastructure/scheduler.py)

```python
from zoneinfo import ZoneInfo

def _is_within_active_hours() -> bool:
    """Return True when Madrid local hour is between 09:00 and 22:00 inclusive."""
    madrid_now = datetime.now(ZoneInfo("Europe/Madrid"))
    return 9 <= madrid_now.hour < 22
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `Job.source` field exists and propagates | Parametrized test: construct `Job(source="linkedin", ...)`; verify `job.source == "linkedin"` |
| Unit | `_is_within_active_hours` boundary cases | Mock `datetime.now` at hour 8, 9, 21, 22, 23 |
| Unit | Scheduler skips cycles outside hours | Mock time at hour 8; assert no lock acquisition |
| Unit | `upsert_jobs` reads `job.source` not param | Inject a repo spy; assert `source` not passed as separate arg |
| Unit | Scraper `Job(...)` includes `source=` | Assert `Job` calls in parser tests include `source="<source>"` |
| Integration | Full scheduler cycle with real DB | `asyncio.run` a mini cycle; assert rows have real source names, not "aggregator" |

## Migration / Rollback

No migration required — this is a pure refactor with no schema change (the `source` column already exists in the DB; the CHECK constraint already names the three valid values). Rollback reverts the 8 changed source files and restores the 3-line signature diff in `ports.py`.

## Open Questions

None — all three changes are fully specified by the proposal and the codebase inspection above.
