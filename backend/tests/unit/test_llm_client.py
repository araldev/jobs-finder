"""Unit tests for the `MiniMaxLLMClient` (T-011 of `ai-chat-filter`).

Spec: REQ-LLM-001 (error mapping) + design §5 (selective retry).

The `MiniMaxLLMClient` posts to `https://api.minimax.io/v1/chat/completions`
with the OpenAI-compatible body shape (model + messages + temperature +
max_completion_tokens + thinking: {type: disabled} + stream: false).
It implements a SELECTIVE retry policy:

  - 5xx, 429, MiniMax codes 1002/1013 → retry ONCE then raise
    `LLMUnavailableError` (per the "transient" classification).
  - 401/403, MiniMax codes 1004/1008/1001 → no retry, raise
    `LLMUnavailableError` (per the "permanent" classification).
  - `httpx.TimeoutException`, `asyncio.TimeoutError` → no retry,
    raise `LLMUnavailableError` (timeouts are NOT transient for
    filter calls; a hung request is hung).
  - Other `httpx.HTTPError` (network errors) → no retry, raise
    `LLMUnavailableError`.

The 7-scenario test matrix below uses `httpx.MockTransport` to
inject canned responses (status codes + bodies) and to count the
HTTP calls. `MockTransport` is the canonical httpx test seam —
it intercepts every request at the transport layer without a
real network connection.
"""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from jobs_finder.infrastructure.llm._client import MiniMaxLLMClient
from jobs_finder.infrastructure.llm.exceptions import LLMUnavailableError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _success_response(content: str) -> httpx.Response:
    """Build a 200 response with a valid chat.completion body."""
    return httpx.Response(
        200,
        json={
            "id": "test",
            "choices": [
                {
                    "finish_reason": "stop",
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                }
            ],
            "model": "MiniMax-M3",
            "object": "chat.completion",
        },
    )


def _error_response(status_code: int, code: int, message: str = "error") -> httpx.Response:
    """Build a MiniMax-style error response with the given HTTP status + error code."""
    return httpx.Response(
        status_code,
        json={"error": {"code": code, "message": message, "type": "minimax_error"}},
    )


def _build_client_with_transport(
    handler: httpx.MockTransport,
    *,
    base_url: str = "https://api.minimax.io",
) -> MiniMaxLLMClient:
    """Build a client with a custom `httpx.MockTransport` for testing.

    The `http_client` is injected so the test owns the transport.
    The `MiniMaxLLMClient` reuses the injected client (does NOT
    own its lifecycle — the test does).
    """
    http_client = httpx.AsyncClient(base_url=base_url, transport=handler, timeout=15.0)
    return MiniMaxLLMClient(
        api_key=SecretStr("test-key"),
        base_url=base_url,
        model="MiniMax-M3",
        temperature=0.0,
        max_tokens=1024,
        timeout_seconds=15.0,
        http_client=http_client,
    )


# ---------------------------------------------------------------------------
# Scenario 1: success
# ---------------------------------------------------------------------------


async def test_happy_path_returns_assistant_content() -> None:
    """A 200 response with a valid chat.completion body returns the content.

    The client MUST extract `choices[0].message.content` from the
    OpenAI-compatible response shape. A regression that returns
    the raw response JSON or the wrong field would break the use
    case (T-013) which feeds the string into the defensive parser.
    """
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return _success_response("hola mundo")

    client = _build_client_with_transport(httpx.MockTransport(handler))
    result = await client.complete(system="sys", user="usr")
    assert result == "hola mundo"
    # Exactly 1 HTTP call (no retry on success).
    assert len(captured_requests) == 1


async def test_happy_path_sends_expected_request_body_and_headers() -> None:
    """The request body matches the OpenAI-compatible shape + the auth header is set.

    Pinned by design §11 #3 — the test fixtures pin the EXACT
    URL, body shape, and headers so a future refactor that
    changes the wire format breaks the test loudly.
    """
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return _success_response("ok")

    client = _build_client_with_transport(httpx.MockTransport(handler))
    await client.complete(system="the system prompt", user="the user message")

    assert captured_request is not None
    # The URL is the canonical chat-completions endpoint.
    assert captured_request.url.path == "/v1/chat/completions"
    # The Authorization header carries the bearer token.
    assert captured_request.headers["Authorization"] == "Bearer test-key"
    # The body is JSON with the exact shape (design §4).
    body = json.loads(captured_request.content)
    assert body["model"] == "MiniMax-M3"
    assert body["messages"] == [
        {"role": "system", "content": "the system prompt"},
        {"role": "user", "content": "the user message"},
    ]
    assert body["temperature"] == 0.0
    assert body["max_completion_tokens"] == 1024
    # `thinking: {type: "disabled"}` is the preflight D2 setting.
    assert body["thinking"] == {"type": "disabled"}
    assert body["stream"] is False


# ---------------------------------------------------------------------------
# Scenario 2: 401 (auth fail, NO retry)
# ---------------------------------------------------------------------------


async def test_401_raises_llm_unavailable_without_retry() -> None:
    """A 401 response raises `LLMUnavailableError` with NO retry.

    Auth failures are NOT transient — the same key will fail again.
    The spec lists `1004` as a MiniMax auth-error code; the
    HTTP-level 401 is the OpenAI-compatible equivalent.
    """
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(401, json={"error": {"message": "Unauthorized"}})

    client = _build_client_with_transport(httpx.MockTransport(handler))
    with pytest.raises(LLMUnavailableError):
        await client.complete(system="sys", user="usr")
    # Exactly 1 HTTP call (no retry on 401).
    assert call_count == 1


# ---------------------------------------------------------------------------
# Scenario 3: 429 (rate limit) — retry once, then raise
# ---------------------------------------------------------------------------


