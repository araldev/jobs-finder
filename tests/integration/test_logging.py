"""Integration tests for the log / request_id correlation.

Spec: REQ-020 (sub-scenario: "request_id correlates with logs"). A
request that triggers a 502 MUST produce at least one log record whose
`request_id` attribute matches the value the client sent in
`X-Request-Id` AND that ended up in the response body.

The plumbing (`RequestIdMiddleware` + `RequestIdLogFilter` +
`configure_logging`) is wired inside `build_app`. The
`LogOnRequestMiddleware` (added in this batch) emits a structured
`INFO` line per request, which is what the test matches.
"""

from __future__ import annotations

import logging

import httpx
import pytest

from jobs_finder.application.usecases.search_linkedin_jobs import (
    SearchLinkedInJobsUseCase,
)
from jobs_finder.infrastructure.linkedin.exceptions import (
    LinkedInBlockedError,
    LinkedInTimeoutError,
)
from jobs_finder.presentation.app_factory import build_app

from .test_api import FakeJobSearchPort


async def test_request_id_correlates_with_log_records(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 502 with a known `X-Request-Id` produces a log record with the same id.

    Spec: REQ-020 sub-scenario. The test:
      1. Triggers a 502 by injecting a `FakeJobSearchPort` that raises
         `LinkedInBlockedError`.
      2. Sends `X-Request-Id: corr-test-123`.
      3. Asserts the response header echoes the same id.
      4. Asserts the response body's `request_id` matches.
      5. Asserts at least one captured log record carries the same
         `request_id` attribute (injected by `RequestIdLogFilter`).
    """
    fake_port = FakeJobSearchPort(error=LinkedInBlockedError("auth wall"))
    app = build_app(use_case=SearchLinkedInJobsUseCase(port=fake_port))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        with caplog.at_level(logging.INFO, logger="jobs_finder"):
            response = await ac.get(
                "/jobs/linkedin?keywords=python&location=madrid",
                headers={"X-Request-Id": "corr-test-123"},
            )

    # 1) 502 with masked detail.
    assert response.status_code == 502
    body = response.json()
    assert body["detail"] == "upstream source unavailable"

    # 2) Header echo.
    assert response.headers.get("X-Request-Id") == "corr-test-123"

    # 3) Body correlation.
    assert body["request_id"] == "corr-test-123"

    # 4) At least one log record carries the same request_id attribute.
    #    The `RequestIdLogFilter` injects the ContextVar value as
    #    `record.request_id`; `LogOnRequestMiddleware` emits the
    #    actual log line that proves the plumbing is wired.
    matching = [r for r in caplog.records if getattr(r, "request_id", None) == "corr-test-123"]
    assert matching, (
        f"No log record with request_id='corr-test-123' was emitted. "
        f"Captured records: "
        f"{[(r.name, getattr(r, 'request_id', None)) for r in caplog.records]}"
    )


async def test_jobsearch_error_handler_logs_exception_class(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The 502 handler must emit a WARNING log with the exception class name.

    Operationally, when the live path fails the response is correctly
    masked (`"upstream source unavailable"`) but the operator MUST be
    able to tell from the server log whether it was a timeout, an
    auth-wall, a parse error, or something unexpected. This is the
    spec's REQ-006 + REQ-020 contract: structured logs surface the
    cause, the client only sees a stable opaque message.

    The test triggers two distinct upstream errors (timeout, blocked)
    and asserts each one is logged with its concrete class name.
    """
    app = build_app(
        use_case=SearchLinkedInJobsUseCase(
            port=FakeJobSearchPort(error=LinkedInTimeoutError("timeout waiting")),
        ),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        with caplog.at_level(logging.WARNING, logger="jobs_finder"):
            response_timeout = await ac.get(
                "/jobs/linkedin?keywords=python&location=madrid",
            )

    # Response is still masked; the operator sees the cause in the log.
    assert response_timeout.status_code == 502
    assert response_timeout.json()["detail"] == "upstream source unavailable"

    # The server log carries the concrete class name.
    timeout_records = [
        r
        for r in caplog.records
        if r.levelname == "WARNING" and "LinkedInTimeoutError" in r.getMessage()
    ]
    assert timeout_records, (
        f"No WARNING log mentions LinkedInTimeoutError. Got: "
        f"{[(r.levelname, r.getMessage()) for r in caplog.records]}"
    )

    # Now a different exception: must surface a different class name.
    caplog.clear()
    app_blocked = build_app(
        use_case=SearchLinkedInJobsUseCase(
            port=FakeJobSearchPort(error=LinkedInBlockedError("auth wall")),
        ),
    )
    transport_blocked = httpx.ASGITransport(app=app_blocked)
    async with httpx.AsyncClient(transport=transport_blocked, base_url="http://test") as ac:
        with caplog.at_level(logging.WARNING, logger="jobs_finder"):
            response_blocked = await ac.get(
                "/jobs/linkedin?keywords=python&location=madrid",
            )

    assert response_blocked.status_code == 502
    blocked_records = [
        r
        for r in caplog.records
        if r.levelname == "WARNING" and "LinkedInBlockedError" in r.getMessage()
    ]
    assert blocked_records, (
        f"No WARNING log mentions LinkedInBlockedError. Got: "
        f"{[(r.levelname, r.getMessage()) for r in caplog.records]}"
    )
