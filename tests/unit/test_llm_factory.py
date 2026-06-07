"""Unit tests for the `build_minimax_llm_client` factory (T-012 of `ai-chat-filter`).

Spec: design §11 #1 (build `httpx.AsyncClient` in the lifespan,
inject at construction time) and design §5 (factory reads from
`Settings`, raises if `llm_api_key` is None).

The factory is the bridge between the env-driven `Settings` and
the concrete `MiniMaxLLMClient`. It does two things:

  1. Validates that `settings.llm_api_key` is set (raises
     `ValueError` if None — the chat route is OFF when the
     key is missing, and the factory should fail loud at
     construction time, not silently produce a half-configured
     client that fails on the first request).
  2. Constructs a `MiniMaxLLMClient` with the right fields from
     `Settings`. The factory MAY take an optional
     `http_client` parameter (for the app's lifespan-managed
     client) so the production wiring (T-016) can pass the
     shared client.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from pydantic import SecretStr

from jobs_finder.infrastructure.config import Settings
from jobs_finder.infrastructure.llm._client import MiniMaxLLMClient
from jobs_finder.infrastructure.llm._factory import build_minimax_llm_client

# ---------------------------------------------------------------------------
# Happy path — builds a client with the right fields
# ---------------------------------------------------------------------------


def test_factory_builds_minimax_llm_client() -> None:
    """A `Settings` with `llm_api_key` set produces a `MiniMaxLLMClient`.

    The factory is the single place that maps `Settings` fields
    to constructor args; the rest of the codebase depends on it
    so the mapping is consistent across callers.
    """
    settings = Settings(
        llm_api_key=SecretStr("sk-factory-test"),
        llm_base_url="https://api.minimax.io",
        llm_model="MiniMax-M3",
        llm_temperature=0.0,
        llm_max_tokens=1024,
        llm_request_timeout_seconds=15.0,
    )
    client = build_minimax_llm_client(settings)
    assert isinstance(client, MiniMaxLLMClient)


def test_factory_forwards_all_settings_fields_to_the_client() -> None:
    """The constructed client carries the Settings values verbatim.

    The mapping is `Settings.X` -> `MiniMaxLLMClient(X)`. A
    regression that drops a field (e.g. forgets
    `llm_request_timeout_seconds`) would silently use the
    default and break production timeouts.
    """
    settings = Settings(
        llm_api_key=SecretStr("sk-factory-test"),
        llm_base_url="https://custom.example.com",
        llm_model="MiniMax-TestModel",
        llm_temperature=0.42,
        llm_max_tokens=2048,
        llm_request_timeout_seconds=7.5,
    )
    client = build_minimax_llm_client(settings)
    # The private attributes hold the Settings values.
    assert client._api_key.get_secret_value() == "sk-factory-test"  # noqa: SLF001
    assert client._base_url == "https://custom.example.com"  # noqa: SLF001
    assert client._model == "MiniMax-TestModel"  # noqa: SLF001
    assert client._temperature == 0.42  # noqa: SLF001
    assert client._max_tokens == 2048  # noqa: SLF001
    assert client._timeout_seconds == 7.5  # noqa: SLF001


def test_factory_uses_thinking_disabled_true_by_default() -> None:
    """The factory sets `thinking_disabled=True` so thinking tokens
    are never billed (preflight D2 — only M3 honors the flag).
    """
    settings = Settings(llm_api_key=SecretStr("sk-factory-test"))
    client = build_minimax_llm_client(settings)
    assert client._thinking_disabled is True  # noqa: SLF001


def test_factory_strips_trailing_slash_from_base_url() -> None:
    """`base_url="https://example.com/"` and `="https://example.com"`
    both produce the same `base_url` (no double slash in the URL).

    The MiniMax endpoint is built as
    `f"{base_url}/v1/chat/completions"`. A trailing slash on
    `base_url` would produce a `//v1/...` URL that some HTTP
    libraries normalize and some don't. The factory normalizes
    by stripping a single trailing slash.
    """
    settings_with_slash = Settings(
        llm_api_key=SecretStr("sk-x"),
        llm_base_url="https://api.minimax.io/",
    )
    settings_without_slash = Settings(
        llm_api_key=SecretStr("sk-x"),
        llm_base_url="https://api.minimax.io",
    )
    client1 = build_minimax_llm_client(settings_with_slash)
    client2 = build_minimax_llm_client(settings_without_slash)
    assert client1._base_url == client2._base_url  # noqa: SLF001
    assert client1._base_url == "https://api.minimax.io"  # noqa: SLF001


# ---------------------------------------------------------------------------
# Validation — llm_api_key=None is a HARD error
# ---------------------------------------------------------------------------


def test_factory_raises_value_error_when_llm_api_key_is_none() -> None:
    """A `Settings` with `llm_api_key=None` (the default) raises `ValueError`.

    The route registration in T-016 checks
    `settings.llm_api_key is not None` BEFORE calling the
    factory, so a default `Settings()` (no env var set) does
    not even reach the factory. The factory's own check is a
    defense-in-depth measure: a future caller that bypasses
    the route's conditional registration would fail loud
    here rather than build a broken client.
    """
    settings = Settings()  # llm_api_key defaults to None
    assert settings.llm_api_key is None
    with pytest.raises(ValueError, match="llm_api_key"):
        build_minimax_llm_client(settings)


# ---------------------------------------------------------------------------
# http_client injection — the factory accepts an injected client
# (for the app's lifespan-managed client, design §11 #1)
# ---------------------------------------------------------------------------


def test_factory_accepts_injected_http_client() -> None:
    """The factory accepts an injected `httpx.AsyncClient` and forwards it to the client.

    Production wiring (T-016) builds the client in the app's
    lifespan so connection pooling is reused across requests.
    A unit test injects its own client to verify the wiring.
    """
    settings = Settings(llm_api_key=SecretStr("sk-factory-test"))
    injected = httpx.AsyncClient(timeout=42.0)
    try:
        client = build_minimax_llm_client(settings, http_client=injected)
        # The client holds the injected client.
        assert client._http is injected  # noqa: SLF001
        # The client does NOT own the injected client (so it will
        # NOT close it on aclose()).
        assert client._owns_http is False  # noqa: SLF001
    finally:
        # The test owns the client; close it via asyncio.run to
        # avoid the deprecation warning from get_event_loop()
        # (the project's pytest config promotes warnings to
        # errors, so a DeprecationWarning would fail the test).
        asyncio.run(injected.aclose())


def test_factory_without_http_client_creates_one() -> None:
    """When `http_client` is omitted, the factory creates one via the client.

    The client's ctor handles the `http_client is None` case
    by building a fresh `httpx.AsyncClient` with the
    configured timeout. The factory's role is just to forward
    the Settings; the client's role is to own or borrow the
    transport.
    """
    settings = Settings(
        llm_api_key=SecretStr("sk-factory-test"),
        llm_request_timeout_seconds=20.0,
    )
    client = build_minimax_llm_client(settings)
    # The client owns the http_client (so it WILL close on aclose()).
    assert client._owns_http is True  # noqa: SLF001
    # The client's http_client has the configured timeout.
    assert client._http.timeout.connect == 20.0  # noqa: SLF001
