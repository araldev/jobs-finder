"""Tests for `LinkedInAuthCookiesPort` (plural) + `MultiEnvLinkedInAuthCookiesAdapter` +
the conftest `FakeLinkedInAuthCookiesPort` companion (T-001 of
`backend-linkedin-stealth`).

Spec coverage (REQ-LST-COOKIE-001..005):
- REQ-LST-COOKIE-001: `LinkedInAuthCookiesPort` structural conformance
  (the application-layer Protocol lives in `application/ports.py` and
  has exactly 1 method `cookies() -> list[tuple[str, SecretStr]] | None`).
- REQ-LST-COOKIE-002: `cookies()` returns `None` when ALL 4 cookies are
  `None` (the soft-mode sentinel — preserves v1 zero-config boot).
- REQ-LST-COOKIE-003: `cookies()` returns a filtered list when ≥1 cookie
  is non-`None`.
- REQ-LST-COOKIE-004: the filtered list is in deterministic order
  `li_at → JSESSIONID → bcookie → li_gc` (the canonical LinkedIn-session
  order — a future refactor that re-orders the fields breaks the test).
- REQ-LST-COOKIE-005: `__repr__` masks the cookie set as
  `MultiEnvLinkedInAuthCookiesAdapter(<set: N cookies>)` for N>0 and
  `MultiEnvLinkedInAuthCookiesAdapter(<unset>)` for N=0; the synthetic
  test values NEVER appear in the repr (AGENTS.md rule #7 / REQ-LST-COOKIE-005).

The synthetic test values:
  `"AQEAAAAQEAAA"` (12 bytes ASCII) — `li_at` placeholder
  `"ajax:12345"` — `JSESSIONID` placeholder
  `"v2_xyz"` — `bcookie` placeholder
  `"gc_abc"` — `li_gc` placeholder

Real LinkedIn cookies are forbidden from the repo by AGENTS.md rule #7.
"""

from __future__ import annotations

from pydantic import SecretStr

from jobs_finder.application.ports import LinkedInAuthCookiesPort
from jobs_finder.infrastructure.linkedin.auth_cookie import (
    MultiEnvLinkedInAuthCookiesAdapter,
)
from tests.conftest import FakeLinkedInAuthCookiesPort

# ---------------------------------------------------------------------------
# REQ-LST-COOKIE-001 — Protocol structural conformance.
# ---------------------------------------------------------------------------


class TestPortProtocolStructuralConformance:
    """REQ-LST-COOKIE-001 — `LinkedInAuthCookiesPort` Protocol shape.

    The Protocol lives in `application/ports.py` (NOT in
    `infrastructure/`); the `MultiEnvLinkedInAuthCookiesAdapter`
    (production) and the `FakeLinkedInAuthCookiesPort` (test) both
    satisfy it structurally. The assignment to the typed local
    variable is the mypy --strict check; no runtime isinstance
    needed.
    """

    def test_port_protocol_exists_in_application_ports(self) -> None:
        """`LinkedInAuthCookiesPort` is importable from `application.ports`."""
        # The top-level import above is the regression check. The
        # Protocol is NOT `@runtime_checkable`; structural
        # conformance is enforced at mypy time.
        assert LinkedInAuthCookiesPort is not None

    def test_multi_env_adapter_conforms_to_protocol(self) -> None:
        """`MultiEnvLinkedInAuthCookiesAdapter` satisfies the Protocol structurally."""
        adapter = MultiEnvLinkedInAuthCookiesAdapter(
            li_at=SecretStr("AQEAAAAQEAAA"),
            jsessionid=SecretStr("ajax:12345"),
            bcookie=SecretStr("v2_xyz"),
            li_gc=SecretStr("gc_abc"),
        )
        # mypy --strict checks this assignment at type-check time.
        port: LinkedInAuthCookiesPort = adapter
        cookies = port.cookies()
        assert cookies is not None
        assert len(cookies) == 4

    def test_fake_double_conforms_to_protocol(self) -> None:
        """`FakeLinkedInAuthCookiesPort` (conftest) satisfies the Protocol structurally."""
        fake = FakeLinkedInAuthCookiesPort(
            cookies=[
                ("li_at", SecretStr("AQEAAAAQEAAA")),
                ("JSESSIONID", SecretStr("ajax:12345")),
            ]
        )
        # mypy --strict checks this assignment at type-check time.
        port: LinkedInAuthCookiesPort = fake
        cookies = port.cookies()
        assert cookies is not None
        assert len(cookies) == 2


