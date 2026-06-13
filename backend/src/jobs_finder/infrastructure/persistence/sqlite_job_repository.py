"""SQLite-backed implementation of `JobRepositoryPort`.

Spec: REQ-DB-002, REQ-DB-003, REQ-DB-004. Uses `aiosqlite` as the async
driver, enables WAL mode on connect, and creates the `jobs` table with
a `UNIQUE(source, source_id)` constraint for upsert semantics.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from jobs_finder.domain.job import Job

# ── Schema ──────────────────────────────────────────────────────────────────

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL CHECK(source IN ('linkedin','indeed','infojobs')),
    source_id       TEXT NOT NULL,
    title           TEXT NOT NULL,
    company         TEXT NOT NULL,
    location        TEXT NOT NULL,
    url             TEXT NOT NULL,
    description     TEXT,
    posted_at       TEXT NOT NULL,
    query_snapshot  TEXT NOT NULL,
    first_seen_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    last_seen_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(source, source_id)
);
"""

_CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);",
    "CREATE INDEX IF NOT EXISTS idx_jobs_posted_at ON jobs(posted_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_jobs_source_source_id ON jobs(source, source_id);",
]

_UPSERT_SQL = """
INSERT INTO jobs (source, source_id, title, company, location, url, description,
                  posted_at, query_snapshot)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(source, source_id) DO UPDATE SET
    title=excluded.title,
    company=excluded.company,
    location=excluded.location,
    url=excluded.url,
    description=excluded.description,
    posted_at=excluded.posted_at,
    last_seen_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
"""


