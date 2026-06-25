"""Unit tests for the structured logging configuration.

Spec: REQ-006. The service emits structured JSON logs by default. A
`plain` log format is available as a fallback for development. The
JSON formatter is built with stdlib only (no `python-json-logger`).
The field set is locked to `{timestamp, level, name, message,
request_id}`.

The tests install `configure_logging` against a `StringIO` stream so
the formatted output can be inspected without going through the real
stderr.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Generator
from io import StringIO

import pytest

from jobs_finder.infrastructure.config import Settings
from jobs_finder.presentation.logging_config import configure_logging


@pytest.fixture
def restore_root_logger() -> Generator[None, None, None]:
    """Restore the root logger's handlers/level after the test.

    `configure_logging` mutates the GLOBAL root logger. Without this
    fixture the JSON handler would leak into other tests.
    """
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    original_filters = list(root.filters)
    try:
        yield
    finally:
        root.handlers = original_handlers
        root.level = original_level
        root.filters = original_filters


def test_configure_logging_json_format_emits_valid_json(
    restore_root_logger: None,
) -> None:
    """A log line under `log_format='json'` is valid JSON with the base field set.

    Spec: REQ-006. The base field set is always present:
        {timestamp, level, name, message, request_id}

    When the caller passes `extra={...}`, those fields appear in an
    `"extra"` sub-object.
    """
    stream = StringIO()
    settings = Settings(log_format="json", log_level="INFO")

    configure_logging(settings, stream=stream)
    logging.getLogger("jobs_finder.test").info("hello world")

    # The handler flushes on emit; pull the single line and parse it.
    output = stream.getvalue().strip()
    assert output, "configure_logging should have produced a log line"

    record = json.loads(output)
    assert record["level"] == "INFO"
    assert record["message"] == "hello world"
    assert record["name"] == "jobs_finder.test"
    assert "timestamp" in record
    # The request_id is injected by RequestIdLogFilter; in this unit test
    # the ContextVar is unset so the filter inserts the "-" placeholder.
    assert "request_id" in record
    # Without extra={...}, there is no "extra" key.
    assert "extra" not in record


def test_configure_logging_json_format_includes_extra_fields(
    restore_root_logger: None,
) -> None:
    """`extra={...}` fields from logger calls appear in the JSON `"extra"` sub-object.

    The aggregator emits structured fields like ``source`` and
    ``error_type`` via ``extra={...}``. Those fields MUST be
    serialised so ops tooling can group by source without parsing
    the message string.
    """
    stream = StringIO()
    settings = Settings(log_format="json", log_level="INFO")

    configure_logging(settings, stream=stream)
    logging.getLogger("jobs_finder.test").warning(
        "aggregator source failed",
        extra={"source": "linkedin", "error_type": "LinkedInTimeoutError"},
    )

    output = stream.getvalue().strip()
    assert output, "configure_logging should have produced a log line"

    record = json.loads(output)
    assert record["extra"]["source"] == "linkedin"
    assert record["extra"]["error_type"] == "LinkedInTimeoutError"


def test_configure_logging_plain_format_emits_non_json(
    restore_root_logger: None,
) -> None:
    """A log line under `log_format='plain'` is NOT valid JSON.

    The `plain` mode uses stdlib's default `Formatter` for human-readable
    output during development.
    """
    stream = StringIO()
    settings = Settings(log_format="plain", log_level="INFO")

    configure_logging(settings, stream=stream)
    logging.getLogger("jobs_finder.test").info("plain text")

    output = stream.getvalue().strip()
    assert output, "configure_logging should have produced a log line"

    # Plain mode emits key=value-ish text, not a single JSON object.
    with pytest.raises(json.JSONDecodeError):
        json.loads(output)
    # Sanity: the message is in the output.
    assert "plain text" in output


def test_configure_logging_sets_root_log_level(
    restore_root_logger: None,
) -> None:
    """`configure_logging` sets the root logger level from `settings.log_level`."""
    settings = Settings(log_format="json", log_level="WARNING")
    configure_logging(settings, stream=StringIO())

    assert logging.getLogger().level == logging.WARNING


def test_configure_logging_is_idempotent(
    restore_root_logger: None,
) -> None:
    """Calling `configure_logging` twice does NOT stack duplicate handlers.

    Tests that exercise the same app twice (e.g. `client` fixture is
    function-scoped, but multiple `build_app` calls in the same test)
    must not accumulate handlers.

    The assertion counts only `configure_logging`-owned handlers
    (marked with the `_jobs_finder_owned_by_configure_logging`
    attribute); pytest adds its own capture/file handlers to the
    root logger and those are out of scope.
    """
    stream = StringIO()
    settings = Settings(log_format="json", log_level="INFO")

    configure_logging(settings, stream=stream)
    configure_logging(settings, stream=stream)

    owned = [
        h
        for h in logging.getLogger().handlers
        if getattr(h, "_jobs_finder_owned_by_configure_logging", False)
    ]
    assert len(owned) == 1
