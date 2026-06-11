# Design: `backend-linkedin-stealth`

> **Status**: `design` (ready for `sdd-tasks`)
> **Base**: `6402798` (post `backend-linkedin-auth` merge on `main`)
> **Spec**: obs #367 (15 REQ-LST-* = 3 CF + 5 COOKIE + 4 SCR + 3 CFG)
> **Proposal**: obs #366
> **Exploration**: obs #365
> **Trigger**: obs #364 (live `ERR_TOO_MANY_REDIRECTS` with the v1 `li_at`)
> **Precedent cycle**: obs #362 (v1 archive), obs #356 (v1 design template)
> **Mode**: `both` (OpenSpec filesystem + Engram)
> **Strict TDD**: ACTIVE
> **Confidence note**: 0.55 per explore obs #365 §4.4 that `playwright-stealth` bypasses the 2026 Cloudflare+LinkedIn 302-loop. Documented fallback: `backend-linkedin-residential-proxy` (out of scope).

## 1. Architecture overview

The change extends the v1 `backend-linkedin-auth` cycle along 3 axes: (1) inject `playwright-stealth` (already a project dep, used by Indeed + InfoJobs) at the `BrowserContext` level; (2) replace the v1 single-cookie `LinkedInAuthCookiePort` with a NEW multi-cookie `LinkedInAuthCookiesPort` (4 cookies: `li_at` + `JSESSIONID` + `bcookie` + `li_gc`); (3) add a `is_cloudflare_challenge(soup)` detector that surfaces the 302-loop gracefully (soft path: WARNING + return `[]`). The v1 single-cookie `EnvLinkedInAuthCookieAdapter` is KEPT as a backward-compat shim (35 v1 tests construct it directly bypassing `Settings`); the v1 anonymous path is preserved byte-identical.

```
.env (LINKEDIN_LI_AT, LINKEDIN_JSESSIONID, LINKEDIN_BCOOKIE, LINKEDIN_LI_GC)
  ↓ pydantic-settings loads (4 SecretStr | None, _normalize_empty_li_at + _reject_short_li_at shared validator)
Settings.linkedin_{li_at, jsessionid, bcookie, li_gc}
  ↓ injected at app_factory.build_app() (composition root — only site that reads env)
MultiEnvLinkedInAuthCookiesAdapter(settings.linkedin_li_at, settings.linkedin_jsessionid,
                                    settings.linkedin_bcookie, settings.linkedin_li_gc)
  ↓ implements
LinkedInAuthCookiesPort  ← NEW Protocol (plural) in application/ports.py
  ↓ injected into (replaces v1 `auth_cookie`; v1 slot kept for backward compat)
LinkedInPlaywrightScraper (with NEW `stealth: Stealth | None = None` ctor kwarg)
  ↓ at BrowserContext level (mirroring Indeed at indeed/scraper.py:246-247, InfoJobs at infojobs/scraper.py:326-327)
await stealth.apply_stealth_async(ctx)  ← NEW
  ↓ on the same context
await ctx.add_cookies([{...} for (n, v) in cookies])  ← EXTENDED to N cookies (was 1)
  ↓ loop
paginated_search()  # source-agnostic, UNCHANGED
  ↓ per page
_make_fetch_one_page() closure precedence (cookie path):
  is_cloudflare_challenge(soup)  ← NEW (soft WARNING + return [] if 0 cards)
  is_auth_wall(soup)              ← v1 (soft WARNING + return parsed cards)
  is_block_page(soup)             ← v1 (hard raise — survives only if both soft filters miss)
_anonymous path: is_block_page first only (v1 byte-identical — 35 v1 tests preserved)
```

**Key seams** (the precedent shapes the design follows):

