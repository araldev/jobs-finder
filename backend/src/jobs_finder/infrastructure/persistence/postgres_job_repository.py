"""PostgreSQL-backed implementation of `JobRepositoryPort`.

Uses `asyncpg` as the async driver. Requires a `DATABASE_URL` pointing to
a Supabase PostgreSQL instance (or any PostgreSQL 15+ with the `unaccent`
extension enabled).

Spec: REQ-DB-002, REQ-DB-003, REQ-DB-004 (adapted for PostgreSQL).
"""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from typing import Any

import asyncpg  # type: ignore[import-untyped]

from jobs_finder.domain.job import Job

# ── Schema ──────────────────────────────────────────────────────────────────

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id              SERIAL PRIMARY KEY,
    source          TEXT NOT NULL CHECK(source IN ('linkedin','indeed','infojobs')),
    source_id       TEXT NOT NULL,
    title           TEXT NOT NULL,
    company         TEXT NOT NULL,
    location        TEXT NOT NULL,
    url             TEXT NOT NULL,
    description     TEXT,
    posted_at       TIMESTAMPTZ NOT NULL,
    query_snapshot  TEXT NOT NULL,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(source, source_id)
);
"""

_CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);",
    "CREATE INDEX IF NOT EXISTS idx_jobs_posted_at ON jobs(posted_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_jobs_source_source_id ON jobs(source, source_id);",
]

_CREATE_UNACCENT_SQL = 'CREATE EXTENSION IF NOT EXISTS "unaccent";'

_UPSERT_SQL = """
INSERT INTO jobs (source, source_id, title, company, location, url, description,
                  posted_at, query_snapshot)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
ON CONFLICT (source, source_id) DO UPDATE SET
    title=EXCLUDED.title,
    company=EXCLUDED.company,
    location=EXCLUDED.location,
    url=EXCLUDED.url,
    description=EXCLUDED.description,
    posted_at=EXCLUDED.posted_at,
    last_seen_at=NOW()
"""


class PostgresJobRepository:
    """Async context manager backed by a PostgreSQL connection pool.

    Opens a pool on ``__aenter__``, runs migrations, closes on ``__aexit__``.
    Satisfies ``JobRepositoryPort`` structurally.
    """

    def __init__(self, database_url: str, min_size: int = 1, max_size: int = 4) -> None:
        self._database_url: str = database_url
        self._min_size: int = min_size
        self._max_size: int = max_size
        self._pool: asyncpg.Pool | None = None

    @property
    def pool(self) -> asyncpg.Pool:
        assert self._pool is not None, "repository not opened; use 'async with repo:'"
        return self._pool

    async def __aenter__(self) -> PostgresJobRepository:
        """Create the pool, run schema migrations, enable unaccent."""
        self._pool = await asyncpg.create_pool(
            self._database_url,
            min_size=self._min_size,
            max_size=self._max_size,
            # Compatibility with Supabase connection pooler (supavisor).
            # Transaction-mode poolers do not support prepared statements;
            # disabling the cache ensures every query works regardless
            # of pooler mode.
            statement_cache_size=0,
        )
        async with self.pool.acquire() as conn:
            await conn.execute(_CREATE_UNACCENT_SQL)
            await conn.execute(_CREATE_TABLE_SQL)
            for idx_sql in _CREATE_INDEXES_SQL:
                await conn.execute(idx_sql)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        """Close the connection pool."""
        await self.close()

    async def upsert_jobs(
        self,
        jobs: list[Job],
        query_snapshot: dict[str, str],
    ) -> int:
        """Upsert via ON CONFLICT DO UPDATE. Returns row count."""
        query_json = json.dumps(query_snapshot)
        rows = 0
        async with self.pool.acquire() as conn:
            for job in jobs:
                result = await conn.execute(
                    _UPSERT_SQL,
                    job.source,
                    job.id,
                    job.title,
                    job.company,
                    job.location,
                    job.url,
                    job.description,
                    job.posted_at,
                    query_json,
                )
                parts = result.split()
                if parts:
                    with contextlib.suppress(ValueError, IndexError):
                        rows += int(parts[-1])
        return rows

    async def delete_older_than(
        self,
        *,
        days: int,
        limit: int = 1000,
    ) -> int:
        """Delete rows with ``last_seen_at`` older than ``days`` days.

        PostgreSQL does NOT support ``DELETE ... LIMIT`` natively, so we
        use a subquery to limit the affected rows. Returns the number of
        deleted rows.
        """
        # Use make_interval(days => $1) to avoid string-interpolation pitfalls
        # with asyncpg INTERVAL binding.
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM jobs WHERE id IN ("
                "SELECT id FROM jobs "
                "WHERE last_seen_at < NOW() - make_interval(days => $1) "
                f"LIMIT {limit}"
                ")",
                days,
            )
            parts = result.split()
            if parts:
                try:
                    return int(parts[-1])
                except (ValueError, IndexError):
                    pass
            return 0

    async def search_jobs(
        self,
        keywords: str | None = None,
        sources: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        """SELECT with optional WHERE filters on source and keyword match."""
        clauses: list[str] = []
        params: list[Any] = []
        param_idx = 1

        if sources is not None:
            placeholders = ", ".join(f"${param_idx + i}" for i in range(len(sources)))
            clauses.append(f"source IN ({placeholders})")
            params.extend(sources)
            param_idx += len(sources)

        if keywords is not None:
            clauses.append(f"(title ILIKE ${param_idx} OR company ILIKE ${param_idx + 1})")
            like_pattern = f"%{keywords}%"
            params.append(like_pattern)
            params.append(like_pattern)
            param_idx += 2

        where_clause = ""
        if clauses:
            where_clause = "WHERE " + " AND ".join(clauses)

        sql = (
            f"SELECT source, source_id AS id, title, company, location, url, "
            f"description, posted_at "
            f"FROM jobs {where_clause} ORDER BY posted_at DESC "
            f"LIMIT ${param_idx} OFFSET ${param_idx + 1}"
        )
        params.append(limit)
        params.append(offset)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        return [_row_to_job(row) for row in rows]

    async def search_jobs_history(
        self,
        *,
        sources: list[str] | None = None,
        keywords: str | None = None,
        location: str | None = None,
        description: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        """SELECT with optional filters on source, keyword, location,
        description, and date range."""
        clauses, params = _build_history_clauses(
            sources, keywords, location, description, date_from, date_to
        )
        where_clause = ""
        if clauses:
            where_clause = "WHERE " + " AND ".join(clauses)

        # Prioritize Spain locations (same list as the SQLite version)
        spain_terms = [
            "Spain",
            "España",
            "Madrid",
            "Barcelona",
            "Málaga",
            "Malaga",
            "Valencia",
            "Sevilla",
            "Zaragoza",
            "Murcia",
            "Bilbao",
            "Galicia",
            "Cataluña",
            "Andalucía",
            "Castilla",
            "Asturias",
            "Cantabria",
            "Rioja",
            "Navarra",
            "Extremadura",
            "Baleares",
            "Canarias",
            "Santiago",
            "Vigo",
            "Gijón",
            "Granada",
            "Córdoba",
            "Valladolid",
            "País Vasco",
            "Aragón",
            "La Rioja",
            "Melilla",
            "Ceuta",
        ]
        spain_clauses = " OR ".join(
            f"location ILIKE '%' || ${len(params) + 1 + i} || '%'"
            for i, _ in enumerate(spain_terms)
        )
        for term in spain_terms:
            params.append(term)

        param_idx = len(params) + 1
        sql = (
            f"SELECT source, source_id AS id, title, company, location, url, "
            f"description, posted_at "
            f"FROM jobs {where_clause} "
            f"ORDER BY "
            f"CASE WHEN ({spain_clauses}) THEN 0 ELSE 1 END, "
            f"posted_at DESC "
            f"LIMIT ${param_idx} OFFSET ${param_idx + 1}"
        )
        params.append(limit)
        params.append(offset)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        return [_row_to_job(row) for row in rows]

    async def count_jobs(
        self,
        *,
        sources: list[str] | None = None,
        keywords: str | None = None,
        location: str | None = None,
        description: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> int:
        """SELECT count(*) with the same optional filters."""
        clauses, params = _build_history_clauses(
            sources, keywords, location, description, date_from, date_to
        )
        where_clause = ""
        if clauses:
            where_clause = "WHERE " + " AND ".join(clauses)

        sql = f"SELECT count(*) FROM jobs {where_clause}"

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *params)

        assert row is not None
        return int(row[0])

    async def get_job_by_source_id(self, source_id: str) -> Job | None:
        """Return a single job by its source_id, or None if not found."""
        sql = (
            "SELECT source, source_id AS id, title, company, location, url, "
            "description, posted_at "
            "FROM jobs WHERE source_id = $1 LIMIT 1"
        )
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, source_id)

        if row is None:
            return None
        return _row_to_job(row)

    async def close(self) -> None:
        """Close the connection pool. Idempotent."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


