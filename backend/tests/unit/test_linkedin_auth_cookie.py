"""Tests for `LinkedInAuthCookiePort` + `EnvLinkedInAuthCookieAdapter` + the
`LinkedInScraperSettings` slot/repr/eq/hash coverage (T-001 of
`backend-linkedin-auth`).

Spec coverage (REQ-LA-COOKIE-001..004):
- REQ-LA-COOKIE-001: `LinkedInAuthCookiePort` structural conformance
- REQ-LA-COOKIE-002: adapter returns `None` when unset / empty
- REQ-LA-COOKIE-003: adapter returns `SecretStr` (masked repr, minimum length 8)
- REQ-LA-COOKIE-004: `LinkedInScraperSettings.__repr__` masks the cookie
  (`<set>` / `<unset>`), `__eq__` / `__hash__` include the field

The synthetic test value `"AQEAAAAQEAAA"` (12 bytes ASCII) is the
canonical NON-REAL placeholder per the `backend-linkedin-auth`
exploration (obs #353). Real `li_at` cookies are forbidden from
the repo by AGENTS.md rule #7.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr

from jobs_finder.application.ports import LinkedInAuthCookiePort
from jobs_finder.infrastructure.linkedin.auth_cookie import (
    EnvLinkedInAuthCookieAdapter,
)
from jobs_finder.infrastructure.linkedin.scraper import LinkedInScraperSettings
from tests.conftest import FakeLinkedInAuthCookiePort


class TestPortProtocolStructuralConformance:
    """REQ-LA-COOKIE-001 — `LinkedInAuthCookiePort` Protocol shape."""

    def test_port_protocol_structural_conformance(self) -> None:
        adapter = EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA"))
        # mypy --strict checks this assignment at type-check time.
        port: LinkedInAuthCookiePort = adapter
        assert port.cookie() is not None

    def test_fake_double_conforms_to_protocol(self) -> None:
        fake = FakeLinkedInAuthCookiePort(cookie=SecretStr("AQEAAAAQEAAA"))
        port: LinkedInAuthCookiePort = fake
        assert port.cookie() is not None


class TestEnvLinkedInAuthCookieAdapter:
    """REQ-LA-COOKIE-002 + REQ-LA-COOKIE-003 — adapter behavior."""

    def test_adapter_returns_none_when_unset(self) -> None:
        adapter = EnvLinkedInAuthCookieAdapter(None)
        assert adapter.cookie() is None

    def test_adapter_returns_none_when_empty_secret(self) -> None:
        adapter = EnvLinkedInAuthCookieAdapter(SecretStr(""))
        assert adapter.cookie() is None

    def test_adapter_returns_secretstr_with_masked_repr(self) -> None:
        adapter = EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA"))
        result = adapter.cookie()
        assert isinstance(result, SecretStr)
        assert result.get_secret_value() == "AQEAAAAQEAAA"
        # Pydantic `SecretStr` masks its repr with the literal `**********`
        assert repr(result) == "SecretStr('**********')"

    def test_adapter_returns_secretstr_at_minimum_length_8(self) -> None:
        adapter = EnvLinkedInAuthCookieAdapter(SecretStr("12345678"))
        result = adapter.cookie()
        assert isinstance(result, SecretStr)
        assert result.get_secret_value() == "12345678"


class TestLinkedInScraperSettingsAuthCookie:
    """REQ-LA-COOKIE-004 — `__repr__` masking + `__eq__` / `__hash__`."""

    def test_settings_repr_masks_set_cookie(self) -> None:
        settings = LinkedInScraperSettings(
            user_agent="ua",
            timeout_ms=10000,
            auth_cookie=EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA")),
        )
        text = repr(settings)
        assert "<set>" in text
        assert "AQEAAAAQEAAA" not in text

    def test_settings_repr_masks_unset_cookie(self) -> None:
        settings = LinkedInScraperSettings(
            user_agent="ua",
            timeout_ms=10000,
            auth_cookie=None,
        )
        text = repr(settings)
        assert "<unset>" in text

    def test_settings_eq_hash_includes_auth_cookie(self) -> None:
        a = LinkedInScraperSettings(
            user_agent="ua",
            timeout_ms=10000,
            auth_cookie=EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA")),
        )
        b = LinkedInScraperSettings(
            user_agent="ua",
            timeout_ms=10000,
            auth_cookie=EnvLinkedInAuthCookieAdapter(SecretStr("DIFF_VAL_AQXQ")),
        )
        assert a != b
        assert hash(a) != hash(b)

        # Sanity: two with the same cookie ARE equal + same hash.
        a_dup = LinkedInScraperSettings(
            user_agent="ua",
            timeout_ms=10000,
            auth_cookie=EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA")),
        )
        assert a == a_dup
        assert hash(a) == hash(a_dup)


class TestOperatorDocs:
    """T-005 of `backend-linkedin-auth` — operator-facing docs.

    The grep tests pin the presence (NOT the value) of the
    `LINKEDIN_LI_AT` env var in `.env.example` and the new
    "LinkedIn auth cookie (optional)" subsection in
    `README.md`. The tests do NOT assert any cookie value
    appears in the docs (AGENTS.md rule #7 forbids real
    `li_at` in the repo).
    """

    def test_env_example_documents_linkedin_li_at(self) -> None:
        env_example = Path(__file__).resolve().parents[2] / ".env.example"
        assert env_example.exists()
        text = env_example.read_text(encoding="utf-8")
        # The presence of the var name is enough — the value
        # is intentionally empty (the line is `LINKEDIN_LI_AT=`
        # with NO real value).
        assert "LINKEDIN_LI_AT=" in text

    def test_readme_documents_linkedin_auth_cookie_subsection(self) -> None:
        readme = Path(__file__).resolve().parents[2] / "README.md"
        assert readme.exists()
        text = readme.read_text(encoding="utf-8")
        assert "### LinkedIn auth cookie (optional)" in text


# ---------------------------------------------------------------------------
# T-001 of `backend-linkedin-stealth` — 3 backward-compat scenarios.
#
# The v1 `EnvLinkedInAuthCookieAdapter` (single cookie) is KEPT
# byte-identical alongside the new `MultiEnvLinkedInAuthCookiesAdapter`
# (4 cookies). The v1 adapter satisfies the v1 `LinkedInAuthCookiePort`
# (singular) Protocol but NOT the new `LinkedInAuthCookiesPort` (plural)
# Protocol — the 2 Protocols are intentionally distinct (one returns
# 1 cookie, the other returns N). The 35 v1 tests that construct
# `EnvLinkedInAuthCookieAdapter` directly stay green.
# ---------------------------------------------------------------------------


class TestV1SingleCookieAdapterBackwardCompat:
    """REQ-LST-COOKIE-001 (backward compat) — the v1
    `EnvLinkedInAuthCookieAdapter(SecretStr | None)` ctor still
    works; the v1 class is byte-identical to the v1 cycle.
    """

    def test_v1_adapter_ctor_accepts_secretstr(self) -> None:
        """The v1 ctor accepts a `SecretStr` value (the v1 contract)."""
        adapter = EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA"))
        cookie = adapter.cookie()
        assert cookie is not None
        assert cookie.get_secret_value() == "AQEAAAAQEAAA"

    def test_v1_adapter_ctor_accepts_none(self) -> None:
        """The v1 ctor accepts `None` (the v1 zero-config boot path)."""
        adapter = EnvLinkedInAuthCookieAdapter(None)
        assert adapter.cookie() is None

    def test_v1_adapter_ctor_normalizes_empty_secretstr(self) -> None:
        """The v1 ctor normalizes empty `SecretStr` to `None` (v1 defense-in-depth)."""
        adapter = EnvLinkedInAuthCookieAdapter(SecretStr(""))
        assert adapter.cookie() is None


# ---------------------------------------------------------------------------
# T-005 of `backend-linkedin-xvfb` — REQ-LBSc-002 (F-4 fold-in).
#
# The 5th LinkedIn cookie (`bscookie`, F-4 per obs #375 §9)
# extends `MultiEnvLinkedInAuthCookiesAdapter` to 5 positions.
# The canonical 5-name order is
# `li_at → JSESSIONID → bcookie → bscookie → li_gc`
# (the new slot lands alphabetically between `bcookie` and `li_gc`).
# The 2 tests below are the RED-first regression: each MUST
# fail on main (the adapter has 4 slots) and pass after the
# 5-slot extension lands.
# ---------------------------------------------------------------------------


class TestBscookieAdapter:
    """REQ-LBSc-002 — `MultiEnvLinkedInAuthCookiesAdapter` 5-slot extension."""

    def test_bscookie_cookie_injection(self) -> None:
        """`cookies()` returns 5 entries in canonical order when all 5 cookies are set.

        REQ-LBSc-002: when ALL 5 cookies are set, the adapter
        returns the filtered list in the canonical order
        `li_at → JSESSIONID → bcookie → bscookie → li_gc`.
        The new `bscookie` slot lands alphabetically between
        `bcookie` and `li_gc` (the position is load-bearing —
        a future refactor that re-orders MUST also update the
        order in `_COOKIE_NAMES` AND in `__init__`).
        """
        from jobs_finder.infrastructure.linkedin.auth_cookie import (  # noqa: PLC0415
            MultiEnvLinkedInAuthCookiesAdapter,
        )

        adapter = MultiEnvLinkedInAuthCookiesAdapter(
            li_at=SecretStr("AQE1234567890"),
            jsessionid=SecretStr("ajax:12345"),
            bcookie=SecretStr("v2_xyz_padded"),
            bscookie=SecretStr("bsc_padded_xx"),
            li_gc=SecretStr("gc_abc_padded"),
        )
        cookies = adapter.cookies()
        assert cookies is not None
        assert len(cookies) == 5
        # The canonical order is load-bearing: li_at → JSESSIONID
        # → bcookie → bscookie → li_gc.
        assert [name for name, _ in cookies] == [
            "li_at",
            "JSESSIONID",
            "bcookie",
            "bscookie",
            "li_gc",
        ]

    def test_bscookie_none_keeps_4_cookies(self) -> None:
        """`cookies()` returns 4 entries when `bscookie=None` (F-4 additivity pin).

        REQ-LBSc-002: when `bscookie=None` AND the other 4 are
        set, the adapter returns 4 entries (the F-4 additivity
        pin — adding a 5th optional cookie MUST NOT break the
        4-cookie path). The order is the canonical 4:
        `li_at → JSESSIONID → bcookie → li_gc`.
        """
        from jobs_finder.infrastructure.linkedin.auth_cookie import (  # noqa: PLC0415
            MultiEnvLinkedInAuthCookiesAdapter,
        )

        adapter = MultiEnvLinkedInAuthCookiesAdapter(
            li_at=SecretStr("AQE1234567890"),
            jsessionid=SecretStr("ajax:12345"),
            bcookie=SecretStr("v2_xyz_padded"),
            bscookie=None,  # F-4 additivity pin
            li_gc=SecretStr("gc_abc_padded"),
        )
        cookies = adapter.cookies()
        assert cookies is not None
        assert len(cookies) == 4
        # The 4 names are in canonical order; `bscookie` is
        # filtered out (not in the returned list).
        assert [name for name, _ in cookies] == [
            "li_at",
            "JSESSIONID",
            "bcookie",
            "li_gc",
        ]
