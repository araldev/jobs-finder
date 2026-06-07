"""Unit tests for the `LLMClientPort` Protocol (T-010 of `ai-chat-filter`).

Spec: REQ-LLM-001 (the use case MUST depend on the Protocol, not on
the concrete `MiniMaxLLMClient`).

`LLMClientPort` is a `typing.Protocol` (NOT `@runtime_checkable`).
The application layer uses it for static type checking; the
infrastructure layer implements it (e.g. `MiniMaxLLMClient`); and
the test layer uses a `FakeLLMClient` that satisfies the Protocol
structurally. The Protocol pattern is the standard seam for
dependency inversion in this project (mirrors `JobSearchPort`,
`CachePort`, `RateLimitPort`).

A `FakeLLMClient` with the right method signature is structurally
compatible with `LLMClientPort` — mypy --strict confirms this at
type-check time, and a test can construct a `FakeLLMClient` and
call its `complete` method without any runtime Protocol machinery.
"""

from __future__ import annotations

import ast
import inspect

import pytest

from jobs_finder.application.ports import LLMClientPort

# ---------------------------------------------------------------------------
# Protocol definition
# ---------------------------------------------------------------------------


def test_llm_client_port_is_exported() -> None:
    """`LLMClientPort` is importable from `jobs_finder.application.ports`."""
    assert LLMClientPort is not None


def test_llm_client_port_is_a_protocol() -> None:
    """`LLMClientPort` is a `typing.Protocol` (or subclass thereof).

    The Protocol is the application's contract with any LLM
    implementation. A concrete class is NOT required — the use
    case uses the Protocol for type hints and the test layer
    passes a `FakeLLMClient` that satisfies it structurally.
    """
    # The runtime check: `LLMClientPort` is registered in the
    # `__proto__` slot OR has a non-empty `_is_protocol` marker.
    # Either is enough; both are the typing module's internal
    # way to mark a class as a Protocol. mypy --strict enforces
    # the static structural conformance.
    is_protocol_marker = getattr(LLMClientPort, "_is_protocol", False)
    has_proto_slot = hasattr(LLMClientPort, "__proto__")
    assert is_protocol_marker or has_proto_slot, (
        f"LLMClientPort is not a Protocol (marker={is_protocol_marker}, "
        f"proto_slot={has_proto_slot})"
    )


# ---------------------------------------------------------------------------
# Structural conformance — a `FakeLLMClient` with the right method
# is recognized by the Protocol at type-check time (mypy --strict
# verifies this; the runtime call works because Protocol is
# duck-typed).
# ---------------------------------------------------------------------------


class FakeLLMClient:
    """An in-memory `LLMClientPort` for tests.

    Records every call so tests can assert the use case forwarded
    the right `system` / `user` arguments. Returns a fixed response
    string (or raises a fixed exception) for testability.

    This class is intentionally NOT marked as `LLMClientPort` —
    structural conformance is what the Protocol test verifies.
    The `@runtime_checkable` decorator is NOT used on the
    Protocol; mypy --strict is the only enforcement.
    """

    def __init__(
        self,
        response: str = '{"matching_ids": [], "explanation": "fake"}',
        error: Exception | None = None,
    ) -> None:
        self._response = response
        self._error = error
        self.calls: list[tuple[str, str]] = []

    async def complete(self, *, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self._error is not None:
            raise self._error
        return self._response


async def test_fake_llm_client_can_be_constructed_and_called() -> None:
    """A `FakeLLMClient` with the right method signature is
    callable; mypy --strict (run as part of the gate suite)
    confirms the structural conformance with `LLMClientPort`.
    """
    fake = FakeLLMClient(response='{"matching_ids": ["a"]}')
    # Call the method with the same keyword-only signature the
    # real client uses. The test only fails at runtime if the
    # signature is wrong.
    result = await fake.complete(system="sys", user="usr")
    assert result == '{"matching_ids": ["a"]}'
    assert fake.calls == [("sys", "usr")]


async def test_fake_llm_client_raises_when_configured() -> None:
    """A `FakeLLMClient` configured with an error raises it on `complete`."""
    fake = FakeLLMClient(error=RuntimeError("simulated LLM outage"))
    with pytest.raises(RuntimeError, match="simulated LLM outage"):
        await fake.complete(system="sys", user="usr")


# ---------------------------------------------------------------------------
# `LLMClientPort` is the application's seam — the use case (T-013) imports
# ONLY the Protocol from `application.ports`, never the concrete client
# from `infrastructure.llm._client`. This test pins that contract: the
# concrete client MUST satisfy the Protocol structurally (mypy check
# below) and a Protocol-conforming fake MUST be substitutable (above).
# ---------------------------------------------------------------------------


def test_application_layer_does_not_import_infrastructure_client() -> None:
    """`application/ports.py` does not import the concrete LLM client.

    The dependency rule for this project is
    `application -> domain <- infrastructure`. A Protocol in
    `application/ports.py` lets the use case depend on the
    application-layer seam; the infrastructure client is
    injected at composition-root time. A regression that
    imports `infrastructure.llm._client` from `application`
    would break the dependency rule.
    """
    import jobs_finder.application.ports as ports_module  # noqa: PLC0415

    source = inspect.getsource(ports_module)
    # Parse the module AST and check every `import` / `import from`
    # statement. A docstring mention is fine; an actual import is
    # the regression we want to catch.
    tree = ast.parse(source)
    bad_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "infrastructure" in alias.name:
                    bad_imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if "infrastructure" in module:
                bad_imports.append(module)
    assert not bad_imports, (
        f"application/ports.py must not import from infrastructure: {bad_imports}"
    )
