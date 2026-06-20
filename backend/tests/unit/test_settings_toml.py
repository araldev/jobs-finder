"""Unit tests for the TOML defaults layer in `load_settings()`.

The TOML layer (added in the `toml-config-defaults` refactor) lets the
service ship non-secret operational defaults in
`backend/config/default.toml` instead of polluting `backend/.env` with
45+ values. The precedence contract is:

    env vars (already set)  >  TOML defaults  >  field defaults

These tests pin the 4 invariants the helper must satisfy:

1. TOML defaults are injected into `Settings` when the env var is unset.
2. Pre-set env vars beat TOML defaults (env > TOML).
3. `local.toml` overrides `default.toml` (operator override).
4. Missing TOML files do not crash `load_settings()` — it falls through
   to field defaults.

The `Settings` class itself is constructed directly (bypassing the TOML
layer) by the other 553 tests in the suite — that path is unchanged.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from jobs_finder.infrastructure import config as config_module
from jobs_finder.infrastructure.config import Settings, load_settings

# ---------------------------------------------------------------------------
# 1. TOML defaults are visible to Settings when env var is unset.
# ---------------------------------------------------------------------------


def test_load_settings_injects_toml_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """`load_settings()` reads `backend/config/default.toml` and injects its
    values into `Settings` when the env var is not set.

    The test picks `INDEED_DOMAIN` because its field default
    (`"es.indeed.com"`) matches the TOML value AND is unlikely to be
    in the user's local `backend/.env` (the committed `.env.example`
    documents it but `.env` overrides it only for operators that have
    changed it). The `monkeypatch.delenv(..., raising=False)` guards
    against the var being set in the runner's environment.
    """
    monkeypatch.delenv("INDEED_DOMAIN", raising=False)

    settings = load_settings()

    assert settings.indeed_domain == "es.indeed.com"


# ---------------------------------------------------------------------------
# 2. Pre-set env vars beat TOML defaults (env > TOML).
# ---------------------------------------------------------------------------


def test_load_settings_env_var_overrides_toml(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting `INDEED_DOMAIN` in the process env beats the TOML default.

    The TOML layer uses `os.environ.setdefault`, so a pre-set env var
    wins over the TOML-injected value. This is the operator-override
    contract: `INDEED_DOMAIN=uk.indeed.com` in `.env` (or shell) must
    produce `settings.indeed_domain == "uk.indeed.com"`.
    """
    monkeypatch.setenv("INDEED_DOMAIN", "uk.indeed.com")

    settings = load_settings()

    assert settings.indeed_domain == "uk.indeed.com"


# ---------------------------------------------------------------------------
# 3. `local.toml` overrides `default.toml` (operator override).
# ---------------------------------------------------------------------------


def test_load_settings_local_toml_overrides_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`config/local.toml` overrides `config/default.toml` for the same key.

    The operator override pattern: ship `default.toml` with sensible
    values; operators who need to tweak ONE knob copy the relevant
    line into `local.toml` (gitignored) without touching `default.toml`.
    The helper reads `default.toml` first, then `local.toml` — the
    local file wins for keys present in BOTH files.
    """
    default_toml = tmp_path / "default.toml"
    default_toml.write_text('INDEED_DOMAIN = "es.indeed.com"\n', encoding="utf-8")

    local_toml = tmp_path / "local.toml"
    local_toml.write_text('INDEED_DOMAIN = "de.indeed.com"\n', encoding="utf-8")

    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.delenv("INDEED_DOMAIN", raising=False)

    settings = load_settings()

    assert settings.indeed_domain == "de.indeed.com"


# ---------------------------------------------------------------------------
# 4. Missing TOML files do not crash `load_settings()`.
# ---------------------------------------------------------------------------


def test_load_settings_skips_when_toml_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`load_settings()` does NOT crash when `default.toml` is absent.

    The TOML layer is opt-in: if `backend/config/default.toml` does
    not exist (e.g. a fresh checkout before this refactor, or a test
    fixture that never wrote the file), `load_settings()` falls
    through to the `Settings` field defaults. The returned instance
    is a valid `Settings` with the field default for the picked key.
    """
    missing_dir = tmp_path / "no-config-here"
    assert not missing_dir.exists()

    monkeypatch.setattr(config_module, "CONFIG_DIR", missing_dir)
    monkeypatch.delenv("INDEED_DOMAIN", raising=False)

    settings = load_settings()

    assert isinstance(settings, Settings)
    assert settings.indeed_domain == "es.indeed.com"


# ---------------------------------------------------------------------------
# 5. `default.toml` is a flat table (top-level keys, not nested sections).
# ---------------------------------------------------------------------------


def test_default_toml_is_flat() -> None:
    """`backend/config/default.toml` contains only flat top-level keys.

    Flat structure is required because the helper does
    `tomllib.load(path)` and expects a single-level `dict`; nested
    sections (`[section]` headers) would surface as nested dicts and
    fail the type assertion in `_load_toml_defaults()`.

    This test catches a future change that introduces a `[linkedin]`
    section header — the helper would silently miss all nested keys
    and the unit tests above would fail (no TOML values injected).
    """
    config_path = Path(config_module.CONFIG_DIR) / "default.toml"
    assert config_path.exists(), (
        f"backend/config/default.toml not found at {config_path}; "
        "the TOML defaults layer is broken"
    )

    with config_path.open("rb") as fh:
        data = tomllib.load(fh)

    assert isinstance(data, dict), (
        f"default.toml must be a flat table, got {type(data).__name__}"
    )
    assert data, "default.toml is empty"
    # Every key MUST be uppercase (env-var shape, case-sensitive match).
    for key in data:
        assert key == key.upper(), (
            f"default.toml key {key!r} is not uppercase; env-var lookup "
            "is case-insensitive but the helper expects uppercase keys"
        )


# ---------------------------------------------------------------------------
# 6. The TOML layer does not break programmatic `Settings(...)` construction.
# ---------------------------------------------------------------------------


def test_settings_constructor_bypasses_toml_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    """`Settings(...)` constructed directly bypasses the TOML layer.

    The existing 553 tests construct `Settings` directly (without
    going through `load_settings()`). The TOML injection is gated
    inside `load_settings()` ONLY — `Settings()` reads from
    `os.environ` + `.env` + field defaults, exactly as before. This
    pins the "no behavioral change for direct construction" contract.

    The `monkeypatch.delenv` guards against a previous test's
    `load_settings()` call having injected `INDEED_DOMAIN` into
    `os.environ` (test isolation — the helper uses
    `os.environ.setdefault` which mutates the env permanently).
    """
    monkeypatch.delenv("INDEED_DOMAIN", raising=False)

    # No env override, no TOML injection → field default applies.
    settings = Settings(_env_file=None)  # type: ignore[call-arg] 

    assert settings.indeed_domain == "es.indeed.com"