async def test_429_retries_once_then_raises() -> None:
    """A 429 response retries ONCE; if both calls return 429, raises `LLMUnavailableError`.

    The retry covers transient rate limiting (a second call 1
    second later typically has a fresh quota slot). The 1-retry
    cap protects against an LLM that is permanently throttled
    (a third call would just waste the user's $0.0025/req budget).
    """
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(429, json={"error": {"message": "Too Many Requests"}})

    client = _build_client_with_transport(httpx.MockTransport(handler))
    with pytest.raises(LLMUnavailableError):
        await client.complete(system="sys", user="usr")
    # 2 calls: initial + 1 retry.
    assert call_count == 2


async def test_429_then_200_succeeds_on_retry() -> None:
    """A 429 followed by a 200 returns the 200's content (retry succeeded).

    This pins the "transient retry" contract — the client does
    NOT raise on the first 429; it tries once more. A
    regression that surfaced the 429 to the user would
    waste money on user-visible failures.
    """
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429, json={"error": {"message": "rate limit"}})
        return _success_response("recovered content")

    client = _build_client_with_transport(httpx.MockTransport(handler))
    result = await client.complete(system="sys", user="usr")
    assert result == "recovered content"
    # 2 calls: initial + 1 retry.
    assert call_count == 2


# ---------------------------------------------------------------------------
# Scenario 4: 5xx — retry once, then raise
# ---------------------------------------------------------------------------


async def test_5xx_retries_once_then_raises() -> None:
    """A 500 response retries ONCE; if both return 5xx, raises `LLMUnavailableError`.

    5xx is transient (the server is overloaded, a second call
    1 second later may succeed). The 1-retry cap protects
    against a permanently-down upstream.
    """
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, json={"error": {"message": "Internal Server Error"}})

    client = _build_client_with_transport(httpx.MockTransport(handler))
    with pytest.raises(LLMUnavailableError):
        await client.complete(system="sys", user="usr")
    # 2 calls: initial + 1 retry.
    assert call_count == 2


# ---------------------------------------------------------------------------
# Scenario 5: MiniMax error code 1002 (rate limit) — retry once, then raise
# ---------------------------------------------------------------------------


async def test_minimax_code_1002_retries_once_then_raises() -> None:
    """A response with error code 1002 (rate limit) retries ONCE then raises.

    The MiniMax API returns 200 with a body shaped
    `{"error": {"code": 1002, ...}}` for rate limit — this is
    the application-level rate limit (not the HTTP-level 429).
    Both must be handled.
    """
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return _error_response(200, 1002, "rate limit exceeded")

    client = _build_client_with_transport(httpx.MockTransport(handler))
    with pytest.raises(LLMUnavailableError):
        await client.complete(system="sys", user="usr")
    # 2 calls: initial + 1 retry.
    assert call_count == 2


async def test_minimax_code_1013_retries_once_then_raises() -> None:
    """A response with error code 1013 (internal error) retries ONCE then raises."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return _error_response(200, 1013, "internal server error")

    client = _build_client_with_transport(httpx.MockTransport(handler))
    with pytest.raises(LLMUnavailableError):
        await client.complete(system="sys", user="usr")
    assert call_count == 2


# ---------------------------------------------------------------------------
# Scenario 6: MiniMax error code 1004/1008 — no retry
# ---------------------------------------------------------------------------


async def test_minimax_code_1004_raises_without_retry() -> None:
    """A response with error code 1004 (auth failed) raises WITHOUT retry.

    The key is bad; retrying with the same key will fail again.
    The route maps this to 502 (the user's key is misconfigured).
    """
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return _error_response(200, 1004, "invalid api key")

    client = _build_client_with_transport(httpx.MockTransport(handler))
    with pytest.raises(LLMUnavailableError):
        await client.complete(system="sys", user="usr")
    # 1 call only (no retry on auth failure).
    assert call_count == 1


async def test_minimax_code_1008_raises_without_retry() -> None:
    """A response with error code 1008 (insufficient balance) raises WITHOUT retry.

    The user's account is out of money; retrying won't help.
    The route maps this to 502.
    """
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return _error_response(200, 1008, "insufficient balance")

    client = _build_client_with_transport(httpx.MockTransport(handler))
    with pytest.raises(LLMUnavailableError):
        await client.complete(system="sys", user="usr")
    assert call_count == 1


# ---------------------------------------------------------------------------
# Scenario 7: timeout
# ---------------------------------------------------------------------------


async def test_timeout_raises_llm_unavailable_without_retry() -> None:
    """A `httpx.TimeoutException` raises WITHOUT retry.

    A hung request is hung; retrying wastes the user's money.
    The route maps this to 502.
    """
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectTimeout("connect timeout after 15s")

    client = _build_client_with_transport(httpx.MockTransport(handler))
    with pytest.raises(LLMUnavailableError):
        await client.complete(system="sys", user="usr")
    # 1 call only (no retry on timeout).
    assert call_count == 1


# ---------------------------------------------------------------------------
# LLMUnavailableError includes the cause for log diagnostics
# ---------------------------------------------------------------------------


async def test_llm_unavailable_error_str_includes_cause() -> None:
    """The raised `LLMUnavailableError` includes the cause's repr in `str(err)`.

    The route's 502 body and the access log use `str(err)`; including
    the underlying HTTP / network error lets operators trace the
    root cause without re-running the request.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Unauthorized"}})

    client = _build_client_with_transport(httpx.MockTransport(handler))
    with pytest.raises(LLMUnavailableError) as exc_info:
        await client.complete(system="sys", user="usr")
    # `str(err)` includes both the message and the cause's repr.
    assert "401" in str(exc_info.value) or "auth" in str(exc_info.value).lower()
