"""Request-id middleware + log filter.

Spec: REQ-020. A `BaseHTTPMiddleware` reads the `X-Request-Id` request
header (or generates a uuid4), stores it on `request.state.request_id`,
echoes it in the response header, and binds it to a `ContextVar` so
log records emitted during the request can carry the same id.

Exception handlers read `request.state.request_id` to correlate masked
error bodies with logs.
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