- `LinkedInAuthCookiesPort` mirrors the v1 `LinkedInAuthCookiePort` (obs #356 §2.2) but EXTENDS it (NOT replaces): same `application/ports.py` location, same structural Protocol, no `@runtime_checkable`. The v1 singular Protocol is KEPT; the v1 35-test conftest companion (`FakeLinkedInAuthCookiePort`) is KEPT.
- `MultiEnvLinkedInAuthCookiesAdapter` mirrors `EnvLinkedInAuthCookieAdapter` (obs #356 §2.3) — `__slots__`, sync, no I/O — but holds 4 references and exposes `cookies() -> list[tuple[str, SecretStr]] | None`. The deterministic order `li_at → JSESSIONID → bcookie → li_gc` is a contract pinned by the test (REQ-LST-COOKIE-004).
- `playwright-stealth` injection mirrors Indeed (obs #83, `indeed/scraper.py:69` + `:246-247`) and InfoJobs (`infojobs/scraper.py:73` + `:326-327`) byte-identically: same import, same `if self._stealth is not None:` gate, same `apply_stealth_async(ctx)` call site. Code review parity is the goal.
- `is_cloudflare_challenge(soup)` mirrors `is_auth_wall(soup)` (obs #356 §2.6) — pure function, no I/O, "cards win" rule. Distinct from `is_block_page` (hard raise) and `is_auth_wall` (soft WARNING) by semantic intent.
- `Settings` 3 new fields + 1 shared validator mirror the v1 `linkedin_li_at` + `_normalize_empty_li_at` + `_reject_short_li_at` (obs #356 §2.4). The v1 field is UNCHANGED; the 4 cookies share `MIN_LI_AT_LENGTH = 8` (already pinned at `config.py:58`).
- Composition root wire mirrors the v1 T-005 (obs #357) — the only site that knows about `Settings`.

**Layer discipline** (`presentation → application → domain ← infrastructure`, per AGENTS.md): application grows a NEW `LinkedInAuthCookiesPort` Protocol; infrastructure grows a NEW `MultiEnvLinkedInAuthCookiesAdapter` + a new pure `is_cloudflare_challenge` parser; composition root wires both. The 4 `Settings` fields stay in the existing `config.py` block (adjacent to v1 `linkedin_li_at`).

## 2. Components

### 2.1 `LinkedInAuthCookiesPort` Protocol (NEW, ADDITIVE to v1)

**File**: `backend/src/jobs_finder/application/ports.py` (EXTEND — add the new Protocol after the v1 `LinkedInAuthCookiePort` at L665)

**Shape** (5-line sketch):
```python
class LinkedInAuthCookiesPort(Protocol):
    """Returns the operator's LinkedIn session cookies (masked), or None.

    Multi-cookie shape (REQ-LST-COOKIE-001): the operator's
    LinkedIn session uses 4 cookies (li_at + JSESSIONID + bcookie
    + li_gc) per explore obs #365 §3.2 + obs #364. The Protocol
    returns a `list[(name, value)]` or `None` for the soft-mode
    sentinel (the v1 anonymous scraper path). Mirrors the v1
    `LinkedInAuthCookiePort` (singular) — both Protocols coexist;
    the v1 singular is kept for backward compat with the 35 v1
    tests that construct `EnvLinkedInAuthCookieAdapter` directly.
    """
    def cookies(self) -> list[tuple[str, SecretStr]] | None: ...
```

**Rationale**:
- `Protocol` (structural typing — matches `JobSearchPort`, `LocationResolverPort`, `LinkedInAuthCookiePort` v1)
- `list[tuple[str, SecretStr]] | None` (Q1: NOT a dict, NOT a value object — the bare shape is the cleanest contract; the per-cookie metadata — domain/path/httpOnly/secure — is the Playwright API's job, NOT the application's)
- NOT `@runtime_checkable` (mirrors v1)
- ADDITIVE to v1: both Protocols live in the same file; the v1 singular is kept byte-identical. The new `cookies()` method is the canonical multi-cookie contract; the v1 `cookie()` method stays for the 35 v1 tests.
- `mypy --strict` MUST validate that `MultiEnvLinkedInAuthCookiesAdapter` and `FakeLinkedInAuthCookiesPort` (the new conftest companion) both structurally conform.

### 2.2 `MultiEnvLinkedInAuthCookiesAdapter` (NEW)

**File**: `backend/src/jobs_finder/infrastructure/linkedin/auth_cookie.py` (EXTEND — add the new class below the v1 `EnvLinkedInAuthCookieAdapter` at L73)

**Shape** (12-line sketch):
```python
class MultiEnvLinkedInAuthCookiesAdapter:
    """Reads 4 LinkedIn cookies from `Settings.linkedin_*` (no I/O at runtime).

    Per Q1 (obs #365 §6, auto-resolved): the multi-cookie shape is
    a `list[tuple[str, SecretStr]]` returned by `cookies()`. The 4
    cookies are independently optional; `cookies()` returns `None`
    ONLY when ALL 4 are `None` (the v1 anonymous sentinel). When
    ≥1 is non-None, the list is filtered to the non-None entries
    in the deterministic order `li_at → JSESSIONID → bcookie → li_gc`
    (the canonical LinkedIn-session order, pinned by REQ-LST-COOKIE-004).
    """
    __slots__ = ("_li_at", "_jsessionid", "_bcookie", "_li_gc")
    _COOKIE_NAMES = ("li_at", "JSESSIONID", "bcookie", "li_gc")
    def __init__(
        self,
        li_at: SecretStr | None,
        jsessionid: SecretStr | None,
        bcookie: SecretStr | None,
        li_gc: SecretStr | None,
    ) -> None:
        self._li_at = li_at
        self._jsessionid = jsessionid
        self._bcookie = bcookie
        self._li_gc = li_gc
    def cookies(self) -> list[tuple[str, SecretStr]] | None:
        pairs: list[tuple[str, SecretStr]] = []
        for name, value in zip(self._COOKIE_NAMES,
                               (self._li_at, self._jsessionid, self._bcookie, self._li_gc),
                               strict=True):
            if value is not None:
                pairs.append((name, value))
        return pairs if pairs else None
    def __repr__(self) -> str:
        # Count-only mask (REQ-LST-COOKIE-005): acceptable 1-bit side-channel.
        count = sum(v is not None for v in (self._li_at, self._jsessionid, self._bcookie, self._li_gc))
        return f"MultiEnvLinkedInAuthCookiesAdapter(<{'set: ' + str(count) + ' cookies' if count else 'unset'}>)"
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MultiEnvLinkedInAuthCookiesAdapter):
            return NotImplemented
        return (self._li_at == other._li_at and self._jsessionid == other._jsessionid
                and self._bcookie == other._bcookie and self._li_gc == other._li_gc)
    def __hash__(self) -> int:
        return hash((self._li_at, self._jsessionid, self._bcookie, self._li_gc))
```

**Rationale**:
- `__slots__` matches the v1 `EnvLinkedInAuthCookieAdapter` style (memory + immutability-at-type-level)
- **Deterministic order** `li_at → JSESSIONID → bcookie → li_gc` is enforced by the `_COOKIE_NAMES` tuple + `zip` (REQ-LST-COOKIE-004 — the test pins the exact order)
- **Returns `None` when all 4 are `None`** (REQ-LST-COOKIE-003 — soft mode preserved; the v1 anonymous sentinel)
- **Filters `None` entries** when ≥1 is non-None (REQ-LST-COOKIE-003 acceptance bullet 3: the list is 1-/3-/4-element, NOT a 4-tuple with `None`s)
- **No `logging` import** (REQ-LST-COOKIE-002 — defense in depth; no log records)
- `__repr__` shows the count only, never the value (REQ-LST-COOKIE-005 — acceptable 1-bit side-channel per obs #365 risk #7)
- `__eq__` + `__hash__` cover all 4 fields (mirrors the v1 `EnvLinkedInAuthCookieAdapter` pattern at L62-73)

**Cookie name note** (REQ-LST-COOKIE-004 acceptance bullet): the v1 `EnvLinkedInAuthCookieAdapter.cookie()` (singular) returns the raw `SecretStr`; the new `cookies()` (plural) uses the canonical names `"li_at"`, `"JSESSIONID"`, `"bcookie"`, `"li_gc"`. These are the names LinkedIn sets in the browser cookie store. The capitalized `"JSESSIONID"` is the Java EE convention (LinkedIn's Tomcat-based backend uses uppercase); `"bcookie"` is lowercase per LinkedIn's actual issuance; `"li_gc"` is lowercase per LinkedIn's GC support cookie.

### 2.3 `FakeLinkedInAuthCookiesPort` conftest companion (NEW, ADDITIVE to v1)

**File**: `backend/tests/conftest.py` (EXTEND — add the new fake below the v1 `FakeLinkedInAuthCookiePort` at L76)

**Shape** (10-line sketch):
```python
class FakeLinkedInAuthCookiesPort:
    """In-memory fake of `LinkedInAuthCookiesPort` for tests (T-001 of `backend-linkedin-stealth`).

    Mirrors the `MultiEnvLinkedInAuthCookiesAdapter` shape: a
    value-holder with a single `cookies()` method that returns the
    configured `list[tuple[str, SecretStr]] | None`. Default is
    `None` (the v1 anonymous-scraper path). Cite REQ-LST-COOKIE-001.
    """
    __slots__ = ("_cookies",)
    def __init__(self, cookies: list[tuple[str, SecretStr]] | None = None) -> None:
        self._cookies = cookies
    def cookies(self) -> list[tuple[str, SecretStr]] | None:
        return self._cookies
```

**Rationale**:
- ADDITIVE to the v1 `FakeLinkedInAuthCookiePort` at L53-76 (NOT a replacement)
- `__slots__` matches the v1 fake style
- A test that wants to drive the multi-cookie path constructs one with `cookies=[("li_at", SecretStr("AQE...")), ("JSESSIONID", SecretStr("ajax:12345"))]`; a test that wants the anonymous path uses the default `None`; a test that wants the v1 single-cookie path uses the v1 `FakeLinkedInAuthCookiePort` directly.
- The v1 35 tests stay GREEN (they use the v1 fake, which is unchanged).

### 2.4 `is_cloudflare_challenge(soup)` pure function (NEW)

**File**: `backend/src/jobs_finder/infrastructure/linkedin/parsers.py` (EXTEND — add the new function after the v1 `is_auth_wall` at L270)

**Shape** (10-line sketch):
```python
def is_cloudflare_challenge(soup: BeautifulSoup) -> bool:
    """Return True ONLY when the SERP is a Cloudflare 2026 challenge page.

    Distinct from `is_block_page` (the 502 hard path — the v1
    anonymous LinkedIn-auth-wall detector) and `is_auth_wall`
    (the v1 soft WARNING path — the cookie-injected LinkedIn
    auth-wall detector). `is_cloudflare_challenge` is the
    NETWORK-layer 302-loop detector: the 3-OR selector set
    matches Cloudflare's 2026 challenge page signature.

    The "cards win" rule (REQ-LST-CF-003): when ≥1
    `div[data-entity-urn]` is present, the function returns
    `False` regardless of the Cloudflare markers (mirrors the v1
    `is_auth_wall` false-positive suppression). Pure: no I/O, no
    `await`, no logging side-effects. Spec: REQ-LST-CF-001..003.
    """
    # Cards win — false-positive suppression (REQ-LST-CF-003).
    if soup.select("div[data-entity-urn]"):
        return False
    # 3-OR Cloudflare 2026 challenge signature (REQ-LST-CF-002).
    has_title = soup.find(string=lambda t: t and "Just a moment" in t) is not None
    has_noscript = soup.find("noscript") is not None
    has_cf_marker = soup.select_one("div.cf-mitigated, [data-cf-challenge]") is not None
    return has_title and has_noscript and has_cf_marker
```

**Rationale**:
- **Pure** (no I/O, no `await`, no module-level mutable state, no logging side-effects — REQ-LST-CF-001 acceptance bullet 4)
- **3-OR signature** to match Cloudflare's 2026 challenge page (the title `<title>Just a moment...</title>` AND a `<noscript>` redirect block AND a `cf-mitigated` / `[data-cf-challenge]` marker). A single selector would be too brittle; 3-OR catches Cloudflare's minor markup rotations.
- **Cards win** (REQ-LST-CF-003): when ≥1 `div[data-entity-urn]` is present, return `False`. A healthy SERP with cards never matches. False positive impossible by construction (matches the v1 `is_auth_wall` false-positive suppression at parsers.py:266-270).
- **3 negative test cases pin the false-positive suppression** (REQ-LST-CF-003): (1) healthy SERP, (2) `BLOCK_PAGE_HTML` (the v1 LinkedIn auth wall — a different anti-bot signal), (3) cards-win (the `body` has a Cloudflare title + 1 card → `False`).
- The new `CLOUDFLARE_CHALLENGE_HTML` fixture (added to `tests/fixtures/linkedin_search.py` alongside the v1 `BLOCK_PAGE_HTML` at L81-97) contains the 3 markers and 0 cards.

### 2.5 `LinkedInPlaywrightScraper` ctor + `search()` — stealth injection (EXTENDED)

**File**: `backend/src/jobs_finder/infrastructure/linkedin/scraper.py` (EXTEND — 2 changes to ctor at L213-225 and to `search()` at L242-356)

**Change A**: ctor gains a new `stealth: Stealth | None = None` keyword-only kwarg + the `_stealth` slot:

```python
from playwright_stealth import Stealth  # type: ignore[import-untyped]   # NEW (mirrors indeed:69, infojobs:73)

class LinkedInPlaywrightScraper(JobSearchPort):
    def __init__(
        self, *, throttle, settings,
        browser_factory=None,
        stealth: Stealth | None = None,                              # NEW kwarg
    ) -> None:
        # ... existing assignments ...
        self._stealth: Stealth | None = stealth                       # NEW slot
```

**Change B**: `search()` calls `apply_stealth_async(ctx)` AFTER `new_context()` and BEFORE `add_cookies()` + `paginated_search()`. The `add_cookies` call is generalized from 1 cookie to N cookies (the v1 list construction is replaced with a list comprehension over `port.cookies()`):

```python
ctx = await self._browser.new_context(user_agent=self._settings.user_agent, viewport=VIEWPORT)
# T-001 of `backend-linkedin-stealth` — REQ-LST-SCR-001 plumb.
# Apply `playwright-stealth` at the BrowserContext level (mirrors
# Indeed at indeed/scraper.py:246-247 + InfoJobs at infojobs/scraper.py:326-327).
# MUST be AFTER `new_context` + BEFORE `add_cookies` + `new_page`
# (per `playwright_stealth` docs: "Apply Stealth to Playwright
# Contexts"). Gated on `self._stealth is not None` so unit tests
# with `stealth=None` (the default) skip the call entirely.
if self._stealth is not None:
    await self._stealth.apply_stealth_async(ctx)
# T-001 of `backend-linkedin-stealth` — REQ-LST-SCR-002 plumb.
# Inject the operator's N cookies ONCE per `search()` (per-context,
# not per-page). The v1 single-cookie injection is REPLACED by a
# list comprehension over `port.cookies()`. When the port returns
# `None` (the v1 anonymous sentinel), the call is skipped — the
# scraper proceeds with the v1 anonymous behavior.
auth_cookies_port = self._settings.auth_cookies   # NEW slot — see Change C
if auth_cookies_port is not None:
    cookies = auth_cookies_port.cookies()
    if cookies is not None:
        await ctx.add_cookies([
            {
                "name": name,
                "value": value.get_secret_value(),   # unwrap at Playwright API boundary ONLY
                "domain": ".linkedin.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
            }
            for (name, value) in cookies
        ])
        _logger.debug(
            "LinkedIn auth cookies injected (count=%d)",
            len(cookies),
        )
try:
    page = await ctx.new_page()
    try:
        return await paginated_search(...)
    finally:
        await page.close()
finally:
    await ctx.close()
```

**Change C**: `LinkedInScraperSettings` gains a new `auth_cookies` (plural) slot, alongside the v1 `auth_cookie` (singular) slot which is KEPT for backward compat:

```python
class LinkedInScraperSettings:
    __slots__ = (
        "auth_cookie",        # KEPT (v1, single — 35 v1 tests use it)
        "auth_cookies",       # NEW (v2, multi — new change)
        "inter_page_delay_seconds",
        "location_resolver",
        "max_pages",
        "timeout_ms",
        "user_agent",
    )
    def __init__(self, *, user_agent, timeout_ms, max_pages=10,
                 inter_page_delay_seconds=1.0, location_resolver=None,
                 auth_cookie: LinkedInAuthCookiePort | None = None,    # KEPT (v1)
                 auth_cookies: LinkedInAuthCookiesPort | None = None,  # NEW
                 stealth: Stealth | None = None,                       # NEW (see Change D)
                 ) -> None:
        # ... existing assignments ...
        self.auth_cookie = auth_cookie            # v1
        self.auth_cookies = auth_cookies          # NEW
        self.stealth = stealth                    # NEW
    def __repr__(self) -> str:
        auth_cookie_repr = "<set>" if self.auth_cookie is not None else "<unset>"
        auth_cookies_repr = "<set>" if self.auth_cookies is not None else "<unset>"
        stealth_repr = "<set>" if self.stealth is not None else "<unset>"
        return (
            f"LinkedInScraperSettings(user_agent={self.user_agent!r}, "
            f"timeout_ms={self.timeout_ms}, max_pages={self.max_pages}, "
            f"inter_page_delay_seconds={self.inter_page_delay_seconds}, "
            f"location_resolver={self.location_resolver!r}, "
            f"auth_cookie={auth_cookie_repr}, "                # v1 mask
            f"auth_cookies={auth_cookies_repr}, "              # NEW mask
            f"stealth={stealth_repr})"                        # NEW mask
        )
```

**Change D**: `LinkedInPlaywrightScraper.__init__` reads `stealth` from settings (NOT from the ctor kwarg directly — same pattern as `auth_cookie` for testability):

```python
def __init__(self, *, throttle, settings, browser_factory=None) -> None:
    self._throttle = throttle
    self._settings = settings
    self._browser_factory = browser_factory
    self._owns_browser = browser_factory is None
    self._browser = None
    self._playwright = None
    self._stealth: Stealth | None = settings.stealth     # NEW — read from settings
```

**Rationale**:
- **Single stealth injection site** between `new_context()` and `add_cookies` + `paginated_search()` (REQ-LST-SCR-001 — mirrors Indeed + InfoJobs byte-identically)
- **Stealth at the BrowserContext level** (NOT the Page level) — context-level survives navigations within the loop; page-level would need re-add on every `goto`
- **N cookies via list comprehension** (REQ-LST-SCR-002 — the v1 list construction generalizes cleanly to N)
- **Per-cookie shape is byte-identical to v1** (the LinkedIn-shape Playwright dict — `domain=".linkedin.com"`, `path="/"`, `httpOnly=True`, `secure=True` — is the canonical LinkedIn issuance contract)
- **`stealth` lives on the settings** (mirrors the v1 `auth_cookie` — settings is the testability seam; a test constructs `LinkedInScraperSettings(..., stealth=Mock())` and the scraper reads it)
- **DEBUG line uses `count` only** (mirrors the v1 `length=%d` line at L335-338 — no value leak)
- **v1 `auth_cookie` slot + ctor kwarg are KEPT** (REQ-LST-COOKIE-001 — backward compat with the 35 v1 tests)
- **v1 `is_block_page` raise path is preserved** (the v1 `test_search_raises_blocked_on_auth_wall` test is the regression check)

### 2.6 `_make_fetch_one_page` closure precedence (EXTENDED)

**File**: `backend/src/jobs_finder/infrastructure/linkedin/scraper.py` (EXTEND — change at L426-435)

**Change** (the v1 conditional precedence flip is the basis; the new `is_cloudflare_challenge` is added as the FIRST check in the cookie path):

```python
# v1 closure (L426-435 in the v1 design):
if self._settings.auth_cookie is not None and is_auth_wall(soup):
    _logger.warning("LinkedIn SERP appears auth-walled despite cookie ...")
    return _parse_cards(soup, remaining)
if is_block_page(soup):
    raise LinkedInBlockedError("LinkedIn returned an auth-wall / verification page")
return _parse_cards(soup, remaining)

# NEW closure (extends v1 with the is_cloudflare_challenge soft path):
# Cookie-injection path (v1 + new): is_cloudflare_challenge → is_auth_wall → is_block_page.
# Anonymous path (v1 byte-identical): is_block_page only (hard-raise).
auth_cookies = self._settings.auth_cookies
if auth_cookies is not None and auth_cookies.cookies() is not None:
    if is_cloudflare_challenge(soup):                              # NEW (soft, softest)
        _logger.warning(
            "LinkedIn Cloudflare challenge detected; stealth may be insufficient. "
            "Consider setting LINKEDIN_JSESSIONID, LINKEDIN_BCOOKIE, LINKEDIN_LI_GC in .env, "
            "or upgrading to a residential proxy."
        )
        return _parse_cards(soup, remaining)                       # soft path: returns [] (0 cards)
    if is_auth_wall(soup):                                          # v1 (soft)
        _logger.warning("LinkedIn SERP appears auth-walled despite cookie injection; ...")
        return _parse_cards(soup, remaining)
    if is_block_page(soup):                                         # v1 (hard — survives only if both soft filters miss)
        raise LinkedInBlockedError("LinkedIn returned an auth-wall / verification page")
    return _parse_cards(soup, remaining)
# Anonymous path — v1 byte-identical (the 35 v1 tests + the v1 test_search_raises_blocked_on_auth_wall).
if is_block_page(soup):
    raise LinkedInBlockedError("LinkedIn returned an auth-wall / verification page")
return _parse_cards(soup, remaining)
```

**Rationale**:
- **Precedence on the cookie path**: `is_cloudflare_challenge` → `is_auth_wall` → `is_block_page` (newest first; the softest filter wins)
- **Anonymous path is byte-identical to v1** (the v1 `if is_block_page(soup): raise` path is preserved)
- **No short-circuit on the soft path** — the closure continues to `_parse_cards` (so when the Cloudflare challenge is on a page WITH cards, the soft path returns the cards; when it's on a page WITHOUT cards, the soft path returns `[]`)
- **The conditional gate** is `auth_cookies is not None AND auth_cookies.cookies() is not None` (covers BOTH the v1 `MultiEnv...` port returning `None` for the all-4-`None` case AND the v1 `auth_cookies` being unset on the settings)
- **The v1 anonymous path** is also reachable through the v1 `auth_cookie is None` path (when the operator uses the v1 single-cookie `EnvLinkedInAuthCookieAdapter` AND didn't wire the new port) — both gates lead to the same byte-identical v1 hard-raise

### 2.7 `Settings` 3 new fields + 1 shared validator (EXTENDED)

**File**: `backend/src/jobs_finder/infrastructure/config.py` (EXTEND — 3 new fields + 1 shared validator helper after the v1 `linkedin_li_at` block at L317-362)

**Shape** (35-line sketch, after the v1 block):
```python
# T-002 of `backend-linkedin-stealth` — REQ-LST-CFG-001..003.
# 3 new optional LinkedIn cookies, each `SecretStr | None` with
# the v1 validator pattern (HARD on `len < MIN_LI_AT_LENGTH` when
# present, soft `None` allowed). Each field uses
# `validation_alias=AliasChoices(<UPPER>, <lower>)` to match the
# per-source `AliasChoices` precedent (`config.py:175-201` for
# Indeed/InfoJobs; the v1 `linkedin_li_at` at L317-320). The 3
# new fields are ADDITIVE — the v1 `linkedin_li_at` field is
# UNCHANGED.
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

# Shared validators (REQ-LST-CFG-002 — the v1 inline validators are
# refactored into reusable helpers so the 3 new fields + the v1
# field all share the same threshold + same error message format).
# The empty-normalization helper applies to all 4 fields; the
# length-rejection helper applies to all 4 fields.

def _normalize_empty_linkedin_optional_secret(
    cls, v: SecretStr | str | None,
) -> SecretStr | None:
    """Mode='before' validator: normalize `None` / `''` / `SecretStr('')` to `None`.

    Mirrors the v1 `_normalize_empty_li_at` at L322-343 (and the
    `_normalize_empty_secret` at L734-743 for `llm_api_key`).
    """
    if v is None:
        return None
    if isinstance(v, SecretStr):
        return v if v.get_secret_value() else None
    if isinstance(v, str):
        return SecretStr(v) if v else None
    return v

def _reject_short_linkedin_optional_cookie(
    cls, v: SecretStr | None, *, field_name: str,
) -> SecretStr | None:
    """Mode='after' validator: HARD on `len < MIN_LI_AT_LENGTH`, SOFT `None` allowed.

    Shared across the 4 LinkedIn cookie fields (`li_at` +
    `jsessionid` + `bcookie` + `li_gc`). The error message
    includes the field name so the operator can self-diagnose
    which env var is wrong.
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

# Apply the 2 shared validators to all 4 fields (3 new + 1 v1).
# The v1 `_normalize_empty_li_at` + `_reject_short_li_at` at
# L322-362 are REFACTORED to delegate to the new helpers
# (no behavior change for the v1 field).
_normalize_linkedin_li_at = field_validator("linkedin_li_at", mode="before")(_normalize_empty_linkedin_optional_secret)
_normalize_linkedin_jsessionid = field_validator("linkedin_jsessionid", mode="before")(_normalize_empty_linkedin_optional_secret)
_normalize_linkedin_bcookie = field_validator("linkedin_bcookie", mode="before")(_normalize_empty_linkedin_optional_secret)
_normalize_linkedin_li_gc = field_validator("linkedin_li_gc", mode="before")(_normalize_empty_linkedin_optional_secret)
# (a factory wraps `_reject_short_linkedin_optional_cookie` to inject the field name)
```

**Rationale**:
- **3 new fields are ADDITIVE** (REQ-LST-CFG-001 — the v1 `linkedin_li_at` field is byte-identical; the 35 v1 tests stay GREEN)
- **`AliasChoices` per field** matches the Indeed+InfoJobs precedent (per-field `validation_alias` survives a future `env_prefix` rename)
- **2 shared validators** (REQ-LST-CFG-002 — NOT 4 individual validators; 1 helper + 4 bindings = 7 lines vs. 4×2 = 8 lines, less code, same contract). The v1 inline validators are refactored to delegate to the helpers (no behavior change for the v1 field).
- **Error message includes the field name** so the operator can self-diagnose (e.g. `"LINKEDIN_JSESSIONID must be at least 8 characters (got 3); check for typos..."`)
- **`__repr__` masking is automatic** via `SecretStr` (REQ-LST-CFG-003 — defense-in-depth; the v1 `test_settings_repr_does_not_leak_cookie_value` pattern extends to 3 new assertions, one per new field)

### 2.8 Composition root wiring (EXTENDED)

**File**: `backend/src/jobs_finder/presentation/app_factory.py` (EXTEND — replace the v1 single-cookie wire at L260-294 with the multi-cookie wire + stealth wire)

**Shape** (15-line sketch, replacing the v1 block at L260-294):
```python
# T-005 of `backend-linkedin-stealth` — REQ-LST-COOKIE-001 plumb.
# The v1 single-cookie `EnvLinkedInAuthCookieAdapter` wire is
# REPLACED with the new `MultiEnvLinkedInAuthCookiesAdapter`
# (4 fields). The v1 startup WARNING at L260-264 is KEPT
# (the operator who has set ZERO of the 4 cookies still gets
# the warning at process start).
if (
    effective_settings.linkedin_li_at is None
    and effective_settings.linkedin_jsessionid is None
    and effective_settings.linkedin_bcookie is None
    and effective_settings.linkedin_li_gc is None
):
    _logger.warning(
        "LinkedIn scraper running without any auth cookies; "
        "SERP will hit the Cloudflare / auth wall and return a reduced list. "
        "Set at least LINKEDIN_LI_AT (or all 4) in .env to bypass the wall."
    )

if use_case is None:
    # REQ-LST-COOKIE-001: the multi-cookie adapter is the
    # production wire. The v1 single-cookie `EnvLinkedInAuthCookieAdapter`
    # is kept in the import path (backward compat with the 35 v1
    # tests that construct it directly) but NOT used in the
    # production wire — the new adapter supersedes it.
    auth_cookies_port = MultiEnvLinkedInAuthCookiesAdapter(
        li_at=effective_settings.linkedin_li_at,
        jsessionid=effective_settings.linkedin_jsessionid,
        bcookie=effective_settings.linkedin_bcookie,
        li_gc=effective_settings.linkedin_li_gc,
    )
    # REQ-LST-SCR-001: the production wires `Stealth()` so the
    # live scraper evades Cloudflare's 2026 bot detection. Tests
    # pass `stealth=None` (the default) and inject `browser_factory`
    # so the stealth script never runs.
    from playwright_stealth import Stealth  # type: ignore[import-untyped]   # NEW (mirrors indeed:69, infojobs:73)
    scraper = LinkedInPlaywrightScraper(
        throttle=AsyncThrottle(min_interval_seconds=effective_settings.throttle_seconds),
        settings=LinkedInScraperSettings(
            user_agent=effective_settings.user_agent,
            timeout_ms=effective_settings.request_timeout_ms,
            max_pages=effective_settings.linkedin_max_pages,
            inter_page_delay_seconds=effective_settings.linkedin_inter_page_delay_seconds,
            location_resolver=location_resolver,
            # v1 backward compat — kept (the 35 v1 tests construct this directly)
            auth_cookie=None,
            # NEW — the multi-cookie port
            auth_cookies=auth_cookies_port,
            # NEW — the Stealth instance
            stealth=Stealth(),
        ),
    )
    # ... existing `raw_use_case` + `linkedin_cache` + `use_case` UNCHANGED
```

**Rationale**:
- **Composition root is the only site that knows about `Settings`** (REQ-LST-COOKIE-001 — the scraper receives the port, NOT the env)
- **The v1 startup WARNING** is KEPT and EXTENDED: it now fires when ALL 4 cookies are `None` (not just `linkedin_li_at is None`). The WARNING message is updated to mention Cloudflare + the 4 cookie names.
- **`Stealth()` is constructed at the composition root** (mirrors Indeed at `app_factory.py:323-339` + InfoJobs below it — the live wire creates a fresh `Stealth()` per `build_app()`)
- **The v1 single-cookie `EnvLinkedInAuthCookieAdapter` is NOT used in the production wire** (it's superseded by the new adapter); but the v1 class is KEPT in the import path so the 35 v1 tests that construct it directly still work
- **The v1 `auth_cookie=None` is passed explicitly** (the new `LinkedInScraperSettings.__init__` has BOTH `auth_cookie` and `auth_cookies` slots; the production wire sets `auth_cookie=None` + `auth_cookies=auth_cookies_port`; v1 tests set `auth_cookie=...` + `auth_cookies=None`)

## 3. File-by-file delta

| File | Change | + | - | Reason |
|---|---|---|---|---|
| `backend/src/jobs_finder/application/ports.py` | EXTENDED | +12 | 0 | Add `LinkedInAuthCookiesPort` Protocol (plural) next to the v1 `LinkedInAuthCookiePort` (singular, kept). |
| `backend/src/jobs_finder/infrastructure/linkedin/auth_cookie.py` | EXTENDED | +45 | 0 | Add `MultiEnvLinkedInAuthCookiesAdapter` (4-field ctor + `cookies()` + `__eq__` + `__hash__` + `__repr__` mask). v1 `EnvLinkedInAuthCookieAdapter` kept UNCHANGED. |
| `backend/src/jobs_finder/infrastructure/linkedin/parsers.py` | EXTENDED | +18 | 0 | Add `is_cloudflare_challenge(soup)` pure function (3-OR signature + cards-win rule). |
| `backend/src/jobs_finder/infrastructure/linkedin/scraper.py` | EXTENDED | +30 | -2 | (1) ctor `stealth: Stealth | None = None` kwarg + `_stealth` slot; (2) `search()` stealth injection at BrowserContext level (3 lines); (3) `search()` multi-cookie `add_cookies` (list comprehension, replaces v1 1-cookie literal); (4) `LinkedInScraperSettings` `auth_cookies` + `stealth` slots + repr/eq/hash; (5) closure `is_cloudflare_challenge` integration BEFORE `is_auth_wall` in the cookie path. |
| `backend/src/jobs_finder/infrastructure/config.py` | EXTENDED | +50 | -10 | (1) 3 new `linkedin_{jsessionid,bcookie,li_gc}` fields with `AliasChoices`; (2) refactor v1 inline validators to delegate to 2 new shared helpers (`_normalize_empty_linkedin_optional_secret` + `_reject_short_linkedin_optional_cookie`); (3) bind 4 fields to the 2 shared validators. |
| `backend/src/jobs_finder/presentation/app_factory.py` | EXTENDED | +15 | -3 | Replace v1 single-cookie `EnvLinkedInAuthCookieAdapter` wire with new `MultiEnvLinkedInAuthCookiesAdapter` (4 fields) + `Stealth()` wire + extended startup WARNING (4-`None` check). |
| `backend/.env.example` | EXTENDED | +3 | 0 | 3 new placeholder lines (`LINKEDIN_JSESSIONID=`, `LINKEDIN_BCOOKIE=`, `LINKEDIN_LI_GC=`) + security note. |
| `backend/README.md` | EXTENDED | +30 | 0 | New "LinkedIn anti-bot stealth (multi-cookie + playwright-stealth)" subsection. |
| `backend/tests/fixtures/linkedin_search.py` | EXTENDED | +20 | 0 | New `CLOUDFLARE_CHALLENGE_HTML` fixture (3 Cloudflare 2026 markers + 0 cards). |
| `backend/tests/conftest.py` | EXTENDED | +15 | 0 | Add `FakeLinkedInAuthCookiesPort` companion (the v1 `FakeLinkedInAuthCookiePort` is kept UNCHANGED). |
| `backend/tests/unit/test_linkedin_stealth.py` | NEW | ~120 | 0 | `MultiEnvLinkedInAuthCookiesAdapter` tests (10 scenarios) + `playwright-stealth` injection mock test (2 scenarios) + 4 closure precedence scenarios. |
| `backend/tests/unit/test_linkedin_cloudflare_challenge.py` | NEW | ~60 | 0 | `is_cloudflare_challenge` tests (5 scenarios: 1 positive + 4 negative on different fixtures). |
| `backend/tests/unit/test_linkedin_auth_cookie.py` | EXTENDED | +15 | 0 | Add 3 scenarios for the v1 `EnvLinkedInAuthCookieAdapter` backward-compat verification (REQs COVERED: REQ-LST-COOKIE-001 backward compat). |
| `backend/tests/unit/test_linkedin_scraper.py` | EXTENDED | +30 | 0 | Add `test_stealth_is_applied_when_provided` + `test_stealth_is_not_applied_when_none` (Indeed mirror) + `test_add_cookies_called_with_all_non_none_cookies` (golden) + `test_closure_warns_on_cloudflare_challenge_cookie_path` (caplog). |
| `backend/tests/unit/test_linkedin_config.py` | EXTENDED | +20 | 0 | Add 3 new field validator tests (HARD <8, soft None, repr mask) + 1 shared-validator test. |
| `backend/tests/integration/test_linkedin_stealth.py` | NEW | ~60 | 0 | End-to-end offline via `build_app(use_case=...)` with the new `MultiEnvLinkedInAuthCookiesAdapter` + caplog assertion. |
| **TOTAL** | | **~533** | **~15** | **~518 net** |

## 4. Test plan (Strict TDD — every scenario is a real test)

| Spec REQ | Test file | Test function |
|---|---|---|
| REQ-LST-CF-001 | `tests/unit/test_linkedin_cloudflare_challenge.py` | `test_is_cloudflare_challenge_signature` + `test_is_cloudflare_challenge_is_pure_no_mutation` |
| REQ-LST-CF-002 | `tests/unit/test_linkedin_cloudflare_challenge.py` | `test_is_cloudflare_challenge_true_for_challenge_fixture` |
| REQ-LST-CF-003 | `tests/unit/test_linkedin_cloudflare_challenge.py` | `test_is_cloudflare_challenge_false_for_healthy_serp` + `test_is_cloudflare_challenge_false_for_linkedin_block_page` + `test_is_cloudflare_challenge_false_when_cards_present_even_with_challenge_marker` |
| REQ-LST-COOKIE-001 | `tests/unit/test_linkedin_stealth.py` | `test_protocol_structural_conformance` (multi-cookie port) + `test_v1_single_cookie_adapter_still_works` (backward compat for the 35 v1 tests) |
| REQ-LST-COOKIE-002 | `tests/unit/test_linkedin_stealth.py` | `test_adapter_accepts_4_independently_optional_params` + `test_adapter_accepts_all_none_constructor` |
| REQ-LST-COOKIE-003 | `tests/unit/test_linkedin_stealth.py` | `test_cookies_returns_none_when_all_4_none` + `test_cookies_returns_filtered_list_when_partial` + `test_cookies_filters_none_entries` |
| REQ-LST-COOKIE-004 | `tests/unit/test_linkedin_stealth.py` | `test_cookies_returns_deterministic_order` (golden: 4-tuple `li_at`/`JSESSIONID`/`bcookie`/`li_gc`) + `test_v1_single_cookie_adapter_still_works` |
| REQ-LST-COOKIE-005 | `tests/unit/test_linkedin_stealth.py` | `test_adapter_repr_does_not_leak_li_at_value` + `test_adapter_repr_does_not_leak_jsessionid_value` |
| REQ-LST-SCR-001 | `tests/unit/test_linkedin_scraper.py` | `test_stealth_is_applied_when_provided` (mirrors Indeed `TestStealthIntegration`; mock `apply_stealth_async`) + `test_stealth_is_not_applied_when_none` |
| REQ-LST-SCR-002 | `tests/unit/test_linkedin_scraper.py` | `test_add_cookies_called_with_all_non_none_cookies` (golden assertion: 2-cookie list with full LinkedIn shape) + `test_no_add_cookies_call_when_all_cookies_none` |
| REQ-LST-SCR-003 | `tests/unit/test_linkedin_scraper.py` | `test_closure_warns_on_cloudflare_challenge_cookie_path` + `test_closure_warns_on_auth_wall_after_cloudflare_false` + `test_anonymous_path_preserves_v1_hard_raise` (regression for the 35 v1 tests) |
| REQ-LST-SCR-004 | `tests/unit/test_linkedin_scraper.py` | `test_closure_warns_on_cloudflare_challenge_with_actionable_message` (caplog asserts WARNING contains `"LinkedIn Cloudflare challenge detected"` + `"LINKEDIN_JSESSIONID"` + `"LINKEDIN_BCOOKIE"` + `"LINKEDIN_LI_GC"`) + `test_closure_does_not_warn_when_cards_present_even_with_cloudflare_marker` |
| REQ-LST-CFG-001 | `tests/unit/test_linkedin_config.py` | `test_settings_reads_linkedin_jsessionid_from_env` + `test_settings_linkedin_jsessionid_defaults_to_none` + `test_settings_programmatic_construction_of_new_fields` |
| REQ-LST-CFG-002 | `tests/unit/test_linkedin_config.py` | `test_settings_rejects_short_jsessionid_with_field_name` (golden: error contains `"LINKEDIN_JSESSIONID"` + `"must be at least 8 characters"` + `"got 3"`) + `test_settings_rejects_short_bcookie_7_chars` (boundary) + `test_settings_accepts_minimum_length_8_for_li_gc` (8 chars, inclusive) + `test_settings_normalizes_empty_jsessionid_to_none` (defense-in-depth) + `test_shared_validator_applies_to_all_4_fields` (parametrized: 4 fields × 2 invalid inputs) |
| REQ-LST-CFG-003 | `tests/unit/test_linkedin_config.py` | `test_settings_repr_does_not_leak_jsessionid` + `test_settings_repr_does_not_leak_bcookie_or_li_gc` (2 assertions, 1 test) |

**Total**: +20 to +30 new test functions on top of the 1,254 v1 baseline. The v1 35 tests stay GREEN (backward compat verified by `test_v1_single_cookie_adapter_still_works` + `test_anonymous_path_preserves_v1_hard_raise`).

## 5. Tradeoffs (explicit)

| # | Decision | Why |
|---|---|---|
| 1 | `list[tuple[str, SecretStr]]` (Q1) — NOT a dict, NOT a value object | Bare shape is the cleanest Protocol contract; the per-cookie Playwright metadata is the API's job, not the application's. Mirrors the v1 `EnvLinkedInAuthCookieAdapter`'s "shape translation is the adapter's job" principle (obs #356 §2.2 rationale). |
| 2 | Individual env vars (Q2) — NOT a JSON blob | Matches the per-source `AliasChoices` precedent (`config.py:175-201` Indeed/InfoJobs; v1 `linkedin_li_at` at L317). Operators `export` them independently. |
| 3 | BrowserContext level stealth (Q3) — NOT Page level | The Indeed + InfoJobs precedent (obs #79 §2; `indeed/scraper.py:247`, `infojobs/scraper.py:327`). Context-level survives navigations within the `paginated_search` loop. |
| 4 | Soft path for Cloudflare (Q4) — mirror `is_auth_wall` | Both anti-bot layers are "the site does not want to serve this request"; a soft path (WARNING + return `[]`) gives the frontend a degraded-but-not-500 response so it can render a meaningful UI rather than a generic 502. |
| 5 | New function `is_cloudflare_challenge` (Q5) — NOT extend `is_block_page` | 3 distinct semantics (Cloudflare 302-loop / LinkedIn auth wall with cookie / LinkedIn 502 hard block) → 3 distinct functions → 3 distinct integration points in the closure. Conflating Cloudflare with LinkedIn's auth wall would lose the operator-actionable signal (the WARNING message names the 3 missing cookies). |
| 6 | `MultiEnvLinkedInAuthCookiesAdapter` (NEW class) — NOT extending `EnvLinkedInAuthCookieAdapter` | Two ctors with different arity (1 vs 4) and different return types (`SecretStr | None` vs `list[tuple[str, SecretStr]] | None`); forcing one to inherit from the other would couple the backward-compat single-cookie ctor to the new multi-cookie semantics. A new class is the cleanest separation. |
| 7 | v1 `EnvLinkedInAuthCookieAdapter` kept UNCHANGED (backward compat) | 35 v1 tests construct it directly bypassing `Settings`; a breaking change would require rewriting all 35. The class is a 1-line dead wire in production (the new adapter supersedes it), but the test surface depends on the v1 class shape. |
| 8 | v1 `LinkedInAuthCookiePort` (singular) Protocol kept UNCHANGED | Mirrors the v1 adapter; the v1 tests that bind a v1 `FakeLinkedInAuthCookiePort` to `LinkedInScraperSettings.auth_cookie` keep working. The new `LinkedInAuthCookiesPort` is additive. |
| 9 | v1 `LinkedInScraperSettings.auth_cookie` slot kept UNCHANGED + new `auth_cookies` slot added | Both ports coexist; the production wire sets `auth_cookie=None` + `auth_cookies=adapter`; v1 tests set `auth_cookie=adapter` + `auth_cookies=None`. No class rename, no kwarg rename. |
| 10 | Closure precedence: `is_cloudflare_challenge` → `is_auth_wall` → `is_block_page` (cookie path) | Newest first, softest first. The Cloudflare 302-loop is a network-layer event (softer than the cookie-injected auth-wall); the LinkedIn 502 is the v1 hard-raise (survives only if both soft filters miss). Mirrors the v1 conditional precedence flip (obs #362 deviation + obs #358). |
| 11 | Anonymous path: `is_block_page` only — v1 byte-identical | The 35 v1 tests + the v1 `test_search_raises_blocked_on_auth_wall` are the regression check. No new code path on the anonymous side. |
| 12 | 2 shared validators (1 helper + 1 factory) for 4 fields | Less code (7 lines vs 8 for 4×2 inline), same contract. The v1 inline validators are REFACTORED to delegate to the new helpers (no behavior change for the v1 field). |
| 13 | Repr mask shows the count only, NOT the names | The 1-bit side-channel is acceptable (obs #365 risk #7). The operator's own `ls -la .env` is a richer side-channel. |
| 14 | `playwright-stealth` is the canonical anti-bot tool — no custom solution | Already a project dep (`pyproject.toml:25`); actively maintained (last release 2026-04-04); proven on Indeed (obs #83 — T-002's 1.28MB real capture succeeded with stealth from the sandbox IP). The 0.55 confidence is the open risk, documented in §6 + §7. |
| 15 | 4 cookies (`li_at` + `JSESSIONID` + `bcookie` + `li_gc`) — NOT 19+ | Minimum viable set per obs #364 (the operator's manual observation that LinkedIn treats this 4-cookie set as a "real session" signal). The Protocol accepts an arbitrary-length list; a future change can add more cookies without Protocol changes. |
| 16 | `__init__.py` files UNCHANGED | AGENTS.md rule #4. The new modules contain real code; the existing `infrastructure/linkedin/__init__.py` stays docstring-only. |
| 17 | No new exception type for the Cloudflare-challenge path | The scraper returns `[]` (REQ-LST-SCR-004) and emits a WARNING. A new exception would force the route to 502, defeating the "degraded but functional" semantic. |
| 18 | `Stealth` is constructed at the composition root (per `build_app()`), NOT lazily | Mirrors Indeed (`app_factory.py:336-339`); a fresh `Stealth()` per `build_app()` keeps the per-`Stealth` JS script state isolated across test runs. |
| 19 | `playwright_stealth` import lives in `scraper.py` AND `app_factory.py` (2 sites) | Mirrors the Indeed precedent (import at `scraper.py:69` + construction at `app_factory.py:336-339`). Same pattern for InfoJobs. |
| 20 | The v1 dev-cycle `MultiEnv...` ctor takes 4 positional/keyword args (not a dict) | The 4 fields are independently optional and named at the call site; the composition root passes them by keyword (`li_at=...`, `jsessionid=...`, `bcookie=...`, `li_gc=...`). A dict would obscure the named contract. |

## 6. Open design questions

**None — all 5 design-level questions from explore obs #365 §6 are auto-resolved by the orchestrator** (Q1=`list[tuple[str, SecretStr]]`, Q2=individual env vars matching the `AliasChoices` precedent, Q3=BrowserContext level, Q4=soft path mirrors `is_auth_wall`, Q5=new function `is_cloudflare_challenge` parallel to `is_auth_wall`). The 0.55 confidence on `playwright-stealth` is the only open risk, and the spec already documents the fallback path (`backend-linkedin-residential-proxy`).

The design adds 1 micro-decision not in the proposal: the v1 closure's conditional precedence flip is **kept byte-identical** in the anonymous branch, and the new `is_cloudflare_challenge` is added as the **first** check in the cookie branch (softer than `is_auth_wall` because the Cloudflare 302-loop is a network-layer event, not a soup-parseable page).

## 7. Risks (carry-forward from proposal §"Risks", with design-level mitigations)

| # | Risk | L | Mitigation (REQ) |
|---|------|---|---|
| 1 | **`playwright-stealth` may NOT bypass the LinkedIn + Cloudflare-2026-302-loop** (0.55 confidence per obs #365 §4.4) | **HIGH** | REQ-LST-SCR-001 (stealth is opt-in via ctor kwarg; `stealth=None` preserves v1), REQ-LST-SCR-004 (soft-path `is_cloudflare_challenge` WARNING surfaces the failure with an operator-actionable message: "Consider setting LINKEDIN_JSESSIONID, LINKEDIN_BCOOKIE, LINKEDIN_LI_GC..."), REQ-LST-CFG-001..003 (3 new cookies give the operator a fallback configuration path). The change is fully reversible. The CI suite does NOT depend on stealth working at runtime (all tests are offline with fixtures). |
| 2 | **Multi-cookie partial injection** (4 cookies vs operator's 19+) | **HIGH** | REQ-LST-COOKIE-002 (the Protocol accepts an arbitrary list; a future change can add more cookies without code changes), REQ-LST-SCR-004 (the WARNING message is operator-actionable: names the 3 missing cookies + the residential-proxy fallback). |
| 3 | **Cloudflare challenge page evolves** (2026 selectors → 2027) | **MED** | REQ-LST-CF-002 pins the 2026 selector set in the `CLOUDFLARE_CHALLENGE_HTML` fixture; a future change is 1 fixture + 1 detector function (the design pre-pins the 3 markers so future drift is contained). |
| 4 | **Backward compat with v1 single-cookie `EnvLinkedInAuthCookieAdapter(SecretStr)` ctor** (35 v1 tests) | **MED** | REQ-LST-COOKIE-001 (v1 singular Protocol is KEPT), REQ-LST-COOKIE-004 (v1 `EnvLinkedInAuthCookieAdapter` is KEPT UNCHANGED — its `cookie()` method is the v1 contract). The test `test_v1_single_cookie_adapter_still_works` + `test_anonymous_path_preserves_v1_hard_raise` are the regression checks. |
| 5 | **`playwright-stealth` Python port maintenance status** | **LOW** | Already pinned at `playwright-stealth>=2.0,<3.0` in `pyproject.toml:25`; 2.x API is stable. The fallback path (residential proxy) does NOT depend on `playwright-stealth`. |
| 6 | **Future LinkedIn-cookie-set growth** | **LOW** | REQ-LST-COOKIE-001 (Protocol accepts an arbitrary `list[tuple[str, SecretStr]]`). A future change adds 1 `Settings` field + 1 adapter line; the Protocol + scraper are unchanged. |
| 7 | **`__repr__` cookie-count side-channel** | **LOW** | REQ-LST-COOKIE-005 (acceptable 1-bit side-channel; the operator's `ls -la .env` is richer). |
| 8 | **3 new env vars leak via process listings** (`/proc/<pid>/environ`) | **LOW** | Same risk as `LINKEDIN_LI_AT`; mitigated by `direnv` (per v1 README). Not in scope. |
| 9 | **`is_cloudflare_challenge` fires a false positive on a healthy SERP** | **LOW** | REQ-LST-CF-003 (3 negative scenarios: healthy SERP, LinkedIn auth wall, cards-win). A healthy SERP with cards never matches. |
| 10 | **V1 lessons not applied** (e.g. `__init__.py` re-export hub, real cookie value) | **LOW** | AGENTS.md rule #4 (no `__init__.py` business logic); AGENTS.md rule #7 (only the synthetic 12-byte `"AQEAAAAQEAAA"` appears in test code). |
| 11 | **NEW — The v1 conditional precedence flip in the closure** (per obs #362 deviation) is intentionally preserved in the anonymous branch. The new `is_cloudflare_challenge` is added as the FIRST check in the cookie branch (softer than `is_auth_wall`); the anonymous branch stays `is_block_page` only. | **LOW** | The conditional gate `auth_cookies is not None AND auth_cookies.cookies() is not None` is the v1-vs-cookie discriminator; the v1 `test_search_raises_blocked_on_auth_wall` (anonymous path) is the canonical regression check. |
| 12 | **NEW — The v1 `LinkedInScraperSettings.__repr__` mask `<set>/<unset>`** extends to 3 new fields (`auth_cookies`, `stealth`). A future contributor who accidentally formats the repr with `f"auth_cookies={self.auth_cookies!r}"` (the unguarded `!r`) would leak the adapter's `__repr__` (the count only — no value leak). | **LOW** | The 3 new fields follow the same `<set>/<unset>` pattern as the v1 `auth_cookie`; the test `test_settings_repr_masks_*` pattern extends. |

## 8. Anti-patterns explicitly avoided

- **Does NOT log any cookie value at any level** — `__repr__` mask + DEBUG line uses `count=` only (REQ-LST-COOKIE-005 + REQ-LST-SCR-002).
- **Does NOT commit a real LinkedIn cookie to any fixture** — only the synthetic 12-byte `"AQEAAAAQEAAA"` (for `li_at`) + synthetic `"ajax:12345"` / `"v2_xyz"` / `"gc_abc"` (for the 3 new fields) appear in test code (AGENTS.md rule #7).
- **Does NOT add business logic to `__init__.py`** — `infrastructure/linkedin/__init__.py` stays docstring-only; import the new adapter from the module path (AGENTS.md rule #4).
- **Does NOT add a global `os.environ['LINKEDIN_*']` read in the scraper** — the scraper reads `self._settings.auth_cookies.cookies()` only (REQ-LST-SCR-001 + REQ-LST-SCR-002).
- **Does NOT modify `JobSearchPort`, `LocationResolverPort`, `JobSearchCacheKey`, `paginated_search`** — the multi-cookie port is a NEW independent Protocol; the cookie + stealth are per-context, applied before the loop; the helper stays source-agnostic with the 7-keyword-only-param signature.
- **Does NOT modify `is_block_page` or `is_auth_wall`** — the new `is_cloudflare_challenge` coexists; the 3 functions have distinct semantics (Cloudflare 302-loop / LinkedIn auth wall / LinkedIn 502).
- **Does NOT add a new exception type for the Cloudflare-challenge path** — the WARNING + empty-list return is the contract (REQ-LST-SCR-004).
- **Does NOT modify the other 2 scrapers (Indeed, InfoJobs)** — they already use stealth; no LinkedIn-specific work applies to them.
- **Does NOT modify the frontend HTTP contract** — `GET /jobs?q=...&location=...` is byte-identical; the multi-cookie + stealth are internal to the scraper.
- **Does NOT add a `LinkedInAuthCookie` value object** — the proposal's value object added no value at the Protocol boundary; the design uses a bare `list[tuple[str, SecretStr]]` and the adapter owns the Playwright-shape translation.
- **Does NOT modify the v1 `Settings.linkedin_li_at` field or its 2 validators** — the 4 cookie fields share the 2 new helpers (refactored from the v1 inline validators), but the v1 field's behavior is byte-identical.
- **Does NOT break the v1 single-cookie `EnvLinkedInAuthCookieAdapter` ctor** — kept UNCHANGED; the 35 v1 tests stay GREEN.
- **Does NOT change the v1 closure's anonymous path** — `is_block_page` only on the anonymous path; the v1 `test_search_raises_blocked_on_auth_wall` is the regression check.
- **Does NOT add a `playwright-stealth` import at the top of `scraper.py` without the `await stealth.apply_stealth_async(ctx)` call site also present** — the import and the call site ship in the same commit (REQ-LST-SCR-001).
- **Does NOT log the cookie COUNT in a way that reveals the specific cookies** — the `__repr__` shows the count only (acceptable 1-bit side-channel; the operator's own `ls -la .env` is richer).

## 9. Workload forecast (for `sdd-tasks`)

| Field | Value |
|-------|-------|
| Estimated changed lines | ~518 net (range 450–600, per §3 + TDD tax) |
| 400-line budget risk | **Low** (~104 LOC/commit avg, 5 commits) |
| Chained PRs recommended | **No** |
| Suggested split | single PR (5 conventional commits) |
| Delivery strategy | ask-on-risk → resolved as `single-pr` |
| Decision needed before apply | No (single PR approved at design) |
| Chain strategy | size-exception (single PR) |
| 400-line budget risk | Low |

**5 work units** (mirrors the v1 cycle's T-001..T-005 + T-006 pattern):

- **T-001** (stealth wiring + `LinkedInAuthCookiesPort` Protocol + `MultiEnvLinkedInAuthCookiesAdapter` + `FakeLinkedInAuthCookiesPort`): ~130 LOC, mirrors the Indeed T-001 + the v1 T-001.
- **T-002** (3 new `Settings.linkedin_*` fields + 2 shared validator helpers extracted from the v1 inline validators): ~95 LOC, mirrors the v1 T-002.
- **T-003** (`is_cloudflare_challenge(soup)` + `CLOUDFLARE_CHALLENGE_HTML` fixture): ~95 LOC, mirrors the v1 T-003 (`is_auth_wall` + `BLOCK_PAGE_HTML`).
- **T-004** (scraper changes: stealth injection + multi-cookie `add_cookies` + `LinkedInScraperSettings` `auth_cookies` + `stealth` slots + closure `is_cloudflare_challenge` integration with cookie-path-vs-anonymous-path conditional): ~130 LOC, mirrors the v1 T-004 (cookie injection + closure `is_auth_wall` integration).
- **T-005** (composition root wire + `app_factory` updates + integration test + `README.md` + `.env.example`): ~70 LOC, mirrors the v1 T-005.

**Total**: ~520 LOC across 5 commits (~104 LOC/commit avg). Well under the 400-line per-PR sub-budget and the 5,000-line hard review budget. Single PR is sufficient — no chained PRs needed.

The `sdd-tasks` phase MUST still emit the workload forecast and the orchestrator will check it before launching `sdd-apply`.

## 10. Next step

Ready for `sdd-tasks`. The orchestrator should:

1. Confirm the 5 auto-resolved decisions (Q1-Q5) are still locked-in — they are, per the launch prompt.
2. Verify the parallel `backend-linkedin-auth` cycle is archived at `6402798` — it is, per the apply-progress + verify-report.
3. Delegate to `sdd-tasks` with inputs: this design (saved to Engram), spec obs #367, proposal obs #366, exploration obs #365, trigger obs #364, the precedent cycle's archive (obs #362) + design (obs #356) + tasks (obs #357) + apply-progress (obs #358) + verify-report (obs #360).
4. Expect ~5 work units (T-001..T-005) for the implementation per the proposal's task list (adapted to the design's file-by-file delta in §3).

**Skill resolution**: `paths-injected` — orchestrator pre-resolved `sdd-design/SKILL.md` + `test-driven-development/SKILL.md` + `work-unit-commits/SKILL.md` + `_shared/sdd-phase-common.md` + `_shared/openspec-convention.md`.

## 11. Deviations from spec (none expected)

This design implements the spec (obs #367) exactly as written. The 15 REQ-LST-* scenarios all have a 1:1 test in §4. The 4 tradeoffs in §5 (Q1-Q5 + the multi-cookie class + the shared validator) were all anticipated in the spec. The v1 cycle's closure deviation (obs #362 §"Deviations from Design") is REPLICATED in the new design (cookie path precedence `is_cloudflare_challenge` → `is_auth_wall` → `is_block_page`; anonymous path `is_block_page` only) — the spec's REQ-LST-SCR-003 already documents this conditional precedence.

If a future apply phase discovers an additional deviation (e.g. the closure needs to emit a different WARNING message format), the deviation will be documented in the apply-progress + archived in the design's `## 11. Deviations from Design` section (mirroring the v1 archive convention per obs #362).
