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
        source: str,
        query_snapshot: dict[str, str],
    ) -> int:
        """Upsert via ON CONFLICT(source, source_id) DO UPDATE. Returns row count."""
        assert self._connection is not None, "repository not opened; use 'async with repo:'"

        query_json = json.dumps(query_snapshot)
        rows = 0
        for job in jobs:
            cursor = await self._connection.execute(
                _UPSERT_SQL,
                (
                    source,
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

    async def close(self) -> None:
        """Close the DB connection. Idempotent."""
        if self._connection is not None:
            await self._connection.close()
            self._connection = None


def _row_to_job(row: aiosqlite.Row) -> Job:
    """Convert an `aiosqlite.Row` to a `Job` domain object."""
    posted_at_str: str = row["posted_at"]
    posted_at_dt = datetime.strptime(posted_at_str, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )

    return Job(
        id=row["source_id"],
        title=row["title"],
        company=row["company"],
        location=row["location"],
        url=row["url"],
        posted_at=posted_at_dt,
        description=row["description"],
    )
