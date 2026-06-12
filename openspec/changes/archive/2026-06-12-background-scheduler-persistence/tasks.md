# Tasks: Background Scheduler + Job Persistence

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~850 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (Foundation) → PR 2 (Repository) → PR 3 (Scheduler + Wiring) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Foundation (deps, ports, config, \_\_init\_\_) | PR 1 | ~90 lines; standalone, testable |
| 2 | Repository (SqliteJobRepository + tests) | PR 2 | ~400 lines; base = main (or tracker branch) |
| 3 | Scheduler + Wiring (BackgroundJobScheduler + app_factory + .env.example + integration tests) | PR 3 | ~360 lines; depends on PR 2 |

## Phase 1: Foundation

- [ ] **T-001** Add `aiosqlite>=0.20,<1.0` to `[project.dependencies]` in `pyproject.toml`. REQ-ROOT-002.
- [ ] **T-002** Add `JobRepositoryPort` Protocol in `application/ports.py` with 3 async methods (`upsert_jobs`, `search_jobs`, `close`). No `@runtime_checkable`. REQ-DB-001.
- [ ] **T-003** Add 5 new `Settings` fields (`db_path`, `scheduler_enabled`, `scheduler_min_interval_seconds`, `scheduler_max_interval_seconds`, `scheduler_queries`) to `infrastructure/config.py` with `AliasChoices`. `scheduler_queries` uses a `mode="before"` validator to parse JSON (same pattern as `RATE_LIMIT_EXEMPT_PATHS`). REQ-CFG-001.
- [ ] **T-004** Create `infrastructure/persistence/__init__.py` with module docstring.

## Phase 2: Repository

- [ ] **T-005** Create `SqliteJobRepository` in `infrastructure/persistence/sqlite_job_repository.py`. Context manager (`__aenter__`/`__aexit__`), WAL pragma, `CREATE TABLE IF NOT EXISTS` migrations, `INSERT ... ON CONFLICT(source, source_id) DO UPDATE` upsert, `search_jobs` with optional filters, idempotent `close`. REQ-DB-002, REQ-DB-003, REQ-DB-004.
- [ ] **T-006** Write `tests/unit/test_repository.py`. Use `":memory:"` SQLite. Cover: schema creation + WAL + indexes, upsert insert, upsert update preserves `first_seen_at`, search with/without filters, empty result returns `[]`, close idempotency, mypy structural conformance.

## Phase 3: Scheduler

- [ ] **T-007** Create `BackgroundJobScheduler` in `infrastructure/scheduler.py`. Constructor accepts `search_fn: Callable[[str, str], Awaitable[list[Job]]]`, `repo: JobRepositoryPort`, `queries`, `min_interval`, `max_interval`. `start()` creates an `asyncio.Task` for `_loop()`, `stop()` cancels gracefully. `_loop()` uses `asyncio.Lock` to prevent overlap, sleeps `random.uniform(min,max)` between cycles. REQ-SCH-001..005.
- [ ] **T-008** Write `tests/unit/test_scheduler.py`. Use `AsyncMock`-based fakes for `search_fn` and `FakeJobRepository`. Cover: `start()` creates task, `stop()` cancels gracefully, lock prevents overlap, random interval observed, multiple queries per cycle, all results upserted once, `CancelledError` caught on mid-cycle stop.

## Phase 4: Wiring

- [ ] **T-009** Wire scheduler + repo in `presentation/app_factory.py` lifespan. When `settings.scheduler_enabled`: build `SqliteJobRepository(db_path)`, open in lifespan, construct `BackgroundJobScheduler(search_fn=lambda kw, loc: aggregator.search(...))`, start/stop around yield, close repo in `finally`. When disabled: zero behavioral change. REQ-ROOT-001.
- [ ] **T-010** Write integration tests (`tests/integration/test_scheduler_wiring.py`). Use `asgi_lifespan.LifespanManager`. Scenario 1: `SCHEDULER_ENABLED=false` → no DB created, no scheduler started. Scenario 2: `SCHEDULER_ENABLED=true` with fake aggregator → repo opened, scheduler started/stopped.
- [ ] **T-011** Add 5 new env vars to `backend/.env.example` with comments and sensible defaults. REQ-ROOT-003.
