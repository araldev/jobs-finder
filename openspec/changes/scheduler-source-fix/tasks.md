# Tasks: `scheduler-source-fix`

## Change Metadata

| Field | Value |
|-------|-------|
| Change | `scheduler-source-fix` |
| Type | Bugfix / Refactor |
| Team | backend |
| Delivery strategy | `single-pr` |
| 400-line budget risk | Low |
| Chained PRs recommended | No |

---

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~340 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR (all 3 changes are independent and fit under the budget) |
| Delivery strategy | `single-pr` |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

---

## Phase 1: Add `source` to `Job` domain + update scrapers

### Tasks

| ID | Scope | Description | Effort | Dependencies |
|----|-------|-------------|--------|--------------|
| 1.1 | domain | Add `source: str` as first positional field to `Job` dataclass in `domain/job.py` (before `description`) | Low | None |
| 1.2 | linkedin | Add `source="linkedin"` to `Job(...)` in `linkedin/scraper.py` `_parse_cards` closure (line ~890) | Low | 1.1 |
| 1.3 | indeed | Add `source="indeed"` to `Job(...)` in `indeed/scraper.py` `_parse_cards` closure (line ~391) | Low | 1.1 |
| 1.4 | infojobs | Add `source="infojobs"` to `Job(...)` in `infojobs/scraper.py` `_parse_cards` closure (line ~493) | Low | 1.1 |
| 1.5 | tests | Update `_make_job` helper in `tests/unit/test_scheduler.py` to include `source` field | Low | 1.1 |
| 1.6 | tests | Update `FakeJobRepository.upsert_jobs` signature in `tests/unit/test_scheduler.py` to remove `source` param; update call sites in test assertions | Medium | 1.5 |
| 1.7 | tests | Update conftest sample jobs (`_make_indeed_sample_jobs`, `_make_infojobs_sample_jobs`) to include `source` field | Low | 1.1 |
| 1.8 | tests | Update `test_linkedin_scraper.py` Job assertions to include `source="linkedin"` | Low | 1.2 |
| 1.9 | tests | Update `test_indeed_scraper.py` Job assertions to include `source="indeed"` | Low | 1.3 |
| 1.10 | tests | Update `test_infojobs_scraper.py` Job assertions to include `source="infojobs"` | Low | 1.4 |

### Phase 1 Acceptance Criteria

- [x] `Job(source="linkedin", id=..., title=..., ...)` constructs without error
- [x] All 3 scrapers' `_parse_cards` closures pass `source=<source_name>`
- [x] `uv run pytest` passes for all scraper unit tests

---

## Phase 2: Remove `source` from `JobRepositoryPort.upsert_jobs`

### Tasks

| ID | Scope | Description | Effort | Dependencies |
|----|-------|-------------|--------|--------------|
| 2.1 | ports | Remove `source: str` from `JobRepositoryPort.upsert_jobs` in `application/ports.py` (line ~386) | Low | 1.1 |
| 2.2 | repository | Remove `source` param from `SqliteJobRepository.upsert_jobs`; read `job.source` per-row; update `_UPSERT_SQL` to use `excluded.source` in `ON CONFLICT` clause | Medium | 2.1 |
| 2.3 | repository | Update `_row_to_job` in `sqlite_job_repository.py` to reconstruct `source` field from row | Low | 2.2 |
| 2.4 | scheduler | Remove `source="aggregator"` from `upsert_jobs` call in `scheduler.py` `_loop()` (line ~143) | Low | 2.1 |
| 2.5 | tests | Update `test_sqlite_job_repository.py` `upsert_jobs` calls to remove `source` param | Medium | 2.2 |

### Phase 2 Acceptance Criteria

- [x] `JobRepositoryPort.upsert_jobs(jobs, query_snapshot)` — no `source` param
- [x] `SqliteJobRepository.upsert_jobs` issues per-row SQL using `job.source`
- [x] `_row_to_job` returns `Job` with `source` field populated
- [x] `uv run mypy --strict` passes for `ports.py`, `sqlite_job_repository.py`, `scheduler.py`

---

## Phase 3: Empty-keyword Spain queries

### Tasks

| ID | Scope | Description | Effort | Dependencies |
|----|-------|-------------|--------|--------------|
| 3.1 | config | Update `scheduler_queries` default in `config.py` to 3 Spain locations with empty keywords: `[{"keywords": "", "location": "Madrid"}, {"keywords": "", "location": "Barcelona"}, {"keywords": "", "location": "España"}]` | Low | None |
| 3.2 | config | Update `.env.example` `SCHEDULER_QUERIES` line with new format + comment explaining empty keywords = location-only search | Low | 3.1 |
| 3.3 | tests | Add test in `test_scheduler.py` verifying `Settings().scheduler_queries` default matches 3 Spain locations + empty keywords | Low | 3.1 |

