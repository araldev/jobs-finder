"""Tests for `JobRepositoryPort` Protocol in `application/ports.py`.

Spec: REQ-DB-001 — the Protocol must have 3 async methods
(`upsert_jobs`, `search_jobs`, `close`) and use structural subtyping
(no `@runtime_checkable`). Mypy --strict enforces structural
conformance at type-check time; these tests verify the Protocol's
shape at runtime + mypy structural conformance via a test helper.

`scheduler-retention-history` adds `delete_older_than` (REQ-DB-001 MODIFIED).
"""

from __future__ import annotations

from typing import Protocol

import pytest

from jobs_finder.application.ports import JobRepositoryPort
from jobs_finder.domain.job import Job


class _TestConcreteRepository:
    """A minimal class that satisfies `JobRepositoryPort` structurally."""

    async def upsert_jobs(
        self, jobs: list[Job], source: str, query_snapshot: dict[str, str]
    ) -> int:
        return 0

    async def search_jobs(
        self,
        keywords: str | None = None,
        sources: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        return []

    async def delete_older_than(self, *, days: int, limit: int = 1000) -> int:
        return 0

    async def close(self) -> None:
        return None


def test_job_repository_port_is_protocol() -> None:
    """`JobRepositoryPort` must be a `typing.Protocol` subclass."""
    assert issubclass(JobRepositoryPort, Protocol)


def test_job_repository_port_has_upsert_jobs() -> None:
    """The Protocol must declare `upsert_jobs`."""
    assert hasattr(JobRepositoryPort, "upsert_jobs")


def test_job_repository_port_has_search_jobs() -> None:
    """The Protocol must declare `search_jobs`."""
    assert hasattr(JobRepositoryPort, "search_jobs")


def test_job_repository_port_has_close() -> None:
    """The Protocol must declare `close`."""
    assert hasattr(JobRepositoryPort, "close")


# ── REQ-DB-001 (MODIFIED): delete_older_than ───────────────────────────────


def test_job_repository_port_has_delete_older_than() -> None:
    """The Protocol must declare `delete_older_than`."""
    assert hasattr(JobRepositoryPort, "delete_older_than")


# ── Structural conformance ──────────────────────────────────────────────────


def test_concrete_class_conforms_structurally() -> None:
    """A class with the right method signatures satisfies the Protocol.

    This is a runtime assertion; mypy --strict enforces the same
    conformance at type-check time. We verify the assignment works
    without error at runtime (REQ-DB-001 scenario 1).
    """
    repo: JobRepositoryPort = _TestConcreteRepository()
    assert repo is not None


def test_protocol_not_runtime_checkable() -> None:
    """The Protocol MUST NOT use `@runtime_checkable`.

    Structural subtyping is enforced by mypy --strict only.
    `isinstance` checks against the Protocol MUST raise TypeError
    because there's no `@runtime_checkable`.
    """
    repo = _TestConcreteRepository()
    with pytest.raises(TypeError, match="runtime_checkable"):
        isinstance(repo, JobRepositoryPort)  # type: ignore[arg-type]
