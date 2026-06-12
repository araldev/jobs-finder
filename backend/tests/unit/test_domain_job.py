"""Tests for `Job` domain object — Phase 1 of `scheduler-source-fix`.

Verifies the `source: str` field added in Task 1.1 propagates correctly.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jobs_finder.domain.job import Job


class TestJobSourceField:
    """Tests for the `source` field on `Job` dataclass."""

    @pytest.mark.parametrize(
        "source_name",
        [
            pytest.param("linkedin", id="linkedin"),
            pytest.param("indeed", id="indeed"),
            pytest.param("infojobs", id="infojobs"),
        ],
    )
    def test_job_constructs_with_source(self, source_name: str) -> None:
        """`Job(...)` with `source` kwarg constructs without error."""
        job = Job(
            id="123",
            title="Python Developer",
            company="Tech Co",
            location="Madrid",
            url="https://example.com/job/123",
            posted_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
            source=source_name,
        )
        assert job.source == source_name

    def test_job_source_is_required(self) -> None:
        """`Job` without `source` raises TypeError."""
        with pytest.raises(TypeError):
            Job(  # type: ignore[call-arg]
                id="123",
                title="Python Developer",
                company="Tech Co",
                location="Madrid",
                url="https://example.com/job/123",
                posted_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
            )

    def test_job_source_preserves_other_fields(self) -> None:
        """Adding `source` does not affect other field values."""
        job = Job(
            id="789",
            title="Senior Engineer",
            company="BigCo",
            location="Valencia",
            url="https://example.com/789",
            posted_at=datetime(2026, 3, 15, 9, 0, 0, tzinfo=UTC),
            source="indeed",
            description="Great opportunity",
        )
        assert job.source == "indeed"
        assert job.title == "Senior Engineer"
        assert job.company == "BigCo"
        assert job.description == "Great opportunity"

    def test_job_source_with_none_description(self) -> None:
        """`source` works when `description` is not passed (uses default None)."""
        job = Job(
            id="555",
            title="Backend Dev",
            company="Startup",
            location="Barcelona",
            url="https://example.com/555",
            posted_at=datetime(2026, 4, 1, tzinfo=UTC),
            source="infojobs",
        )
        assert job.source == "infojobs"
        assert job.description is None
