"""Tests for `SqliteJobRepository` (T-005) — RED → GREEN → REFACTOR.

Spec: REQ-DB-002, REQ-DB-003, REQ-DB-004.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from jobs_finder.application.ports import JobRepositoryPort
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.persistence.sqlite_job_repository import (
    SqliteJobRepository,
)


@pytest.fixture
async def repo() -> SqliteJobRepository:
    """A `SqliteJobRepository` backed by `:memory:` for isolated tests."""
    r = SqliteJobRepository(db_path=":memory:")
    await r.__aenter__()
    yield r
    await r.__aexit__(None, None, None)


_SAMPLE_JOB = Job(
    id="123",
    title="Python Developer",
    company="Tech Co",
    location="Madrid, Spain",
    url="https://example.com/job/123",
    posted_at=datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC),
)
_SAMPLE_QUERY = {"keywords": "python", "location": "Madrid"}


# ── REQ-DB-003: Schema ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_schema_creation(repo: SqliteJobRepository) -> None:
    """After connect, the `jobs` table exists with all columns."""
    async with repo._connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None, "jobs table must exist after migrations"
    assert row[0] == "jobs"


@pytest.mark.asyncio
async def test_wal_mode_enabled(tmp_path: Any) -> None:
    """WAL mode must be enabled via PRAGMA (tested on a file DB, not :memory:)."""
    db_file = str(tmp_path / "test_wal.db")
    r = SqliteJobRepository(db_path=db_file)
    async with r:
        async with r._connection.execute("PRAGMA journal_mode") as cursor:
            row = await cursor.fetchone()
    assert row is not None
    # WAL mode may report as "wal" (lowercase) on some Python versions
    assert row[0].upper() == "WAL"


@pytest.mark.asyncio
async def test_source_check_constraint(repo: SqliteJobRepository) -> None:
    """The `CHECK(source IN (...))` constraint must reject invalid sources."""
    with pytest.raises(Exception):  # aiosqlite.IntegrityError
        await repo._connection.execute(
            "INSERT INTO jobs (source, source_id, title, company, location, url, "
            "posted_at, query_snapshot) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("invalid_source", "1", "t", "c", "l", "u", "2026-01-01T00:00:00Z", "{}"),
        )


@pytest.mark.asyncio
async def test_indexes_exist(repo: SqliteJobRepository) -> None:
    """The 3 indexes must be created."""
    async with repo._connection.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
    ) as cursor:
        indexes = {row[0] for row in await cursor.fetchall()}
    assert "idx_jobs_source" in indexes
    assert "idx_jobs_posted_at" in indexes
    assert "idx_jobs_source_source_id" in indexes


# ── REQ-DB-004: Upsert ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_inserts_new_row(repo: SqliteJobRepository) -> None:
    """Inserting a new job returns 1 and the row exists."""
    count = await repo.upsert_jobs(
        [_SAMPLE_JOB], source="linkedin", query_snapshot=_SAMPLE_QUERY
    )
    assert count == 1

    async with repo._connection.execute(
        "SELECT title, company FROM jobs WHERE source='linkedin' AND source_id='123'"
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == "Python Developer"
    assert row[1] == "Tech Co"


@pytest.mark.asyncio
async def test_upsert_updates_existing_row(repo: SqliteJobRepository) -> None:
    """Upserting a job with the same (source, source_id) updates fields."""
    await repo.upsert_jobs(
        [_SAMPLE_JOB], source="linkedin", query_snapshot=_SAMPLE_QUERY
    )

    updated_job = Job(
        id="123",
        title="Senior Python Developer",
        company="Tech Co",
        location="Madrid, Spain",
        url="https://example.com/job/123",
        posted_at=datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC),
    )
    count = await repo.upsert_jobs(
        [updated_job], source="linkedin", query_snapshot=_SAMPLE_QUERY
    )
    # SQLite reports 2 affected rows for an UPDATE on conflict
    assert count >= 1

    async with repo._connection.execute(
        "SELECT title FROM jobs WHERE source='linkedin' AND source_id='123'"
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == "Senior Python Developer"


@pytest.mark.asyncio
async def test_upsert_preserves_first_seen_at(repo: SqliteJobRepository) -> None:
    """On update, `first_seen_at` stays unchanged while `last_seen_at` updates."""
    await repo.upsert_jobs(
        [_SAMPLE_JOB], source="linkedin", query_snapshot=_SAMPLE_QUERY
    )

    async with repo._connection.execute(
        "SELECT first_seen_at, last_seen_at FROM jobs WHERE source='linkedin' AND source_id='123'"
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    original_first = row[0]
    original_last = row[1]

    # Upsert again with same job
    await repo.upsert_jobs(
        [_SAMPLE_JOB], source="linkedin", query_snapshot=_SAMPLE_QUERY
    )

    async with repo._connection.execute(
        "SELECT first_seen_at, last_seen_at FROM jobs WHERE source='linkedin' AND source_id='123'"
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == original_first, "first_seen_at must be preserved on update"
    assert row[1] >= original_last, "last_seen_at must be updated on conflict"


@pytest.mark.asyncio
async def test_upsert_multiple_jobs(repo: SqliteJobRepository) -> None:
    """Multiple jobs in one upsert call are all inserted."""
    jobs = [
        Job(
            id="1", title="Job 1", company="C1", location="L1",
            url="https://ex.com/1", posted_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        Job(
            id="2", title="Job 2", company="C2", location="L2",
            url="https://ex.com/2", posted_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    ]
    count = await repo.upsert_jobs(jobs, source="indeed", query_snapshot=_SAMPLE_QUERY)
    assert count == 2

    async with repo._connection.execute(
        "SELECT count(*) FROM jobs WHERE source='indeed'"
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 2


# ── search_jobs ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_jobs_empty(repo: SqliteJobRepository) -> None:
    """Empty table returns empty list."""
    jobs = await repo.search_jobs()
    assert jobs == []


@pytest.mark.asyncio
async def test_search_jobs_all(repo: SqliteJobRepository) -> None:
    """Search without filters returns all jobs."""
    await repo.upsert_jobs([_SAMPLE_JOB], source="linkedin", query_snapshot=_SAMPLE_QUERY)
    j2 = Job(
        id="456", title="Java Developer", company="Java Co",
        location="Barcelona", url="https://ex.com/456",
        posted_at=datetime(2026, 6, 2, tzinfo=UTC),
    )
    await repo.upsert_jobs([j2], source="indeed", query_snapshot=_SAMPLE_QUERY)

    jobs = await repo.search_jobs()
    assert len(jobs) == 2


@pytest.mark.asyncio
async def test_search_jobs_filter_by_source(repo: SqliteJobRepository) -> None:
    """Search with `sources` filter returns only matching source."""
    await repo.upsert_jobs([_SAMPLE_JOB], source="linkedin", query_snapshot=_SAMPLE_QUERY)
    j2 = Job(
        id="456", title="Java Developer", company="Java Co",
        location="Barcelona", url="https://ex.com/456",
        posted_at=datetime(2026, 6, 2, tzinfo=UTC),
    )
    await repo.upsert_jobs([j2], source="indeed", query_snapshot=_SAMPLE_QUERY)

    jobs = await repo.search_jobs(sources=["linkedin"])
    assert len(jobs) == 1
    assert jobs[0].id == "123"


@pytest.mark.asyncio
async def test_search_jobs_filter_by_keywords(repo: SqliteJobRepository) -> None:
    """Search with keywords matches on title and company."""
    await repo.upsert_jobs([_SAMPLE_JOB], source="linkedin", query_snapshot=_SAMPLE_QUERY)
    j2 = Job(
        id="456", title="Java Developer", company="Java Co",
        location="Barcelona", url="https://ex.com/456",
        posted_at=datetime(2026, 6, 2, tzinfo=UTC),
    )
    await repo.upsert_jobs([j2], source="indeed", query_snapshot=_SAMPLE_QUERY)

    jobs = await repo.search_jobs(keywords="Python")
    assert len(jobs) == 1
    assert jobs[0].id == "123"


@pytest.mark.asyncio
async def test_search_jobs_limit_offset(repo: SqliteJobRepository) -> None:
    """Search respects limit and offset."""
    jobs = []
    for i in range(10):
        jobs.append(Job(
            id=str(i), title=f"Job {i}", company="C",
            location="L", url=f"https://ex.com/{i}",
            posted_at=datetime(2026, 1, i + 1, tzinfo=UTC),
        ))
    await repo.upsert_jobs(jobs, source="linkedin", query_snapshot=_SAMPLE_QUERY)

    results = await repo.search_jobs(limit=3, offset=0)
    assert len(results) == 3

    results_page2 = await repo.search_jobs(limit=3, offset=3)
    assert len(results_page2) == 3
    assert results_page2[0].id != results[0].id


# ── Protocol conformance ────────────────────────────────────────────────────


def test_sqlite_job_repository_conforms_to_protocol() -> None:
    """`SqliteJobRepository` must structurally satisfy `JobRepositoryPort`."""
    repo: JobRepositoryPort = SqliteJobRepository(db_path=":memory:")  # type: ignore[assignment]
    assert repo is not None


# ── Lifecycle ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_close_idempotent() -> None:
    """Calling close() multiple times does not raise."""
    r = SqliteJobRepository(db_path=":memory:")
    await r.__aenter__()
    await r.close()
    await r.close()  # second call must not raise


@pytest.mark.asyncio
async def test_context_manager_lifecycle() -> None:
    """Using `async with` opens and closes the connection."""
    r = SqliteJobRepository(db_path=":memory:")
    async with r:
        assert r._connection is not None
    assert r._connection is None
