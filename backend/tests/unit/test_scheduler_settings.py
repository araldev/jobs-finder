"""Tests for the scheduler & persistence settings fields.

Spec: REQ-CFG-001. 5 new fields: `db_path`, `scheduler_enabled`,
`scheduler_min_interval_seconds`, `scheduler_max_interval_seconds`,
`scheduler_queries`. All use `AliasChoices` so they read from both
UPPER and lower env var names.

`scheduler-retention-history` adds `retention_days: int = 0`
(REQ-RET-001).
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
    """`scheduler_queries` code default is a 30-entry IT-keyword × city matrix.

    Per the deliberate config change tracked in Q6 of the
    `refactor-pre-existing-baseline-debt` change — the
    scheduler now scrapes 10 IT keywords × 3 cities
    (Madrid, Barcelona, Málaga) for a richer dataset than
    the previous 3 location-only entries. See
    `config.py:1430-1467` for the canonical list.

    `_env_file=None` forces pydantic-settings to ignore the
    operator's local `.env` (which may override
    `SCHEDULER_QUERIES`).
    """
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.scheduler_queries == [
        # Madrid - IT keywords
        {"keywords": "React", "location": "Madrid"},
        {"keywords": "TypeScript", "location": "Madrid"},
        {"keywords": "Python", "location": "Madrid"},
        {"keywords": "Node.js", "location": "Madrid"},
        {"keywords": "DevOps", "location": "Madrid"},
        {"keywords": "AWS", "location": "Madrid"},
        {"keywords": "Docker", "location": "Madrid"},
        {"keywords": "Full Stack", "location": "Madrid"},
        {"keywords": "Backend", "location": "Madrid"},
        {"keywords": "Frontend", "location": "Madrid"},
        # Barcelona - IT keywords
        {"keywords": "React", "location": "Barcelona"},
        {"keywords": "TypeScript", "location": "Barcelona"},
        {"keywords": "Python", "location": "Barcelona"},
        {"keywords": "Node.js", "location": "Barcelona"},
        {"keywords": "DevOps", "location": "Barcelona"},
        {"keywords": "AWS", "location": "Barcelona"},
        {"keywords": "Docker", "location": "Barcelona"},
        {"keywords": "Full Stack", "location": "Barcelona"},
        {"keywords": "Backend", "location": "Barcelona"},
        {"keywords": "Frontend", "location": "Barcelona"},
        # Málaga - IT keywords
        {"keywords": "React", "location": "Málaga"},
        {"keywords": "TypeScript", "location": "Málaga"},
        {"keywords": "Python", "location": "Málaga"},
        {"keywords": "Node.js", "location": "Málaga"},
        {"keywords": "DevOps", "location": "Málaga"},
        {"keywords": "AWS", "location": "Málaga"},
        {"keywords": "Docker", "location": "Málaga"},
        {"keywords": "Full Stack", "location": "Málaga"},
        {"keywords": "Backend", "location": "Málaga"},
        {"keywords": "Frontend", "location": "Málaga"},
    ]


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


# ── REQ-RET-001: retention_days ────────────────────────────────────────────


def test_retention_days_default() -> None:
    """`retention_days` defaults to 0 (disabled)."""
    s = Settings()
    assert s.retention_days == 0


def test_retention_days_from_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """`RETENTION_DAYS=30` sets the field to 30."""
    monkeypatch.setenv("RETENTION_DAYS", "30")
    s = Settings()
    assert s.retention_days == 30


def test_retention_days_programmatic() -> None:
    """Programmatic construction via `retention_days` works."""
    s = Settings(retention_days=45)
    assert s.retention_days == 45


def test_retention_days_negative_clamps() -> None:
    """Negative `retention_days` is clamped to 0."""
    s = Settings(retention_days=-10)
    assert s.retention_days == 0


def test_retention_days_has_alias_choices() -> None:
    """`retention_days` must read from `RETENTION_DAYS` env var."""
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("RETENTION_DAYS", "90")
    s = Settings()
    assert s.retention_days == 90
    monkeypatch.undo()
