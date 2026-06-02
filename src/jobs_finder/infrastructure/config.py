"""Runtime configuration for the jobs-finder service.

Spec: REQ-005, REQ-006. Env-driven so the same image can run in dev, CI,
and prod with different throttles, UAs, and timeouts.

`Settings` is a `pydantic_settings.BaseSettings` subclass. Each field
maps to a `LINKEDIN_*` env var (case-insensitive, prefix configurable in
the model config). Defaults are pinned in the field declarations and
match the design doc.

The T-008 batch landed a plain `@dataclass` skeleton with the same
fields; T-009 converts it to `BaseSettings` and adds `load_settings()`.
The dataclass skeleton is intentionally NOT retained — `BaseSettings`
is the canonical loader for the project from this point on.

T-012 (CRITICAL fix batch) adds three fields required by the design
but missing from the previous impl:
  - `cors_allow_origins` (REQ-006): list of origins the CORS
    middleware will accept. Default `["*"]` so a browser-based dev
    client can call the API. **Not for production**: set the env var
    to a comma-separated allowlist in any non-dev environment.
  - `log_level` (REQ-006): root logger level. Default `INFO`.
  - `log_format` (REQ-006): `json` (default, structured) or `plain`
    (stdlib default formatter, useful for local development).

T-001 of `infojobs_platform` adds six InfoJobs-specific fields below
the Indeed block. The same per-field `validation_alias` pattern is
used so each `infojobs_*` field reads from its own `INFOJOBS_*` env
var (the model-level `env_prefix="LINKEDIN_"` is preserved and the
new fields opt out of the prefix by declaring an alias).
"""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# A plausible stealth desktop UA. The exact fingerprint is not load-bearing;
# any modern Chrome string is enough to bypass the most basic anti-bot
# filters LinkedIn's public search applies.
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class Settings(BaseSettings):
    """Env-overridable runtime configuration.

    LinkedIn env vars (case-insensitive, `LINKEDIN_` prefix — model-level):
        - `LINKEDIN_THROTTLE_SECONDS` (float, default 3.0)
        - `LINKEDIN_USER_AGENT` (str, default modern-Chrome UA)
        - `LINKEDIN_HEADLESS` (bool, default True)
        - `LINKEDIN_REQUEST_TIMEOUT_MS` (int, default 10_000)
        - `LINKEDIN_CORS_ALLOW_ORIGINS` (comma-separated str,
          default `*`. Not for production.)
        - `LINKEDIN_LOG_LEVEL` (str, default `INFO`)
        - `LINKEDIN_LOG_FORMAT` (`json`|`plain`, default `json`)

    Indeed env vars (per-field `validation_alias` — see REQ-I-011):
        - `INDEED_USER_AGENT` (str, default same stealth UA as LinkedIn)
        - `INDEED_THROTTLE_SECONDS` (float, default 3.0)
        - `INDEED_TIMEOUT_MS` (int, default 15_000)
        - `INDEED_DOMAIN` (str, default `es.indeed.com`)
        - `INDEED_MAX_PAGES` (int, default 10 — hard cap on pagination)
        - `INDEED_INTER_PAGE_DELAY_SECONDS` (float, default 1.0) — sleep
          between pagination pages to reduce Cloudflare re-challenge
          probability. Set to `0.0` to disable. Added as a follow-up to
          the page-2 timeout bug fixed in `fd51ea1`.

    InfoJobs env vars (per-field `validation_alias` — see REQ-J-001,
    REQ-J-003; added in T-001 of `infojobs_platform`):
        - `INFOJOBS_USER_AGENT` (str, default same stealth UA as LinkedIn)
        - `INFOJOBS_THROTTLE_SECONDS` (float, default 3.0)
        - `INFOJOBS_TIMEOUT_MS` (int, default 15_000)
        - `INFOJOBS_DOMAIN` (str, default `www.infojobs.net`)
        - `INFOJOBS_MAX_PAGES` (int, default 10 — hard cap on pagination)
        - `INFOJOBS_INTER_PAGE_DELAY_SECONDS` (float, default 1.5) —
          sleep between pagination pages. Stricter than the Indeed
          default `1.0` because InfoJobs anti-bot (Distil + Geetest) is
          more aggressive than Cloudflare. Set to `0.0` to disable.
    """

    model_config = SettingsConfigDict(
        env_prefix="LINKEDIN_",
        case_sensitive=False,
        extra="ignore",
    )

    throttle_seconds: float = 3.0
    user_agent: str = _DEFAULT_USER_AGENT
    headless: bool = True
    request_timeout_ms: int = 10_000

    # REQ-006 — CORS allowlist. `*` is the dev default; production must
    # override via `LINKEDIN_CORS_ALLOW_ORIGINS=https://app.example.com`.
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"])

    # REQ-006 — structured logging controls.
    log_level: str = "INFO"
    log_format: Literal["json", "plain"] = "json"

    # ------------------------------------------------------------------
    # Indeed-specific settings (REQ-I-011)
    #
    # The model-level `env_prefix="LINKEDIN_"` only applies to fields
    # that do not declare a `validation_alias`. For each Indeed field
    # we use `AliasChoices("INDEED_*", "indeed_*")` so that:
    #
    #   - Env var lookup reads the `INDEED_*` env var
    #     (e.g. `INDEED_THROTTLE_SECONDS=6.0`).
    #   - Programmatic construction (`Settings(indeed_throttle_seconds=6.0)`)
    #     still works via the second choice in `AliasChoices`.
    #
    # The LinkedIn fields above are intentionally left untouched; their
    # env-var lookup is still driven by the model-level prefix.
    # ------------------------------------------------------------------

    indeed_user_agent: str = Field(
        default=_DEFAULT_USER_AGENT,
        validation_alias=AliasChoices("INDEED_USER_AGENT", "indeed_user_agent"),
    )
    indeed_throttle_seconds: float = Field(
        default=3.0,
        validation_alias=AliasChoices("INDEED_THROTTLE_SECONDS", "indeed_throttle_seconds"),
    )
    indeed_timeout_ms: int = Field(
        default=15_000,
        validation_alias=AliasChoices("INDEED_TIMEOUT_MS", "indeed_timeout_ms"),
    )
    indeed_domain: str = Field(
        default="es.indeed.com",
        validation_alias=AliasChoices("INDEED_DOMAIN", "indeed_domain"),
    )
    indeed_max_pages: int = Field(
        default=10,
        validation_alias=AliasChoices("INDEED_MAX_PAGES", "indeed_max_pages"),
    )
    indeed_inter_page_delay_seconds: float = Field(
        default=1.0,
        validation_alias=AliasChoices(
            "INDEED_INTER_PAGE_DELAY_SECONDS", "indeed_inter_page_delay_seconds"
        ),
    )

    # ------------------------------------------------------------------
    # InfoJobs-specific settings (REQ-J-001, REQ-J-003)
    #
    # The model-level `env_prefix="LINKEDIN_"` only applies to fields
    # that do not declare a `validation_alias`. For each InfoJobs field
    # we use `AliasChoices("INFOJOBS_*", "infojobs_*")` so that:
    #
    #   - Env var lookup reads the `INFOJOBS_*` env var
    #     (e.g. `INFOJOBS_THROTTLE_SECONDS=6.0`).
    #   - Programmatic construction (`Settings(infojobs_throttle_seconds=6.0)`)
    #     still works via the second choice in `AliasChoices`.
    #
    # The LinkedIn + Indeed fields above are intentionally left
    # untouched; their env-var lookup is still driven by their
    # respective per-field aliases (or the model-level prefix for the
    # LinkedIn fields).
    # ------------------------------------------------------------------

    infojobs_user_agent: str = Field(
        default=_DEFAULT_USER_AGENT,
        validation_alias=AliasChoices("INFOJOBS_USER_AGENT", "infojobs_user_agent"),
    )
    infojobs_throttle_seconds: float = Field(
        default=3.0,
        validation_alias=AliasChoices("INFOJOBS_THROTTLE_SECONDS", "infojobs_throttle_seconds"),
    )
    infojobs_timeout_ms: int = Field(
        default=15_000,
        validation_alias=AliasChoices("INFOJOBS_TIMEOUT_MS", "infojobs_timeout_ms"),
    )
    infojobs_domain: str = Field(
        default="www.infojobs.net",
        validation_alias=AliasChoices("INFOJOBS_DOMAIN", "infojobs_domain"),
    )
    infojobs_max_pages: int = Field(
        default=10,
        validation_alias=AliasChoices("INFOJOBS_MAX_PAGES", "infojobs_max_pages"),
    )
    infojobs_inter_page_delay_seconds: float = Field(
        default=1.5,
        validation_alias=AliasChoices(
            "INFOJOBS_INTER_PAGE_DELAY_SECONDS", "infojobs_inter_page_delay_seconds"
        ),
    )


def load_settings() -> Settings:
    """Read env vars and return a fully-populated `Settings`.

    A thin wrapper that exists so callers (and tests) can refer to a
    single factory function instead of importing the class directly.
    """
    return Settings()
