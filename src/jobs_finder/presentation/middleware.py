"""Request-id middleware + log filter.

Spec: REQ-020. A `BaseHTTPMiddleware` reads the `X-Request-Id` request
header (or generates a uuid4), stores it on `request.state.request_id`,
echoes it in the response header, and binds it to a `ContextVar` so
log records emitted during the request can carry the same id.

Exception handlers read `request.state.request_id` to correlate masked
error bodies with logs.

`LogOnRequestMiddleware` (T-012) emits one INFO line per request on
the `jobs_finder.access` logger. It must be installed INNER of
`RequestIdMiddleware` so the request id is bound to the `ContextVar`
by the time the access log line is rendered.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

REQUEST_ID_HEADER = "X-Request-Id"

# Set by the middleware on entry, reset on exit. Consumed by
# `RequestIdLogFilter` so log records emitted during the request can
# carry the current id. Default is "-" so log records that are NOT
# inside a request still render a placeholder rather than crashing.
_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Return the current request id from the `ContextVar` (or `-`)."""
    return _request_id_var.get()


# Module-level logger for the access log line emitted by
# `LogOnRequestMiddleware`. Reusing a module-level logger (instead
# of one per request) is the standard pattern; pytest's `caplog`
# captures it via propagation to the parent `jobs_finder` logger.
_access_logger = logging.getLogger("jobs_finder.access")


class RequestIdLogFilter(logging.Filter):
    """Inject `request_id` from the ContextVar into every `LogRecord`."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get()
        return True


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Read or generate a request id, store it, and echo it in the response.

    Order in the middleware stack does not matter for this layer — it does
    not need to wrap any other middleware, it only needs to run before the
    route handler executes.
    """

    def __init__(self, app: ASGIApp, header_name: str = REQUEST_ID_HEADER) -> None:
        super().__init__(app)
        self._header: str = header_name

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming = request.headers.get(self._header)
        request_id = incoming if incoming else str(uuid.uuid4())
        request.state.request_id = request_id
        token = _request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            _request_id_var.reset(token)
        response.headers[self._header] = request_id
        return response


class LogOnRequestMiddleware(BaseHTTPMiddleware):
    """Emit one INFO line per request once the response status is known.

    The line is emitted on `jobs_finder.access` and includes the bound
    `request_id` (injected by `RequestIdLogFilter`). The access log
    proves the REQ-020 log correlation wiring end to end: a downstream
    operator can grep one id and see the request, the response, and
    any error logged during processing.

    This middleware MUST be installed INNER of `RequestIdMiddleware`
    (i.e. added to the app BEFORE it in code). Starlette runs
    middlewares outermost-first; if `LogOnRequest` were outer, the
    `ContextVar` would still be unset when it tried to read the id.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        # The ContextVar is still bound to the current request at this
        # point: `RequestIdMiddleware` resets it only in its `finally`,
        # which runs after this middleware's `call_next` returns.
        _access_logger.info(
            "request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
            },
        )
        return response
