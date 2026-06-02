"""Exception handlers for the FastAPI app.

Spec: REQ-020.
- `JobSearchError` (and every subclass) -> 502 with a MASKED detail
  (`"upstream source unavailable"`) and the request id. The original
  exception type and message are NEVER included in the response.
- `RequestValidationError` (FastAPI's pydantic validation) -> 422 with
  FastAPI's default `{"detail": [...errors...]}` shape.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from jobs_finder.domain.exceptions import JobSearchError

UPSTREAM_UNAVAILABLE_DETAIL = "upstream source unavailable"


def _request_id(request: Request) -> str:
    """Return the request id set by `RequestIdMiddleware`; empty if missing."""
    value = getattr(request.state, "request_id", None)
    return str(value) if value is not None else ""


async def jobsearch_error_handler(request: Request, exc: JobSearchError) -> JSONResponse:
    """Translate any `JobSearchError` to a 502 with masked detail.

    The body's `request_id` correlates with the response header and with
    the log line emitted by the same request (REQ-020).
    """
    return JSONResponse(
        status_code=502,
        content={
            "detail": UPSTREAM_UNAVAILABLE_DETAIL,
            "request_id": _request_id(request),
        },
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Translate a `RequestValidationError` to a 422 with FastAPI's default shape."""
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Wire the documented handlers onto the given app instance."""
    # FastAPI's add_exception_handler expects handlers typed against
    # `Exception`; our narrow signatures are intentional and correct.
    app.add_exception_handler(JobSearchError, jobsearch_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
