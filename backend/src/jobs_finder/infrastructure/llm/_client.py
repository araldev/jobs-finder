"""Concrete `MiniMaxLLMClient` (T-011 of `ai-chat-filter`).

Spec: REQ-LLM-001 (error mapping) + design §5 (selective retry).

The client posts to `{base_url}/v1/chat/completions` with the
OpenAI-compatible body shape (model + messages + temperature +
max_completion_tokens + thinking: {type: disabled} + stream: false).
The `thinking: {type: disabled}` setting is preflight D2 — it's
the only model-level knob that actually disables thinking on the
M-series (M2.x ignores it; only M3 honors it).

The error-mapping policy is SELECTIVE — not every failure mode
gets a retry:

  - TRANSIENT (retry ONCE, then raise `LLMUnavailableError`):
    5xx, 429, MiniMax codes 1002 (rate limit) / 1013 (internal).
  - PERMANENT (no retry, raise `LLMUnavailableError`):
    401/403, MiniMax codes 1004 (auth) / 1008 (balance) / 1001
    (timeout), any `httpx.TimeoutException`, `asyncio.TimeoutError`,
    and other `httpx.HTTPError` (network errors).

The 1-retry cap protects against an LLM that is permanently
broken — a third call would just waste the user's $0.0025/req
budget. The transient classification (5xx, 429, 1002, 1013) is
the application-level judgment that a second call ~100ms later
has a reasonable chance of succeeding (a fresh quota slot, a
brief overload cleared).

`httpx.AsyncClient` is injected at construction time so unit
tests can pass a client with a `MockTransport` (the canonical
httpx test seam). The production wiring (T-012 + T-016) builds
the client in the app's lifespan so connection pooling is
reused across requests.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from pydantic import SecretStr

from jobs_finder.infrastructure.llm.exceptions import (
    LLMRequestTimeoutError,
    LLMStreamError,
    LLMUnavailableError,
)

# HTTP status codes that are PERMANENT (no retry).
_AUTH_STATUS_CODES: frozenset[int] = frozenset({401, 403})

# MiniMax error codes that are TRANSIENT (retry once).
_TRANSIENT_MINIMAX_CODES: frozenset[int] = frozenset({1002, 1013})

# MiniMax error codes that are PERMANENT (no retry).
_PERMANENT_MINIMAX_CODES: frozenset[int] = frozenset({1001, 1004, 1008})

# HTTP status code for rate limiting (transient — retry once).
_STATUS_RATE_LIMIT: int = 429

# Backoff delay between the initial call and the single retry.
# The 1-retry cap means exponential backoff adds no value; a
# small fixed delay is enough to escape a quota-refresh window.
_RETRY_BACKOFF_SECONDS: float = 0.1

# Total attempts: 1 initial + 1 retry = 2.
_TOTAL_ATTEMPTS: int = 2


class MiniMaxLLMClient:
    """Concrete `LLMClientPort` implementation for MiniMax's OpenAI-compatible API.

    The constructor is keyword-only so callers cannot accidentally
    pass a positional `base_url` that the constructor would
    misinterpret. The `http_client` parameter is optional — when
    omitted, the client creates its own `httpx.AsyncClient` with
    the configured timeout. Production wiring (T-016) injects a
    shared client built in the app's lifespan.
    """

    __slots__ = (
        "_api_key",
        "_base_url",
        "_model",
        "_temperature",
        "_max_tokens",
        "_timeout_seconds",
        "_http",
        "_owns_http",
        "_thinking_disabled",
        "_supports_thinking",
    )

    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_url: str,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float,
        http_client: httpx.AsyncClient | None = None,
        thinking_disabled: bool = True,
        supports_thinking: bool = True,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout_seconds = timeout_seconds
        if http_client is None:
            self._http = httpx.AsyncClient(timeout=timeout_seconds)
            self._owns_http = True
        else:
            self._http = http_client
            self._owns_http = False
        self._thinking_disabled = thinking_disabled
        self._supports_thinking = supports_thinking

    def _build_request_body(self, system: str, user: str) -> dict[str, Any]:
        """Build the OpenAI-compatible request body.

        The shape is pinned by design §4 (pinned by the
        `test_happy_path_sends_expected_request_body_and_headers`
        test). Any future change to the body shape must update
        that test AND re-verify the MiniMax API contract.
        """
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self._temperature,
            "max_completion_tokens": self._max_tokens,
            "stream": False,
        }
        if self._supports_thinking and self._thinking_disabled:
            # MiniMax: both parameters are needed.
            # reasoning_effort=off shortens the thinking block.
            # thinking.type=disabled suppresses the extended thinking.
            body["reasoning_effort"] = "off"
            body["thinking"] = {"type": "disabled"}
        # Request JSON mode so the model returns a JSON object
        body["response_format"] = {"type": "json_object"}
        return body

    def _build_headers(self) -> dict[str, str]:
        """Build the request headers (auth + content type)."""
        return {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }

    async def complete(self, *, system: str, user: str) -> str:
        """Complete a chat-completion request with a system + user message pair.

        Implements the selective retry policy documented in the
        module docstring. Returns the raw
        `choices[0].message.content` string. May include markdown
        fences or trailing prose — the defensive parser
        (`_parser.parse_llm_response`) handles those.

        Raises:
            LLMUnavailableError: on every failure mode (auth,
                rate limit, internal, timeout, network). The
                exception's `cause` is the underlying httpx /
                JSON error for log diagnostics.
        """
        url = f"{self._base_url}/v1/chat/completions"
        body = self._build_request_body(system, user)
        headers = self._build_headers()
        last_exc: Exception | None = None
        for attempt in range(_TOTAL_ATTEMPTS):  # 0 = initial, 1 = single retry
            try:
                response = await self._http.post(url, json=body, headers=headers)
            except httpx.TimeoutException as e:
                # Timeouts are NOT transient — a hung request is hung.
                raise LLMUnavailableError(
                    f"timeout after {self._timeout_seconds}s",
                    cause=e,
                ) from e
            except httpx.HTTPError as e:
                # Other httpx errors (connection refused, DNS, etc.) are
                # not transient in the same way as 5xx — do not retry.
                raise LLMUnavailableError(
                    f"http error while calling MiniMax: {e!r}",
                    cause=e,
                ) from e

            # HTTP-level status handling.
            status = response.status_code
            if status in _AUTH_STATUS_CODES:
                # Auth fail — no retry.
                raise LLMUnavailableError(
                    f"auth failed (HTTP {status})",
                )
            if status == _STATUS_RATE_LIMIT:
                if attempt == 0:
                    await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
                    last_exc = LLMUnavailableError("rate limited (HTTP 429)")
                    continue
                # Retry exhausted.
                raise LLMUnavailableError(
                    "rate limited (HTTP 429) after retry",
                    cause=last_exc,
                )
            if status >= 500:
                if attempt == 0:
                    await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
                    last_exc = LLMUnavailableError(f"server error (HTTP {status})")
                    continue
                raise LLMUnavailableError(
                    f"server error (HTTP {status}) after retry",
                    cause=last_exc,
                )

            # 2xx — parse the body. MiniMax can return 200 with an
            # error in the body's `error.code` field.
            try:
                payload = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                # Malformed JSON body — treat as a 5xx-like transient
                # and retry once.
                if attempt == 0:
                    await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
                    last_exc = LLMUnavailableError(
                        f"malformed JSON in MiniMax response: {e!r}",
                        cause=e,
                    )
                    continue
                raise LLMUnavailableError(
                    "malformed JSON in MiniMax response after retry",
                    cause=last_exc,
                )

            # Check for MiniMax application-level error codes.
            error = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(error, dict):
                code = error.get("code")
                if isinstance(code, int) and code in _TRANSIENT_MINIMAX_CODES:
                    if attempt == 0:
                        await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
                        last_exc = LLMUnavailableError(f"transient MiniMax error (code {code})")
                        continue
                    raise LLMUnavailableError(
                        f"transient MiniMax error (code {code}) after retry",
                        cause=last_exc,
                    )
                if isinstance(code, int) and code in _PERMANENT_MINIMAX_CODES:
                    # Permanent — no retry.
                    raise LLMUnavailableError(
                        f"permanent MiniMax error (code {code})",
                    )

            # Success — extract the assistant content.
            try:
                choices = payload["choices"]
                content = choices[0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as e:
                # Unexpected response shape — treat as transient and
                # retry once.
                if attempt == 0:
                    await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
                    last_exc = LLMUnavailableError(
                        f"unexpected MiniMax response shape: {e!r}",
                        cause=e,
                    )
                    continue
                raise LLMUnavailableError(
                    "unexpected MiniMax response shape after retry",
                    cause=last_exc,
                )
            if not isinstance(content, str):
                raise LLMUnavailableError(
                    f"MiniMax response content is not a string: {type(content).__name__}",
                )
            return content

        # Unreachable: the loop always returns or raises.
        raise LLMUnavailableError(
            "MiniMax request exited retry loop without response",
            cause=last_exc,
        )

    async def aclose(self) -> None:
        """Close the owned `httpx.AsyncClient` (if any).

        Only the client that OWNS its http_client (i.e. was
        constructed with `http_client=None`) closes on `aclose`.
        An injected client is owned by the caller; the caller
        controls its lifecycle (typically via the app's lifespan).
        """
        if self._owns_http:
            await self._http.aclose()

    async def stream_complete(self, *, system: str, user: str) -> AsyncIterator[str]:
        """Stream-complete a chat-completion request, yielding one string per token.

        Spec: `chat-streaming` REQ-LLM-002. The streaming
        counterpart of `complete(...)`. Posts to
        `{base_url}/v1/chat/completions` with
        `{"stream": True, ...}` and iterates the SSE response,
        yielding the `choices[0].delta.content` of each
        `data: <json>` line. The `[DONE]` sentinel breaks
        the loop; empty `delta.content` is skipped (no yield).

        The body is a thin wrapper over
        `self._http.stream("POST", url, ...)` + `aiter_lines()`.
        The `stream: True` field is added to the body (the
        same OpenAI-compatible shape used by `complete`, with
        the streaming flag flipped). The auth headers are
        reused verbatim.

        Raises:
            LLMStreamError: on non-200 status or malformed SSE
                (status code embedded in the message). NO
                retry mid-stream — retrying would destroy
                chunks already enqueued for the client.
            LLMRequestTimeoutError: on `httpx.TimeoutException`
                mid-stream. NO retry — the upstream request
                is allowed to complete in the background
                (the proposal's user decision; cost is
                negligible).
        """
        url = f"{self._base_url}/v1/chat/completions"
        body = self._build_request_body(system, user)
        # The streaming variant is byte-identical to the
        # non-streaming body shape with `stream: True` flipped.
        body["stream"] = True
        headers = self._build_headers()

        try:
            async with self._http.stream("POST", url, json=body, headers=headers) as response:
                if response.status_code != 200:
                    # Surface the status + body excerpt so the
                    # route's SSE error event carries the same
                    # info (the `data.message` field).
                    body_excerpt = response.text[:200] if response.text else ""
                    raise LLMStreamError(
                        f"stream status {response.status_code}: {body_excerpt!r}",
                    )
                async for line in response.aiter_lines():
                    # SSE protocol lines: each `data: <json>` line
                    # carries one token; empty lines are framing
                    # separators. Lines not starting with `data: `
                    # (e.g. `event:` lines, comments) are ignored.
                    if not line.startswith("data: "):
                        continue
                    payload = line.removeprefix("data: ").strip()
                    if payload == "[DONE]":
                        # The OpenAI-compatible stream signals
                        # end-of-stream with the literal
                        # `data: [DONE]` line. Break BEFORE
                        # attempting to JSON-parse the sentinel.
                        break
                    try:
                        chunk = json.loads(payload)
                    except (json.JSONDecodeError, ValueError) as exc:
                        # A malformed `data: <garbage>` line is
                        # a protocol-level error; surface as
                        # LLMStreamError (the route maps to the
                        # `llm_stream` machine code, NOT the
                        # `llm_parse` machine code — `llm_parse`
                        # is reserved for the end-of-stream
                        # `StreamEventParser`).
                        raise LLMStreamError(
                            f"malformed SSE line: {payload[:200]!r}",
                            cause=exc,
                        ) from exc
                    # Extract `choices[0].delta.content`. A
                    # missing `content` key (or a missing
                    # `choices` array) is a defensible "skip"
                    # case (the model emitted an empty delta,
                    # e.g. a function-call delta or a
                    # tool-call delta) — the spec says skip
                    # empties, do not yield.
                    try:
                        delta = chunk["choices"][0]["delta"].get("content")
                    except (KeyError, IndexError, TypeError):
                        delta = None
                    if delta:
                        yield delta
        except httpx.TimeoutException as exc:
            # The streaming timeout is a separate class from
            # the non-streaming one — the route maps it to
            # the `llm_timeout` machine code (REQ-ERROR-
            # MAPPING-001). NO retry: a hung stream is hung,
            # and the proposal's user decision is to let the
            # upstream request complete in the background.
            raise LLMRequestTimeoutError(
                f"streaming request timed out after {self._timeout_seconds}s",
                cause=exc,
            ) from exc
