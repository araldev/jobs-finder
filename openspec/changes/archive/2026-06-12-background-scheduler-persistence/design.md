# Design: Background Scheduler + Job Persistence

## Technical Approach

Two new capabilities added to the existing hexagonal architecture: a **job-repository** (persistent SQLite storage via `aiosqlite`) and a **background-scheduler** (asyncio task that periodically scrapes all 3 sources). Both are OPT-IN — `SCHEDULER_ENABLED=false` (default) means zero behavioral change. The in-memory TTL cache is preserved unchanged; the DB is a parallel persistence layer that survives restarts.

## Architecture Decisions

### Decision: aiosqlite over libsql / raw sqlite3

| Option | Tradeoff | Decision |
|--------|----------|----------|
| `aiosqlite` | Async-native, non-blocking I/O, context-manager API | ✅ **Selected** |
| `libsql-client` | Archived upstream, sync-only API | Rejected |
| `sqlite3` (stdlib) | Blocking; would need thread pool | Rejected |

**Rationale**: `aiosqlite` is async-native, well-typed, and compatible with the existing asyncio lifespan. WAL mode is enabled via `PRAGMA journal_mode=WAL` at connection open.

### Decision: `__aenter__`/`__aexit__` lifecycle on SqliteJobRepository

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Lazy connect on first operation | Simpler API; harder to fail-fast on misconfiguration | Rejected |
| **Explicit context manager** | Fail-fast at boot; clear lifecycle; reusable | ✅ **Selected** |

**Rationale**: Matches the existing `PlaywrightScraper.__aenter__`/`__aexit__` pattern. The lifespan opens the repo, starts the scheduler, serves, stops the scheduler, closes the repo — clean LIFO shutdown.

### Decision: BackgroundJobScheduler accepts `search_fn` not a use case

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Accept `SearchAllSourcesUseCase` | Couples scheduler to concrete class | Rejected |
| **Accept `Callable[[str, str], Awaitable[list[Job]]]`** | Testable with any callable; no coupling | ✅ **Selected** |

**Rationale**: The scheduler wraps `aggregator.search` at composition root. Tests inject a `FakeSearchAllSources` (or a simple `async def`). The `Callable` Protocol is self-documenting.

### Decision: `SearchAllSourcesUseCase.search` as the scheduler's `search_fn`

The scheduler receives the aggregator's `search()` method as a `Callable[[str, str], Awaitable[list[Job]]]`. Each tick calls `search_fn(keywords, location)` for each configured query. Results are accumulated and upserted to the repo after all queries complete.

## Data Flow

```
SCHEDULER TICK
┌──────────────┐     for each query in scheduler_queries[]
│  Background  │ ──► search_fn(keywords, location)
│  Scheduler   │      │  └─► SearchAllSourcesUseCase.search()
│  _loop()     │      │       ├─► LinkedIn scraper (3 sources, parallel)
│              │      │       ├─► Indeed scraper
│              │      │       └─► InfoJobs scraper
│              │      │       └─► dedup + rank (existing)
│              │      ◄─────── list[Job]
│              │     accumulate all jobs
│              │ ──► repo.upsert_jobs(all_jobs, source="aggregator",
│              │                       query_snapshot={keywords, location})
│              │     └─► INSERT ... ON CONFLICT DO UPDATE
│              │     sleep random.uniform(min, max)
└──────────────┘
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/jobs_finder/application/ports.py` | Modify | Add `JobRepositoryPort` Protocol (3 async methods) |
| `src/jobs_finder/infrastructure/persistence/__init__.py` | Create | Module docstring only |
| `src/jobs_finder/infrastructure/persistence/sqlite_job_repository.py` | Create | `SqliteJobRepository` — `aiosqlite`, WAL, migrations, upsert, search, close |
| `src/jobs_finder/infrastructure/scheduler.py` | Create | `BackgroundJobScheduler` — `start()`, `stop()`, `_loop()`, `asyncio.Lock` |
| `src/jobs_finder/infrastructure/config.py` | Modify | 5 new `Settings` fields with `AliasChoices` |
| `src/jobs_finder/presentation/app_factory.py` | Modify | Wire scheduler in lifespan when `SCHEDULER_ENABLED=true` |
| `pyproject.toml` | Modify | Add `aiosqlite>=0.20,<1.0` |
| `.env.example` | Modify | 5 new env vars with comments |
| `tests/unit/test_repository.py` | Create | Unit tests for `SqliteJobRepository` with `":memory:"` |
| `tests/unit/test_scheduler.py` | Create | Unit tests for `BackgroundJobScheduler` with `FakeJobRepository` + controlled clock |

## Interfaces / Contracts

```python
# application/ports.py
class JobRepositoryPort(Protocol):
    """Persistent job storage. No @runtime_checkable — structural only."""

    async def upsert_jobs(
        self, jobs: list[Job], source: str,
        query_snapshot: dict[str, str],
    ) -> int:
        """Upsert via ON CONFLICT(source, source_id) DO UPDATE. Returns row count."""
        ...

    async def search_jobs(
        self, keywords: str | None = None,
        sources: list[str] | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[Job]:
        """SELECT with optional WHERE filters."""
        ...

    async def close(self) -> None:
        """Close the DB connection. Idempotent."""
        ...
```