### Phase 3 Acceptance Criteria

- [x] `Settings().scheduler_queries == [{"keywords": "", "location": "Madrid"}, {"keywords": "", "location": "Barcelona"}, {"keywords": "", "location": "España"}]`
- [x] `.env.example` documents the empty-keywords format

---

## Phase 4: Madrid work-hours gate

### Tasks

| ID | Scope | Description | Effort | Dependencies |
|----|-------|-------------|--------|--------------|
| 4.1 | scheduler | Import `ZoneInfo` from `zoneinfo` in `scheduler.py` | Low | None |
| 4.2 | scheduler | Add `_is_within_active_hours() -> bool` helper: checks `9 <= datetime.now(ZoneInfo("Europe/Madrid")).hour < 22` | Low | 4.1 |
| 4.3 | scheduler | Add pre-lock while loop in `_loop()`: if outside hours, `await asyncio.sleep(300)` and re-check | Medium | 4.2 |
| 4.4 | tests | Add `test_is_within_active_hours` with `pytestfreeze`/`monkeypatch` to mock Madrid hour at 8, 9, 21, 22, 23 | Medium | 4.2 |
| 4.5 | tests | Add `test_scheduler_skips_outside_hours` mocking time at hour 8; assert no lock acquisition | Medium | 4.3 |

### Phase 4 Acceptance Criteria

- [ ] `_is_within_active_hours()` returns `False` for hours 0-8 and 22-23
- [ ] `_is_within_active_hours()` returns `True` for hours 9-21
- [ ] Scheduler sleeps 300s in a loop when outside 09:00–22:00 Madrid time
- [ ] All new scheduler tests pass

---

## Phase 5: Verification

### Tasks

| ID | Scope | Description | Effort | Dependencies |
|----|-------|-------------|--------|--------------|
| 5.1 | all | Run `uv run pytest` from `backend/` — all tests pass | Low | All above |
| 5.2 | all | Run `uv run mypy --strict` on `src/jobs_finder/` — no errors | Low | All above |
| 5.3 | all | Run `uv run ruff check` and `uv run ruff format --check` — no violations | Low | All above |

---

## File Inventory

| File | Change |
|------|--------|
| `backend/src/jobs_finder/domain/job.py` | Add `source: str` as first positional field |
| `backend/src/jobs_finder/application/ports.py` | Remove `source` from `upsert_jobs` Protocol |
| `backend/src/jobs_finder/infrastructure/persistence/sqlite_job_repository.py` | Remove source param; use `job.source` per-row; update `_row_to_job` |
| `backend/src/jobs_finder/infrastructure/scheduler.py` | Remove `source="aggregator"`; add `ZoneInfo` import + `_is_within_active_hours()` + pre-lock gate |
| `backend/src/jobs_finder/infrastructure/config.py` | Update `scheduler_queries` default to 3 Spain locations + empty keywords |
| `backend/.env.example` | Update `SCHEDULER_QUERIES` documentation |
| `backend/src/jobs_finder/infrastructure/linkedin/scraper.py` | Add `source="linkedin"` to `Job(...)` |
| `backend/src/jobs_finder/infrastructure/indeed/scraper.py` | Add `source="indeed"` to `Job(...)` |
| `backend/src/jobs_finder/infrastructure/infojobs/scraper.py` | Add `source="infojobs"` to `Job(...)` |
| `backend/tests/unit/test_scheduler.py` | Update `_make_job`, `FakeJobRepository.upsert_jobs`, add work-hours tests |
| `backend/tests/unit/test_linkedin_scraper.py` | Update Job assertions with `source="linkedin"` |
| `backend/tests/unit/test_indeed_scraper.py` | Update Job assertions with `source="indeed"` |
| `backend/tests/unit/test_infojobs_scraper.py` | Update Job assertions with `source="infojobs"` |
| `backend/tests/unit/test_sqlite_job_repository.py` | Remove `source` param from `upsert_jobs` calls |
| `backend/tests/conftest.py` | Update sample job factories with `source` field |

---

## Test Strategy

| Layer | What to Test | File |
|-------|-------------|------|
| Unit | `Job.source` field propagates correctly | `test_job.py` (existing or new) |
| Unit | Each scraper `_parse_cards` sets correct `source` | `test_*_scraper.py` |
| Unit | `_is_within_active_hours` boundary cases (8, 9, 21, 22, 23) | `test_scheduler.py` |
| Unit | Scheduler skips cycles outside hours | `test_scheduler.py` |
| Unit | `upsert_jobs` reads `job.source` not param | `test_sqlite_job_repository.py` |
| Unit | `Settings().scheduler_queries` default | `test_scheduler.py` or `test_settings.py` |
| Integration | Full scheduler cycle with real DB — rows have real source names | `test_scheduler_wiring.py` |
