"""Persistent job storage infrastructure.

The `persistence` package provides two implementations of
`JobRepositoryPort`:

- `SqliteJobRepository` (in `sqlite_job_repository.py`): `aiosqlite`-backed,
  used for local development and testing.
- `PostgresJobRepository` (in `postgres_job_repository.py`): `asyncpg`-backed,
  used for production deployments with Supabase PostgreSQL or any PostgreSQL
  instance (set `DATABASE_URL` to activate).
"""
