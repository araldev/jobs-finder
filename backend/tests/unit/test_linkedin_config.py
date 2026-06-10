"""Tests for `Settings.linkedin_li_at` field + 2 validators (T-002 of
`backend-linkedin-auth`).

Spec coverage (REQ-LA-CFG-001..004):
- REQ-LA-CFG-001: env binding (case-insensitive `LINKEDIN_LI_AT` +
  programmatic `linkedin_li_at=` kwarg; default `None`)
- REQ-LA-CFG-002: Q1 validator rejects `len < 8` (3 chars, 7 chars) and
  accepts the 8-char boundary (`len >= 8`)
- REQ-LA-CFG-003: validator is a no-op when value is `None`; the
  `mode="before"` validator normalizes empty `""` and empty
  `SecretStr("")` to `None`
- REQ-LA-CFG-004: `Settings.__repr__` does NOT include the cookie
  value (the `SecretStr` type enforces the field-level mask; this
  test pins the model-level repr mask)

The synthetic test value `"AQEAAAAQEAAA"` (12 bytes ASCII) is the
canonical NON-REAL placeholder per the `backend-linkedin-auth`
exploration (obs #353). Real `li_at` cookies are forbidden from
the repo by AGENTS.md rule #7.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from jobs_finder.infrastructure.config import Settings


class TestSettingsEnvBinding:
    """REQ-LA-CFG-001 — env binding + default `None`."""

    def test_settings_reads_linkedin_li_at_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LINKEDIN_LI_AT", "AQEAAAAQEAAA")
        settings = Settings()
        assert settings.linkedin_li_at is not None
        assert settings.linkedin_li_at.get_secret_value() == "AQEAAAAQEAAA"

    def test_settings_linkedin_li_at_defaults_to_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LINKEDIN_LI_AT", raising=False)
        settings = Settings()
        assert settings.linkedin_li_at is None

    def test_settings_linkedin_li_at_programmatic_construction(self) -> None:
        settings = Settings(linkedin_li_at=SecretStr("AQEAAAAQEAAA"))
        assert settings.linkedin_li_at is not None
        assert settings.linkedin_li_at.get_secret_value() == "AQEAAAAQEAAA"


class TestSettingsLengthValidator:
    """REQ-LA-CFG-002 — Q1 validator rejects `len < 8`."""

    def test_settings_rejects_short_li_at_3_chars(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            Settings(linkedin_li_at=SecretStr("abc"))
        msg = str(exc_info.value)
        assert "must be at least 8 characters" in msg
        assert "got 3" in msg

    def test_settings_rejects_short_li_at_7_chars(self) -> None:
        # Boundary: 7 chars is rejected (threshold is `< 8`, inclusive)
        with pytest.raises(ValidationError) as exc_info:
            Settings(linkedin_li_at=SecretStr("1234567"))
        msg = str(exc_info.value)
        assert "must be at least 8 characters" in msg
        assert "got 7" in msg

    def test_settings_accepts_minimum_length_8(self) -> None:
        # Boundary: 8 chars is accepted (the minimum valid length)
        settings = Settings(linkedin_li_at=SecretStr("12345678"))
        assert settings.linkedin_li_at is not None
        assert settings.linkedin_li_at.get_secret_value() == "12345678"


class TestSettingsEmptyNormalization:
    """REQ-LA-CFG-003 — no-op when `None`; empty→`None` normalization."""

    def test_settings_accepts_none_li_at(self) -> None:
        settings = Settings(linkedin_li_at=None)
        assert settings.linkedin_li_at is None

    def test_settings_normalizes_empty_secret_to_none(self) -> None:
        settings = Settings(linkedin_li_at=SecretStr(""))
        assert settings.linkedin_li_at is None

    def test_settings_normalizes_empty_string_to_none(self) -> None:
        settings = Settings(linkedin_li_at="")  # type: ignore[arg-type]
        assert settings.linkedin_li_at is None


class TestSettingsReprNoLeak:
    """REQ-LA-CFG-004 — `Settings.__repr__` does NOT include the cookie value."""

    def test_settings_repr_does_not_leak_cookie_value(self) -> None:
        settings = Settings(linkedin_li_at=SecretStr("AQEAAAAQEAAA"))
        text = repr(settings)
        assert "AQEAAAAQEAAA" not in text


# ---------------------------------------------------------------------------
# T-002 of `backend-linkedin-stealth` — 3 new `Settings.linkedin_*`
# fields + 2 shared validator helpers (REQ-LST-CFG-001..003).
#
# The 3 new fields are `linkedin_jsessionid`, `linkedin_bcookie`,
# `linkedin_li_gc` — each is `SecretStr | None` with
# `AliasChoices(<UPPER>, <lower>)` (the same shape as the v1
# `linkedin_li_at`). The 2 v1 inline validators on `linkedin_li_at`
# are REFACTORED to delegate to 2 new shared helpers (the v1 field
# behavior is unchanged; the 10 v1 `test_linkedin_config.py` tests
# stay GREEN).
# ---------------------------------------------------------------------------


class TestLinkedInStealthCookies:
    """REQ-LST-CFG-001..003 — 3 new `Settings.linkedin_*` cookie
    fields + 2 shared validator helpers.
    """

    def test_settings_rejects_short_jsessionid_with_field_name(self) -> None:
        """`Settings(linkedin_jsessionid=SecretStr('abc'))` raises with the field name.

        Pins REQ-LST-CFG-002: the error message names the field so the
        operator can self-diagnose (a 3-char `LINKEDIN_JSESSIONID` typo is
        not the same as a 3-char `LINKEDIN_LI_AT` typo). Mirrors the v1
        `test_settings_rejects_short_li_at_3_chars` pattern with a
        different field + a different env-var name in the error.
        """
        with pytest.raises(ValidationError) as exc_info:
            Settings(linkedin_jsessionid=SecretStr("abc"))
        msg = str(exc_info.value)
        assert "LINKEDIN_JSESSIONID" in msg
        assert "must be at least 8 characters" in msg
        assert "got 3" in msg

    def test_settings_accepts_minimum_length_8_for_jsessionid(self) -> None:
        """`Settings(linkedin_jsessionid=SecretStr('12345678'))` (8 chars) PASSES."""
        settings = Settings(linkedin_jsessionid=SecretStr("12345678"))
        assert settings.linkedin_jsessionid is not None
        assert settings.linkedin_jsessionid.get_secret_value() == "12345678"

    def test_settings_normalizes_empty_bcookie_to_none(self) -> None:
        """`Settings(linkedin_bcookie='')` normalizes to `None` (REQ-LST-CFG-001)."""
        settings = Settings(linkedin_bcookie="")  # type: ignore[arg-type]
        assert settings.linkedin_bcookie is None

    def test_settings_repr_does_not_leak_jsessionid_value(self) -> None:
        """`repr(Settings(linkedin_jsessionid=...))` does NOT contain the value.

        Pins REQ-LST-CFG-003: the new field's repr mask matches the
        v1 `linkedin_li_at` repr mask (the `SecretStr` type
        enforces field-level masking; this test pins the model-level
        repr mask).
        """
        settings = Settings(linkedin_jsessionid=SecretStr("AQEAAAAQEAAA"))
        text = repr(settings)
        assert "AQEAAAAQEAAA" not in text

    def test_settings_env_alias_binds_uppercase(self) -> None:
        """`LINKEDIN_LI_GC` env var is bound to `settings.linkedin_li_gc`.

        Pins REQ-LST-CFG-001: the new fields follow the v1
        `AliasChoices(<UPPER>, <lower>)` pattern. A monkeypatched
        `LINKEDIN_LI_GC=...` env var MUST populate
        `settings.linkedin_li_gc` (case-insensitive binding).
        """
        monkeypatch = pytest.MonkeyPatch()
        try:
            monkeypatch.setenv("LINKEDIN_LI_GC", "12345678")
            settings = Settings()
            assert settings.linkedin_li_gc is not None
            assert settings.linkedin_li_gc.get_secret_value() == "12345678"
        finally:
            monkeypatch.undo()
