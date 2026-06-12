# Proposal: Background Scheduler + Job Persistence

## Intent

Jobs are scrapped on-demand per HTTP request and lost on restart. Add a background scheduler collecting offers at pseudo-random intervals, persisted to a local SQLite DB with Turso-compatible schema.

## Scope

### In Scope
- aiosqlite dep + Turso-compatible schema with WAL mode
- `JobRepositoryPort` Protocol in `application/ports.py`
- `SqliteJobRepository` in `infrastructure/repository/`
- `BackgroundJobScheduler` as asyncio.Task in FastAPI lifespan
- 5 new Settings fields (DB_PATH, SCHEDULER_ENABLED, MIN/MAX interval, SCHEDULER_QUERIES)
- UPSERT: `INSERT ... ON CONFLICT(source, source_id) DO UPDATE`
- Unit + integration tests

### Out of Scope
- Turso cloud migration (future file swap)
- Job retention/cleanup policy (follow-up)
- Frontend changes
- Replacing in-memory TTL cache

## Capabilities

### New Capabilities
- `background-scheduler`: Scrapes all sources at pseudo-random intervals, persists to repository
- `job-repository`: Persistent storage with upsert, aiosqlite impl, Turso-compatible schema

### Modified Capabilities
None

## Approach

**DB**: aiosqlite (async-native). `libsql` is sync-only; `libsql-client` is archived. ISO 8601 TEXT dates, WAL mode.

**Repository**: `JobRepositoryPort` Protocol → `SqliteJobRepository`. Turso swap = one new infra file.

**Scheduler**: `BackgroundJobScheduler`. asyncio.Task in lifespan. `random.uniform(1500, 2100)` for human-like intervals. `asyncio.Lock` prevents overlap. Reuses `SearchAllSourcesUseCase`. Graceful shutdown via `task.cancel()`.

**DB ↔ Cache**: In-memory cache stays for HTTP speed. DB persists data across restarts. Scheduler writes after each scrape.

## Affected Areas

| Area | Impact |
|------|--------|
| `application/ports.py` | Modified — add `JobRepositoryPort` |
| `infrastructure/repository/` | New — `SqliteJobRepository` + schema |
| `infrastructure/scheduler.py` | New — `BackgroundJobScheduler` |
| `infrastructure/config.py` | Modified — 5 new fields |
| `presentation/app_factory.py` | Modified — wire scheduler in lifespan |
| `pyproject.toml` | Modified — add aiosqlite |
| `.env.example` | Modified — 5 new env vars |
| `tests/unit/test_repository.py` | New |
| `tests/unit/test_scheduler.py` | New |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Scheduler lost on restart | High | Acceptable — no data loss; next tick resumes |
| SQLite single-writer | Low | WAL mode; writes from scheduler only |
| Disk growth unbounded | Medium | Follow-up retention; timestamps enable cleanup |
| .env.example drift | Low | Spec will pin contract |

## Rollback

Set `SCHEDULER_ENABLED=false` (default) → no task, no DB init. Remove aiosqlite dep if desired. Delete `jobs.db`.

## Dependencies

- `aiosqlite>=0.22.1,<1.0`

## Success Criteria

- [ ] `JobRepositoryPort` passes mypy --strict with `SqliteJobRepository`
- [ ] UPSERT on `(source, source_id)` conflict works
- [ ] Scheduler runs N cycles (tested with fake port)
- [ ] Graceful shutdown via `task.cancel()`
- [ ] `SCHEDULER_ENABLED=false`: zero behavioral change
- [ ] Table created with UNIQUE constraint + WAL pragma
- [ ] `cd backend && bash scripts/check.sh` green
