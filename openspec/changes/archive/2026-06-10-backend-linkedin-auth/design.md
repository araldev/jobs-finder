# Design: `backend-linkedin-auth`

> **Status**: `design` (ready for `sdd-tasks`)
> **Base**: `017d6fa` (post `backend-infojobs-provinces` + `backend-scraper-query-tuning` merge, main; working tree clean per `git status -s`)
> **Spec**: Engram obs #355 (REQ-LA-COOKIE-001..004, REQ-LA-SCR-001..006, REQ-LA-CFG-001..004, REQ-LA-AWALL-001..006 — 19 REQs total)
> **Proposal**: Engram obs #354
> **Exploration**: Engram obs #353
> **Mode**: `both` (OpenSpec filesystem + Engram)
> **Strict TDD**: ACTIVE — every scenario in the spec is a real test, written RED first

## 1. Architecture overview

This change plumbs the operator's `li_at` session cookie from the env
var `LINKEDIN_LI_AT` into the Playwright `BrowserContext` of the
LinkedIn scraper. The cookie is **internal to the scraper** (never
touches the HTTP contract), gated by a new `LinkedInAuthCookiePort`
Protocol, validated at boot by a `Settings.linkedin_li_at` field, and
observed post-scrape by a defensive `is_auth_wall(soup)` detector.
The 4 new pieces land in 4 layers and compose at the existing
composition root:

```
.env (LINKEDIN_LI_AT=<operator's cookie>)
   ↓ pydantic-settings loads (config.py, after linkedin_inter_page_delay_seconds:292)
Settings.linkedin_li_at: SecretStr | None
   ↓ mode="before" validator normalizes empty→None
Settings.linkedin_li_at: SecretStr | None
   ↓ mode="after" validator rejects len<8
   ↓ app_factory.build_app() (L172)
EnvLinkedInAuthCookieAdapter(settings.linkedin_li_at)
   ↓ implements
LinkedInAuthCookiePort  ← NEW Protocol in application/ports.py
   ↓ injected into
LinkedInScraperSettings.auth_cookie (additive kwarg; default None = v1 anonymous)
   ↓ scraper.search() reads at L274 (per-context, per-search)
await ctx.add_cookies([{"name": "li_at", "value": ..., "domain": ".linkedin.com", ...}])
   ↓ loop (one-time injection, cookie travels with all page requests)
paginated_search() (helper, source-agnostic, UNCHANGED)
   ↓ each page renders
is_auth_wall(soup) detector
   ↓ if True → WARNING log (REQ-LA-AWALL-005); else parse normally
_parse_cards(soup, remaining)
```

**Key seams** (the precedent shapes the design follows):

