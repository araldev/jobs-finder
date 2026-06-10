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