class SqliteJobRepository:
    """Context manager. Opens DB on `__aenter__`, runs migrations, closes on `__aexit__`.

    Satisfies `JobRepositoryPort` structurally.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path: str = db_path
        self._connection: aiosqlite.Connection | None = None

    async def __aenter__(self) -> SqliteJobRepository:
        """Open aiosqlite.connect, enable WAL, run CREATE TABLE + INDEX IF NOT EXISTS."""
        self._connection = await aiosqlite.connect(self._db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute(_CREATE_TABLE_SQL)
        for idx_sql in _CREATE_INDEXES_SQL:
            await self._connection.execute(idx_sql)
        await self._connection.commit()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        """Close the connection."""
        await self.close()

    async def upsert_jobs(
        self,
        jobs: list[Job],
        query_snapshot: dict[str, str],
    ) -> int:
        """Upsert via ON CONFLICT(source, source_id) DO UPDATE. Returns row count."""
        assert self._connection is not None, "repository not opened; use 'async with repo:'"

        by_source: dict[str, list[Job]] = {}
        for job in jobs:
            by_source.setdefault(job.source, []).append(job)

        rows = 0
        for _source, group in by_source.items():
            query_json = json.dumps(query_snapshot)
            for job in group:
                cursor = await self._connection.execute(
                    _UPSERT_SQL,
                    (
                        job.source,
                        job.id,
                        job.title,
                        job.company,
                        job.location,
                        job.url,
                        job.description,
                        job.posted_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        query_json,
                    ),
                )
                rows += cursor.rowcount
        await self._connection.commit()
        return rows

    async def delete_older_than(
        self,
        *,
        days: int,
        limit: int = 1000,
    ) -> int:
        """Delete rows with `last_seen_at` older than `days` days.

        SQL: DELETE FROM jobs WHERE last_seen_at < datetime('now', '-' || ? || ' days') LIMIT ?
        Returns the number of deleted rows.
        """
        assert self._connection is not None, "repository not opened; use 'async with repo:'"

        cursor = await self._connection.execute(
            "DELETE FROM jobs WHERE last_seen_at < datetime('now', '-' || ? || ' days') LIMIT ?",
            (days, limit),
        )
        await self._connection.commit()
        return cursor.rowcount

    async def search_jobs(
        self,
        keywords: str | None = None,
        sources: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        """SELECT with optional WHERE filters on source and keyword match."""
        assert self._connection is not None, "repository not opened; use 'async with repo:'"

        clauses: list[str] = []
        params: list[Any] = []

        if sources is not None:
            placeholders = ", ".join("?" for _ in sources)
            clauses.append(f"source IN ({placeholders})")
            params.extend(sources)

        if keywords is not None:
            clauses.append("(title LIKE ? OR company LIKE ?)")
            like_pattern = f"%{keywords}%"
            params.append(like_pattern)
            params.append(like_pattern)

        where_clause = ""
        if clauses:
            where_clause = "WHERE " + " AND ".join(clauses)

        sql = f"SELECT * FROM jobs {where_clause} ORDER BY posted_at DESC LIMIT ? OFFSET ?"
        params.append(limit)
        params.append(offset)

        async with self._connection.execute(sql, params) as cursor:
            rows = await cursor.fetchall()

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
        exclude_ids: list[str] | None = None,
    ) -> list[Job]:
        """SELECT with optional filters on source, keyword, location, description, and date range."""
        assert self._connection is not None, "repository not opened; use 'async with repo:'"

        clauses, params = _build_history_clauses(
            sources, keywords, location, description, date_from, date_to
        )

        # Exclude previously seen job IDs (for "visto" tracking)
        if exclude_ids:
            placeholders = ", ".join("?" for _ in exclude_ids)
            clauses.append(f"id NOT IN ({placeholders})")
            params.extend(exclude_ids)

        where_clause = ""
        if clauses:
            where_clause = "WHERE " + " AND ".join(clauses)

        # Prioritize Spain locations (all Spanish cities and regions)
        spain_terms = [
            "Spain", "España", "Madrid", "Barcelona", "Málaga", "Malaga",
            "Valencia", "Sevilla", "Zaragoza", "Murcia", "Bilbao",
            "Galicia", "Cataluña", "Andalucía", "Castilla", "Asturias",
            "Cantabria", "Rioja", "Navarra", "Extremadura", "Baleares",
            "Canarias", "Santiago", "Vigo", "Gijón", "Granada", "Córdoba",
            "Valladolid", "País Vasco", "Aragón", "La Rioja", "Navarra",
            "Asturias", "Melilla", "Ceuta",
        ]
        spain_clauses = " OR ".join(f"location LIKE '%{t}%'" for t in spain_terms)
        sql = (
            f"SELECT * FROM jobs {where_clause} "
            f"ORDER BY "
            f"CASE WHEN {spain_clauses} THEN 0 ELSE 1 END, "
            f"posted_at DESC "
            f"LIMIT ? OFFSET ?"
        )
        params = [*params, limit, offset]

        async with self._connection.execute(sql, params) as cursor:
            rows = await cursor.fetchall()

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
        assert self._connection is not None, "repository not opened; use 'async with repo:'"

        clauses, params = _build_history_clauses(
            sources, keywords, location, description, date_from, date_to
        )
        where_clause = ""
        if clauses:
            where_clause = "WHERE " + " AND ".join(clauses)

        sql = f"SELECT count(*) FROM jobs {where_clause}"

        async with self._connection.execute(sql, params) as cursor:
            row = await cursor.fetchone()

        assert row is not None
        return int(row[0])

    async def close(self) -> None:
        """Close the DB connection. Idempotent."""
        if self._connection is not None:
            await self._connection.close()
            self._connection = None


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
    into a ``WHERE`` expression. Shared by ``search_jobs_history`` and
    ``count_jobs``.
    """
    clauses: list[str] = []
    params: list[Any] = []

    if sources is not None:
        placeholders = ", ".join("?" for _ in sources)
        clauses.append(f"source IN ({placeholders})")
        params.extend(sources)

    if keywords is not None:
        clauses.append("(title LIKE ? OR company LIKE ?)")
        like_pattern = f"%{keywords}%"
        params.append(like_pattern)
        params.append(like_pattern)

    if location is not None:
        clauses.append("location LIKE ?")
        params.append(f"%{location}%")

    if description is not None:
        clauses.append("description LIKE ?")
        params.append(f"%{description}%")

    if date_from is not None:
        clauses.append("posted_at >= ?")
        params.append(date_from)

    if date_to is not None:
        clauses.append("posted_at <= ?")
        params.append(date_to)

    return clauses, params


def _row_to_job(row: aiosqlite.Row) -> Job:
    """Convert an `aiosqlite.Row` to a `Job` domain object."""
    posted_at_str: str = row["posted_at"]
    posted_at_dt = datetime.strptime(posted_at_str, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc  # noqa: UP017 — datetime.UTC unavailable on Python 3.12.3
    )

    return Job(
        id=row["source_id"],
        title=row["title"],
        company=row["company"],
        location=row["location"],
        url=row["url"],
        posted_at=posted_at_dt,
        description=row["description"],
        source=row["source"],
    )