```python
# infrastructure/persistence/sqlite_job_repository.py
class SqliteJobRepository:
    """Context manager. Opens DB on __aenter__, runs migrations, closes on __aexit__."""

    def __init__(self, db_path: str) -> None: ...

    async def __aenter__(self) -> SqliteJobRepository:
        """Open aiosqlite.connect, enable WAL, run CREATE TABLE + INDEX IF NOT EXISTS."""
        ...

    async def __aexit__(self, *exc: Any) -> None:
        """Close the connection."""
        ...

    async def upsert_jobs(
        self, jobs: list[Job], source: str,
        query_snapshot: dict[str, str],
    ) -> int: ...

    async def search_jobs(
        self, keywords: str | None = None,
        sources: list[str] | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[Job]: ...

    async def close(self) -> None: ...
```

```python
# infrastructure/scheduler.py
class BackgroundJobScheduler:
    """Periodically calls search_fn, persists to repo. asyncio.Task lifecycle."""

    def __init__(
        self,
        search_fn: Callable[[str, str], Awaitable[list[Job]]],
        repo: JobRepositoryPort,
        queries: list[dict[str, str]],
        min_interval: float = 1500.0,
        max_interval: float = 2100.0,
    ) -> None: ...

    def start(self) -> None:
        """Create asyncio.create_task(self._loop()). Never awaited; fire-and-forget."""

    async def stop(self) -> None:
        """Cancel task, catch CancelledError. Idempotent."""
        ...

    async def _loop(self) -> None:
        """Lock-protected infinite loop with random.uniform sleep."""
        ...
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit — Repository | Upsert inserts new rows; upsert updates on conflict; search with/without filters; search empty returns `[]` | `SqliteJobRepository(":memory:")` — opens lazily on first call. Assert row counts, field values, `first_seen_at` preserved on update |
| Unit — Repository | Schema creation, WAL pragma, indexes exist | Inspect `PRAGMA journal_mode`, query `sqlite_master` |
| Unit — Scheduler | `start()` creates task; `stop()` cancels gracefully | Controlled clock with `asyncio.Event` + `FakeJobRepository` that records `upsert_jobs` calls |
| Unit — Scheduler | Lock prevents overlapping runs; random interval observed | Fast `min_interval/max_interval` (0.01/0.02s), `FakeSearchFn` with configurable delay |
| Unit — Scheduler | Multiple queries per cycle; all results upserted once | Assert `repo.upsert_jobs` call count and args |
| Integration | Lifespan wiring with `SCHEDULER_ENABLED=true` | `asgi_lifespan.LifespanManager` + fake aggregator. Verify repo opened, scheduler started/stopped |
| Integration | Lifespan wiring with `SCHEDULER_ENABLED=false` | Zero behavioral change; no DB file created |

## Migration / Rollout

No migration required. The initial `CREATE TABLE IF NOT EXISTS` is idempotent. The scheduler is opt-in (`SCHEDULER_ENABLED=false` by default). When enabled for the first time, the `jobs.db` file is created at `db_path` (default `"jobs.db"` in the working directory). A future follow-up change may add a retention/cleanup policy.

## Configuration

| Field | Env Var | Type | Default |
|-------|---------|------|---------|
| `db_path` | `DB_PATH` / `db_path` | `str` | `"jobs.db"` |
| `scheduler_enabled` | `SCHEDULER_ENABLED` / `scheduler_enabled` | `bool` | `False` |
| `scheduler_min_interval_seconds` | `SCHEDULER_MIN_INTERVAL_SECONDS` / `scheduler_min_interval_seconds` | `float` | `1500.0` |
| `scheduler_max_interval_seconds` | `SCHEDULER_MAX_INTERVAL_SECONDS` / `scheduler_max_interval_seconds` | `float` | `2100.0` |
| `scheduler_queries` | `SCHEDULER_QUERIES` / `scheduler_queries` | `list[dict[str, str]]` | `[{"keywords": "desarrollador", "location": "España"}]` |

The `scheduler_queries` field uses a `mode="before"` validator to parse JSON, matching the `RATE_LIMIT_EXEMPT_PATHS` pattern. All fields use `AliasChoices("UPPER", "lower")` so env-var and programmatic construction both work.

## Lifecycle (when `SCHEDULER_ENABLED=true`)

```
STARTUP:          SHUTDOWN:
repo.__aenter__   scheduler.stop()     # cancel task
  ├─ aiosqlite    repo.__aexit__()     # close DB
  ├─ WAL pragma
  └─ migrations
scheduler.start()
  └─ create_task
       └─ _loop()
```

The repo is opened BEFORE the scheduler starts so the DB is ready when the first tick fires. Shutdown is LIFO: stop scheduler first (cancels the task), then close the repo. The schedule is in the `finally` block of the lifespan, after scrapers close.

## Dependencies

`aiosqlite>=0.20,<1.0` added to `[project.dependencies]` in `pyproject.toml`.

## Open Questions

- None — all decisions are resolved in the proposal and spec.
