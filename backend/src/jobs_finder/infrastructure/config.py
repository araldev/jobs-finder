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

import ipaddress
import json
from ipaddress import IPv4Network, IPv6Network
from typing import Any, Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# A plausible stealth desktop UA. The exact fingerprint is not load-bearing;
# any modern Chrome string is enough to bypass the most basic anti-bot
# filters LinkedIn's public search applies.
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Minimum length for `LINKEDIN_LI_AT` (T-002 of `backend-linkedin-auth`,
# REQ-LA-CFG-002). Real `li_at` cookies are ~150 chars; 8 is a
# conservative threshold that catches operator typos
# (`LINKEDIN_LI_AT=abc` → 3 chars → hard error) without rejecting
# any realistic real cookie. The constant lives at module scope so
# the validator + the error message reference the same value
# (no magic numbers per ruff PLR2004).
MIN_LI_AT_LENGTH: int = 8


# ---------------------------------------------------------------------------
# Shared `linkedin_*` cookie validators (T-002 of `backend-linkedin-stealth`,
# REQ-LST-CFG-001..003).
#
# The 4 `linkedin_*` cookie fields (`linkedin_li_at`, `linkedin_jsessionid`,
# `linkedin_bcookie`, `linkedin_li_gc`) share the same 2 validation
# concerns:
#   1. `mode="before"`: normalize empty inputs (`None` / `""` /
#      `SecretStr("")`) to `None` (the kill-switch contract,
#      REQ-LST-CFG-001).
#   2. `mode="after"`: reject short values with a HARD `ValueError`
#      (REQ-LST-CFG-002 — the operator typo guard).
#
# The 2 helpers are module-level functions (NOT methods) so the
# 4 `field_validator` decorators can delegate to them. The 2nd
# helper accepts a `field_name: str` kwarg so the error message
# can name the field (a 3-char `LINKEDIN_JSESSIONID` typo is NOT
# the same as a 3-char `LINKEDIN_LI_AT` typo — the operator can
# self-diagnose).
# ---------------------------------------------------------------------------


def _normalize_empty_linkedin_optional_secret(
    v: SecretStr | str | None,
) -> SecretStr | None:
    """Mode='before': None / '' / SecretStr('') -> None (REQ-LST-CFG-001).

    Mirrors the v1 `_normalize_empty_li_at` behavior byte-identically:
    - `None`          -> `None`
    - `''` (str)      -> `None`
    - `SecretStr('')` -> `None`
    - non-empty `str`      -> `SecretStr(str)` (Pydantic's native wrap)
    - non-empty `SecretStr` -> as-is (idempotent passthrough)
    """
    if v is None:
        return None
    if isinstance(v, SecretStr):
        return v if v.get_secret_value() else None
    if isinstance(v, str):
        return SecretStr(v) if v else None
    return v


def _reject_short_linkedin_optional_cookie(
    v: SecretStr | None,
    *,
    field_name: str,
) -> SecretStr | None:
    """Mode='after': HARD `len < MIN_LI_AT_LENGTH`, SOFT `None` allowed.

    REQ-LST-CFG-002 — same contract as the v1 `_reject_short_li_at`
    but with a parameterized `field_name` so the error message
    names the field. The `field_name` is the env-var name (e.g.
    `LINKEDIN_JSESSIONID`), not the Python attribute name (`linkedin_jsessionid`),
    so the operator sees the env-var they have to set in `.env`.
    """
    if v is None:
        return None
    if len(v.get_secret_value()) < MIN_LI_AT_LENGTH:
        raise ValueError(
            f"{field_name} must be at least {MIN_LI_AT_LENGTH} "
            f"characters (got {len(v.get_secret_value())}); check for "
            "typos or unset the variable to run the scraper anonymously."
        )
    return v


def _validate_str_dict_list(items: list[object], name: str) -> None:
    """Validate each element is a `dict[str, str]`. Raises `ValueError` on mismatch.

    Shared helper for validators that parse JSON lists of `{string_key: string_value}`.
    """
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{name} items must be dicts, got {type(item).__name__}")
        for key, val in item.items():
            if not isinstance(key, str) or not isinstance(val, str):
                raise ValueError(f"{name} dict keys and values must be strings: {key!r}: {val!r}")


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
        # Load from a local `.env` file (gitignored) on top of the
        # process environment. Shell env vars take precedence over
        # `.env` entries (pydantic-settings standard precedence). The
        # template lives at `.env.example` (committed, no secrets).
        env_file=".env",
        env_file_encoding="utf-8",
    )

    @classmethod
    def _settings_build_values(
        cls, sources: tuple[Any, ...], init_kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        """Override `BaseSettings._settings_build_values` to work around a
        pydantic-settings 2.14.1 `deep_update` quirk for `dict`-typed
        fields.

        Without this override, programmatic
        `Settings(aggregator_priority_map={"x": 99})` is silently merged
        with the `.env` value (which is itself a `dict`) into
        `{"linkedin": 0, "indeed": 1, "infojobs": 2, "x": 99}` — the
        user's dict is *added* to the `.env` default instead of
        *replacing* it. `deep_update` is the function that pydantic-
        settings uses to combine each `BaseSettingsSource`'s state
        (`init_settings`, `env_settings`, `dotenv_settings`, etc.); it
        deep-merges two `dict` values rather than replacing. This breaks
        `test_programmatic_construction_still_works` for ANY
        `dict[str, int]`-typed field that ALSO has a `.env` entry.

        The fix is a 3-line override: when the user explicitly passed
        `aggregator_priority_map` programmatically, force the merged
        `state` to use the user's dict verbatim. Non-dict fields are
        unaffected (`deep_update` already replaces scalars, lists, and
        frozensets correctly).

        Tracked as a follow-up from the `chat-filter-2stage` cycle
        (obs #285). The v1 test
        `test_aggregator_settings::test_programmatic_construction_still_works`
        was deselected at the v1 baseline and is now GREEN again.
        """
        state = super()._settings_build_values(sources, init_kwargs)
        if "aggregator_priority_map" in init_kwargs:
            state["aggregator_priority_map"] = init_kwargs["aggregator_priority_map"]
        return state

    throttle_seconds: float = 3.0
    user_agent: str = _DEFAULT_USER_AGENT
    headless: bool = True
    request_timeout_ms: int = 10_000

    # REQ-006 — CORS allowlist. Defaults to a sentinel `["*"]` that the
    # model_validator replaces with a safe localhost list in development
    # (auto-discovery). In production, a ValueError is raised if CORS is
    # not explicitly overridden via LINKEDIN_CORS_ALLOW_ORIGINS.
    cors_allow_origins: list[str] = Field(
        default_factory=lambda: ["*"],
        validation_alias=AliasChoices(
            "LINKEDIN_CORS_ALLOW_ORIGINS", "cors_allow_origins"
        ),
    )

    # Auto-detect deployment environment. Set ENVIRONMENT=production for prod.
    # In development mode, CORS is auto-set to localhost; in production,
    # CORS must be explicitly configured.
    deployment_environment: Literal["development", "production"] = Field(
        default="development",
        validation_alias=AliasChoices("ENVIRONMENT", "deployment_environment"),
    )

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
    # INFOJOBS_LAUNCH_CHANNEL: same pattern as LINKEDIN_LAUNCH_CHANNEL.
    # When set (e.g. "chrome"), Playwright uses the system Chrome
    # binary instead of the bundled Chromium, giving InfoJobs the
    # same TLS/HTTP-2 fingerprint as a real browser session.
    infojobs_launch_channel: str | None = Field(
        default=None,
        validation_alias=AliasChoices("INFOJOBS_LAUNCH_CHANNEL", "infojobs_launch_channel"),
    )
    # INFOJOBS_CHROMIUM_PATH: absolute path to the Chromium executable.
    # When set, this is passed as `executable_path` to
    # `chromium.launch()`, bypassing Playwright's channel/binary search.
    # This is needed when the system Chromium is not at the path
    # Playwright's `channel` option expects (e.g. snap Chromium on Linux).
    # Common snap path: /snap/chromium/3459/usr/lib/chromium-browser/chrome
    # (the revision may change after system updates).
    infojobs_chromium_path: str | None = Field(
        default=None,
        validation_alias=AliasChoices("INFOJOBS_CHROMIUM_PATH", "infojobs_chromium_path"),
    )

    # ------------------------------------------------------------------
    # Cache TTL (REQ-C-002)
    #
    # Default 60.0 seconds — the same value Cloudflare's free tier
    # uses for browser cache hits; long enough to absorb typical
    # burst traffic (a frontend dashboard refreshing every 5s
    # collapses 12 requests into 1), short enough that stale data
    # is rare.
    #
    # Set `CACHE_TTL_SECONDS=0` to disable the cache entirely (every
    # call becomes a miss, so the scraper is invoked every time).
    #
    # The model-level `env_prefix="LINKEDIN_"` does not apply to
    # this field because it has its own `validation_alias`. The
    # env var lookup reads `CACHE_TTL_SECONDS`; programmatic
    # construction (`Settings(cache_ttl_seconds=120.0)`) works via
    # the second choice in `AliasChoices`.
    # ------------------------------------------------------------------

    cache_ttl_seconds: float = Field(
        default=60.0,
        validation_alias=AliasChoices("CACHE_TTL_SECONDS", "cache_ttl_seconds"),
    )

    # ------------------------------------------------------------------
    # LinkedIn-pagination settings (REQ-L-008)
    #
    # Two new LinkedIn-specific fields opt out of the model-level
    # `env_prefix="LINKEDIN_"` by declaring their own
    # `validation_alias` (the same pattern used by `indeed_*` and
    # `infojobs_*` above). Each field reads from a `LINKEDIN_*` env
    # var that the prefix would emit anyway, so the env-var contract
    # for the existing LinkedIn fields is unchanged.
    #
    # `linkedin_max_pages` (default 10) caps the pagination loop in
    # `LinkedInPlaywrightScraper.search()` (REQ-L-007). Set to a
    # larger value to fetch deeper result streams; set to 1 to keep
    # the v0 single-page behavior.
    #
    # `linkedin_inter_page_delay_seconds` (default 1.0) paces
    # successive page navigations (REQ-L-009) to reduce the chance
    # of LinkedIn's anti-bot re-challenging the 2nd+ request. Set to
    # 0.0 to disable the call entirely (no event-loop yield).
    # ------------------------------------------------------------------

    linkedin_max_pages: int = Field(
        default=10,
        validation_alias=AliasChoices("LINKEDIN_MAX_PAGES", "linkedin_max_pages"),
    )
    linkedin_inter_page_delay_seconds: float = Field(
        default=1.0,
        validation_alias=AliasChoices(
            "LINKEDIN_INTER_PAGE_DELAY_SECONDS", "linkedin_inter_page_delay_seconds"
        ),
    )
    # `linkedin_li_at` (T-002 of `backend-linkedin-auth` —
    # REQ-LA-CFG-001..004). The operator's personal `li_at`
    # session cookie. Mirrors the v1 `llm_api_key: SecretStr |
    # None` pattern (`config.py:714` + the
    # `_normalize_empty_secret` validator below) and adds a
    # second `mode="after"` validator that rejects values
    # with `len < 8` (REQ-LA-CFG-002 — Q1 option C: catches
    # operator typos at boot; soft None is allowed to
    # preserve v1 zero-config boot). Real `li_at` cookies are
    # ~150 chars; the 8-char threshold is conservative.
    #
    # When UNSET: the scraper runs anonymously (v1 behavior
    # preserved). When SET + `len >= 8`: the scraper injects
    # the cookie into the Playwright `BrowserContext` before
    # the first navigation (T-004 wires the consumer).
    linkedin_li_at: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("LINKEDIN_LI_AT", "linkedin_li_at"),
    )
    # T-002 of `backend-linkedin-stealth` — REQ-LST-CFG-001..003.
    # The 3 new `linkedin_*` cookie fields (the 4 LinkedIn cookies
    # Cloudflare+LinkedIn 2026 treat as a "real session" signal —
    # see obs #364). Each is `SecretStr | None` with
    # `AliasChoices(<UPPER>, <lower>)` (mirrors the v1
    # `linkedin_li_at` shape exactly). The v1 field stays
    # unchanged; the 3 new fields are additive. The 2 v1 inline
    # validators on `linkedin_li_at` are REFACTORED to delegate
    # to 2 new shared helpers below; the v1 field's behavior is
    # unchanged (the 10 v1 `test_linkedin_config.py` tests stay
    # GREEN).
    linkedin_jsessionid: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("LINKEDIN_JSESSIONID", "linkedin_jsessionid"),
    )
    linkedin_bcookie: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("LINKEDIN_BCOOKIE", "linkedin_bcookie"),
    )
    linkedin_li_gc: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("LINKEDIN_LI_GC", "linkedin_li_gc"),
    )
    # T-005 of `backend-linkedin-xvfb` (F-4 fold-in per
    # obs #375 §9) — REQ-LBSc-001. The 5th LinkedIn cookie
    # (`bscookie`) the operator's per-session browser has in
    # addition to the 4 cycle-2 cookies. The new field
    # reuses the 2 shared validators
    # (`_normalize_empty_linkedin_optional_secret` +
    # `_reject_short_linkedin_optional_cookie` with
    # `field_name="LINKEDIN_BSCOOKIE"`) — no new helper code.
    # The `__slots__` and `cookies()` of
    # `MultiEnvLinkedInAuthCookiesAdapter` grow a 5th position
    # in T-005's adapter extension. The field defaults to
    # `None` (the F-4 additivity pin — the 4-cookie path is
    # byte-identical when `bscookie` is unset).
    linkedin_bscookie: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("LINKEDIN_BSCOOKIE", "linkedin_bscookie"),
    )

    @field_validator("linkedin_bscookie", mode="before")
    @classmethod
    def _normalize_empty_linkedin_bscookie(cls, v: SecretStr | str | None) -> SecretStr | None:
        return _normalize_empty_linkedin_optional_secret(v)

    @field_validator("linkedin_bscookie", mode="after")
    @classmethod
    def _reject_short_linkedin_bscookie(cls, v: SecretStr | None) -> SecretStr | None:
        return _reject_short_linkedin_optional_cookie(v, field_name="LINKEDIN_BSCOOKIE")

    # ------------------------------------------------------------------
    # LinkedIn-Xvfb settings (REQ-LXV-005, `backend-linkedin-xvfb` T-002).
    #
    # The 1 new field below configures the opt-in `LINKEDIN_XVFB_DISPLAY`
    # switch: when set to a non-`None` display string (e.g. `":99"`),
    # the LinkedIn scraper launches Chromium non-headless under a
    # virtual X display (Xvfb) so the browser has a real windowing
    # context + real TLS / HTTP-2 SETTINGS frame, evading
    # Cloudflare 2026's headless-Chromium fingerprint detection.
    #
    # The field opts out of the model-level `env_prefix="LINKEDIN_"`
    # by declaring its own `validation_alias` (same pattern used by
    # `indeed_*`, `infojobs_*`, `linkedin_*` pagination, cache, and
    # rate-limit fields). The env var is `LINKEDIN_XVFB_DISPLAY`; the
    # second alias in `AliasChoices` lets tests construct the field
    # programmatically (`Settings(linkedin_xvfb_display=":99")`).
    #
    # The default `None` preserves the v1 + v2 byte-identical
    # headless path (the `headless=True` launch is unchanged when
    # the field is unset). An empty-string env value (e.g.
    # `LINKEDIN_XVFB_DISPLAY=` in `.env`) normalizes to `None` via
    # the `_normalize_empty_linkedin_xvfb_display` mode="before"
    # validator (the kill-switch contract — operators can set the
    # var to an explicit empty string to disable Xvfb).
    #
    # The design's truth table (4 rows, design §2):
    #   xvfb=None  + headless=True  → launch(headless=True,  args=[])                (Row 1)
    #   xvfb=None  + headless=False → launch(headless=False, args=[])                (Row 2)
    #   xvfb=":99" + headless=True  → launch(headless=True,  args=[--ns,--ddsu])     (Row 3)
    #   xvfb=":99" + headless=False → launch(headless=False, args=[--ns,--ddsu])     (Row 4)
    # ------------------------------------------------------------------

    linkedin_xvfb_display: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LINKEDIN_XVFB_DISPLAY", "linkedin_xvfb_display"),
    )

    @field_validator("linkedin_xvfb_display", mode="before")
    @classmethod
    def _normalize_empty_linkedin_xvfb_display(cls, v: str | None) -> str | None:
        """Mode='before': `None` / `""` → `None` (the empty-string kill switch).

        Mirrors the v1 `_normalize_empty_li_at` empty-string
        normalization but for the non-`SecretStr` `xvfb_display`
        field. The field is `str | None` (NOT `SecretStr` because
        the display string is not a secret — the operator's
        `.env` can contain `LINKEDIN_XVFB_DISPLAY=:99` without
        any value-masking concern).
        """
        if v is None:
            return None
        if isinstance(v, str):
            return v if v else None
        return v

    # NEW: The opt-in `LINKEDIN_LAUNCH_CHANNEL` env var tells Playwright
    # which browser channel to launch (e.g. "chrome" for system Chrome).
    # When set, `chromium.launch(channel="chrome")` uses the system Chrome
    # binary instead of Playwright's bundled Chromium. This gives LinkedIn
    # the same TLS / HTTP-2 fingerprint as the user's real browser (where
    # the cookies were originally created), breaking the session-fingerprint
    # binding redirect loop.
    #
    # Default `None` → no `channel` kwarg (Playwright's bundled Chromium).
    linkedin_launch_channel: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LINKEDIN_LAUNCH_CHANNEL", "linkedin_launch_channel"),
    )

    @field_validator("linkedin_launch_channel", mode="before")
    @classmethod
    def _normalize_empty_linkedin_launch_channel(cls, v: str | None) -> str | None:
        """Mode='before': `None` / `""` → `None` (the empty-string kill switch).

        Mirrors the v1 `_normalize_empty_linkedin_xvfb_display`
        empty-string normalization. The field is `str | None` (NOT
        `SecretStr` because the channel name, e.g. `"chrome"`, is
        neither secret nor unique per session).
        """
        if v is None:
            return None
        if isinstance(v, str):
            return v if v else None
        return v

    # ------------------------------------------------------------------
    # Shared validators (REFACTORED from v1 inline validators — T-002 of
    # `backend-linkedin-stealth`, REQ-LST-CFG-001..003).
    #
    # The 4 `linkedin_*` cookie fields share the same 2 validation
    # concerns:
    #   1. Normalize empty inputs (`None` / `""` / `SecretStr("")`)
    #      → `None` (the kill-switch contract, REQ-LST-CFG-001).
    #   2. Reject short values (when present) with a HARD
    #      `ValueError` (REQ-LST-CFG-002 — the operator typo
    #      guard).
    #
    # The 2 helpers are module-level functions (not methods)
    # so they can be reused across the 4 fields. The 2nd helper
    # accepts a `field_name: str` kwarg (the env-var name) so
    # the error message can name the field; a small factory
    # (`_make_reject_short`) wraps it as a `field_validator`
    # for each field.
    #
    # The v1 inline validators (`_normalize_empty_li_at` and
    # `_reject_short_li_at`) are REFACTORED to delegate to the
    # 2 shared helpers — the v1 field's behavior is unchanged
    # (the 10 v1 `test_linkedin_config.py` tests stay GREEN).
    # ------------------------------------------------------------------

    @field_validator("linkedin_li_at", mode="before")
    @classmethod
    def _normalize_empty_li_at(cls, v: SecretStr | str | None) -> SecretStr | None:
        # REFACTORED in T-002 of `backend-linkedin-stealth` to
        # delegate to the shared `_normalize_empty_linkedin_optional_secret`.
        # The v1 behavior is unchanged.
        return _normalize_empty_linkedin_optional_secret(v)

    @field_validator("linkedin_li_at", mode="after")
    @classmethod
    def _reject_short_li_at(cls, v: SecretStr | None) -> SecretStr | None:
        # REFACTORED in T-002 of `backend-linkedin-stealth` to
        # delegate to the shared `_reject_short_linkedin_optional_cookie`
        # with `field_name="LINKEDIN_LI_AT"`. The v1 behavior
        # is unchanged (the error message text is byte-identical
        # to the v1 inline error).
        return _reject_short_linkedin_optional_cookie(v, field_name="LINKEDIN_LI_AT")

    @field_validator("linkedin_jsessionid", mode="before")
    @classmethod
    def _normalize_empty_linkedin_jsessionid(cls, v: SecretStr | str | None) -> SecretStr | None:
        return _normalize_empty_linkedin_optional_secret(v)

    @field_validator("linkedin_jsessionid", mode="after")
    @classmethod
    def _reject_short_linkedin_jsessionid(cls, v: SecretStr | None) -> SecretStr | None:
        return _reject_short_linkedin_optional_cookie(v, field_name="LINKEDIN_JSESSIONID")

    @field_validator("linkedin_bcookie", mode="before")
    @classmethod
    def _normalize_empty_linkedin_bcookie(cls, v: SecretStr | str | None) -> SecretStr | None:
        return _normalize_empty_linkedin_optional_secret(v)

    @field_validator("linkedin_bcookie", mode="after")
    @classmethod
    def _reject_short_linkedin_bcookie(cls, v: SecretStr | None) -> SecretStr | None:
        return _reject_short_linkedin_optional_cookie(v, field_name="LINKEDIN_BCOOKIE")

    @field_validator("linkedin_li_gc", mode="before")
    @classmethod
    def _normalize_empty_linkedin_li_gc(cls, v: SecretStr | str | None) -> SecretStr | None:
        return _normalize_empty_linkedin_optional_secret(v)

    @field_validator("linkedin_li_gc", mode="after")
    @classmethod
    def _reject_short_linkedin_li_gc(cls, v: SecretStr | None) -> SecretStr | None:
        return _reject_short_linkedin_optional_cookie(v, field_name="LINKEDIN_LI_GC")

    # ------------------------------------------------------------------
    # Persistent-cache settings (REQ-PC-004, persistent-cache change)
    #
    # The 4 fields below select the cache backend and configure the
    # Redis client when `cache_backend=\"redis\"`. The model-level
    # `env_prefix=\"LINKEDIN_\"` does not apply to these fields
    # because each declares its own `validation_alias` (same pattern
    # used by the `indeed_*`, `infojobs_*`, and `linkedin_*`
    # pagination fields above).
    #
    # - `cache_backend`: `Literal[\"memory\", \"redis\"]`. The
    #   in-memory backend is the default — it preserves the
    #   pre-persistent-cache behavior (single-process, 60s TTL,
    #   in-memory dict) and keeps the 553 pre-existing tests green.
    #   `redis` shares the cache across workers and hosts via a
    #   `redis.asyncio` client (REQ-PC-001).
    # - `cache_redis_url`: the `redis://` URL passed to
    #   `redis.asyncio.from_url`. Includes the db suffix (e.g.
    #   `redis://localhost:6379/0`).
    # - `cache_redis_namespace`: a single-segment label prepended to
    #   every Redis key. MUST be non-empty and MUST NOT contain
    #   `:` (enforced by `_validate_cache_redis_namespace` below)
    #   because the runtime key is `f\"{ns}:{source}:{hash}\"` —
    #   a `:` in the namespace would let two deployments collide.
    # - `cache_redis_db`: the integer db index passed to
    #   `redis.asyncio.from_url(..., db=...)`. Default `0`.
    # ------------------------------------------------------------------

    cache_backend: Literal["memory", "redis"] = Field(
        default="memory",
        validation_alias=AliasChoices("CACHE_BACKEND", "cache_backend"),
    )
    cache_redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("CACHE_REDIS_URL", "cache_redis_url"),
    )
    cache_redis_namespace: str = Field(
        default="jobs-finder",
        validation_alias=AliasChoices("CACHE_REDIS_NAMESPACE", "cache_redis_namespace"),
    )
    cache_redis_db: int = Field(
        default=0,
        validation_alias=AliasChoices("CACHE_REDIS_DB", "cache_redis_db"),
    )

    @field_validator("cache_redis_namespace")
    @classmethod
    def _validate_cache_redis_namespace(cls, v: str) -> str:
        """Reject empty and `:`-containing values for `cache_redis_namespace`.

        The runtime key is `f"{ns}:{source}:{hash}"` (3 colon-separated
        segments). A `:` in the namespace would introduce a 4th
        segment and risk collision with another deployment sharing
        the same Redis instance. An empty namespace would let two
        deployments' keys share a single root segment and is the
        most dangerous form of the same bug. Both are rejected at
        startup so misconfiguration surfaces immediately, not on
        the first cache write.
        """
        if not v:
            raise ValueError("CACHE_REDIS_NAMESPACE must be non-empty")
        if ":" in v:
            raise ValueError(f"CACHE_REDIS_NAMESPACE must not contain ':' (got {v!r})")
        return v

    # ------------------------------------------------------------------
    # Rate-limit settings (REQ-RL-008, rate-limiting change +
    # `rate-limit-followups` defaults alignment)
    #
    # The 10 fields below configure the `RateLimitMiddleware` (T-002)
    # and the `build_rate_limiter` factory (T-003). Each field
    # declares its own `validation_alias` (same pattern used by the
    # `indeed_*`, `infojobs_*`, `linkedin_*` pagination, and cache
    # fields above).
    #
    # - `rate_limit_enabled`: kill-switch — `False` makes the
    #   middleware a no-op (no headers, no rejection, no log noise).
    # - `rate_limit_backend`: `Literal["memory", "redis"]` mirrors
    #   `cache_backend`. `memory` is the default; `redis` shares
    #   the limiter across workers/hosts.
    # - `rate_limit_requests`: capacity (max burst). **Default 20**
    #   (`rate-limit-followups`, was 60). Aligned to the per-source
    #   `AsyncThrottle.min_interval_seconds=3.0` pace — 1 req/3sec
    #   = 20 req/min. The HTTP rate limit is a coarse top layer
    #   that matches the per-source throttles' actual pacing.
    # - `rate_limit_window_seconds`: refill period. Refill rate is
    #   `capacity / window_seconds` tokens/sec. With the new
    #   default 20/60, refill rate is 1/3 tokens/sec (matches the
    #   per-source throttles exactly).
    # - `rate_limit_redis_url` / `rate_limit_redis_db`: fall back
    #   to `cache_redis_url` / `cache_redis_db` via the
    #   `_fall_back_redis` model_validator below. Empty / `-1` is
    #   the sentinel "use the cache value".
    # - `rate_limit_redis_namespace`: separate from the cache
    #   namespace so the 2 features don't collide. Default
    #   `"rate-limiter"`.
    # - `rate_limit_exempt_paths`: JSON list per spec OQ-B
    #   (Pydantic-friendly). Default `["/health"]`.
    # - `rate_limit_aggregator_path_cost`: **default 1** (`rate-
    #   limit-followups`, was 3). Each per-source `AsyncThrottle`
    #   already paces the 3 parallel scraper calls in
    #   `SearchAllSourcesUseCase`; charging 3× at the HTTP rate
    #   limiter would double-count. Per-call cost is 1.
    # - `rate_limit_per_source_path_cost`: per-source cost
    #   (default 1, unchanged).
    # ------------------------------------------------------------------

    rate_limit_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("RATE_LIMIT_ENABLED", "rate_limit_enabled"),
    )
    rate_limit_backend: Literal["memory", "redis"] = Field(
        default="memory",
        validation_alias=AliasChoices("RATE_LIMIT_BACKEND", "rate_limit_backend"),
    )
    rate_limit_requests: int = Field(
        default=20,
        validation_alias=AliasChoices("RATE_LIMIT_REQUESTS", "rate_limit_requests"),
        ge=1,
    )
    rate_limit_window_seconds: float = Field(
        default=60.0,
        validation_alias=AliasChoices("RATE_LIMIT_WINDOW_SECONDS", "rate_limit_window_seconds"),
        gt=0.0,
    )
    rate_limit_redis_url: str = Field(
        default="",  # sentinel: "use cache_redis_url" — see _fall_back_redis
        validation_alias=AliasChoices("RATE_LIMIT_REDIS_URL", "rate_limit_redis_url"),
    )
    rate_limit_redis_namespace: str = Field(
        default="rate-limiter",
        validation_alias=AliasChoices("RATE_LIMIT_REDIS_NAMESPACE", "rate_limit_redis_namespace"),
    )
    rate_limit_redis_db: int = Field(
        default=-1,  # sentinel: "use cache_redis_db" — see _fall_back_redis
        validation_alias=AliasChoices("RATE_LIMIT_REDIS_DB", "rate_limit_redis_db"),
    )
    rate_limit_exempt_paths: frozenset[str] = Field(
        default_factory=lambda: frozenset({"/health"}),
        validation_alias=AliasChoices("RATE_LIMIT_EXEMPT_PATHS", "rate_limit_exempt_paths"),
    )
    rate_limit_aggregator_path_cost: int = Field(
        default=1,
        validation_alias=AliasChoices(
            "RATE_LIMIT_AGGREGATOR_PATH_COST", "rate_limit_aggregator_path_cost"
        ),
        ge=1,
    )
    rate_limit_per_source_path_cost: int = Field(
        default=1,
        validation_alias=AliasChoices(
            "RATE_LIMIT_PER_SOURCE_PATH_COST", "rate_limit_per_source_path_cost"
        ),
        ge=1,
    )
    # REQ-RL-008 (scenarios 8, 9, 10) + REQ-RL-011: `RATE_LIMIT_TRUSTED_PROXIES`
    # is a JSON list of CIDR strings parsed by the validator below.
    # Default is `frozenset()` (the security default — no proxy
    # trust, `X-Forwarded-For` is IGNORED). Operators set
    # `RATE_LIMIT_TRUSTED_PROXIES='["10.0.0.0/8","::1/128"]'`
    # to enable the rightmost-untrusted algorithm.
    rate_limit_trusted_proxies: frozenset[IPv4Network | IPv6Network] = Field(
        default_factory=frozenset,
        validation_alias=AliasChoices("RATE_LIMIT_TRUSTED_PROXIES", "rate_limit_trusted_proxies"),
    )

    # ------------------------------------------------------------------
    # API Key authentication (api-key-auth change)
    #
    # - `api_keys`: comma-separated list of valid API keys. If empty,
    #   API key authentication is DISABLED (all requests allowed).
    #   If non-empty, all requests must have a valid X-API-Key header.
    # - `api_key_rate_limit`: requests per minute per API key (when auth is enabled).
    #   Uses the same rate limiter instance but with a "key:<api_key>" prefix.
    # ------------------------------------------------------------------

    api_keys: frozenset[str] = Field(
        default_factory=frozenset,
        validation_alias=AliasChoices("API_KEYS", "api_keys"),
    )

    api_key_rate_limit: int = Field(
        default=60,
        validation_alias=AliasChoices("API_KEY_RATE_LIMIT", "api_key_rate_limit"),
        ge=1,
    )

    @field_validator("api_keys", mode="before")
    @classmethod
    def _parse_api_keys(cls, v: object) -> frozenset[str]:
        """Parse `API_KEYS` as a JSON list of strings (same pattern as
        `rate_limit_exempt_paths` and `aggregator_priority_map`).

        Also accepts a pre-parsed list / tuple / set for programmatic
        construction. An empty / None / "[]" value yields an empty
        frozenset (auth DISABLED).
        """
        if isinstance(v, (frozenset, set, list, tuple)):
            return frozenset(str(k) for k in v if k)
        if isinstance(v, str) and v.strip():
            if v.strip().startswith("["):
                # JSON list format: '["key1","key2"]'
                parsed = json.loads(v)
                if not isinstance(parsed, list):
                    raise ValueError("API_KEYS must be a JSON list of strings")
                return frozenset(str(k) for k in parsed if k)
            else:
                # Fallback: comma-separated for convenience in dev
                return frozenset(k.strip() for k in v.split(",") if k.strip())
        return frozenset()

    @field_validator("rate_limit_exempt_paths", mode="before")
    @classmethod
    def _parse_exempt_paths(cls, v: object) -> frozenset[str]:
        """Parse `RATE_LIMIT_EXEMPT_PATHS` as a JSON list of strings.

        Spec OQ-B: Pydantic-friendly JSON list. A
        `RATE_LIMIT_EXEMPT_PATHS='["/health", "/internal/ping"]'`
        env var parses to `frozenset({"/health", "/internal/ping"})`.
        Also accepts a pre-parsed list / tuple / set for programmatic
        construction (`Settings(rate_limit_exempt_paths=[...])`).
        An empty / None value yields the default `frozenset({"/health"})`.
        """
        if isinstance(v, (frozenset, set, list, tuple)):
            return frozenset(str(p) for p in v)
        if isinstance(v, str) and v:
            parsed = json.loads(v)
            if not isinstance(parsed, list):
                raise ValueError(
                    "RATE_LIMIT_EXEMPT_PATHS must be a JSON list of strings, "
                    f"got {type(parsed).__name__}"
                )
            return frozenset(str(p) for p in parsed)
        if v is None or v == "":
            return frozenset({"/health"})
        raise ValueError(f"unparseable RATE_LIMIT_EXEMPT_PATHS: {v!r}")

    @field_validator("rate_limit_trusted_proxies", mode="before")
    @classmethod
    def _parse_trusted_proxies(cls, v: object) -> frozenset[IPv4Network | IPv6Network]:
        """Parse `RATE_LIMIT_TRUSTED_PROXIES` as a JSON list of CIDR strings.

        REQ-RL-008 scenarios 8/9/10: a
        `RATE_LIMIT_TRUSTED_PROXIES='["10.0.0.0/8","::1/128"]'`
        env var parses to
        `frozenset({IPv4Network("10.0.0.0/8"), IPv6Network("::1/128")})`.
        Each entry is parsed with `ipaddress.ip_network(s, strict=False)`
        which auto-detects single IPs (`"10.0.0.1"` -> `IPv4Network("10.0.0.1/32")`).
        Invalid CIDR raises `ValueError`; malformed JSON raises
        `json.JSONDecodeError`; Pydantic surfaces both as
        `ValidationError` at app construction time so misconfiguration
        fails fast (not on the first 429).

        Also accepts a pre-parsed `list` / `tuple` / `set` /
        `frozenset` (Pydantic-Settings auto-parses the JSON env var
        into a list BEFORE the `mode="before"` validator runs, so
        programmatic `Settings(rate_limit_trusted_proxies=[...])`
        construction lands here as a list).
        """
        if isinstance(v, frozenset):
            return v
        if isinstance(v, (set, list, tuple)):
            return frozenset(ipaddress.ip_network(str(s), strict=False) for s in v)
        if isinstance(v, str):
            if not v.strip():
                return frozenset()
            parsed = json.loads(v)
            if not isinstance(parsed, list):
                raise ValueError(
                    "RATE_LIMIT_TRUSTED_PROXIES must be a JSON list of CIDR strings, "
                    f"got {type(parsed).__name__}"
                )
            return frozenset(ipaddress.ip_network(str(s), strict=False) for s in parsed)
        raise ValueError(f"unparseable RATE_LIMIT_TRUSTED_PROXIES: {v!r}")

    # ------------------------------------------------------------------
    # Aggregator ranking settings (REQ-AR-008, jobs-aggregator-ranking)
    #
    # The 2 fields below configure the `rank_jobs` step that
    # `SearchAllSourcesUseCase.search()` runs AFTER the dedup step
    # (see `application/ranking.py` + `application/aggregator.py`).
    # Each field declares its own `validation_alias` (same pattern
    # used by the rate-limit, cache, and per-source fields above).
    #
    # - `aggregator_ranking_strategy`: `Literal["posted_at", "priority",
    #   "none"]` — the default is `"posted_at"` (freshness DESC, the
    #   most useful default for a job search). Pydantic's `Literal`
    #   validator rejects unknown values at startup with a
    #   `ValidationError`. `none` is the explicit escape hatch that
    #   preserves the pre-change source-priority + scrape-order
    #   behavior for clients depending on it.
    # - `aggregator_priority_map`: `dict[str, int]` — the source-
    #   priority map used as the primary sort key for
    #   `strategy="priority"` AND as the tie-breaker for
    #   `strategy="posted_at"`. Parsed from a JSON env var by the
    #   `_parse_aggregator_priority_map` validator below. The
    #   default is LinkedIn-first (matches the existing
    #   `SOURCE_PRIORITY` tuple in `application/aggregator.py`).
    #   Sources not in the map are treated as priority `999` (last)
    #   by the `rank_jobs` consumer — the validator does NOT
    #   reject unknown source names (forward compatibility for
    #   future sources).
    # ------------------------------------------------------------------

    aggregator_ranking_strategy: Literal["posted_at", "priority", "none"] = Field(
        default="posted_at",
        validation_alias=AliasChoices("AGGREGATOR_RANKING_STRATEGY", "aggregator_ranking_strategy"),
    )

    # ------------------------------------------------------------------
    # Opt-in keyword-score ranking (REQ-SCORE-001 scenarios 5-6,
    # `backend-scraper-query-tuning` T-008)
    #
    # The 1 field below configures the opt-in `keyword_score`
    # relevance ranking. When `False` (the default), the
    # aggregator's sort path is the v1 `posted_at` desc
    # (REQ-SCORE-001 scenario 5). When `True`, the aggregator
    # uses `keyword_score desc, posted_at desc` (REQ-SCORE-001
    # scenario 6). The opt-in pattern is intentional: the
    # `keyword_score` heuristic is a v1 best-effort signal;
    # operators enable it on a per-deployment basis without
    # code changes.
    #
    # The env var is `ENABLE_KEYWORD_SCORING` (model-level
    # `env_prefix="LINKEDIN_"` does not apply because the
    # field declares its own `validation_alias`).
    # `bool` type accepts the canonical truthy strings
    # (`"true"`, `"1"`, `"yes"`, `"on"`, case-insensitive)
    # via Pydantic's standard bool coercion.
    # ------------------------------------------------------------------

    enable_keyword_scoring: bool = Field(
        default=False,
        validation_alias=AliasChoices("ENABLE_KEYWORD_SCORING", "enable_keyword_scoring"),
    )
    aggregator_priority_map: dict[str, int] = Field(
        default_factory=lambda: {"linkedin": 0, "indeed": 1, "infojobs": 2},
        validation_alias=AliasChoices("AGGREGATOR_PRIORITY_MAP", "aggregator_priority_map"),
    )

    @field_validator("aggregator_priority_map", mode="before")
    @classmethod
    def _parse_aggregator_priority_map(cls, v: object) -> dict[str, int]:
        """Parse `AGGREGATOR_PRIORITY_MAP` as a JSON object of `{source: int}`.

        REQ-AR-004 (jobs-aggregator-ranking): a
        `AGGREGATOR_PRIORITY_MAP='{"linkedin":0,"indeed":1,"infojobs":2}'`
        env var parses to the corresponding `dict[str, int]`. Also
        accepts a pre-parsed `dict` (programmatic `Settings(...)`
        construction) and an empty string (yields the default).
        Invalid JSON raises `ValueError`; non-dict JSON raises
        `ValueError`; non-`int` values raise `ValueError` — all
        surface as `pydantic.ValidationError` at app construction
        time so misconfiguration fails fast at startup.

        Mirrors the `_parse_exempt_paths` pattern at lines 418-442.
        """
        if isinstance(v, dict):
            # Programmatic `Settings(aggregator_priority_map={...})` — already
            # parsed. Validate the values are ints (Pydantic's outer
            # `dict[str, int]` annotation handles the rest on
            # assignment).
            for k, val in v.items():
                if not isinstance(k, str) or not isinstance(val, int) or isinstance(val, bool):
                    raise ValueError(
                        f"AGGREGATOR_PRIORITY_MAP keys must be str, values must be int: "
                        f"{k!r}: {val!r}"
                    )
            return v
        if isinstance(v, str):
            if not v.strip():
                # Empty env var → default. Returning the dict
                # directly here would short-circuit the default
                # factory; we want the default to take over, so we
                # raise a sentinel that Pydantic treats as
                # "use the default". `pydantic_core.PydanticUndefined`
                # is the right sentinel, but importing it adds a
                # dependency. Simpler: return the same default shape
                # the factory produces.
                return {"linkedin": 0, "indeed": 1, "infojobs": 2}
            try:
                parsed = json.loads(v)
            except json.JSONDecodeError as e:
                raise ValueError(f"AGGREGATOR_PRIORITY_MAP must be JSON: {e}") from e
            if not isinstance(parsed, dict):
                raise ValueError(
                    f"AGGREGATOR_PRIORITY_MAP must be a JSON object, got {type(parsed).__name__}"
                )
            for k, val in parsed.items():
                if not isinstance(k, str) or not isinstance(val, int) or isinstance(val, bool):
                    raise ValueError(
                        f"AGGREGATOR_PRIORITY_MAP keys must be str, values must be int: "
                        f"{k!r}: {val!r}"
                    )
            return parsed
        raise ValueError(f"unparseable AGGREGATOR_PRIORITY_MAP: {v!r}")

    @model_validator(mode="after")
    def _fall_back_redis(self) -> Settings:
        """Copy `cache_redis_url` / `cache_redis_db` into the rate-limit fields when unset.

        The sentinel values (empty string for `rate_limit_redis_url`,
        `-1` for `rate_limit_redis_db`) are the "unset" markers. An
        explicit value (any string / int) bypasses the fallback so a
        deployment can split the cache and the rate-limiter across
        two Redis instances.

        `AliasChoices` does not support computed fallbacks, so the
        copy is implemented here as a `model_validator(mode="after")`.
        Settings is NOT frozen, so a direct attribute assignment works
        (no `object.__setattr__` is needed).
        """
        if not self.rate_limit_redis_url:
            self.rate_limit_redis_url = self.cache_redis_url
        if self.rate_limit_redis_db == -1:
            self.rate_limit_redis_db = self.cache_redis_db
        return self

    # ------------------------------------------------------------------
    # LLM (chat filter) settings (REQ-CHAT-001, REQ-CHAT-002,
    # `ai-chat-filter` change T-006)
    #
    # The 9 fields below configure the `MiniMaxLLMClient` (T-011) and
    # the chat filter route (T-014, T-016 — both OUT of this PR).
    # Each field declares its own `validation_alias` (the same
    # pattern used by the `indeed_*`, `infojobs_*`, `linkedin_*`
    # pagination, cache, rate-limit, and aggregator fields above).
    # The model-level `env_prefix="LINKEDIN_"` does not apply to
    # these fields because each declares its own alias.
    #
    # - `llm_api_key`: `SecretStr | None` — the kill switch. When
    #   `None`, the chat route is NOT registered. Pydantic's
    #   `SecretStr` masks the value in `repr()` / `str()` to prevent
    #   accidental leakage into logs; the actual key is only
    #   accessible via `.get_secret_value()`. This is a security
    #   contract — a regression to plain `str` would silently leak
    #   the key into tracebacks + log lines.
    # - `llm_base_url`: the OpenAI-compatible chat-completions base.
    #   Default `"https://api.minimax.io"` (the documented public
    #   endpoint per `sdd/ai-chat-filter/explore` §4).
    # - `llm_model`: the model identifier. Default `"MiniMax-M3"`
    #   (preflight D2 — the ONLY model that actually honors
    #   `thinking: {"type": "disabled"}`; M2.x cannot disable
    #   thinking).
    # - `llm_temperature`: 0.0 by default — the chat filter is a
    #   deterministic selection, not a creative writing task.
    # - `llm_max_tokens`: 1024 — large enough for the JSON
    #   `{"matching_ids": [...], "explanation": "..."}` response
    #   plus a safety margin.
    # - `llm_request_timeout_seconds`: 15.0 — the per-request
    #   timeout for the httpx client.
    # - `llm_max_message_chars`: 1000 — the chat-message length cap
    #   enforced by the route (Q2 — 400 explicit reject when the
    #   user message exceeds this).
    # - `llm_filter_enabled`: `False` by default (Q3) — the chat
    #   route is OFF by default. Operators flip the switch via
    #   `LLM_FILTER_ENABLED=true` + `LLM_API_KEY=<key>` in prod.
    #   The 2-stage rollout (code merged disabled, ops enables
    #   later) is the zero-risk path.
    # - `llm_filter_rate_limit_rpm`: 20 — per-user chat bucket
    #   (Q3). Matches the existing `RATE_LIMIT_REQUESTS` default
    #   so the chat bucket has the same per-minute capacity as the
    #   main bucket.
    # ------------------------------------------------------------------

    llm_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_API_KEY", "llm_api_key"),
    )

    # T-001 of `chat-filter-2stage` — REQ-SET-LLM-001 baseline fix.
    # Pydantic-settings wraps an empty env-var value (e.g. `LLM_API_KEY=`
    # in `.env`) as `SecretStr('')`, which breaks the kill-switch
    # contract (`app_factory` treats `llm_api_key is None` as "route
    # NOT registered"). The validator normalizes the 3 empty inputs
    # to `None` so the kill switch triggers correctly:
    #   `None`          → `None`
    #   `""`            → `None`
    #   `SecretStr("")` → `None`
    # Non-empty `str` is wrapped in `SecretStr` (Pydantic's native
    # behavior — the validator runs BEFORE the field's `SecretStr`
    # coercion, so wrapping here keeps the contract uniform).
    # Non-empty `SecretStr` is returned as-is (idempotent passthrough).
    # The validator is INDEPENDENT of the chat-filter-2stage feature
    # and is kept even if `chat-filter-2stage` is rolled back.
    @field_validator("llm_api_key", mode="before")
    @classmethod
    def _normalize_empty_secret(cls, v: SecretStr | str | None) -> SecretStr | None:
        if v is None:
            return None
        if isinstance(v, SecretStr):
            return v if v.get_secret_value() else None
        if isinstance(v, str):
            return SecretStr(v) if v else None
        return v

    llm_base_url: str = Field(
        default="https://api.minimax.io",
        validation_alias=AliasChoices("LLM_BASE_URL", "llm_base_url"),
    )
    llm_model: str = Field(
        default="MiniMax-M3",
        validation_alias=AliasChoices("LLM_MODEL", "llm_model"),
    )
    llm_temperature: float = Field(
        default=0.0,
        validation_alias=AliasChoices("LLM_TEMPERATURE", "llm_temperature"),
    )
    llm_max_tokens: int = Field(
        default=1024,
        validation_alias=AliasChoices("LLM_MAX_TOKENS", "llm_max_tokens"),
    )
    llm_request_timeout_seconds: float = Field(
        default=15.0,
        validation_alias=AliasChoices("LLM_REQUEST_TIMEOUT_SECONDS", "llm_request_timeout_seconds"),
    )
    llm_max_message_chars: int = Field(
        default=1000,
        validation_alias=AliasChoices("LLM_MAX_MESSAGE_CHARS", "llm_max_message_chars"),
    )
    llm_filter_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("LLM_FILTER_ENABLED", "llm_filter_enabled"),
    )
    llm_filter_rate_limit_rpm: int = Field(
        default=20,
        validation_alias=AliasChoices("LLM_FILTER_RATE_LIMIT_RPM", "llm_filter_rate_limit_rpm"),
        ge=1,
    )
    # Whether the LLM provider supports the `thinking: {"type": "disabled"}`
    # parameter. MiniMax M3 does (default True). Groq does NOT (set to False).
    llm_supports_thinking: bool = Field(
        default=True,
        validation_alias=AliasChoices("LLM_SUPPORTS_THINKING", "llm_supports_thinking"),
    )

    # ------------------------------------------------------------------
    # Chat filter — 2-stage LLM settings (REQ-CHAT-INT-006,
    # `chat-filter-2stage` change T-007)
    #
    # The 6 fields below configure the 2-stage LLM flow: stage 1
    # extracts a structured `Intent` from the user's free-form
    # message; stage 2 calls the aggregator with the extracted
    # `q`/`location` (and a higher `limit`); stage 3 is the
    # existing v1 LLM filter. Each field declares its own
    # `validation_alias` (same pattern as every other field group
    # above). The model-level `env_prefix="LINKEDIN_"` does not
    # apply to these fields because each declares its own alias.
    #
    # - `intent_extraction_enabled: bool` (default True) — the
    #   master switch for the 2-stage flow. Set to `false` to
    #   revert to v1 behavior (the kill switch). REQ-CHAT-INT-005.
    # - `intent_extraction_confidence_threshold: float` (default
    #   0.7, `ge=0.0, le=1.0`) — below this confidence, the use
    #   case falls back to the v1 path. REQ-CHAT-INT-004.
    # - `intent_max_results: int` (default 100, `ge=1, le=500`) —
    #   the per-source cap for the stage-2 aggregator scrape
    #   (higher than the v1 `limit=20` to give the LLM more
    #   recall). REQ-CHAT-INT-001.
    # - `llm_stage1_max_tokens: int` (default 256, `ge=64, le=1024`)
    #   — the stage-1 LLM response size cap. The 6-field
    #   extraction is small; 256 tokens is generous and keeps
    #   cost low. REQ-CHAT-INT-001.
    # - `llm_stage1_temperature: float` (default 0.0,
    #   `ge=0.0, le=2.0`) — the stage-1 LLM temperature. 0.0 =
    #   deterministic. The 6-field extraction is well-defined.
    # - `intent_extraction_retry: int` (default 1, `ge=0, le=3`) —
    #   the number of retries on stage-1 parse failure
    #   (retry-once with corrective system prompt, per the
    #   design's deliberate trade). REQ-LLM-SEC-002.
    # ------------------------------------------------------------------

    intent_extraction_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("INTENT_EXTRACTION_ENABLED", "intent_extraction_enabled"),
    )
    intent_extraction_confidence_threshold: float = Field(
        default=0.7,
        validation_alias=AliasChoices(
            "INTENT_EXTRACTION_CONFIDENCE_THRESHOLD",
            "intent_extraction_confidence_threshold",
        ),
        ge=0.0,
        le=1.0,
    )
    intent_max_results: int = Field(
        default=100,
        validation_alias=AliasChoices("INTENT_MAX_RESULTS", "intent_max_results"),
        ge=1,
        le=500,
    )
    llm_stage1_max_tokens: int = Field(
        default=256,
        validation_alias=AliasChoices("LLM_STAGE1_MAX_TOKENS", "llm_stage1_max_tokens"),
        ge=64,
        le=1024,
    )
    llm_stage1_temperature: float = Field(
        default=0.0,
        validation_alias=AliasChoices("LLM_STAGE1_TEMPERATURE", "llm_stage1_temperature"),
        ge=0.0,
        le=2.0,
    )
    intent_extraction_retry: int = Field(
        default=1,
        validation_alias=AliasChoices("INTENT_EXTRACTION_RETRY", "intent_extraction_retry"),
        ge=0,
        le=3,
    )

    # ------------------------------------------------------------------
    # Chat streaming — keepalive settings (REQ-SSE-002,
    # `chat-streaming` change T-002)
    #
    # The 1 field below configures the SSE keepalive interval for
    # the new `POST /jobs/chat/stream` endpoint. Each field declares
    # its own `validation_alias` (same pattern as every other
    # field group above). The model-level `env_prefix="LINKEDIN_"`
    # does not apply to this field because it declares its own
    # alias.
    #
    # - `sse_keepalive_seconds`: `float` (default 15.0, `ge=0.0`,
    #   `le=60.0`) — the interval between `: keepalive\\n\\n`
    #   comments during quiet periods (primarily the stage-2
    #   aggregator scrape wait). The 60.0 upper bound matches
    #   Chrome's idle timeout (a value above 60.0 risks the
    #   browser closing the connection before the next event).
    #   The 0.0 lower bound (NOT `gt=0.0`) is the design
    #   decision flagged in the proposal: `SSE_KEEPALIVE_SECONDS=0`
    #   is the documented kill switch per REQ-SSE-002 3rd
    #   scenario (operators can disable keepalive entirely).
    # ------------------------------------------------------------------

    sse_keepalive_seconds: float = Field(
        default=15.0,
        validation_alias=AliasChoices("SSE_KEEPALIVE_SECONDS", "sse_keepalive_seconds"),
        ge=0.0,
        le=60.0,
    )

    # ------------------------------------------------------------------
    # Scheduler & Persistence settings (background-scheduler-persistence change)
    #
    # 5 new fields that configure the background job scheduler and the
    # SQLite job repository. Each field declares its own
    # `validation_alias` (same pattern as every other field group
    # above). The model-level `env_prefix="LINKEDIN_"` does not apply
    # to these fields because each declares its own alias.
    #
    # - `db_path`: path to the SQLite database file. Default `"jobs.db"`.
    # - `scheduler_enabled`: master switch. `False` (default) means zero
    #   behavioral change — no task, no DB init.
    # - `scheduler_min_interval_seconds`: minimum sleep between cycles.
    #   Default 1500.0 (25 min).
    # - `scheduler_max_interval_seconds`: maximum sleep between cycles.
    #   Default 2100.0 (35 min).
    # - `scheduler_queries`: JSON list of `{"keywords": ..., "location": ...}`
    #   dicts to run each cycle. Parsed via a `mode="before"` validator
    #   (same pattern as `_parse_exempt_paths` and `_parse_aggregator_priority_map`).
    # ------------------------------------------------------------------

    db_path: str = Field(
        default="jobs.db",
        validation_alias=AliasChoices("DB_PATH", "db_path"),
    )
    scheduler_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("SCHEDULER_ENABLED", "scheduler_enabled"),
    )
    scheduler_min_interval_seconds: float = Field(
        default=1500.0,
        validation_alias=AliasChoices(
            "SCHEDULER_MIN_INTERVAL_SECONDS", "scheduler_min_interval_seconds"
        ),
        gt=0.0,
    )
    scheduler_max_interval_seconds: float = Field(
        default=2100.0,
        validation_alias=AliasChoices(
            "SCHEDULER_MAX_INTERVAL_SECONDS", "scheduler_max_interval_seconds"
        ),
        gt=0.0,
    )
    scheduler_queries: list[dict[str, str]] = Field(
        default_factory=lambda: [
            # Madrid - IT keywords
            {"keywords": "React", "location": "Madrid"},
            {"keywords": "TypeScript", "location": "Madrid"},
            {"keywords": "Python", "location": "Madrid"},
            {"keywords": "Node.js", "location": "Madrid"},
            {"keywords": "DevOps", "location": "Madrid"},
            {"keywords": "AWS", "location": "Madrid"},
            {"keywords": "Docker", "location": "Madrid"},
            {"keywords": "Full Stack", "location": "Madrid"},
            {"keywords": "Backend", "location": "Madrid"},
            {"keywords": "Frontend", "location": "Madrid"},
            # Barcelona - IT keywords
            {"keywords": "React", "location": "Barcelona"},
            {"keywords": "TypeScript", "location": "Barcelona"},
            {"keywords": "Python", "location": "Barcelona"},
            {"keywords": "Node.js", "location": "Barcelona"},
            {"keywords": "DevOps", "location": "Barcelona"},
            {"keywords": "AWS", "location": "Barcelona"},
            {"keywords": "Docker", "location": "Barcelona"},
            {"keywords": "Full Stack", "location": "Barcelona"},
            {"keywords": "Backend", "location": "Barcelona"},
            {"keywords": "Frontend", "location": "Barcelona"},
            # Málaga - IT keywords
            {"keywords": "React", "location": "Málaga"},
            {"keywords": "TypeScript", "location": "Málaga"},
            {"keywords": "Python", "location": "Málaga"},
            {"keywords": "Node.js", "location": "Málaga"},
            {"keywords": "DevOps", "location": "Málaga"},
            {"keywords": "AWS", "location": "Málaga"},
            {"keywords": "Docker", "location": "Málaga"},
            {"keywords": "Full Stack", "location": "Málaga"},
            {"keywords": "Backend", "location": "Málaga"},
            {"keywords": "Frontend", "location": "Málaga"},
        ],
        validation_alias=AliasChoices("SCHEDULER_QUERIES", "scheduler_queries"),
    )

    # `scheduler-retention-history`: TTL-based retention after each
    # scheduler cycle. `0` (default) means "never delete"; any
    # positive value deletes jobs with `last_seen_at` older than
    # that many days, capped at `LIMIT 1000` per call
    # (REQ-RET-001).
    retention_days: int = Field(
        default=0,
        validation_alias=AliasChoices("RETENTION_DAYS", "retention_days"),
    )

    @field_validator("retention_days", mode="after")
    @classmethod
    def _clamp_negative_retention_days(cls, v: int) -> int:
        """Clamp negative `retention_days` to 0."""
        return max(0, v)

    @field_validator("scheduler_queries", mode="before")
    @classmethod
    def _parse_scheduler_queries(cls, v: object) -> list[dict[str, str]]:
        """Parse `SCHEDULER_QUERIES` as a JSON list of `{keywords, location}` objects.

        Mirrors the `_parse_exempt_paths` and `_parse_aggregator_priority_map`
        patterns: accepts a pre-parsed list (programmatic construction) or a
        JSON string (env var). An empty / None value yields the default.
        """
        if isinstance(v, list):
            _validate_str_dict_list(v, "SCHEDULER_QUERIES")
            return v
        if isinstance(v, str):
            if not v.strip():
                return [
                    {"keywords": "", "location": "España"},
                    {"keywords": "", "location": "Madrid, España"},
                    {"keywords": "", "location": "Barcelona, España"},
                ]
            try:
                parsed = json.loads(v)
            except json.JSONDecodeError as e:
                raise ValueError(f"SCHEDULER_QUERIES must be JSON: {e}") from e
            if not isinstance(parsed, list):
                raise ValueError(
                    f"SCHEDULER_QUERIES must be a JSON list, got {type(parsed).__name__}"
                )
            _validate_str_dict_list(parsed, "SCHEDULER_QUERIES")
            return parsed
        raise ValueError(f"unparseable SCHEDULER_QUERIES: {v!r}")

    @model_validator(mode="after")
    def _auto_cors_for_development(self) -> "Settings":
        """Auto-configure CORS origins based on deployment environment.

        - development (ENVIRONMENT=development or unset): set CORS to
          localhost-only allowlist so local frontend can call the API.
        - production (ENVIRONMENT=production): require explicit CORS config;
          raise ValueError if still at the sentinel default ["*"].
        """
        if self.deployment_environment == "development":
            # Override the bare "*" sentinel with a safe localhost list.
            self.cors_allow_origins = [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
            ]
        elif self.cors_allow_origins == ["*"]:
            # production but CORS was not explicitly set
            raise ValueError(
                "CORS not configured: set LINKEDIN_CORS_ALLOW_ORIGINS to your "
                "production frontend origin (e.g. https://jobsfinder.example.com) "
                "or set ENVIRONMENT=development for local dev."
            )
        return self


def load_settings() -> Settings:
    """Read env vars and return a fully-populated `Settings`.

    A thin wrapper that exists so callers (and tests) can refer to a
    single factory function instead of importing the class directly.
    """
    return Settings()