# ---------------------------------------------------------------------------
# REQ-LST-COOKIE-002..004 — adapter behavior.
# ---------------------------------------------------------------------------


class TestMultiEnvAdapter:
    """REQ-LST-COOKIE-002..004 — `MultiEnvLinkedInAuthCookiesAdapter` behavior."""

    def test_cookies_returns_none_when_all_unset(self) -> None:
        """REQ-LST-COOKIE-002 — `cookies()` returns `None` when all 4 are `None`."""
        adapter = MultiEnvLinkedInAuthCookiesAdapter(
            li_at=None, jsessionid=None, bcookie=None, li_gc=None
        )
        assert adapter.cookies() is None

    def test_cookies_filters_out_none_values(self) -> None:
        """REQ-LST-COOKIE-003 — `cookies()` returns a filtered list (no `None` entries)."""
        adapter = MultiEnvLinkedInAuthCookiesAdapter(
            li_at=SecretStr("AQEAAAAQEAAA"),
            jsessionid=None,
            bcookie=SecretStr("v2_xyz"),
            li_gc=None,
        )
        result = adapter.cookies()
        assert result is not None
        # Only the 2 non-None values appear; None values are filtered.
        assert len(result) == 2
        names = [name for (name, _value) in result]
        assert "li_at" in names
        assert "bcookie" in names
        # The None values are NOT in the list.
        assert "JSESSIONID" not in names
        assert "li_gc" not in names

    def test_cookies_returns_deterministic_order(self) -> None:
        """`cookies()` always returns li_at, JSESSIONID, bcookie, li_gc in that order.

        Pins REQ-LST-COOKIE-004: the order is the canonical LinkedIn-session
        order (the v1 caplog bug was a wrong-order assertion; this test
        pins the correct order so a future refactor that re-orders the
        fields breaks the test loudly).
        """
        adapter = MultiEnvLinkedInAuthCookiesAdapter(
            li_at=SecretStr("AQEAAAAQEAAA"),
            jsessionid=SecretStr("ajax:12345"),
            bcookie=SecretStr("v2_xyz"),
            li_gc=SecretStr("gc_abc"),
        )
        cookies = adapter.cookies()
        assert cookies is not None
        names = [name for (name, _value) in cookies]
        assert names == ["li_at", "JSESSIONID", "bcookie", "li_gc"]

    def test_cookies_returns_all_four_when_all_set(self) -> None:
        """When all 4 are non-None, `cookies()` returns all 4 in canonical order."""
        adapter = MultiEnvLinkedInAuthCookiesAdapter(
            li_at=SecretStr("AQEAAAAQEAAA"),
            jsessionid=SecretStr("ajax:12345"),
            bcookie=SecretStr("v2_xyz"),
            li_gc=SecretStr("gc_abc"),
        )
        result = adapter.cookies()
        assert result is not None
        assert len(result) == 4
        # The values are wrapped in `SecretStr` (the unmasked list
        # is consumed by the scraper inside `search()`).
        for _name, value in result:
            assert isinstance(value, SecretStr)

    def test_cookies_filters_order_preserved_with_subset(self) -> None:
        """Subset order follows the canonical order even when 1 or more is None.

        With `li_at=None, jsessionid=set, bcookie=set, li_gc=None`:
        the returned order is `JSESSIONID → bcookie` (the canonical
        order, NOT the order the constructor was called with).
        """
        adapter = MultiEnvLinkedInAuthCookiesAdapter(
            li_at=None,
            jsessionid=SecretStr("ajax:12345"),
            bcookie=SecretStr("v2_xyz"),
            li_gc=None,
        )
        result = adapter.cookies()
        assert result is not None
        names = [name for (name, _value) in result]
        assert names == ["JSESSIONID", "bcookie"]


# ---------------------------------------------------------------------------
# REQ-LST-COOKIE-005 — `__repr__` mask.
# ---------------------------------------------------------------------------