def _build_history_clauses(
    sources: list[str] | None,
    keywords: str | None,
    location: str | None,
    description: str | None,
    date_from: str | None,
    date_to: str | None,
) -> tuple[list[str], list[Any]]:
    """Build WHERE-clause fragments and params for history queries.

    Returns a ``(clauses, params)`` tuple suitable for ``AND``-joining
    into a ``WHERE`` expression. Uses PostgreSQL ``unaccent`` + ``ILIKE``
    for case- and accent-insensitive matching.
    """
    clauses: list[str] = []
    params: list[Any] = []
    param_idx = 1

    if sources is not None:
        placeholders = ", ".join(f"${param_idx + i}" for i in range(len(sources)))
        clauses.append(f"source IN ({placeholders})")
        params.extend(sources)
        param_idx += len(sources)

    if keywords is not None:
        clauses.append(
            f"(unaccent(title) ILIKE unaccent(${param_idx}) "
            f"OR unaccent(company) ILIKE unaccent(${param_idx + 1}))"
        )
        like_pattern = f"%{keywords}%"
        params.append(like_pattern)
        params.append(like_pattern)
        param_idx += 2

    if location is not None:
        clauses.append(f"unaccent(location) ILIKE unaccent(${param_idx})")
        params.append(f"%{location}%")
        param_idx += 1

    if description is not None:
        clauses.append(f"unaccent(description) ILIKE unaccent(${param_idx})")
        params.append(f"%{description}%")
        param_idx += 1

    if date_from is not None:
        clauses.append(f"posted_at >= ${param_idx}")
        date_from_val: Any = (
            datetime.fromisoformat(date_from).date() if isinstance(date_from, str) else date_from
        )
        params.append(date_from_val)
        param_idx += 1

    if date_to is not None:
        clauses.append(f"posted_at <= ${param_idx}")
        date_to_val: Any = (
            datetime.fromisoformat(date_to).date() if isinstance(date_to, str) else date_to
        )
        params.append(date_to_val)
        param_idx += 1

    return clauses, params


def _row_to_job(row: asyncpg.Record) -> Job:
    """Convert an ``asyncpg.Record`` to a ``Job`` domain object."""
    posted_at: datetime = row["posted_at"]
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=UTC)

    return Job(
        id=row["id"],
        title=row["title"],
        company=row["company"],
        location=row["location"],
        url=row["url"],
        posted_at=posted_at,
        description=row.get("description"),
        source=row["source"],
    )