- `LinkedInAuthCookiePort` mirrors `LocationResolverPort` (per
  `backend-linkedin-location-fallback` archive, obs #302): sync,
  single-method, structural Protocol, no `@runtime_checkable`. The
  cookie adapter is a pure in-process value provider (no I/O) so
  the sync signature is correct.
- `Settings.linkedin_li_at` mirrors `llm_api_key` (per
  `chat-filter-2stage` archive): `SecretStr | None` + `AliasChoices`
  + `field_validator(mode="before")` to normalize empty→None. The
  new `field_validator(mode="after")` adds the Q1 length check (a
  second validator is the minimum-surface extension).
- `is_auth_wall(soup)` mirrors `is_block_page(soup)` (per
  `parsers.py:213-242`): pure function, no I/O, "cards win" rule.

**Layer discipline** (`presentation → application → domain ← infrastructure`, per AGENTS.md):
- Application grows a NEW `LinkedInAuthCookiePort` Protocol
  (in `ports.py` next to `LocationResolverPort`) — application
  knows the contract, NOT the impl.
- Infrastructure grows a NEW `EnvLinkedInAuthCookieAdapter` (in
  `infrastructure/linkedin/auth_cookie.py`) — impl reads `Settings`.
- Composition root (`app_factory.build_app()`) wires the adapter
  to the scraper's settings — only place that knows the env.

## 2. Components

### 2.1 `LinkedInAuthCookie` value object (NEW)

**File**: `backend/src/jobs_finder/application/linkedin_auth.py` (new
module, mirrors the inline-Ports pattern of `application/ports.py` —
the value object is the port's "return type", and ports.py is the
Protocol declaration; splitting into 2 files is the convention).

**Shape** (5-line sketch):

```python
from dataclasses import dataclass
from pydantic import SecretStr

@dataclass(frozen=True, slots=True)
class LinkedInAuthCookie:
    name: str           # always "li_at"
    value: SecretStr
    domain: str         # always ".linkedin.com"
    path: str           # always "/"
    http_only: bool     # always True
    secure: bool        # always True

    def __repr__(self) -> str:                # AGENTS.md rule #7
        return f"LinkedInAuthCookie(name={self.name!r}, value=***, domain={self.domain!r})"

    def to_playwright_dict(self) -> dict[str, str | bool]:
        return {
            "name": self.name,
            "value": self.value.get_secret_value(),   # unwrap at the Playwright API boundary ONLY
            "domain": self.domain,
            "path": self.path,
            "httpOnly": self.http_only,
            "secure": self.secure,
        }
```

**Rationale**: `frozen=True` + `slots=True` (immutable, hashable,
no accidental mutation — mirrors `RateLimitDecision` at
`application/ports.py:313`); explicit `__repr__` mask
(REQ-LA-COOKIE-004); `to_playwright_dict()` adapter for the
Playwright API surface (REQ-LA-SCR-002). The `SecretStr` field
preserves the type-level log-masking at the value-object level
(REQ-LA-COOKIE-003); `get_secret_value()` is called ONLY in
`to_playwright_dict()` (the one place that needs the raw bytes for
the Playwright API).

### 2.2 `LinkedInAuthCookiePort` Protocol (NEW)

**File**: `backend/src/jobs_finder/application/ports.py` (extend the
existing file; add at the end of the file, after the
`NoOpRateLimiter` class at line 642 — Protocol host file is
already long, no need for a new file).

**Shape** (4-line sketch):

```python
from pydantic import SecretStr
from jobs_finder.application.linkedin_auth import LinkedInAuthCookie

class LinkedInAuthCookiePort(Protocol):
    """Returns the operator's `li_at` cookie (SecretStr-masked), or None."""
    def cookie(self) -> SecretStr | None: ...
```

**Rationale**: `Protocol` (structural typing — matches
`JobSearchPort`, `LocationResolverPort`, `LLMClientPort`); single
method `cookie(self) -> SecretStr | None` (intentionally minimal —
no set/refresh/clear, no async — the value comes from `Settings`
at process start); returns `None` (NOT raise) when absent
(REQ-LA-COOKIE-002 soft mode). The `SecretStr | None` return type
(not `LinkedInAuthCookie | None`) keeps the contract minimal:
the value object is the adapter's implementation detail, the
Protocol returns the raw value. The adapter is a `SecretStr`
value-holder; the scraper passes it to `ctx.add_cookies` directly
(dict construction inline — no `to_playwright_dict()` needed at
the Protocol boundary, only at the `EnvLinkedInAuthCookieAdapter`
impl which owns the Playwright-shape translation).

**Re-evaluation (from proposal §4.1)**: the proposal suggested
returning `LinkedInAuthCookie | None` to encapsulate the
`to_playwright_dict` method. The design (per strict TDD feedback
in the orchestrator's spec phase) returns `SecretStr | None`
directly — the cookie name (`"li_at"`), domain (`".linkedin.com"`),
path (`"/"`), `http_only`, and `secure` flags are PURE
infrastructure concerns (they're the Playwright `add_cookies` API
shape). They have no business in the application-layer Protocol.
The adapter is the single source of truth for the shape; the
scraper calls the adapter and builds the dict. The Protocol stays
narrow (1 method, 1 return type), the value object is dropped.

The `LinkedInAuthCookie` value object (§2.1) is REMOVED from the
final design — the proposal's `to_playwright_dict()` method is
moved into the adapter as a private helper. The 4-line Protocol
above is the FINAL shape.

### 2.3 `EnvLinkedInAuthCookieAdapter` (NEW)

**File**: `backend/src/jobs_finder/infrastructure/linkedin/auth_cookie.py`
(new file — `__init__.py` is a docstring-only file, NOT a re-export
hub per AGENTS.md rule #4; import the adapter from
`jobs_finder.infrastructure.linkedin.auth_cookie` directly).

**Shape** (10-line sketch):

```python
from pydantic import SecretStr

class EnvLinkedInAuthCookieAdapter:
    """Reads `li_at` from `Settings.linkedin_li_at` (no I/O at runtime)."""
    __slots__ = ("_cookie",)

    def __init__(self, cookie: SecretStr | None) -> None:
        self._cookie = cookie

    def cookie(self) -> SecretStr | None:
        return self._cookie
```

**Rationale**: sync (no I/O — `Settings` is loaded at process
start); `__slots__` (memory efficiency + immutability
documented at the type level, matches `NoOpRateLimiter` at
`application/ports.py:625`); the adapter is a value-holder
pattern (the only state is the `SecretStr | None` reference);
`get_secret_value()` is NEVER called in this class — the
adapter returns the `SecretStr` as-is, and the scraper (the
only consumer) calls `get_secret_value()` at the `add_cookies`
call site, where the raw bytes are needed for the Playwright
API.

### 2.4 `Settings.linkedin_li_at` + 2 validators (EXTENDED)

**File**: `backend/src/jobs_finder/infrastructure/config.py`
(extend the existing file; add the field + 2 validators AFTER
`linkedin_inter_page_delay_seconds` at line 292 — same
LinkedIn-pagination block; the 2 validators sit next to the
field as a private helper, mirrors `_normalize_empty_secret` at
line 734-743 for `llm_api_key`).

**Shape** (8-line sketch for the field + 2 validators):

```python
linkedin_li_at: SecretStr | None = Field(
    default=None,
    validation_alias=AliasChoices("LINKEDIN_LI_AT", "linkedin_li_at"),
)

@field_validator("linkedin_li_at", mode="before")
@classmethod
def _normalize_empty_li_at(cls, v: SecretStr | str | None) -> SecretStr | None:
    # Mirrors _normalize_empty_secret (config.py:734-743) for llm_api_key.
    if v is None: return None
    if isinstance(v, SecretStr): return v if v.get_secret_value() else None
    if isinstance(v, str):         return SecretStr(v) if v else None
    return v

@field_validator("linkedin_li_at", mode="after")
@classmethod
def _reject_short_li_at(cls, v: SecretStr | None) -> SecretStr | None:
    # Q1 option C: HARD reject when present+<8 chars; SOFT None is allowed.
    if v is None: return None
    if len(v.get_secret_value()) < 8:
        raise ValueError(
            f"LINKEDIN_LI_AT must be at least 8 characters (got {len(v.get_secret_value())}); "
            "check for typos or unset the variable to run the scraper anonymously."
        )
    return v
```

**Rationale**: `SecretStr | None` (REQ-LA-CFG-001 — the
kill-switch semantic: `None` = anonymous, `SecretStr` =
authenticated; auto-masks in `repr`/`str`); per-field
`validation_alias=AliasChoices("LINKEDIN_LI_AT", "linkedin_li_at")`
(matches the `linkedin_max_pages` pattern at `config.py:283-286`;
the explicit alias survives a future prefix rename); 2
`field_validator`s: `mode="before"` normalizes the 3 empty inputs
(`None`, `""`, `SecretStr("")`) to `None` (REQ-LA-CFG-003); the
new `mode="after"` rejects `len < 8` (REQ-LA-CFG-002 — the 8-char
threshold catches operator typos like `LINKEDIN_LI_AT=abc` while
accepting every realistic real `li_at` which is ~150 chars). The
error message includes `got <N>` so the operator can self-diagnose
the typo (no need to re-run with DEBUG).

### 2.5 `LinkedInPlaywrightScraper.search()` cookie injection (EXTENDED)

**File**: `backend/src/jobs_finder/infrastructure/linkedin/scraper.py`
(extend the existing file; 2 changes — `LinkedInScraperSettings`
kwargs/repr/eq/hash at lines 118-176, and `search()` injection at
line 274).

**Change A**: `LinkedInScraperSettings` adds an `auth_cookie`
kwarg + slot + repr masking + eq/hash coverage:

```python
class LinkedInScraperSettings:
    __slots__ = (
        "auth_cookie",            # NEW
        "inter_page_delay_seconds",
        "location_resolver",
        "max_pages",
        "timeout_ms",
        "user_agent",
    )
    def __init__(
        self, *, user_agent, timeout_ms, max_pages=10,
        inter_page_delay_seconds=1.0, location_resolver=None,
        auth_cookie: LinkedInAuthCookiePort | None = None,  # NEW
    ) -> None:
        # ... existing 4 assignments ...
        self.auth_cookie = auth_cookie
    def __repr__(self) -> str:
        auth_cookie_repr = "<set>" if self.auth_cookie is not None else "<unset>"
        return (
            f"LinkedInScraperSettings(user_agent={self.user_agent!r}, "
            f"timeout_ms={self.timeout_ms}, max_pages={self.max_pages}, "
            f"inter_page_delay_seconds={self.inter_page_delay_seconds}, "
            f"location_resolver={self.location_resolver!r}, "
            f"auth_cookie={auth_cookie_repr})"      # masked: NEVER the SecretStr value
        )
```

**Change B**: `search()` injects the cookie after `new_context()`
at line 274 (single injection site, per the spec):

```python
ctx = await self._browser.new_context(
    user_agent=self._settings.user_agent,
    viewport=VIEWPORT,
)
# T-004 of `backend-linkedin-auth` — REQ-LA-SCR-002 plumb.
# Inject the operator's `li_at` cookie ONCE per `search()` (per-context,
# not per-page). The cookie travels with every page request in the
# pagination loop (the `BrowserContext` shares the cookie store with
# all pages in the context).
cookie = self._settings.auth_cookie.cookie() if self._settings.auth_cookie is not None else None
if cookie is not None:
    await ctx.add_cookies([{
        "name": "li_at",
        "value": cookie.get_secret_value(),   # unwrap ONLY at the Playwright API boundary
        "domain": ".linkedin.com",
        "path": "/",
        "httpOnly": True,
        "secure": True,
    }])
    _logger.debug("LinkedIn auth cookie injected (length=%d)", len(cookie.get_secret_value()))
# else: legacy anonymous path — no `add_cookies` call, no log spam
try:
    page = await ctx.new_page()
    # ... existing `return await paginated_search(...)` UNCHANGED
```

**Rationale**: single injection site between `new_context()` and
`paginated_search()` (REQ-LA-SCR-002 — the cookie travels with the
context's cookie store, so per-page injection is unnecessary);
`__repr__` masks the cookie as `<set>`/`<unset>` (REQ-LA-COOKIE-004
— AGENTS.md rule #7); the `else` branch is the v1 anonymous path
(REQ-LA-SCR-003 — no log noise, the WARNING is emitted at
`app_factory.build_app()` startup, not inside `search()`);
`__eq__`/`__hash__` include `auth_cookie` (REQ-LA-COOKIE-004 3rd
scenario — two settings with different cookies are NOT equal);
the `_logger.debug` line at `length=<N>` shows the cookie length
to the operator without logging the value (REQ-LA-SCR-005).

### 2.6 `is_auth_wall(soup)` defensive detector (NEW)

**File**: `backend/src/jobs_finder/infrastructure/linkedin/parsers.py`
(extend the existing file; add the pure function AFTER
`is_block_page` at line 242 — same module, same selector-style
helper).

**Shape** (10-line sketch):

```python
def is_auth_wall(soup: BeautifulSoup) -> bool:
    """Return True ONLY when the SERP rendered an auth-wall variant.

    Distinct from `is_block_page` (the 502 path): `is_block_page`
    fires on a true auth-wall with ZERO cards (raises
    `LinkedInBlockedError`); this function fires on an auth-wall
    variant with zero cards (emits a WARNING log + returns the
    empty list — REQ-LA-AWALL-006: NO raise). The "cards win"
    rule (REQ-LA-AWALL-004) suppresses false positives on
    healthy SERPs that happen to render the `auth-wall` class
    as defensive markup.
    """
    auth_wall_signal = soup.select_one("body.auth-wall, .auth-wall")
    if auth_wall_signal is None:
        return False
    if soup.select("div[data-entity-urn]"):
        return False   # cards win — false positive suppressed
    return True
```

**Rationale**: pure (no I/O, no `await`, no module-level mutable
state, no logging side-effects — REQ-LA-AWALL-001); mirrors
`is_block_page` style (single-return boolean, `select_one` for the
auth-wall signal, `select` for the cards check); "cards win" rule
matches `is_block_page:233-234` (consistency between the 2
detectors — same HTML yields the same verdict on the "cards
present" case). The function is the WARNING-path detector; the
raise-path is `is_block_page` (preserved untouched per the spec).

**Integration in `_make_fetch_one_page` closure** (scraper.py:336-345):

```python
async def fetch_one_page(page, page_index, remaining) -> list[Job]:
    url = self._build_url(...)
    await self._navigate_and_wait(page, url)
    content = await page.content()
    soup = BeautifulSoup(content, "html.parser")
    if is_block_page(soup):                    # existing — HARD block (502)
        raise LinkedInBlockedError("LinkedIn returned an auth-wall / verification page")
    if is_auth_wall(soup):                     # NEW — soft WARNING (REQ-LA-AWALL-005)
        _logger.warning(
            "LinkedIn SERP appears auth-walled despite cookie injection; "
            "cookie may be expired. Returning 0 jobs from this page (degraded)."
        )
    return _parse_cards(soup, remaining)
```

**Rationale**: position is AFTER `is_block_page` (so the HARD
raise takes precedence when both fire) and BEFORE
`_parse_cards` (so the WARNING fires before any parse work); the
closure continues to parse + return the parsed jobs
(REQ-LA-AWALL-005 — does NOT raise, does NOT short-circuit); the
WARNING is emitted ONCE per page that triggers it (REQ-LA-AWALL-005
last acceptance bullet — a multi-page search can hit the wall on
a subset of pages).

### 2.7 Composition root wiring (EXTENDED)

**File**: `backend/src/jobs_finder/presentation/app_factory.py`
(extend the existing file; 1 new import + 1 new adapter
construction + 1 new kwarg on `LinkedInScraperSettings`).

**Change** (in the `if use_case is None:` block at line 239,
inside the `LinkedInPlaywrightScraper(...)` ctor at line 240):

```python
# T-006 of `backend-linkedin-auth` — REQ-LA-SCR-001 plumb.
# Build the `EnvLinkedInAuthCookieAdapter` from the resolved
# `Settings.linkedin_li_at` (default None = v1 anonymous).
# The adapter is constructed ONCE per `build_app()` call and
# lives in the `LinkedInScraperSettings` slot.
auth_cookie_port = EnvLinkedInAuthCookieAdapter(effective_settings.linkedin_li_at)
if effective_settings.linkedin_li_at is None:
    # REQ-LA-SCR-003: single startup WARNING when cookie is absent.
    # Emitted ONCE per process start (not per `search()`).
    _logger.warning(
        "LinkedIn scraper running without auth cookie; "
        "SERP will hit the auth wall and return a reduced list"
    )
scraper = LinkedInPlaywrightScraper(
    throttle=AsyncThrottle(min_interval_seconds=effective_settings.throttle_seconds),
    settings=LinkedInScraperSettings(
        user_agent=effective_settings.user_agent,
        timeout_ms=effective_settings.request_timeout_ms,
        max_pages=effective_settings.linkedin_max_pages,
        inter_page_delay_seconds=effective_settings.linkedin_inter_page_delay_seconds,
        location_resolver=location_resolver,
        auth_cookie=auth_cookie_port,   # NEW kwarg
    ),
)
```

**Rationale**: the composition root is the ONLY site that knows
about `Settings.linkedin_li_at` (REQ-LA-SCR-001 — the scraper
receives the port, NOT the env); the WARNING log is emitted
ONCE at startup, NOT inside `search()` (REQ-LA-SCR-003 — per-
search log spam avoided); the adapter ctor takes the
`SecretStr | None` value directly (no separate factory, no env
read — the `Settings` field is the only source of truth).

## 3. File-by-file delta

| File | Change | + | - | Reason |
|---|---|---|---|---|
| `backend/src/jobs_finder/application/ports.py` | EXTENDED | +12 | 0 | Add `LinkedInAuthCookiePort` Protocol + `SecretStr` import. (The value object §2.1 was removed in design simplification — see §2.2 rationale.) |
| `backend/src/jobs_finder/infrastructure/linkedin/auth_cookie.py` | NEW | ~30 | 0 | `EnvLinkedInAuthCookieAdapter` (the value-holder). |
| `backend/src/jobs_finder/infrastructure/linkedin/__init__.py` | UNCHANGED | 0 | 0 | Docstring-only per AGENTS.md rule #4 (no re-export hub). |
| `backend/src/jobs_finder/infrastructure/linkedin/scraper.py` | EXTENDED | ~18 | ~2 | Add `auth_cookie` slot + kwarg + repr/eq/hash (REQ-LA-COOKIE-004); inject cookie after `new_context()` (REQ-LA-SCR-002..006); `is_auth_wall` WARNING log in closure (REQ-LA-AWALL-005). |
| `backend/src/jobs_finder/infrastructure/linkedin/parsers.py` | EXTENDED | +12 | 0 | `is_auth_wall(soup)` pure function. |
| `backend/src/jobs_finder/infrastructure/config.py` | EXTENDED | +25 | 0 | `linkedin_li_at: SecretStr \| None` field + `mode="before"` empty→None validator + `mode="after"` `len<8`→`ValueError` validator. |
| `backend/src/jobs_finder/presentation/app_factory.py` | EXTENDED | +12 | 0 | Import `EnvLinkedInAuthCookieAdapter`; construct adapter; emit startup WARNING when None; pass `auth_cookie=` kwarg. |
| `backend/.env.example` | EXTENDED | +6 | 0 | `LINKEDIN_LI_AT=` placeholder line in the LinkedIn block + security note. |
| `backend/README.md` | EXTENDED | +35 | 0 | New "LinkedIn auth cookie (optional)" subsection in the manual verification section. |
| `backend/tests/conftest.py` | EXTENDED | +12 | 0 | `FakeLinkedInAuthCookiePort` companion. |
| `backend/tests/unit/test_linkedin_auth_cookie.py` | NEW | ~120 | 0 | 7 tests: Protocol conformance, adapter happy/None/empty, settings repr masking (set + unset), eq/hash. |
| `backend/tests/unit/test_linkedin_config.py` | NEW | ~70 | 0 | 4 tests: env binding, validator rejects 3/7 chars, accepts 8/12 chars, settings repr no-leak. |
| `backend/tests/unit/test_linkedin_auth_wall.py` | NEW | ~50 | 0 | 4 tests: signature/purity, `BLOCK_PAGE_HTML` → True, `SEARCH_PAGE_HTML` → False, cards+auth-wall-class → False. |
| `backend/tests/unit/test_linkedin_scraper.py` | EXTENDED | +90 | 0 | 5 tests: no cookie → no `add_cookies`; with cookie → shape; per-search not per-page; 2-searches 2-calls; no cookie value in logs (caplog); auth-wall WARNING at closure. |
| `backend/tests/integration/test_linkedin_auth_cookie.py` | NEW | ~60 | 0 | 1-2 end-to-end scenarios via `build_app(use_case=...)` + `FakeLinkedInAuthCookiePort` (no Playwright launch). |
| **TOTAL** | | **~542** | **~2** | |

(Rough; design may shift the count by ±50. Well under the 5000-line
review budget; single PR is sufficient — no chained PRs needed.)

## 4. Test plan (Strict TDD — every scenario is a real test)

Per spec REQ → test file → test function:

| Spec REQ | Test file | Test function |
|---|---|---|
| REQ-LA-COOKIE-001 | `tests/unit/test_linkedin_auth_cookie.py` | `test_port_protocol_structural_conformance` |
| REQ-LA-COOKIE-002 | `tests/unit/test_linkedin_auth_cookie.py` | `test_adapter_returns_none_when_unset` + `test_adapter_returns_none_when_empty_secret` |
| REQ-LA-COOKIE-003 | `tests/unit/test_linkedin_auth_cookie.py` | `test_adapter_returns_secretstr_with_masked_repr` + `test_adapter_returns_secretstr_at_minimum_length_8` |
| REQ-LA-COOKIE-004 | `tests/unit/test_linkedin_auth_cookie.py` | `test_settings_repr_masks_set_cookie` + `test_settings_repr_masks_unset_cookie` + `test_settings_eq_hash_includes_auth_cookie` |
| REQ-LA-SCR-001 | `tests/unit/test_linkedin_scraper.py` | `test_search_reads_cookie_from_injected_port_not_env` |
| REQ-LA-SCR-002 | `tests/unit/test_linkedin_scraper.py` | `test_add_cookies_called_with_correct_shape` |
| REQ-LA-SCR-003 | `tests/unit/test_linkedin_scraper.py` + `tests/integration/test_linkedin_auth_cookie.py` | `test_no_add_cookies_call_when_auth_cookie_none` + `test_startup_warning_when_cookie_absent` |
| REQ-LA-SCR-004 | `tests/unit/test_linkedin_scraper.py` | `test_add_cookies_shape_matches_linkedin_contract` (golden assertion) |
| REQ-LA-SCR-005 | `tests/unit/test_linkedin_scraper.py` | `test_search_does_not_log_cookie_value` (caplog) |
| REQ-LA-SCR-006 | `tests/unit/test_linkedin_scraper.py` | `test_add_cookies_called_once_per_search` + `test_add_cookies_called_once_per_search_for_multiple_searches` |
| REQ-LA-CFG-001 | `tests/unit/test_linkedin_config.py` | `test_settings_reads_linkedin_li_at_from_env` + `test_settings_linkedin_li_at_defaults_to_none` + `test_settings_linkedin_li_at_programmatic_construction` |
| REQ-LA-CFG-002 | `tests/unit/test_linkedin_config.py` | `test_settings_rejects_short_li_at_3_chars` + `test_settings_rejects_short_li_at_7_chars` + `test_settings_accepts_minimum_length_8` |
| REQ-LA-CFG-003 | `tests/unit/test_linkedin_config.py` | `test_settings_accepts_none_li_at` + `test_settings_normalizes_empty_secret_to_none` + `test_settings_normalizes_empty_string_to_none` |
| REQ-LA-CFG-004 | `tests/unit/test_linkedin_config.py` | `test_settings_repr_does_not_leak_cookie_value` |
| REQ-LA-AWALL-001 | `tests/unit/test_linkedin_auth_wall.py` | `test_is_auth_wall_signature` + `test_is_auth_wall_is_pure_no_mutation` |
| REQ-LA-AWALL-002 | `tests/unit/test_linkedin_auth_wall.py` | `test_is_auth_wall_true_for_block_page_fixture` |
| REQ-LA-AWALL-003 | `tests/unit/test_linkedin_auth_wall.py` | `test_is_auth_wall_false_for_healthy_serp` |
| REQ-LA-AWALL-004 | `tests/unit/test_linkedin_auth_wall.py` | `test_is_auth_wall_false_when_cards_present_even_with_auth_wall_class` |
| REQ-LA-AWALL-005 | `tests/unit/test_linkedin_scraper.py` | `test_closure_warns_on_auth_wall_zero_cards` + `test_closure_does_not_warn_when_cards_present_with_auth_wall_class` |
| REQ-LA-AWALL-006 | `tests/unit/test_linkedin_scraper.py` | `test_closure_returns_empty_list_on_auth_wall_no_raise` |

**Total**: ~18 new test functions (matches the spec's 14-18
estimate). 1,142 baseline tests continue to pass (no regressions —
the `auth_cookie=None` default + the v1 anonymous `if/else` branch
preserve all existing behavior).

## 5. Tradeoffs (explicit)

| # | Decision | Why |
|---|---|---|
| 1 | `SecretStr` (not a custom masked type) | Pydantic canonical masked type; the existing `llm_api_key` field uses it (`config.py:714`); rolling our own would diverge from the precedent. |
| 2 | `EnvLinkedInAuthCookieAdapter` (not env read in scraper) | The scraper must be testable offline with a fake adapter; the env read happens at composition time, not at search time. Mirrors `EnvLinkedInAuthCookieAdapter`-style env adapters elsewhere. |
| 3 | `LinkedInAuthCookie` value object REMOVED from design (was in proposal §4.1) | The value object exists only as the Playwright-shape translation. Moving the shape into the adapter (private helper) keeps the Protocol narrow (1 method, `SecretStr \| None`) and the value object out of the application layer. The Protocol returns a `SecretStr` directly; the scraper passes it to `add_cookies` as a one-line dict construction. |
| 4 | Cookie on `BrowserContext` (not `Page`) | Context-level survives navigations within the loop; page-level would need re-add on every `goto`. `paginated_search` does many `page.goto` calls — context-level is the only sane choice. |
| 5 | `is_auth_wall` conservative (class OR descendant) | A single selector misses LinkedIn's variant A/B renderings; the OR catches both with a tiny false-positive risk (mitigated by the "cards win" rule). |
| 6 | No log test at integration level | Log assertions are flaky across pytest capture modes; the unit test (`test_search_does_not_log_cookie_value`) is sufficient. |
| 7 | No new exception type for the auth-wall path | The scraper returns `[]` (REQ-LA-AWALL-006) and emits a WARNING. A new exception would force the route to 502, defeating the "degraded but functional" semantic. |
| 8 | `__repr__` mask as `<set>`/`<unset>` (not the value) | `SecretStr` already masks the value at the field level; the settings repr override is defense-in-depth (REQ-LA-COOKIE-004). |
| 9 | `__init__.py` files UNCHANGED | AGENTS.md rule #4 — no business logic. The new modules contain real code; the existing `__init__.py` files stay docstring-only. |
| 10 | 2 `field_validator`s (not 1) | The Q1 spec says HARD error on `len<8` BUT soft None is allowed. Pydantic's `mode="before"` normalizes empty→None; `mode="after"` rejects length. A single `mode="after"` validator with `if v is None: return v` would also work but mirrors the `llm_api_key` 2-validator pattern (`config.py:734-743`); 2 validators is the convention. |
| 11 | `auth_cookie` kwarg on `LinkedInScraperSettings` (NOT on `JobSearchPort`) | The Port stays source-agnostic. Mirrors the `location_resolver` kwarg at `scraper.py:133` (the `linkedin-structured-location-fallback` precedent). |

## 6. Open design questions

**None — all design decisions resolved in preflight + spec.** The
proposal locked-in Q1=C (validator: HARD `<8`, SOFT None), Q3=include
(`is_auth_wall` detector), Q4=new_subsection (README structure).
Q2 (per-context injection) and Q5 (synthetic 12-byte cookie) are
resolved in `explore` §5. The design adds 1 micro-decision not in
the proposal: **drop the `LinkedInAuthCookie` value object** (it
added no value at the Protocol boundary; the shape translation
moved into the adapter as a private helper).

## 7. Risks (carry-forward from proposal §8 + new design-level risks)

| # | Risk | L | M |
|---|---|---|---|
| 1 | Real `li_at` cookie leaks into the repo (AGENTS.md rule #7) | M | `SecretStr` + `__repr__` mask + synthetic test value + `.env.example` empty line (4 layers). |
| 2 | Expired cookie → degraded results without operator awareness | M | `is_auth_wall` + WARNING log (REQ-LA-AWALL-002/005/006). |
| 3 | LinkedIn changes cookie name (`li_at` → `JSESSIONID`) | L | The cookie name is a string literal at `scraper.py`; a LinkedIn change requires a follow-up PR. The design documents the name as a constant. |
| 4 | `add_cookies` API change in Playwright | L | Playwright is `>=1.45` pinned; the call shape is stable since v1.10. The golden assertion test catches any shape drift. |
| 5 | Q1 validator `<8` too aggressive for future cookies | L | Real `li_at` are ~150 chars; if LinkedIn shortens, the threshold is bumped in a follow-up. |
| 6 | Pre-change test doubles don't conform to the new Protocol | L | `FakeLinkedInAuthCookiePort` companion in `conftest.py` is the default. Existing tests stay GREEN (the `auth_cookie` kwarg default is `None`). |
| 7 | Concurrent `search()` calls share state | L | Per-context lifecycle: each `search()` opens a fresh `new_context()` and the `add_cookies` runs inside the per-search `try` block. |
| 8 | `is_auth_wall` false positives | M | "Cards win" rule (REQ-LA-AWALL-004). |
| 9 | Operator configures `LINKEDIN_LI_AT` with an expired value | M | README FAQ + WARNING log. |
| 10 | `Settings` repr leaks via future plain-`str` regression | L | `test_settings_repr_does_not_leak_cookie_value` (REQ-LA-CFG-004). |
| 11 | **NEW** — Adapter ctor is `__init__(self, cookie: SecretStr \| None)` (takes a value, not a `Settings`) | L | The composition root does the `Settings.linkedin_li_at` unwrap; the adapter stays a value-holder. A test that constructs the adapter with a `SecretStr("AQEAAAAQEAAA")` directly is independent of `Settings` ctor side-effects. The risk is a future refactor that passes the `Settings` instance to the adapter and accidentally calls `.linkedin_li_at.get_secret_value()` at search time. The design pins the adapter's ctor to the value. |
| 12 | **NEW** — `_logger.debug("cookie injected length=%d", len(...))` | L | The DEBUG line is the only place that mentions the cookie at all (the WARNING is only on the absence path). A future contributor who re-formats this line as `f"cookie={cookie}"` would leak. The `test_search_does_not_log_cookie_value` test pins the no-leak contract. |

## 8. Anti-patterns explicitly avoided

- **Does NOT log the cookie value at any level** — `__repr__` mask + DEBUG line uses `len()` only (REQ-LA-SCR-005).
- **Does NOT commit a real `li_at` value to any fixture** — only the 12-byte synthetic `"AQEAAAAQEAAA"` appears in test code (AGENTS.md rule #7).
- **Does NOT add business logic to `__init__.py`** — `infrastructure/linkedin/__init__.py` stays docstring-only; import the adapter from the module path (AGENTS.md rule #4).
- **Does NOT add a global `os.environ['LINKEDIN_LI_AT']` read in the scraper** — the scraper reads `self._settings.auth_cookie.cookie()` only (REQ-LA-SCR-001).
- **Does NOT modify `JobSearchPort`, `LocationResolverPort`, `JobSearchCacheKey`** — the cookie is internal to the scraper's `LinkedInScraperSettings` (mirrors the `location_resolver` injection precedent).
- **Does NOT modify the `paginated_search` helper** — the cookie is per-context, applied before the loop; the helper stays source-agnostic.
- **Does NOT modify `is_block_page`** — the new `is_auth_wall` coexists; they have distinct semantics.
- **Does NOT add a new exception type for the auth-wall path** — the WARNING + empty-list return is the contract (REQ-LA-AWALL-006).
- **Does NOT modify the other 2 scrapers (Indeed, InfoJobs)** — their anti-bot measures are different.
- **Does NOT modify the frontend HTTP contract** — `GET /jobs?q=...&location=...` is byte-identical; the cookie is internal.
- **Does NOT add a `LinkedInAuthCookie` value object** — the proposal's value object added no value at the Protocol boundary; the design dropped it (see §2.2 rationale and §5 tradeoff #3).

## 9. Workload forecast (for `sdd-tasks`)

**Total estimated**: ~540 LOC (production + tests + docs, including
strict-TDD tax). Well under the 5000-line review budget.

**Per the orchestrator's Review Workload Guard** (sdd-phase-common §E):

- `Chained PRs recommended: No` (single PR is sufficient; the
  change is well-bounded, < 600 LOC, orthogonally scoped to one
  Protocol + one Settings field + one parsers function).
- `400-line budget risk: Low` (the 400-line per-PR sub-budget is
  for "size:exception" overages; this change is 35% of the
  default 400-line per-PR sub-budget when sliced into 2-3 work
  units; well under).
- `Decision needed before apply: No` (no design-level decisions
  remain for the user; the design is ready for tasks).

The `sdd-tasks` phase MUST still emit the workload forecast and
the orchestrator will check it before launching `sdd-apply`.

## 10. Next step

Ready for `sdd-tasks`. The orchestrator should:

1. Confirm the preflight Q1/Q3/Q4 answers are still locked-in.
2. Verify the parallel `backend-infojobs-provinces` change is
   archived (it is — see `openspec/changes/archive/2026-06-10-`).
3. Delegate to `sdd-tasks` with inputs: design (this doc, saved
   to Engram), spec obs #355, proposal obs #354, exploration
   obs #353, init obs #1, #2, #3.
4. Expect ~5-7 work units (T-001..T-007) for the implementation
   per the proposal's task list (adapted to the design's
   file-by-file delta in §3).

**Skill resolution**: `paths-injected` — orchestrator pre-resolved
`sdd-design/SKILL.md` + `test-driven-development/SKILL.md` +
`work-unit-commits/SKILL.md` + `_shared/sdd-phase-common.md` +
`_shared/openspec-convention.md` + `_shared/engram-convention.md`.

## 11. Deviations from Design (archive note — added during sdd-archive)

The apply phase (T-004 in `obs #358`) implemented a **conditional
precedence flip** between `is_block_page` and `is_auth_wall` that
differs from §2.6's ordering. The spec contract
(`REQ-LA-AWALL-005/006`) is fully satisfied; the deviation is in
the ordering of the two checks, not the behavior.

**Design §2.6 said**: "AFTER `is_block_page(soup)` returns `False` …
BEFORE `_parse_cards(soup, remaining)` is called, the closure MUST
check `is_auth_wall(soup)`". The two checks were ordered
`is_block_page → is_auth_wall`.

**Implementation (T-004 commit `5a547df`)** inverts the precedence
in the closure:

```python
# When auth_cookie is set: is_auth_wall FIRST (soft path → WARNING + [])
# When auth_cookie is None: is_block_page FIRST (hard path → raise 502)
if self._settings.auth_cookie is not None:
    if is_auth_wall(soup):
        _logger.warning("LinkedIn SERP appears auth-walled ...")
        return _parse_cards(soup, remaining)  # soft path: returns []
    if is_block_page(soup):
        raise LinkedInBlockedError("...")
else:
    if is_block_page(soup):  # pre-existing v1 path, unchanged
        raise LinkedInBlockedError("...")
    # is_auth_wall is not checked in the anonymous path
```

**Why the flip** (per `obs #358` "Deviations from Design"):

- The spec's `REQ-LA-AWALL-005` says: when the cookie IS injected
  and the SERP renders an auth-wall variant (despite the cookie),
  the closure MUST emit a WARNING + return the parsed jobs (NOT
  raise). The `is_block_page` raise would short-circuit before
  `is_auth_wall` ever fires, defeating the soft-failure path.
- The v1 anonymous path (no cookie) is byte-identical to the
  pre-change: `is_block_page` still raises, `is_auth_wall` is not
  consulted. The pre-existing test
  `test_search_raises_blocked_on_auth_wall` (anonymous path)
  still passes without changes.
- The conditional gate `if self._settings.auth_cookie is not None`
  is the v1-vs-cookie discriminator. Two paths, two orderings:
  - **Cookie-injection path** (new): `is_auth_wall` FIRST (soft,
    WARNING + return), `is_block_page` SECOND (only fires on a
    genuine hard block that survived the soft filter — extremely
    rare; in practice the cookie + auth-wall variant takes the
    soft path and the function returns `[]`).
  - **Anonymous path** (v1, unchanged): `is_block_page` only
    (raise on hard block; the `is_auth_wall` WARNING would be
    noise on a path the operator already knows is degraded).

**Test coverage** (per `obs #358` TDD table): both branches are
exercised — `test_closure_warns_on_auth_wall_zero_cards` covers
the cookie-injection soft path; `test_search_raises_blocked_on_auth_wall`
covers the anonymous hard-raise path. **No regression**.

**Behavior contract preserved**: the spec's 6 REQ-LA-AWALL-*
scenarios all pass. The 38/38 spec compliance from the prior
verify report (obs #360 §"Spec compliance matrix") includes the
auth-wall scenarios. The flip is an implementation detail, not a
contract change.

**Future archeology note**: if a future contributor reads §2.6
and the implementation side-by-side, the conditional precedence
is the intentional design refinement. The implementation
documents the order in inline comments at the call site.