class TestMultiEnvAdapterReprMask:
    """REQ-LST-COOKIE-005 — `__repr__` masks the cookie set (count only, no values)."""

    def test_repr_marks_unset_when_all_none(self) -> None:
        """When all 4 are `None`, the repr says `<unset>`."""
        adapter = MultiEnvLinkedInAuthCookiesAdapter(
            li_at=None, jsessionid=None, bcookie=None, li_gc=None
        )
        text = repr(adapter)
        assert "MultiEnvLinkedInAuthCookiesAdapter" in text
        assert "<unset>" in text

    def test_repr_marks_set_count_when_at_least_one_set(self) -> None:
        """When ≥1 is set, the repr says `<set: N cookies>` (the count, not the names)."""
        adapter = MultiEnvLinkedInAuthCookiesAdapter(
            li_at=SecretStr("AQEAAAAQEAAA"),
            jsessionid=SecretStr("ajax:12345"),
            bcookie=SecretStr("v2_xyz"),
            li_gc=SecretStr("gc_abc"),
        )
        text = repr(adapter)
        assert "<set: 4 cookies>" in text
        # The synthetic test values are NOT in the repr.
        assert "AQEAAAAQEAAA" not in text
        assert "ajax:12345" not in text
        assert "v2_xyz" not in text
        assert "gc_abc" not in text

    def test_repr_count_is_2_when_partial(self) -> None:
        """When 2 of 4 are set, the repr says `<set: 2 cookies>`."""
        adapter = MultiEnvLinkedInAuthCookiesAdapter(
            li_at=SecretStr("AQEAAAAQEAAA"),
            jsessionid=None,
            bcookie=SecretStr("v2_xyz"),
            li_gc=None,
        )
        text = repr(adapter)
        assert "<set: 2 cookies>" in text
        # The synthetic test values are NOT in the repr.
        assert "AQEAAAAQEAAA" not in text
        assert "v2_xyz" not in text


# ---------------------------------------------------------------------------
# Adapter equality / hash (slot-based, all 4 fields).
# ---------------------------------------------------------------------------


class TestMultiEnvAdapterEquality:
    """`__eq__` / `__hash__` cover all 4 fields (so the adapter is
    settings-comparable, mirroring v1's `EnvLinkedInAuthCookieAdapter`).
    """

    def test_two_adapters_with_same_values_are_equal(self) -> None:
        a = MultiEnvLinkedInAuthCookiesAdapter(
            li_at=SecretStr("AQEAAAAQEAAA"),
            jsessionid=SecretStr("ajax:12345"),
            bcookie=SecretStr("v2_xyz"),
            li_gc=SecretStr("gc_abc"),
        )
        a_dup = MultiEnvLinkedInAuthCookiesAdapter(
            li_at=SecretStr("AQEAAAAQEAAA"),
            jsessionid=SecretStr("ajax:12345"),
            bcookie=SecretStr("v2_xyz"),
            li_gc=SecretStr("gc_abc"),
        )
        assert a == a_dup
        assert hash(a) == hash(a_dup)

    def test_adapters_with_different_li_at_are_not_equal(self) -> None:
        a = MultiEnvLinkedInAuthCookiesAdapter(
            li_at=SecretStr("AQEAAAAQEAAA"),
            jsessionid=None,
            bcookie=None,
            li_gc=None,
        )
        b = MultiEnvLinkedInAuthCookiesAdapter(
            li_at=SecretStr("DIFFERENT_LI_AT"),
            jsessionid=None,
            bcookie=None,
            li_gc=None,
        )
        assert a != b
        assert hash(a) != hash(b)


# ---------------------------------------------------------------------------
# Conftest companion — `FakeLinkedInAuthCookiesPort`.
# ---------------------------------------------------------------------------


class TestFakeLinkedInAuthCookiesPort:
    """`FakeLinkedInAuthCookiesPort` is the conftest test double for
    `LinkedInAuthCookiesPort`. Mirrors the v1 `FakeLinkedInAuthCookiePort`
    pattern (a value-holder with no I/O, no async, no side-effects).
    """

    def test_default_is_none_when_no_cookies(self) -> None:
        """Default ctor (no `cookies=`) → `cookies()` returns `None`."""
        fake = FakeLinkedInAuthCookiesPort()
        assert fake.cookies() is None

    def test_cookies_returns_provided_list(self) -> None:
        """When constructed with a `cookies=` list, returns it verbatim."""
        fake = FakeLinkedInAuthCookiesPort(cookies=[("li_at", SecretStr("AQEAAAAQEAAA"))])
        result = fake.cookies()
        assert result is not None
        assert len(result) == 1
        assert result[0][0] == "li_at"

    def test_fake_conforms_to_protocol_typecheck(self) -> None:
        """The fake satisfies `LinkedInAuthCookiesPort` structurally (mypy check)."""
        fake: LinkedInAuthCookiesPort = FakeLinkedInAuthCookiesPort(
            cookies=[("li_at", SecretStr("AQEAAAAQEAAA"))]
        )
        assert fake.cookies() is not None
