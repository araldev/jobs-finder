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
