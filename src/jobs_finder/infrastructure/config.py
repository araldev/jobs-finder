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
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
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

    Env vars (case-insensitive, `LINKEDIN_` prefix):
        - `LINKEDIN_THROTTLE_SECONDS` (float, default 3.0)
        - `LINKEDIN_USER_AGENT` (str, default modern-Chrome UA)
        - `LINKEDIN_HEADLESS` (bool, default True)
        - `LINKEDIN_REQUEST_TIMEOUT_MS` (int, default 10_000)
        - `LINKEDIN_CORS_ALLOW_ORIGINS` (comma-separated str,
          default `*`. Not for production.)
        - `LINKEDIN_LOG_LEVEL` (str, default `INFO`)
        - `LINKEDIN_LOG_FORMAT` (`json`|`plain`, default `json`)
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


def load_settings() -> Settings:
    """Read env vars and return a fully-populated `Settings`.

    A thin wrapper that exists so callers (and tests) can refer to a
    single factory function instead of importing the class directly.
    """
    return Settings()
