"""Unit tests for the `Job` value object and the `from_url` classmethod.

Spec: REQ-007.
Design: `domain/job.py` is a frozen dataclass with id, title, company, location,
url, posted_at. `posted_at` must be timezone-aware (UTC). `id` is derived from
the LinkedIn job URL.
"""

from __future__ import annotations

import ast
import re
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone

import pytest

from jobs_finder.domain.exceptions import DomainError, JobSearchError
from jobs_finder.domain.job import Job


def _aware_utc(year: int = 2026, month: int = 1, day: int = 1) -> datetime:
    """Build a timezone-aware UTC datetime for tests."""
    return datetime(year, month, day, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Construction & invariants
# ---------------------------------------------------------------------------


def test_job_constructs_with_all_fields() -> None:
    """All six fields can be supplied; posted_at tzinfo is preserved."""
    posted = _aware_utc(2026, 5, 1)
    job = Job(
        id="3850000000",
        title="Senior Python Developer",
        company="Acme Corp",
        location="Madrid, Spain",
        url="https://www.linkedin.com/jobs/view/3850000000/",
        posted_at=posted,
    )
    assert job.id == "3850000000"
    assert job.title == "Senior Python Developer"
    assert job.company == "Acme Corp"
    assert job.location == "Madrid, Spain"
    assert job.url == "https://www.linkedin.com/jobs/view/3850000000/"
    assert job.posted_at == posted
    assert job.posted_at.tzinfo is not None


def test_job_rejects_naive_datetime() -> None:
    """A naive `posted_at` (no tzinfo) is rejected in __post_init__."""
    naive = datetime(2026, 5, 1)  # no tzinfo
    with pytest.raises(ValueError, match=re.compile(r"tz|zone|aware|utc", re.IGNORECASE)):
        Job(
            id="1",
            title="t",
            company="c",
            location="l",
            url="https://www.linkedin.com/jobs/view/1/",
            posted_at=naive,
        )


def test_description_default_is_none() -> None:
    """`Job(...)` without a `description` argument defaults to `None`.

    Spec: REQ-JOB-001 — `description: str | None = None` is
    backward-compatible. Pre-existing `Job(...)` constructions that
    omit `description` MUST keep working and MUST yield
    `job.description is None`. The `frozen=True, slots=True`
    contract is preserved.
    """
    job = Job(
        id="100",
        title="t",
        company="c",
        location="l",
        url="https://www.linkedin.com/jobs/view/100/",
        posted_at=_aware_utc(),
    )
    assert job.description is None


def test_description_with_value() -> None:
    """`Job(..., description="text")` stores the value and is included in equality.

    Spec: REQ-JOB-001 — `description` is a first-class field.
    Equality (`==`) MUST include the `description` value: two `Job`s
    that differ only by `description` compare unequal. The field
    survives the round-trip through the dataclass (it is NOT
    dropped, NOT normalized to `""`).
    """
    job = Job(
        id="200",
        title="t",
        company="c",
        location="l",
        url="https://www.linkedin.com/jobs/view/200/",
        posted_at=_aware_utc(),
        description="Senior Python role",
    )
    assert job.description == "Senior Python role"

    other = Job(
        id="200",
        title="t",
        company="c",
        location="l",
        url="https://www.linkedin.com/jobs/view/200/",
        posted_at=_aware_utc(),
        description="Other description",
    )
    assert job != other, "Jobs differing only by description must compare unequal"


def test_job_accepts_other_aware_timezone() -> None:
    """An aware non-UTC tzinfo is acceptable; the spec only forbids naive."""
    # We don't reject non-UTC offsets here — the prompt's strictness is
    # "reject naive" not "force UTC". A run-time coercion to UTC belongs to
    # a higher layer. This test pins the current contract: aware == ok.
    plus_two = timezone(timedelta(hours=2))
    aware = datetime(2026, 5, 1, tzinfo=plus_two)
    job = Job(
        id="2",
        title="t",
        company="c",
        location="l",
        url="https://www.linkedin.com/jobs/view/2/",
        posted_at=aware,
    )
    assert job.posted_at.tzinfo is plus_two


def test_job_is_frozen() -> None:
    """Attempting to mutate any field raises FrozenInstanceError."""
    job = Job(
        id="3",
        title="t",
        company="c",
        location="l",
        url="https://www.linkedin.com/jobs/view/3/",
        posted_at=_aware_utc(),
    )
    with pytest.raises(FrozenInstanceError):
        job.title = "new"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# from_url — happy paths
# ---------------------------------------------------------------------------


def test_from_url_extracts_id_from_canonical_path() -> None:
    """Canonical `https://www.linkedin.com/jobs/view/<id>/` yields the id."""
    assert Job.from_url("https://www.linkedin.com/jobs/view/3850000000/") == "3850000000"


def test_from_url_works_with_query_params() -> None:
    """Path-id is used even when query params are present."""
    url = "https://www.linkedin.com/jobs/view/3850000000/?trk=public_jobs_jobs-search-results_search-card"
    assert Job.from_url(url) == "3850000000"


def test_from_url_works_without_trailing_slash() -> None:
    """A path without the final `/` still yields the id."""
    assert Job.from_url("https://www.linkedin.com/jobs/view/3850000000") == "3850000000"


def test_from_url_extracts_id_from_slugged_path() -> None:
    """LinkedIn's current URL format is `/jobs/view/<slug>-<id>`.

    The slug is a SEO-friendly rewrite; the trailing numeric segment
    is the actual id. Example seen on the public job search:
    `/jobs/view/developer-python-aws-at-plexus-tech-4217873836`.
    """
    url = "https://es.linkedin.com/jobs/view/developer-python-aws-at-plexus-tech-4217873836?position=1&pageNum=0"
    assert Job.from_url(url) == "4217873836"


def test_from_url_slugged_path_works_with_locale_subdomain() -> None:
    """The slug regex must work for `es.linkedin.com`, `www.linkedin.com`, etc."""
    url = "https://es.linkedin.com/jobs/view/python-developer-at-statkraft-4414091381"
    assert Job.from_url(url) == "4414091381"


def test_from_url_falls_back_to_currentJobId_query_param() -> None:  # noqa: N802
    """When the path has no id, `currentJobId=<id>` in the query is used."""
    url = "https://www.linkedin.com/jobs/search/?currentJobId=3850000000&trk=foo"
    assert Job.from_url(url) == "3850000000"


# ---------------------------------------------------------------------------
# from_url — sad paths
# ---------------------------------------------------------------------------


def test_from_url_raises_on_unrecognized_url() -> None:
    """A URL with neither a path id nor a currentJobId query param raises."""
    with pytest.raises(ValueError):
        Job.from_url("https://example.com/not-linkedin/123")


# ---------------------------------------------------------------------------
# from_urn — the primary id extraction path
# ---------------------------------------------------------------------------


def test_from_urn_extracts_id_from_standard_urn() -> None:
    """A `urn:li:jobPosting:<id>` string yields the numeric id."""
    assert Job.from_urn("urn:li:jobPosting:4217873836") == "4217873836"


def test_from_urn_works_when_surrounded_by_other_text() -> None:
    """`from_urn` is permissive about surrounding whitespace / text."""
    assert Job.from_urn("  urn:li:jobPosting:4217873836  ") == "4217873836"


def test_from_urn_raises_on_unrecognized_urn() -> None:
    """A URN that does not match the `urn:li:jobPosting:<id>` shape raises."""
    with pytest.raises(ValueError):
        Job.from_urn("urn:li:fsd_profile:abc123")


# ---------------------------------------------------------------------------
# Base exceptions
# ---------------------------------------------------------------------------


def test_job_search_error_is_domain_error() -> None:
    """JobSearchError subclasses DomainError; both are Exceptions."""
    assert issubclass(JobSearchError, DomainError)
    assert issubclass(DomainError, Exception)


def test_job_search_error_is_raisable() -> None:
    """JobSearchError can be raised with a message and re-raised/caught."""
    with pytest.raises(JobSearchError, match="boom"):
        raise JobSearchError("boom")


# ---------------------------------------------------------------------------
# Compile-time guard: domain does not import infrastructure or presentation.
# ---------------------------------------------------------------------------


def test_domain_module_does_not_import_infra_or_presentation() -> None:
    """Sanity check for the dependency rule: domain is the innermost layer.

    REQ-002: domain MUST NOT import from infrastructure or presentation.
    This is a build-time rule; this test pins it so a regression is caught.

    Uses AST so docstrings and comments that mention "infrastructure" or
    "presentation" do not trip the check.
    """
    import jobs_finder.domain.exceptions as exc_mod  # noqa: PLC0415
    import jobs_finder.domain.job as job_mod  # noqa: PLC0415

    for mod in (job_mod, exc_mod):
        module_file = mod.__file__
        assert module_file is not None
        with open(module_file, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=module_file)
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported.append(node.module)
        joined = " ".join(imported)
        assert "infrastructure" not in joined
        assert "presentation" not in joined
        assert "playwright" not in joined
        assert "fastapi" not in joined
