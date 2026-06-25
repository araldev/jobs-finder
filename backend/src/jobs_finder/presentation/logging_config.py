"""Structured logging configuration.

Spec: REQ-006. The service MUST emit structured JSON logs by default;
a `plain` mode is available for local development. The JSON formatter
is built with the stdlib only (no `python-json-logger`) and the
output field set is locked to:

    {timestamp, level, name, message, request_id}

The `request_id` field is injected into EVERY `LogRecord` by a
`logging.setLogRecordFactory` hook installed in this module. The
factory reads the same `ContextVar` that `RequestIdMiddleware` writes
on every HTTP request, so records emitted inside a request carry
the request id and records emitted outside one (startup, shutdown,
scripts) get `"-"` as a placeholder. A factory — rather than a
`logging.Filter` on the root logger — is used because Python logging
only runs a logger's filter on the *originating* logger, not on its
ancestors; the factory runs once per record at construction time and
works for every handler, including pytest's `caplog`.

`RequestIdLogFilter` is still attached to the production handler
because the design specifies "wire it into the JSON handler". With
the factory in place the filter is effectively a no-op for the
production path, but it preserves the public API of the middleware
module in case a downstream consumer (e.g. uvicorn) wants to attach
the filter to its own handler too.

`configure_logging` is idempotent: calling it twice does not stack
duplicate handlers on the root logger. Tests rely on this to set up
the logging environment, exercise the app, and tear down without
leaking handlers into other tests.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import TextIO

from jobs_finder.infrastructure.config import Settings
from jobs_finder.presentation.middleware import (
    RequestIdLogFilter,
    get_request_id,
)

# Marker set on handlers that `configure_logging` owns, so the next
# call can clean them up before installing a fresh one. Using a
# sentinel attribute keeps the rest of the handler attributes
# pristine for stdlib / third-party tooling.
_HANDLER_OWNER_KEY = "_jobs_finder_owned_by_configure_logging"


# Standard `LogRecord` attributes managed by the stdlib. Everything
# else on the record was injected via `extra={...}` at the call site.
_LOG_RECORD_STANDARD_ATTRS: frozenset[str] = frozenset({
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "message", "module",
    "msecs", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "taskName", "thread", "threadName",
})


class JsonLogFormatter(logging.Formatter):
    """Render a `LogRecord` as a single-line JSON object.

    Standard output fields:
        {timestamp, level, name, message, request_id}

    When the caller passes ``extra={...}`` to a logger call (e.g.
    ``_logger.warning("aggregator source failed", extra={"source": src})``),
    those extra fields are serialised inside an ``"extra"`` sub-object so
    structured log consumers can group by source or error_type without
    parsing the message string.

    The base field set is stable (REQ-006); the ``extra`` sub-object is
    additive — it appears only when the record carries non-standard
    attributes.
    """

    def format(self, record: logging.LogRecord) -> str:
        # `record.request_id` is injected by the `LogRecordFactory`
        # installed by `configure_logging`; if no factory is in
        # effect (e.g. a one-off script), fall back to the
        # ContextVar default set in `middleware.py`.
        request_id = getattr(record, "request_id", "-")
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "request_id": request_id,
        }

        # Collect any `extra={...}` fields the caller injected.
        # We iterate ``record.__dict__`` (instance attributes only,
        # not inherited methods) and filter out the standard fields
        # that ``LogRecord.__init__`` always sets. Everything that
        # remains was injected via ``extra={...}``.
        extra: dict[str, object] = {}
        for key, value in record.__dict__.items():
            if key in _LOG_RECORD_STANDARD_ATTRS:
                continue
            if key == "request_id":  # already serialised above
                continue
            # Skip callables (methods, lambdas) — they're never
            # from ``extra={...}`` and not JSON-serialisable.
            if callable(value):
                continue
            extra[key] = value
        if extra:
            payload["extra"] = extra

        # Serialise `exc_info` when present (e.g. from
        # `_logger.exception(...)`) so tracebacks are visible in
        # structured logs instead of silently dropped.
        if record.exc_info and record.exc_info[1] is not None:
            payload["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }
            if record.exc_text:
                payload["traceback"] = record.exc_text

        # `ensure_ascii=False` keeps non-ASCII log lines readable.
        return json.dumps(payload, ensure_ascii=False)


def _build_handler(stream: TextIO) -> logging.StreamHandler[TextIO]:
    """Construct a single root-logger handler with the configured formatter."""
    handler: logging.StreamHandler[TextIO] = logging.StreamHandler(stream)
    setattr(handler, _HANDLER_OWNER_KEY, True)
    return handler


def _install_request_id_factory() -> None:
    """Install (once) a `LogRecordFactory` that sets `request_id` on every record.

    The factory wraps the previous factory (Python keeps a chain)
    so any record created anywhere in the process carries the
    current `request_id` from the `ContextVar`. The factory is
    installed at most once per process; subsequent calls are a
    no-op (the same factory instance is still installed).
    """
    current = logging.getLogRecordFactory()
    if getattr(current, "_jobs_finder_request_id_factory", False):
        return  # already installed

    base_factory = current

    def _factory(  # type: ignore[no-untyped-def]
        *args,
        **kwargs,
    ) -> logging.LogRecord:
        record = base_factory(*args, **kwargs)
        record.request_id = get_request_id()
        return record

    # Marker attribute so the idempotency check below can tell
    # that THIS factory is already installed (avoids wrapping it
    # again on a second `configure_logging` call).
    _factory._jobs_finder_request_id_factory = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(_factory)


def _owned_handlers() -> list[logging.Handler]:
    """Return the handlers that `configure_logging` previously installed."""
    return [h for h in logging.getLogger().handlers if getattr(h, _HANDLER_OWNER_KEY, False)]


def configure_logging(
    settings: Settings,
    *,
    stream: TextIO | None = None,
) -> None:
    """Install a single root-logger handler per the given `Settings`.

    Idempotent: a second call removes the handler installed by the
    first call before installing a fresh one. This lets tests call
    `configure_logging` repeatedly without stacking handlers.

    Args:
        settings: Runtime configuration. Reads `log_level` and
            `log_format`. The `log_format` field accepts `"json"`
            (default, structured) or `"plain"` (stdlib formatter).
        stream: Output stream for the handler. Defaults to
            `sys.stderr`. Tests pass a `StringIO` to inspect the
            rendered output without touching the real stderr.
    """
    root = logging.getLogger()
    target_stream = stream if stream is not None else sys.stderr

    # 1. Make every LogRecord carry the current request_id — once
    #    per process. The factory is idempotent: a second call is
    #    a no-op.
    _install_request_id_factory()

    # 2. Remove any handler this function installed previously so
    #    we never stack duplicates (idempotency for tests + reloads).
    for existing in _owned_handlers():
        root.removeHandler(existing)

    # 3. Install a single fresh handler with the right formatter.
    handler = _build_handler(target_stream)
    if settings.log_format == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    # The design says "wire `RequestIdLogFilter` into the JSON
    # handler". With the LogRecordFactory in place the filter is
    # a defensive no-op for the production path, but it preserves
    # the design contract for the handler's public filter chain.
    handler.addFilter(RequestIdLogFilter())
    root.addHandler(handler)

    # 4. Set the root logger level from settings.
    root.setLevel(settings.log_level.upper())
