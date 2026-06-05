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

`RateLimitMiddleware` (REQ-RL-005, rate-limiting change) is the
HTTP-layer token-bucket rate limiter. It reads the bucket key from
`request.client.host` and the cost from a per-route cost map. A 429
short-circuits `call_next` (so the route, the cached use case, and
the Playwright scraper are NEVER reached from a 429 path —
`X-Cache: MISS` is therefore impossible on 429).
"""

from __future__ import annotations

import ipaddress
import logging
import math
import uuid
from collections.abc import Awaitable, Callable, Mapping
from contextvars import ContextVar
from ipaddress import IPv4Network, IPv6Network

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from jobs_finder.application.ports import RateLimitPort
from jobs_finder.presentation.schemas import RateLimitedResponse

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

# Module-level logger for the rate-limiter middleware. The
# `X-Forwarded-For` WARNINGs are emitted on this logger so ops can
# configure a separate handler / filter for proxy-related warnings.
_rate_limit_logger = logging.getLogger("jobs_finder.presentation.middleware")


def _ip_in_any_cidr(
    ip_obj: str | ipaddress.IPv4Address | ipaddress.IPv6Address | IPv4Network | IPv6Network,
    cidrs: frozenset[IPv4Network | IPv6Network],
) -> bool:
    """Return `True` if `ip_obj` is a valid IP/Network in any of `cidrs`.

    Accepts a string (parsed with `ipaddress.ip_address`), a
    pre-parsed `IPv4Address` / `IPv6Address` / `IPv4Network` /
    `IPv6Network` instance, or any object whose `__str__` returns
    a parseable IP. Used by `_resolve_client_id` to check
    whether the socket IP and each XFF hop are in the trusted
    CIDR set.
    """
    try:
        if isinstance(
            ip_obj,
            (
                IPv4Network,
                IPv6Network,
                ipaddress.IPv4Address,
                ipaddress.IPv6Address,
            ),
        ):
            addr = ip_obj
        else:
            addr = ipaddress.ip_address(str(ip_obj))
    except ValueError:
        return False
    return any(addr in cidr for cidr in cidrs)


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


# ---------------------------------------------------------------------------
# Rate-limit middleware (REQ-RL-005, REQ-RL-006, REQ-RL-007, rate-limiting change)
#
# Stack order (innermost → outermost):
#   route → LogOnRequest → RequestId → RateLimit → CORS
#
# - `RateLimit` sits INSIDE `CORS` (so OPTIONS preflights use CORS's
#   normal handling) and OUTSIDE `RequestId` (so the 429 body can
#   read `request.state.request_id`).
# - The exempt check runs FIRST in `dispatch` (no state touched, no
#   log noise — REQ-RL-007).
# - 429 short-circuits `call_next` (REQ-RL-005 invariant) so the
#   cache namespace stays clean.
# ---------------------------------------------------------------------------

# Paths that are unconditionally exempt from rate limiting, regardless
# of `RATE_LIMIT_EXEMPT_PATHS`. Hardcoded for the k8s liveness probe
# invariant: `/health` MUST NEVER 429 (a 429 on the liveness probe
# would cause Kubernetes to kill the pod).
EXEMPT_UNCONDITIONAL: frozenset[str] = frozenset({"/health"})

# `Retry-After` (RFC 6585) and the de-facto `X-RateLimit-*` headers
# (GitHub / Stripe / draft-ietf-httpapi-ratelimit-headers).
RATE_LIMIT_HEADERS: dict[str, str] = {
    "limit": "X-RateLimit-Limit",
    "remaining": "X-RateLimit-Remaining",
    "reset": "X-RateLimit-Reset",
    "retry_after": "Retry-After",
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-bucket rate limiter at the HTTP layer.

    REQ-RL-005: on `allowed=True`, the request is forwarded and the
    3 `X-RateLimit-*` headers are set on the response. On
    `allowed=False`, a 429 `JSONResponse` is returned (short-
    circuiting `call_next`) with `Retry-After`, the 3
    `X-RateLimit-*` headers, and the 429 body shape
    `{"detail": "rate limit exceeded", "request_id": "..."}`.

    The middleware is constructed with the `RateLimitPort`
    instance, the effective exempt set (settings ∪ FastAPI docs
    paths), the per-route cost map (a `MappingProxyType` for
    runtime immutability), and the bucket capacity (for the
    `X-RateLimit-Limit` header).
    """

    __slots__ = ("_limiter", "_exempt_paths", "_cost_map", "_capacity", "_trusted_proxies")

    def __init__(
        self,
        app: ASGIApp,
        *,
        limiter: RateLimitPort,
        exempt_paths: frozenset[str] | set[str],
        cost_map: Mapping[str, int],
        capacity: int,
        trusted_proxies: frozenset[IPv4Network | IPv6Network]
        | set[IPv4Network | IPv6Network]
        | None = None,
    ) -> None:
        super().__init__(app)
        self._limiter: RateLimitPort = limiter
        # The effective exempt set (settings ∪ FastAPI docs paths,
        # computed in `app_factory`). `EXEMPT_UNCONDITIONAL` is
        # checked separately at the top of `dispatch`.
        self._exempt_paths: frozenset[str] = frozenset(exempt_paths)
        # The per-route cost map. Wrapped as a `MappingProxyType`
        # in `app_factory` so runtime mutation raises `TypeError`.
        self._cost_map: Mapping[str, int] = cost_map
        # Bucket capacity — used for the `X-RateLimit-Limit` header.
        self._capacity: int = capacity
        # The TRUSTED_PROXY CIDR set. Default `frozenset()` (security
        # default — never trust `X-Forwarded-For`). The middleware
        # passes this to `_resolve_client_id` to compute the bucket
        # key per request.
        self._trusted_proxies: frozenset[IPv4Network | IPv6Network] = frozenset(
            trusted_proxies or frozenset()
        )

    @staticmethod
    def _resolve_client_id(
        request: Request,
        trusted_proxies: frozenset[IPv4Network | IPv6Network],
    ) -> str:
        """Resolve the rate-limiter `client_id` from the request (rightmost-untrusted).

        REQ-RL-011: with no proxy trust, the security default is
        "use the socket IP, IGNORE `X-Forwarded-For`" (AD-7). With
        a non-empty `trusted_proxies` AND a socket IP in a trusted
        CIDR, parse `X-Forwarded-For` right-to-left, skip trusted
        hops, return the first untrusted IP. Falls back to the
        socket IP when the header is absent, all hops are trusted,
        or any hop is malformed (logs WARNING on malformed input).

        The helper is a `@staticmethod` so it is testable in
        isolation (the `RateLimitMiddleware` constructor requires
        an ASGI app; a unit test of the resolution logic does not
        need one).
        """
        socket_ip = request.client.host if request.client else ""
        # AD-7: never trust `X-Forwarded-For` without explicit trust
        # config (empty trusted_proxies is the security default).
        # Also bail out if the socket IP is not parseable as an IP
        # address (e.g., ASGI test client with `client=("testclient", 50000)`)
        # — in that case we return the opaque string and the
        # rightmost-untrusted walk is meaningless.
        if not socket_ip or not trusted_proxies:
            return socket_ip
        if not _ip_in_any_cidr(socket_ip, trusted_proxies):
            return socket_ip
        xff = request.headers.get("X-Forwarded-For", "")
        if not xff:
            return socket_ip
        hops = [h.strip() for h in xff.split(",") if h.strip()]
        for hop in reversed(hops):
            try:
                hop_addr = ipaddress.ip_address(hop)
            except ValueError:
                _rate_limit_logger.warning(
                    "rate_limit: malformed X-Forwarded-For hop: %r; falling back to socket IP %r",
                    hop,
                    socket_ip,
                )
                return socket_ip
            if not _ip_in_any_cidr(hop_addr, trusted_proxies):
                return hop
        # `for ... else`: runs ONLY if the loop completes without
        # `break` (i.e., no untrusted hop found). All hops are
        # in the trusted chain — fall back to the socket IP, NOT
        # the leftmost hop (the leftmost is the "original client"
        # per XFF semantics, but if all hops are trusted we have
        # no way to verify the real client).
        return socket_ip

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # 1. Unconditional exempt (k8s liveness probe invariant).
        #    Runs FIRST so /health never reaches the limiter, never
        #    consults `request.client.host`, never logs.
        if request.url.path in EXEMPT_UNCONDITIONAL:
            return await call_next(request)

        # 2. App-factory-configured exempt set (e.g. /docs, /openapi.json, /redoc).
        if request.url.path in self._exempt_paths:
            return await call_next(request)

        # 3. Per-route cost (default 1 for unknown paths).
        cost = int(self._cost_map.get(request.url.path, 1))

        # 4. Resolve the client_id (rightmost-untrusted). With no
        #    trusted proxies this is just `request.client.host` and
        #    `X-Forwarded-For` is IGNORED (the security default).
        client_id = self._resolve_client_id(request, self._trusted_proxies)

        # 5. Acquire a token. The limiter NEVER raises (the Redis
        #    impl catches `redis.exceptions.RedisError` and returns
        #    `allowed=True`; the in-memory impl is pure math).
        decision = await self._limiter.try_acquire(
            key=client_id or "unknown",
            cost=float(cost),
        )

        # 6. Denied: 429 + JSON body + Retry-After + 3 X-RateLimit-* headers.
        if not decision.allowed:
            request_id = str(getattr(request.state, "request_id", "") or "")
            body = RateLimitedResponse(
                detail="rate limit exceeded",
                request_id=request_id,
            ).model_dump()
            return JSONResponse(
                status_code=429,
                content=body,
                headers={
                    RATE_LIMIT_HEADERS["retry_after"]: str(int(math.ceil(decision.retry_after))),
                    RATE_LIMIT_HEADERS["limit"]: str(self._capacity),
                    RATE_LIMIT_HEADERS["remaining"]: "0",
                    RATE_LIMIT_HEADERS["reset"]: str(int(math.ceil(decision.reset_after))),
                    # Echo the request id so the 429 is self-contained
                    # for clients that don't merge headers.
                    REQUEST_ID_HEADER: request_id,
                },
            )

        # 7. Allowed: forward the request, then decorate the response.
        response = await call_next(request)
        response.headers[RATE_LIMIT_HEADERS["limit"]] = str(self._capacity)
        response.headers[RATE_LIMIT_HEADERS["remaining"]] = str(int(math.floor(decision.remaining)))
        response.headers[RATE_LIMIT_HEADERS["reset"]] = str(int(math.ceil(decision.reset_after)))
        return response
