"""Tests for the scheduler & persistence settings fields.

Spec: REQ-CFG-001. 5 new fields: `db_path`, `scheduler_enabled`,
`scheduler_min_interval_seconds`, `scheduler_max_interval_seconds`,
`scheduler_queries`. All use `AliasChoices` so they read from both
UPPER and lower env var names.
"""

from __future__ import annotations

import pytest

from jobs_finder.infrastructure.config import Settings


def test_db_path_default() -> None:
    """`db_path` defaults to `"jobs.db"`."""
    s = Settings()
    assert s.db_path == "jobs.db"


def test_db_path_from_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """`DB_PATH` env var overrides the default."""
    monkeypatch.setenv("DB_PATH", "/tmp/test.db")
    s = Settings()
    assert s.db_path == "/tmp/test.db"


def test_db_path_programmatic() -> None:
    """Programmatic construction via `db_path` works."""
    s = Settings(db_path="custom.db")
    assert s.db_path == "custom.db"


def test_scheduler_enabled_default() -> None:
    """`scheduler_enabled` defaults to `False`."""
    s = Settings()
    assert s.scheduler_enabled is False


def test_scheduler_enabled_from_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """`SCHEDULER_ENABLED=true` sets the field to `True`."""
    monkeypatch.setenv("SCHEDULER_ENABLED", "true")
    s = Settings()
    assert s.scheduler_enabled is True


def test_scheduler_min_interval_default() -> None:
    """`scheduler_min_interval_seconds` defaults to 1500.0."""
    s = Settings()
    assert s.scheduler_min_interval_seconds == 1500.0


def test_scheduler_max_interval_default() -> None:
    """`scheduler_max_interval_seconds` defaults to 2100.0."""
    s = Settings()
    assert s.scheduler_max_interval_seconds == 2100.0


def test_scheduler_queries_default() -> None:
    """`scheduler_queries` defaults to a single query for 'desarrollador' in 'España'."""
    s = Settings()
    assert s.scheduler_queries == [{"keywords": "desarrollador", "location": "España"}]


def test_scheduler_queries_from_json_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """`SCHEDULER_QUERIES` JSON env var parses correctly."""
    monkeypatch.setenv(
        "SCHEDULER_QUERIES",
        '[{"keywords": "python", "location": "Madrid"}]',
    )
    s = Settings()
    assert s.scheduler_queries == [{"keywords": "python", "location": "Madrid"}]


def test_scheduler_queries_programmatic() -> None:
    """Programmatic construction via `scheduler_queries` works."""
    s = Settings(scheduler_queries=[{"keywords": "java", "location": "Barcelona"}])
    assert s.scheduler_queries == [{"keywords": "java", "location": "Barcelona"}]


def test_all_scheduler_fields_have_alias_choices() -> None:
    """Each new field must have a `validation_alias` with `AliasChoices`.

    We verify this by constructing via the UPPER env var name.
    """
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("DB_PATH", "env.db")
    monkeypatch.setenv("SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("SCHEDULER_MIN_INTERVAL_SECONDS", "100.0")
    monkeypatch.setenv("SCHEDULER_MAX_INTERVAL_SECONDS", "200.0")
    monkeypatch.setenv(
        "SCHEDULER_QUERIES",
        '[{"keywords": "test", "location": "Valencia"}]',
    )
    s = Settings()
    assert s.db_path == "env.db"
    assert s.scheduler_enabled is True
    assert s.scheduler_min_interval_seconds == 100.0
    assert s.scheduler_max_interval_seconds == 200.0
    assert s.scheduler_queries == [{"keywords": "test", "location": "Valencia"}]
    monkeypatch.undo()
