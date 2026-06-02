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
from jobs_finder.infrastructure.linkedin.exceptions import LinkedInBlockedError
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
