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
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
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
        # Load from a local `.env` file (gitignored) on top of the
        # process environment. Shell env vars take precedence over
        # `.env` entries (pydantic-settings standard precedence). The
        # template lives at `.env.example` (committed, no secrets).
        env_file=".env",
        env_file_encoding="utf-8",
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


def load_settings() -> Settings:
    """Read env vars and return a fully-populated `Settings`.

    A thin wrapper that exists so callers (and tests) can refer to a
    single factory function instead of importing the class directly.
    """
    return Settings()
