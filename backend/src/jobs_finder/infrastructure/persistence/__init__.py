"""Persistent job storage infrastructure (background-scheduler-persistence).

The `persistence` package provides an `aiosqlite`-backed implementation of
`JobRepositoryPort` (`SqliteJobRepository` in
`sqlite_job_repository.py`) and the corresponding schema
(REQ-DB-002, REQ-DB-003, REQ-DB-004).
"""
