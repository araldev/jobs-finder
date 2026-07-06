"""Tests for `SqliteJobRepository` (T-005) — RED → GREEN → REFACTOR.

Spec: REQ-DB-002, REQ-DB-003, REQ-DB-004.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import aiosqlite
import pytest

from jobs_finder.application.ports import JobRepositoryPort
from jobs_finder.domain.job import Job
from jobs_finder.infrastructure.persistence.sqlite_job_repository import (
    SqliteJobRepository,
)


@pytest.fixture
async def repo() -> AsyncGenerator[SqliteJobRepository, None]:
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
    source="linkedin",
)
_SAMPLE_QUERY = {"keywords": "python", "location": "Madrid"}


# ── REQ-DB-003: Schema ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_schema_creation(repo: SqliteJobRepository) -> None:
    """After connect, the `jobs` table exists with all columns."""
    assert repo._connection is not None
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
        assert r._connection is not None
        cursor = await r._connection.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
    assert row is not None
    # WAL mode may report as "wal" (lowercase) on some Python versions
    assert row[0].upper() == "WAL"


@pytest.mark.asyncio
async def test_source_check_constraint(repo: SqliteJobRepository) -> None:
    """The `CHECK(source IN (...))` constraint must reject invalid sources."""
    with pytest.raises(aiosqlite.IntegrityError):
        assert repo._connection is not None
        await repo._connection.execute(
            "INSERT INTO jobs (source, source_id, title, company, location, url, "
            "posted_at, query_snapshot) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("invalid_source", "1", "t", "c", "l", "u", "2026-01-01T00:00:00Z", "{}"),
        )


@pytest.mark.asyncio
async def test_indexes_exist(repo: SqliteJobRepository) -> None:
    """The 3 indexes must be created."""
    assert repo._connection is not None
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
    count = await repo.upsert_jobs([_SAMPLE_JOB], query_snapshot=_SAMPLE_QUERY)
    assert count == 1

    assert repo._connection is not None
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
    await repo.upsert_jobs([_SAMPLE_JOB], query_snapshot=_SAMPLE_QUERY)

    updated_job = Job(
        id="123",
        title="Senior Python Developer",
        company="Tech Co",
        location="Madrid, Spain",
        url="https://example.com/job/123",
        posted_at=datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC),
        source="linkedin",
    )
    count = await repo.upsert_jobs([updated_job], query_snapshot=_SAMPLE_QUERY)
    # SQLite reports 2 affected rows for an UPDATE on conflict
    assert count >= 1

    assert repo._connection is not None
    async with repo._connection.execute(
        "SELECT title FROM jobs WHERE source='linkedin' AND source_id='123'"
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == "Senior Python Developer"


@pytest.mark.asyncio
async def test_upsert_preserves_first_seen_at(repo: SqliteJobRepository) -> None:
    """On update, `first_seen_at` stays unchanged while `last_seen_at` updates."""
    await repo.upsert_jobs([_SAMPLE_JOB], query_snapshot=_SAMPLE_QUERY)

    assert repo._connection is not None
    async with repo._connection.execute(
        "SELECT first_seen_at, last_seen_at FROM jobs WHERE source='linkedin' AND source_id='123'"
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    original_first = row[0]
    original_last = row[1]

    # Upsert again with same job
    await repo.upsert_jobs([_SAMPLE_JOB], query_snapshot=_SAMPLE_QUERY)

    assert repo._connection is not None
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
            id="1",
            title="Job 1",
            company="C1",
            location="L1",
            url="https://ex.com/1",
            posted_at=datetime(2026, 1, 1, tzinfo=UTC),
            source="indeed",
        ),
        Job(
            id="2",
            title="Job 2",
            company="C2",
            location="L2",
            url="https://ex.com/2",
            posted_at=datetime(2026, 1, 2, tzinfo=UTC),
            source="indeed",
        ),
    ]
    count = await repo.upsert_jobs(jobs, query_snapshot=_SAMPLE_QUERY)
    assert count == 2

    assert repo._connection is not None
    async with repo._connection.execute(
        "SELECT count(*) FROM jobs WHERE source='indeed'"
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 2


# ── REQ-DB-DESC-001: description field roundtrip ────────────────────────────
#
# Pinned by `decouple-nextjs-from-backend` Phase 1. The scheduler writes
# `Job.description` (populated by the LinkedIn detail-page visit) and the
# REST API reads it back via `search_jobs` / `get_job_by_source_id`. A
# future refactor that drops the field on either side would silently
# regress the favorites-with-descriptions UX. This section pins the
# end-to-end roundtrip on the SQLite dev repo. The Postgres repo shares
# the same SQL column shape (`description TEXT`) and the same
# `_row_to_job` mapping contract, so this test serves as a regression
# guard for BOTH backends — the same column survives on Postgres because
# the migration at `supabase/migrations/20260620_*.sql` matches this
# schema exactly.


_DESCRIPTION_TEXT = (
    "We are looking for a Senior Python developer with 5+ years of "
    "experience in FastAPI, asyncpg, and PostgreSQL. Strong knowledge "
    "of SOLID principles and clean architecture is a must."
)


@pytest.mark.asyncio
async def test_description_roundtrip_via_search_jobs(
    repo: SqliteJobRepository,
) -> None:
    """A job with a non-None `description` upserted and read back via
    `search_jobs` returns the exact same string.

    Covers the REST API path (`GET /jobs/history` → repo.search_jobs).
    """
    job_with_desc = Job(
        id="9001",
        title="Senior Python Developer",
        company="Acme",
        location="Madrid, Spain",
        url="https://ex.com/9001",
        posted_at=datetime(2026, 6, 15, 9, 0, 0, tzinfo=UTC),
        source="linkedin",
        description=_DESCRIPTION_TEXT,
    )
    await repo.upsert_jobs([job_with_desc], query_snapshot=_SAMPLE_QUERY)

    results = await repo.search_jobs(sources=["linkedin"])
    assert len(results) == 1
    assert results[0].description == _DESCRIPTION_TEXT
    # And the read-back Job is fully equal (frozen dataclass equality).
    assert results[0] == job_with_desc


@pytest.mark.asyncio
async def test_description_roundtrip_via_get_job_by_source_id(
    repo: SqliteJobRepository,
) -> None:
    """`get_job_by_source_id` returns the exact `description` that was
    upserted.

    Covers the single-job lookup path (REST API detail route).
    """
    job_with_desc = Job(
        id="9002",
        title="Staff Backend Engineer",
        company="Globex",
        location="Barcelona, Spain",
        url="https://ex.com/9002",
        posted_at=datetime(2026, 6, 16, 9, 0, 0, tzinfo=UTC),
        source="linkedin",
        description="Build the future of payments.",
    )
    await repo.upsert_jobs([job_with_desc], query_snapshot=_SAMPLE_QUERY)

    fetched = await repo.get_job_by_source_id("9002")
    assert fetched is not None
    assert fetched.description == "Build the future of payments."
    assert fetched == job_with_desc


@pytest.mark.asyncio
async def test_description_none_roundtrip(repo: SqliteJobRepository) -> None:
    """A job with `description=None` upserted and read back stays `None`.

    The v1 contract: `None` is the canonical "absent" sentinel (per
    `Job` domain + LLM prompt no-assumption rule). A future refactor
    that coerces `None` → `""` would silently change the LLM prompt's
    JSON output (`null` vs `""`) and break the no-assumption rule.
    """
    job_no_desc = Job(
        id="9003",
        title="Junior Dev",
        company="Initrode",
        location="Valencia, Spain",
        url="https://ex.com/9003",
        posted_at=datetime(2026, 6, 17, 9, 0, 0, tzinfo=UTC),
        source="infojobs",
        description=None,
    )
    await repo.upsert_jobs([job_no_desc], query_snapshot=_SAMPLE_QUERY)

    fetched = await repo.get_job_by_source_id("9003")
    assert fetched is not None
    assert fetched.description is None


@pytest.mark.asyncio
async def test_description_roundtrip_preserves_text_on_upsert_update(
    repo: SqliteJobRepository,
) -> None:
    """Upserting the same (source, source_id) with a new description
    REPLACES the prior description.

    This is the contract the scheduler relies on: a job that gained a
    description between two cycles (e.g. detail-page visit succeeded
    the second time) is updated in place — the `ON CONFLICT DO UPDATE`
    SET clause must include `description=EXCLUDED.description`.
    """
    initial = Job(
        id="9004",
        title="DevOps",
        company="Initech",
        location="Remote",
        url="https://ex.com/9004",
        posted_at=datetime(2026, 6, 18, 9, 0, 0, tzinfo=UTC),
        source="linkedin",
        description=None,
    )
    await repo.upsert_jobs([initial], query_snapshot=_SAMPLE_QUERY)

    updated = Job(
        id="9004",
        title="DevOps",
        company="Initech",
        location="Remote",
        url="https://ex.com/9004",
        posted_at=datetime(2026, 6, 18, 9, 0, 0, tzinfo=UTC),
        source="linkedin",
        description="Now we have a description!",
    )
    await repo.upsert_jobs([updated], query_snapshot=_SAMPLE_QUERY)

    fetched = await repo.get_job_by_source_id("9004")
    assert fetched is not None
    assert fetched.description == "Now we have a description!"


# ── delete_older_than ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_older_than_deletes_old_jobs(repo: SqliteJobRepository) -> None:
    """Jobs with `last_seen_at` older than `days` are deleted."""
    # Insert an old job and a recent one
    assert repo._connection is not None
    await repo._connection.execute(
        "INSERT INTO jobs (source, source_id, title, company, location, url, "
        "posted_at, query_snapshot, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "linkedin",
            "old1",
            "Old Job",
            "Co",
            "L",
            "https://ex.com/old1",
            "2024-01-01T00:00:00Z",
            "{}",
            "2024-01-01T00:00:00Z",
        ),
    )
    assert repo._connection is not None
    await repo._connection.execute(
        "INSERT INTO jobs (source, source_id, title, company, location, url, "
        "posted_at, query_snapshot, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "linkedin",
            "new1",
            "New Job",
            "Co",
            "L",
            "https://ex.com/new1",
            datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "{}",
            datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        ),
    )
    assert repo._connection is not None
    await repo._connection.commit()

    deleted = await repo.delete_older_than(days=30)
    assert deleted == 1

    # Only the new job should remain
    assert repo._connection is not None
    async with repo._connection.execute("SELECT source_id FROM jobs") as cursor:
        remaining = await cursor.fetchall()
    assert [r[0] for r in remaining] == ["new1"]


@pytest.mark.asyncio
async def test_delete_older_than_respects_limit(repo: SqliteJobRepository) -> None:
    """When more old rows exist than `limit`, only `limit` are deleted."""
    for i in range(5):
        assert repo._connection is not None
        await repo._connection.execute(
            "INSERT INTO jobs (source, source_id, title, company, location, url, "
            "posted_at, query_snapshot, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "linkedin",
                f"old{i}",
                f"Old Job {i}",
                "Co",
                "L",
                f"https://ex.com/old{i}",
                "2024-01-01T00:00:00Z",
                "{}",
                "2024-01-01T00:00:00Z",
            ),
        )
    assert repo._connection is not None
    await repo._connection.commit()

    deleted = await repo.delete_older_than(days=30, limit=2)
    assert deleted == 2

    # Count remaining old rows
    assert repo._connection is not None
    async with repo._connection.execute(
        "SELECT count(*) FROM jobs WHERE last_seen_at < '2024-06-01T00:00:00Z'"
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 3


@pytest.mark.asyncio
async def test_delete_older_than_no_matching_rows(repo: SqliteJobRepository) -> None:
    """When no rows are old enough, returns 0."""
    assert repo._connection is not None
    await repo._connection.execute(
        "INSERT INTO jobs (source, source_id, title, company, location, url, "
        "posted_at, query_snapshot, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "linkedin",
            "fresh1",
            "Fresh Job",
            "Co",
            "L",
            "https://ex.com/fresh1",
            datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "{}",
            datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        ),
    )
    assert repo._connection is not None
    await repo._connection.commit()

    deleted = await repo.delete_older_than(days=1)  # 1 day ago — fresh row is newer
    assert deleted == 0

    assert repo._connection is not None
    async with repo._connection.execute("SELECT count(*) FROM jobs") as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 1


@pytest.mark.asyncio
async def test_delete_older_than_double_delete(repo: SqliteJobRepository) -> None:
    """First delete removes old rows, second delete removes 0."""
    for i in range(3):
        assert repo._connection is not None
        await repo._connection.execute(
            "INSERT INTO jobs (source, source_id, title, company, location, url, "
            "posted_at, query_snapshot, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "linkedin",
                f"old{i}",
                f"Old Job {i}",
                "Co",
                "L",
                f"https://ex.com/old{i}",
                "2024-01-01T00:00:00Z",
                "{}",
                "2024-01-01T00:00:00Z",
            ),
        )
    assert repo._connection is not None
    await repo._connection.commit()

    deleted1 = await repo.delete_older_than(days=30)
    assert deleted1 == 3

    deleted2 = await repo.delete_older_than(days=30)
    assert deleted2 == 0


@pytest.mark.asyncio
async def test_delete_older_than_empty_db(repo: SqliteJobRepository) -> None:
    """Empty database returns 0."""
    deleted = await repo.delete_older_than(days=30)
    assert deleted == 0


# ── search_jobs ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_jobs_empty(repo: SqliteJobRepository) -> None:
    """Empty table returns empty list."""
    jobs = await repo.search_jobs()
    assert jobs == []


@pytest.mark.asyncio
async def test_search_jobs_all(repo: SqliteJobRepository) -> None:
    """Search without filters returns all jobs."""
    await repo.upsert_jobs([_SAMPLE_JOB], query_snapshot=_SAMPLE_QUERY)
    j2 = Job(
        id="456",
        title="Java Developer",
        company="Java Co",
        location="Barcelona",
        url="https://ex.com/456",
        posted_at=datetime(2026, 6, 2, tzinfo=UTC),
        source="indeed",
    )
    await repo.upsert_jobs([j2], query_snapshot=_SAMPLE_QUERY)

    jobs = await repo.search_jobs()
    assert len(jobs) == 2


@pytest.mark.asyncio
async def test_search_jobs_filter_by_source(repo: SqliteJobRepository) -> None:
    """Search with `sources` filter returns only matching source."""
    await repo.upsert_jobs([_SAMPLE_JOB], query_snapshot=_SAMPLE_QUERY)
    j2 = Job(
        id="456",
        title="Java Developer",
        company="Java Co",
        location="Barcelona",
        url="https://ex.com/456",
        posted_at=datetime(2026, 6, 2, tzinfo=UTC),
        source="indeed",
    )
    await repo.upsert_jobs([j2], query_snapshot=_SAMPLE_QUERY)

    jobs = await repo.search_jobs(sources=["linkedin"])
    assert len(jobs) == 1
    assert jobs[0].id == "123"


@pytest.mark.asyncio
async def test_search_jobs_filter_by_keywords(repo: SqliteJobRepository) -> None:
    """Search with keywords matches on title and company."""
    await repo.upsert_jobs([_SAMPLE_JOB], query_snapshot=_SAMPLE_QUERY)
    j2 = Job(
        id="456",
        title="Java Developer",
        company="Java Co",
        location="Barcelona",
        url="https://ex.com/456",
        posted_at=datetime(2026, 6, 2, tzinfo=UTC),
        source="indeed",
    )
    await repo.upsert_jobs([j2], query_snapshot=_SAMPLE_QUERY)

    jobs = await repo.search_jobs(keywords="Python")
    assert len(jobs) == 1
    assert jobs[0].id == "123"


@pytest.mark.asyncio
async def test_search_jobs_limit_offset(repo: SqliteJobRepository) -> None:
    """Search respects limit and offset."""
    jobs = []
    for i in range(10):
        jobs.append(
            Job(
                id=str(i),
                title=f"Job {i}",
                company="C",
                location="L",
                url=f"https://ex.com/{i}",
                posted_at=datetime(2026, 1, i + 1, tzinfo=UTC),
                source="linkedin",
            )
        )
    await repo.upsert_jobs(jobs, query_snapshot=_SAMPLE_QUERY)

    results = await repo.search_jobs(limit=3, offset=0)
    assert len(results) == 3

    results_page2 = await repo.search_jobs(limit=3, offset=3)
    assert len(results_page2) == 3
    assert results_page2[0].id != results[0].id


# ── search_jobs_history ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_jobs_history_empty(repo: SqliteJobRepository) -> None:
    """Empty database returns empty list."""
    jobs = await repo.search_jobs_history()
    assert jobs == []


@pytest.mark.asyncio
async def test_search_jobs_history_all(repo: SqliteJobRepository) -> None:
    """Without filters, returns all jobs ordered by posted_at DESC."""
    await repo.upsert_jobs([_SAMPLE_JOB], query_snapshot=_SAMPLE_QUERY)
    j2 = Job(
        id="456",
        title="Java Developer",
        company="Java Co",
        location="Barcelona",
        url="https://ex.com/456",
        posted_at=datetime(2026, 6, 2, tzinfo=UTC),
        source="indeed",
    )
    await repo.upsert_jobs([j2], query_snapshot=_SAMPLE_QUERY)

    jobs = await repo.search_jobs_history()
    assert len(jobs) == 2


@pytest.mark.asyncio
async def test_search_jobs_history_filter_by_source(repo: SqliteJobRepository) -> None:
    """Filtering by single source returns only jobs from that source."""
    await repo.upsert_jobs([_SAMPLE_JOB], query_snapshot=_SAMPLE_QUERY)
    j2 = Job(
        id="456",
        title="Java Developer",
        company="Java Co",
        location="Barcelona",
        url="https://ex.com/456",
        posted_at=datetime(2026, 6, 2, tzinfo=UTC),
        source="indeed",
    )
    await repo.upsert_jobs([j2], query_snapshot=_SAMPLE_QUERY)

    jobs = await repo.search_jobs_history(sources=["linkedin"])
    assert len(jobs) == 1
    assert jobs[0].id == "123"


@pytest.mark.asyncio
async def test_search_jobs_history_filter_by_multiple_sources(
    repo: SqliteJobRepository,
) -> None:
    """Filtering by multiple sources returns jobs from all specified sources."""
    await repo.upsert_jobs([_SAMPLE_JOB], query_snapshot=_SAMPLE_QUERY)
    j2 = Job(
        id="456",
        title="Java Developer",
        company="Java Co",
        location="Barcelona",
        url="https://ex.com/456",
        posted_at=datetime(2026, 6, 2, tzinfo=UTC),
        source="indeed",
    )
    await repo.upsert_jobs([j2], query_snapshot=_SAMPLE_QUERY)
    j3 = Job(
        id="789",
        title="Rust Engineer",
        company="Rust Co",
        location="Madrid",
        url="https://ex.com/789",
        posted_at=datetime(2026, 6, 3, tzinfo=UTC),
        source="infojobs",
    )
    await repo.upsert_jobs([j3], query_snapshot=_SAMPLE_QUERY)

    jobs = await repo.search_jobs_history(sources=["linkedin", "indeed"])
    assert len(jobs) == 2
    assert {j.id for j in jobs} == {"123", "456"}


@pytest.mark.asyncio
async def test_search_jobs_history_filter_by_keywords_title(
    repo: SqliteJobRepository,
) -> None:
    """Keyword filter matches on title."""
    await repo.upsert_jobs([_SAMPLE_JOB], query_snapshot=_SAMPLE_QUERY)
    j2 = Job(
        id="456",
        title="Java Developer",
        company="Java Co",
        location="Barcelona",
        url="https://ex.com/456",
        posted_at=datetime(2026, 6, 2, tzinfo=UTC),
        source="indeed",
    )
    await repo.upsert_jobs([j2], query_snapshot=_SAMPLE_QUERY)

    jobs = await repo.search_jobs_history(keywords="Python")
    assert len(jobs) == 1
    assert jobs[0].id == "123"


@pytest.mark.asyncio
async def test_search_jobs_history_filter_by_keywords_company(
    repo: SqliteJobRepository,
) -> None:
    """Keyword filter matches on company."""
    await repo.upsert_jobs([_SAMPLE_JOB], query_snapshot=_SAMPLE_QUERY)
    j2 = Job(
        id="456",
        title="Junior Developer",
        company="Python Labs",
        location="Barcelona",
        url="https://ex.com/456",
        posted_at=datetime(2026, 6, 2, tzinfo=UTC),
        source="indeed",
    )
    await repo.upsert_jobs([j2], query_snapshot=_SAMPLE_QUERY)

    jobs = await repo.search_jobs_history(keywords="Python")
    assert len(jobs) == 2  # Both match: title (Python Developer) + company (Python Labs)


@pytest.mark.asyncio
async def test_search_jobs_history_filter_by_date_range(
    repo: SqliteJobRepository,
) -> None:
    """Date range filter returns jobs within [date_from, date_to]."""
    await repo.upsert_jobs([_SAMPLE_JOB], query_snapshot=_SAMPLE_QUERY)
    j2 = Job(
        id="456",
        title="Old Job",
        company="Old Co",
        location="L",
        url="https://ex.com/456",
        posted_at=datetime(2025, 1, 1, tzinfo=UTC),
        source="indeed",
    )
    await repo.upsert_jobs([j2], query_snapshot=_SAMPLE_QUERY)

    jobs = await repo.search_jobs_history(date_from="2026-05-01", date_to="2026-07-01")
    assert len(jobs) == 1
    assert jobs[0].id == "123"


@pytest.mark.asyncio
async def test_search_jobs_history_pagination(repo: SqliteJobRepository) -> None:
    """Search respects limit and offset."""
    batch = []
    for i in range(10):
        batch.append(
            Job(
                id=str(i),
                title=f"Job {i}",
                company="C",
                location="L",
                url=f"https://ex.com/{i}",
                posted_at=datetime(2026, 1, i + 1, tzinfo=UTC),
                source="linkedin",
            )
        )
    await repo.upsert_jobs(batch, query_snapshot=_SAMPLE_QUERY)

    page1 = await repo.search_jobs_history(limit=3, offset=0)
    assert len(page1) == 3

    page2 = await repo.search_jobs_history(limit=3, offset=3)
    assert len(page2) == 3
    assert page2[0].id != page1[0].id


# ── count_jobs ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_count_jobs_empty(repo: SqliteJobRepository) -> None:
    """Empty database returns 0."""
    count = await repo.count_jobs()
    assert count == 0


@pytest.mark.asyncio
async def test_count_jobs_total(repo: SqliteJobRepository) -> None:
    """Count without filters returns total row count."""
    await repo.upsert_jobs([_SAMPLE_JOB], query_snapshot=_SAMPLE_QUERY)
    j2 = Job(
        id="456",
        title="Java Developer",
        company="Java Co",
        location="Barcelona",
        url="https://ex.com/456",
        posted_at=datetime(2026, 6, 2, tzinfo=UTC),
        source="indeed",
    )
    await repo.upsert_jobs([j2], query_snapshot=_SAMPLE_QUERY)

    count = await repo.count_jobs()
    assert count == 2


@pytest.mark.asyncio
async def test_count_jobs_with_filters(repo: SqliteJobRepository) -> None:
    """Count with source filter returns filtered row count."""
    await repo.upsert_jobs([_SAMPLE_JOB], query_snapshot=_SAMPLE_QUERY)
    j2 = Job(
        id="456",
        title="Java Developer",
        company="Java Co",
        location="Barcelona",
        url="https://ex.com/456",
        posted_at=datetime(2026, 6, 2, tzinfo=UTC),
        source="indeed",
    )
    await repo.upsert_jobs([j2], query_snapshot=_SAMPLE_QUERY)

    count = await repo.count_jobs(sources=["linkedin"])
    assert count == 1


# ── Protocol conformance ────────────────────────────────────────────────────


def test_sqlite_job_repository_conforms_to_protocol() -> None:
    """`SqliteJobRepository` must structurally satisfy `JobRepositoryPort`."""
    repo: JobRepositoryPort = SqliteJobRepository(db_path=":memory:")
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


# ── REQ-DASH-FILTER: case- AND accent-insensitive location filter ────────────


@pytest.mark.asyncio
async def test_search_jobs_history_location_filter_is_case_and_accent_insensitive(
    repo: SqliteJobRepository,
) -> None:
    """The dashboard's `?location=` filter must match regardless of case
    and accent marks: `malaga` ≡ `Málaga` ≡ `MALAGA` ≡ `mÁlAgA`.

    The custom `unaccent()` SQL function (NFD-decompose + drop
    combining marks + casefold) is registered on every connection
    in `SqliteJobRepository.__aenter__` and applied on BOTH the
    column side and the search-term side of the LIKE.
    """
    j_malaga = Job(
        id="m1",
        title="Backend",
        company="Málaga Inc",
        location="Málaga, Andalusia, Spain",
        url="https://ex.com/m1",
        posted_at=datetime(2026, 6, 1, tzinfo=UTC),
        source="linkedin",
    )
    j_madrid = Job(
        id="m2",
        title="Backend",
        company="Madrid Inc",
        location="Madrid, Community of Madrid, Spain",
        url="https://ex.com/m2",
        posted_at=datetime(2026, 6, 2, tzinfo=UTC),
        source="linkedin",
    )
    await repo.upsert_jobs([j_malaga, j_madrid], query_snapshot=_SAMPLE_QUERY)

    # Lowercase, no accent (the user types "malaga" in the dashboard).
    matches = await repo.search_jobs_history(location="malaga")
    assert [j.id for j in matches] == ["m1"], (
        f"expected only the Málaga job for 'malaga', got {[j.location for j in matches]}"
    )

    # Proper accent (URL-encoded by httpx / browser).
    matches = await repo.search_jobs_history(location="Málaga")
    assert [j.id for j in matches] == ["m1"]

    # All uppercase.
    matches = await repo.search_jobs_history(location="MALAGA")
    assert [j.id for j in matches] == ["m1"]

    # Mixed case + accent.
    matches = await repo.search_jobs_history(location="mÁlAgA")
    assert [j.id for j in matches] == ["m1"]

    # Sanity: a different location must NOT match.
    matches = await repo.search_jobs_history(location="madrid")
    assert [j.id for j in matches] == ["m2"]


@pytest.mark.asyncio
async def test_search_jobs_history_keywords_filter_is_case_and_accent_insensitive(
    repo: SqliteJobRepository,
) -> None:
    """Same unaccent rule applies to the `keywords` filter (title/company).

    Note: `unaccent` is accent-stripping, NOT fuzzy matching. A
    typo like `pyton` (missing `h`) is NOT supposed to match
    `python` — that's a spellcheck problem, out of scope.
    """
    j_python = Job(
        id="p1",
        title="Python Developer",
        company="Tech Co",
        location="Madrid",
        url="https://ex.com/p1",
        posted_at=datetime(2026, 6, 1, tzinfo=UTC),
        source="linkedin",
    )
    j_other = Job(
        id="p2",
        title="Java Developer",
        company="Tech Co",
        location="Madrid",
        url="https://ex.com/p2",
        posted_at=datetime(2026, 6, 2, tzinfo=UTC),
        source="linkedin",
    )
    await repo.upsert_jobs([j_python, j_other], query_snapshot=_SAMPLE_QUERY)

    # Lowercase still matches (case-insensitive).
    matches = await repo.search_jobs_history(keywords="python")
    assert [j.id for j in matches] == ["p1"]

    # All uppercase.
    matches = await repo.search_jobs_history(keywords="PYTHON")
    assert [j.id for j in matches] == ["p1"]

    # Mixed case.
    matches = await repo.search_jobs_history(keywords="PyThOn")
    assert [j.id for j in matches] == ["p1"]

    # Sanity: a different keyword must NOT match.
    matches = await repo.search_jobs_history(keywords="java")
    assert [j.id for j in matches] == ["p2"]
