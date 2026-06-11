# Spec: `backend-linkedin-stealth` — `playwright-stealth` + multi-cookie + Cloudflare detector (delta)

> **Status**: `spec` (ready for `sdd-design`)
> **Base**: `6402798` (post `backend-linkedin-auth` merge on `main`; working tree clean)
> **Proposal**: Engram obs #366
> **Exploration**: Engram obs #365
> **Trigger**: Engram obs #364 (live `ERR_TOO_MANY_REDIRECTS` with v1 cookie)
> **Precedent**: Engram obs #362 (`backend-linkedin-auth` archive), obs #83 (Indeed stealth)
> **Mode**: `both` (OpenSpec filesystem + Engram)
> **Strict TDD**: ACTIVE — every scenario is a real test, RED first
> **Confidence note** (per explore obs #365 §4.4): **0.55** that `playwright-stealth` bypasses the 2026 LinkedIn + Cloudflare `ERR_TOO_MANY_REDIRECTS` case. The change ships as a reversible first-intent mitigation with a documented fallback (`backend-linkedin-residential-proxy`, out of scope here).
> **REQ namespace**: `REQ-LST-*` (LinkedIn-S-Tealth) to keep this delta grep-clean from the v1 `REQ-LA-*` (LinkedIn-A-uth) and `REQ-LI-*` (LinkedIn-Info) namespaces. **No MODIFIED or REMOVED requirements** — all v1 `REQ-LA-*` and `REQ-LI-*` stay byte-identical. Archive sync will add 1 NEW global spec (`linkedin-anti-bot-detector`) + 3 EXTENDED global specs (`linkedin-auth-cookie`, `linkedin-scraper`, `linkedin-config`).

## 1. Purpose

The just-merged `backend-linkedin-auth` works at the code level (the cookie loads, the adapter returns it, the wiring is correct — confirmed by obs #364's live test) but LinkedIn/Cloudflare blocks every request with `ERR_TOO_MANY_REDIRECTS` (50 redirects → 302 loop) on both Playwright and direct curl. Cloudflare's Bot Management decision happens at the TLS/canvas/behavioral layer BEFORE checking `li_at`, and `is_auth_wall` from v1 does NOT fire because the browser never reaches a soup-parseable page. This change is the **first-intent mitigation**: inject `playwright-stealth` (already a project dep, used by Indeed at `infrastructure/indeed/scraper.py:247` and InfoJobs at `infrastructure/infojobs/scraper.py:206`), extend the cookie port to support **multiple LinkedIn cookies** (`li_at` + `JSESSIONID` + `bcookie` + `li_gc` — the 4-minimum set per obs #364), and add a `is_cloudflare_challenge(soup)` detector that surfaces the 302 loop gracefully (soft path: WARNING + return `[]`, no raise). The change is reversible; the v1 anonymous path is preserved byte-identical; the 35 v1 tests stay GREEN.

## 2. Requirements

RFC 2119 keywords (MUST, SHALL, SHOULD, MAY) apply. Every REQ has ≥2 Given/When/Then scenarios (positive + negative). All scenarios are mechanically testable (assert on a return value, a raised exception, an observable state mutation, or a captured log record).

---

### Capability: `linkedin-anti-bot-detector` (NEW)

**File anchors**: `backend/src/jobs_finder/infrastructure/linkedin/parsers.py` (NEW `is_cloudflare_challenge`); `backend/tests/fixtures/linkedin_search.py` (NEW `CLOUDFLARE_CHALLENGE_HTML`); `backend/tests/unit/test_linkedin_cloudflare_challenge.py` (NEW test file — mirror of v1 `test_linkedin_auth_wall.py`).

#### REQ-LST-CF-001 — `is_cloudflare_challenge(soup)` is a pure function
**Capability**: `linkedin-anti-bot-detector`
**Statement**: The function `is_cloudflare_challenge(soup: BeautifulSoup) -> bool` MUST be a pure function in `backend/src/jobs_finder/infrastructure/linkedin/parsers.py`, defined next to the v1 `is_block_page` and `is_auth_wall` functions. "Pure" means: no I/O, no `await`, no module-level mutable state, no logging side-effects. The function does NOT import `logging`. The function does NOT mutate the input `soup` (pure read).
**Rationale**: Mirrors the v1 `is_block_page` + `is_auth_wall` precedent (per `linkedin-auth-wall-detector` spec §REQ-LA-AWALL-001). A pure function is trivially testable offline with the new `CLOUDFLARE_CHALLENGE_HTML` fixture (no Playwright, no async). The distinct semantics — Cloudflare's 302-loop challenge at the network/JS layer (not LinkedIn's auth wall, not the LinkedIn 502 block) — is the third detector in the suite.
**Acceptance**:
- [ ] `is_cloudflare_challenge` lives in `infrastructure/linkedin/parsers.py` next to `is_block_page` and `is_auth_wall`
- [ ] Function signature: `def is_cloudflare_challenge(soup: BeautifulSoup) -> bool`
- [ ] The function does NOT import `logging` and does NOT emit log records
- [ ] `inspect.signature(is_cloudflare_challenge) == "(soup: BeautifulSoup) -> bool"`
- [ ] Calling the function does NOT mutate the input `soup` (verified by `soup.prettify()` byte-for-byte equality before vs. after)

**Scenarios**:
- **GIVEN** `is_cloudflare_challenge` is imported from `jobs_finder.infrastructure.linkedin.parsers`
  - **WHEN** `inspect.signature(is_cloudflare_challenge)` is introspected
  - **THEN** returns `(soup: BeautifulSoup) -> bool`
  - **AND** the test `tests/unit/test_linkedin_cloudflare_challenge.py::test_is_cloudflare_challenge_signature` passes

- **GIVEN** `is_cloudflare_challenge(BeautifulSoup(CLOUDFLARE_CHALLENGE_HTML, "html.parser"))` is called
  - **WHEN** the result is captured AND `soup.prettify()` is called again
  - **THEN** returns `True` AND the post-call `soup.prettify()` is byte-identical to the pre-call
  - **AND** the test `tests/unit/test_linkedin_cloudflare_challenge.py::test_is_cloudflare_challenge_is_pure_no_mutation` passes

#### REQ-LST-CF-002 — `is_cloudflare_challenge` returns `True` for the `CLOUDFLARE_CHALLENGE_HTML` fixture
**Capability**: `linkedin-anti-bot-detector`
**Statement**: `is_cloudflare_challenge(BeautifulSoup(CLOUDFLARE_CHALLENGE_HTML))` MUST return `True`. The new `CLOUDFLARE_CHALLENGE_HTML` fixture (in `backend/tests/fixtures/linkedin_search.py`) is a string containing the Cloudflare 2026 challenge signature — the `<title>Just a moment...</title>` element AND/OR the `<noscript>` redirect message AND/OR a `cf-mitigated` challenge marker (the exact selector set is pinned in the test). The detector MUST match at least ONE of the pinned Cloudflare 2026 selectors.
**Rationale**: The fixture is the canonical "Cloudflare 302-loop page" representation (per obs #365 §2.9 + the Indeed precedent at `tests/fixtures/indeed_search.py:BLOCKED_PAGE_HTML` that was proved against the live Cloudflare variant per obs #74). Captured offline — committed, no live network (AGENTS.md rule #1).
**Acceptance**:
- [ ] `CLOUDFLARE_CHALLENGE_HTML` is committed to `backend/tests/fixtures/linkedin_search.py` (no live network)
- [ ] The fixture contains at least the `<title>Just a moment...</title>` element AND a `<noscript>` redirect message
- [ ] `is_cloudflare_challenge(BeautifulSoup(CLOUDFLARE_CHALLENGE_HTML, "html.parser"))` returns `True`

**Scenarios**:
- **GIVEN** the `CLOUDFLARE_CHALLENGE_HTML` string from `tests/fixtures/linkedin_search.py` (a Cloudflare 2026 challenge page with `<title>Just a moment...</title>` and a `<noscript>` redirect block)
  - **WHEN** `is_cloudflare_challenge(BeautifulSoup(CLOUDFLARE_CHALLENGE_HTML, "html.parser"))` is called
  - **THEN** returns `True`
  - **AND** the test `tests/unit/test_linkedin_cloudflare_challenge.py::test_is_cloudflare_challenge_true_for_challenge_fixture` passes

#### REQ-LST-CF-003 — `is_cloudflare_challenge` returns `False` for healthy SERP, `BLOCK_PAGE_HTML`, and cards-win edge case
**Capability**: `linkedin-anti-bot-detector`
**Statement**: The detector MUST return `False` on three independent inputs to prevent false positives:
  1. The v1 `SEARCH_PAGE_HTML` fixture (a healthy SERP with 3+ `<div data-entity-urn="...">` job cards).
  2. The v1 `BLOCK_PAGE_HTML` fixture (LinkedIn's `<body class="auth-wall">` page — a different anti-bot signal owned by the v1 `is_auth_wall` detector).
  3. An HTML fragment containing BOTH a Cloudflare challenge marker AND at least one job card (`<div data-entity-urn="...">`) — the "cards win" rule suppresses the false positive (same pattern as v1 `is_auth_wall` per `REQ-LA-AWALL-004`).
**Rationale**: Per obs #365 risk #9: a false positive on a healthy SERP would break the operator UX (the scraper returns `[]` when actually a valid SERP rendered). Per the v1 `is_auth_wall` precedent, the "cards win" rule is the load-bearing false-positive suppression. The detector and the v1 `is_auth_wall` are **distinct signals** for distinct anti-bot layers — a healthy SERP with `class="auth-wall"` as defensive markup is a known LinkedIn pattern.
**Acceptance**:
- [ ] `is_cloudflare_challenge(BeautifulSoup(SEARCH_PAGE_HTML, "html.parser"))` returns `False` (no false positive on healthy SERP)
- [ ] `is_cloudflare_challenge(BeautifulSoup(BLOCK_PAGE_HTML, "html.parser"))` returns `False` (no false positive on LinkedIn's auth wall — that is `is_auth_wall`'s signal)
- [ ] The "cards win" rule mirrors v1 `is_auth_wall`: when at least one `<div data-entity-urn="...">` is present in the parsed soup, the function returns `False` regardless of Cloudflare markers

**Scenarios**:
- **GIVEN** the v1 `SEARCH_PAGE_HTML` fixture (healthy SERP with 3+ job cards, no Cloudflare markers)
  - **WHEN** `is_cloudflare_challenge(BeautifulSoup(SEARCH_PAGE_HTML, "html.parser"))` is called
  - **THEN** returns `False`
  - **AND** the test `tests/unit/test_linkedin_cloudflare_challenge.py::test_is_cloudflare_challenge_false_for_healthy_serp` passes

- **GIVEN** the v1 `BLOCK_PAGE_HTML` fixture (LinkedIn auth wall, NOT Cloudflare)
  - **WHEN** `is_cloudflare_challenge(BeautifulSoup(BLOCK_PAGE_HTML, "html.parser"))` is called
  - **THEN** returns `False` (the `is_auth_wall` detector is the correct signal for this HTML)
  - **AND** the test `tests/unit/test_linkedin_cloudflare_challenge.py::test_is_cloudflare_challenge_false_for_linkedin_block_page` passes

- **GIVEN** an HTML fragment `<body><title>Just a moment...</title><div data-entity-urn="urn:li:jobPosting:1"></div></body>` (Cloudflare title + 1 card)
  - **WHEN** `is_cloudflare_challenge(BeautifulSoup(fragment, "html.parser"))` is called
  - **THEN** returns `False` (cards win — false positive suppressed)
  - **AND** the test `tests/unit/test_linkedin_cloudflare_challenge.py::test_is_cloudflare_challenge_false_when_cards_present_even_with_challenge_marker` passes

---

### Capability: `linkedin-auth-cookie` (EXTENDED)

**File anchors**: `backend/src/jobs_finder/application/ports.py` (EXTEND with new `LinkedInAuthCookiesPort` Protocol — plural, alongside the v1 `LinkedInAuthCookiePort` which stays); `backend/src/jobs_finder/infrastructure/linkedin/auth_cookie.py` (NEW `MultiEnvLinkedInAuthCookiesAdapter`; the v1 `EnvLinkedInAuthCookieAdapter` is kept UNCHANGED); `backend/tests/conftest.py` (EXTEND with `FakeLinkedInAuthCookiesPort` companion).

#### REQ-LST-COOKIE-001 — `LinkedInAuthCookiesPort` Protocol (plural) declares `cookies()` method
**Capability**: `linkedin-auth-cookie`
**Statement**: A new `LinkedInAuthCookiesPort` (plural) Protocol MUST be declared in `backend/src/jobs_finder/application/ports.py` with a single synchronous method `def cookies(self) -> list[tuple[str, SecretStr]] | None` that returns either `None` (no cookies configured — the v1 anonymous sentinel) OR a `list` of `(name, value)` pairs for every non-None cookie. The Protocol is NOT `@runtime_checkable` (mirrors v1 `LinkedInAuthCookiePort`).
**Rationale**: Per Q1 in obs #365 §6 (auto-resolved by orchestrator): the multi-cookie shape is a `list[tuple[str, SecretStr]]` (not a `dict`, not a value object). The Protocol stays minimal (1 method). The v1 `LinkedInAuthCookiePort` (singular) is KEPT for backward compat (35 v1 tests construct `EnvLinkedInAuthCookieAdapter(SecretStr("AQE..."))` directly); the new `LinkedInAuthCookiesPort` is ADDITIVE. `mypy --strict` MUST validate that `MultiEnvLinkedInAuthCookiesAdapter` and `FakeLinkedInAuthCookiesPort` both structurally conform.
**Acceptance**:
- [ ] `LinkedInAuthCookiesPort` lives in `application/ports.py` (next to the v1 `LinkedInAuthCookiePort`)
- [ ] Exactly one method: `def cookies(self) -> list[tuple[str, SecretStr]] | None: ...`
- [ ] The Protocol is NOT `@runtime_checkable`
- [ ] The v1 `LinkedInAuthCookiePort` is UNCHANGED (the 35 v1 tests stay GREEN)

**Scenarios**:
- **GIVEN** a `MultiEnvLinkedInAuthCookiesAdapter(SecretStr("li_at_val"), None, None, None)` is constructed (1 cookie configured)
  - **WHEN** `port.cookies()` is called
  - **THEN** returns a `list` of length 1: `[("li_at", SecretStr("li_at_val"))]`
  - **AND** `mypy --strict` validates `port: LinkedInAuthCookiesPort = adapter` (structural conformance)
  - **AND** the test `tests/unit/test_linkedin_auth_cookies.py::test_protocol_structural_conformance` passes

- **GIVEN** the v1 `EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA"))` is constructed (the v1 single-cookie shape, KEPT for backward compat)
  - **WHEN** `adapter.cookie()` is called (the v1 method, unchanged)
  - **THEN** returns `SecretStr("AQEAAAAQEAAA")` (the v1 contract is preserved)
  - **AND** the 35 v1 tests stay GREEN (regression check)

#### REQ-LST-COOKIE-002 — `MultiEnvLinkedInAuthCookiesAdapter` ctor accepts 4 independently optional `SecretStr | None` params
**Capability**: `linkedin-auth-cookie`
**Statement**: The new `MultiEnvLinkedInAuthCookiesAdapter` class (in `infrastructure/linkedin/auth_cookie.py` next to the v1 `EnvLinkedInAuthCookieAdapter`) MUST accept 4 keyword-only `SecretStr | None` params: `li_at`, `jsessionid`, `bcookie`, `li_gc`. Each is independently optional. The class MUST be `__slots__`-based (`__slots__ = ("_li_at", "_jsessionid", "_bcookie", "_li_gc")`) and MUST NOT import `logging` (no log records emitted).
**Rationale**: Per Q2 in obs #365 §6: individual env vars matching the per-source `AliasChoices` precedent at `config.py:292-294` (Indeed/InfoJobs use individual env vars per source, not a JSON blob). Each cookie's `SecretStr | None` type preserves the v1 `li_at` kill-switch semantic (`None` = skip that cookie). The adapter is a pure in-process value provider (no I/O, no `await`).
**Acceptance**:
- [ ] `MultiEnvLinkedInAuthCookiesAdapter(li_at=..., jsessionid=..., bcookie=..., li_gc=...)` accepts all 4 params as kwargs
- [ ] Each param is `SecretStr | None` (independently optional)
- [ ] `__slots__ = ("_li_at", "_jsessionid", "_bcookie", "_li_gc")` (memory efficiency + immutability)
- [ ] The adapter does NOT import `logging`

**Scenarios**:
- **GIVEN** `MultiEnvLinkedInAuthCookiesAdapter(li_at=SecretStr("AQEAAAAQEAAA"), jsessionid=SecretStr("ajax:12345"), bcookie=None, li_gc=SecretStr("gc_xyz"))` (3 cookies present, 1 absent)
  - **WHEN** the construction completes
  - **THEN** no exception is raised
  - **AND** the test `tests/unit/test_linkedin_auth_cookies.py::test_adapter_accepts_4_independently_optional_params` passes

- **GIVEN** `MultiEnvLinkedInAuthCookiesAdapter(li_at=None, jsessionid=None, bcookie=None, li_gc=None)` (all 4 absent — v1 anonymous sentinel)
  - **WHEN** the construction completes
  - **THEN** no exception is raised
  - **AND** the test `tests/unit/test_linkedin_auth_cookies.py::test_adapter_accepts_all_none_constructor` passes

#### REQ-LST-COOKIE-003 — `cookies()` returns `None` when all 4 are `None`; otherwise returns the list of non-None cookies
**Capability**: `linkedin-auth-cookie`
**Statement**: The `cookies()` method MUST return `None` when ALL 4 ctor params are `None` (the v1 anonymous-path sentinel — soft mode preserved). When at least one cookie is `non-None`, it MUST return a `list[tuple[str, SecretStr]]` containing ONLY the non-None cookies (the `None` entries are filtered out, NOT included as `None` in the list).
**Rationale**: The v1 `EnvLinkedInAuthCookieAdapter.cookie()` returned `None` when no cookie was configured; the multi-cookie version preserves that semantic. The list is filtered (not a sparse 4-tuple) so the scraper's loop can iterate over the cookies without null-checking each entry.
**Acceptance**:
- [ ] `MultiEnvLinkedInAuthCookiesAdapter(None, None, None, None).cookies() is None` (soft mode preserved)
- [ ] When 1 cookie is set (e.g. only `li_at`): returns a 1-element list
- [ ] When 3 cookies are set (e.g. `li_at`, `bcookie`, `li_gc` but not `jsessionid`): returns a 3-element list (the `None` `jsessionid` is filtered out)
- [ ] When all 4 cookies are set: returns a 4-element list

**Scenarios**:
- **GIVEN** `MultiEnvLinkedInAuthCookiesAdapter(li_at=None, jsessionid=None, bcookie=None, li_gc=None)` (the v1 anonymous sentinel)
  - **WHEN** `adapter.cookies()` is called
  - **THEN** returns `None` (the soft mode)
  - **AND** the test `tests/unit/test_linkedin_auth_cookies.py::test_cookies_returns_none_when_all_4_none` passes

- **GIVEN** `MultiEnvLinkedInAuthCookiesAdapter(li_at=SecretStr("AQEAAAAQEAAA"), jsessionid=None, bcookie=None, li_gc=None)` (only `li_at`)
  - **WHEN** `adapter.cookies()` is called
  - **THEN** returns `[("li_at", SecretStr("AQEAAAAQEAAA"))]` (1-element list, NOT a 4-tuple with `None`s)
  - **AND** the test `tests/unit/test_linkedin_auth_cookies.py::test_cookies_returns_filtered_list_when_partial` passes

- **GIVEN** `MultiEnvLinkedInAuthCookiesAdapter(li_at=SecretStr("AQE..."), jsessionid=SecretStr("ajax:12345"), bcookie=None, li_gc=SecretStr("gc_xyz"))` (3 set, 1 absent)
  - **WHEN** `adapter.cookies()` is called
  - **THEN** returns a 3-element list (the `None` `bcookie` is filtered out)
  - **AND** the test `tests/unit/test_linkedin_auth_cookies.py::test_cookies_filters_none_entries` passes

#### REQ-LST-COOKIE-004 — `cookies()` returns deterministic order `li_at` → `jsessionid` → `bcookie` → `li_gc`
**Capability**: `linkedin-auth-cookie`
**Statement**: When the returned list is non-None, the cookie pairs MUST be ordered deterministically as `li_at` → `jsessionid` → `bcookie` → `li_gc` (the canonical LinkedIn-session order). The v1 single-cookie `EnvLinkedInAuthCookieAdapter(SecretStr("AQE..."))` ctor is PRESERVED UNCHANGED (the 35 v1 tests stay GREEN); its `cookie()` method (singular) returns the `SecretStr` as-is, and a backward-compat shim method `cookies()` (plural) returns `[(name, value)]` with `name="li_at"`.
**Rationale**: Deterministic order is load-bearing for the test (the order is the contract). The order matches LinkedIn's "session-establishing" cookie precedence — `li_at` first (the auth token), then the JSESSIONID/GC support cookies, then `bcookie` (browser fingerprint) last. A future change that re-orders would break the closure precedence test.
**Acceptance**:
- [ ] `MultiEnvLinkedInAuthCookiesAdapter(li_at=A, jsessionid=B, bcookie=C, li_gc=D).cookies() == [("li_at", A), ("jsessionid", B), ("bcookie", C), ("li_gc", D)]` (exact order)
- [ ] The v1 `EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA")).cookie()` returns `SecretStr("AQEAAAAQEAAA")` (the v1 contract is preserved, 35 v1 tests stay GREEN)

**Scenarios**:
- **GIVEN** `MultiEnvLinkedInAuthCookiesAdapter(li_at=SecretStr("A"), jsessionid=SecretStr("B"), bcookie=SecretStr("C"), li_gc=SecretStr("D"))` (all 4 set)
  - **WHEN** `adapter.cookies()` is called
  - **THEN** returns `[("li_at", SecretStr("A")), ("jsessionid", SecretStr("B")), ("bcookie", SecretStr("C")), ("li_gc", SecretStr("D"))]` (exact canonical order)
  - **AND** the test `tests/unit/test_linkedin_auth_cookies.py::test_cookies_returns_deterministic_order` passes

- **GIVEN** the v1 `EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA"))` (the 35 v1 tests' construction pattern)
  - **WHEN** `adapter.cookie()` is called (the v1 method, UNCHANGED)
  - **THEN** returns `SecretStr("AQEAAAAQEAAA")` (v1 contract preserved)
  - **AND** the v1 tests `tests/unit/test_linkedin_auth_cookie.py` all stay GREEN (regression check)

#### REQ-LST-COOKIE-005 — `MultiEnvLinkedInAuthCookiesAdapter.__repr__` masks cookie count, not values
**Capability**: `linkedin-auth-cookie`
**Statement**: `MultiEnvLinkedInAuthCookiesAdapter.__repr__` MUST return a string that does NOT contain any cookie value (defense in depth — `SecretStr` already masks `repr()` of the values). The repr MAY show the cookie count (e.g. `"MultiEnvLinkedInAuthCookiesAdapter(<set: 3 cookies>)"` or `"<unset>"` when all 4 are `None`); a 1-bit side-channel on "is the operator fully configured" is acceptable (per obs #365 risk #7). The 4 v1 `__repr__` no-leak assertions (per v1 `REQ-LA-CFG-004`) extend to the 3 new fields.
**Rationale**: The `SecretStr` type masks `repr()` at the value-object level; the adapter-level `__repr__` is defense-in-depth. The count-only side-channel is acceptable (the operator's own `ls -la .env` is a richer side-channel).
**Acceptance**:
- [ ] `repr(MultiEnvLinkedInAuthCookiesAdapter(SecretStr("AQEAAAAQEAAA"), None, None, None))` does NOT contain `"AQEAAAAQEAAA"`
- [ ] `repr(MultiEnvLinkedInAuthCookiesAdapter(None, None, None, None))` does NOT contain any substring that could be a cookie value
- [ ] The repr shows the cookie count (acceptable) but never the value (mandatory)

**Scenarios**:
- **GIVEN** `MultiEnvLinkedInAuthCookiesAdapter(li_at=SecretStr("AQEAAAAQEAAA"), jsessionid=None, bcookie=None, li_gc=None)`
  - **WHEN** `repr(adapter)` is evaluated
  - **THEN** the returned string does NOT contain the substring `"AQEAAAAQEAAA"` (the synthetic test value)
  - **AND** the test `tests/unit/test_linkedin_auth_cookies.py::test_adapter_repr_does_not_leak_li_at_value` passes

- **GIVEN** `MultiEnvLinkedInAuthCookiesAdapter(li_at=None, jsessionid=SecretStr("ajax:99999"), bcookie=None, li_gc=None)` (only `jsessionid` set, sensitive substring)
  - **WHEN** `repr(adapter)` is evaluated
  - **THEN** the returned string does NOT contain the substring `"ajax:99999"`
  - **AND** the test `tests/unit/test_linkedin_auth_cookies.py::test_adapter_repr_does_not_leak_jsessionid_value` passes (1 assertion per non-`None` cookie)

---

### Capability: `linkedin-scraper` (EXTENDED)

**File anchors**: `backend/src/jobs_finder/infrastructure/linkedin/scraper.py` (EXTEND ctor + `search()`); `backend/tests/unit/test_linkedin_scraper_auth.py` (EXTEND with multi-cookie + stealth + closure precedence tests).

#### REQ-LST-SCR-001 — `search()` applies `playwright-stealth` at the `BrowserContext` level
**Capability**: `linkedin-scraper`
**Statement**: `LinkedInPlaywrightScraper` constructor MUST accept a new keyword-only kwarg `stealth: Stealth | None = None` (default `None` — the v1 behavior is preserved when no stealth is wired). The `Stealth` instance is held in `self._stealth: Stealth | None`. In `search()`, AFTER `await self._browser.new_context(...)` returns the context AND BEFORE `add_cookies` and `paginated_search()` are called, `search()` MUST call `await self._stealth.apply_stealth_async(ctx)` GATED on `self._stealth is not None` (i.e. the call is skipped when `stealth=None`, preserving v1 behavior). The import is `from playwright_stealth import Stealth  # type: ignore[import-untyped]` (matches Indeed+InfoJobs precedent at `infrastructure/indeed/scraper.py:69`).
**Rationale**: Per Q3 in obs #365 §6 (auto-resolved): BrowserContext level is the canonical pattern (Indeed+InfoJobs use it). The Indeed precedent is at `infrastructure/indeed/scraper.py:240-247` (the `if self._stealth is not None:` gate + `await self._stealth.apply_stealth_async(ctx)` call); the InfoJobs precedent is at `infrastructure/infojobs/scraper.py:206` (ctor kwarg) + L327 (the call). Mirroring them keeps code-review parity.
**Acceptance**:
- [ ] `LinkedInPlaywrightScraper(..., stealth: Stealth | None = None)` is a keyword-only kwarg
- [ ] `self._stealth: Stealth | None = stealth` is set in `__init__`
- [ ] `search()` calls `await self._stealth.apply_stealth_async(ctx)` after `new_context()` and before `add_cookies` + `paginated_search()`, gated on `self._stealth is not None`
- [ ] When `stealth=None`, the call is SKIPPED (v1 behavior preserved)
- [ ] The import matches Indeed+InfoJobs: `from playwright_stealth import Stealth  # type: ignore[import-untyped]`

**Scenarios**:
- **GIVEN** a `LinkedInPlaywrightScraper` constructed with `stealth=MagicMock()` whose `apply_stealth_async` is an `AsyncMock` AND a `FakeBrowser` capturing the call
  - **WHEN** `search("react", "Madrid", limit=10)` runs
  - **THEN** the `MagicMock().apply_stealth_async` is called exactly once with the context object
  - **AND** the call happens AFTER `new_context` AND BEFORE `add_cookies` (order is verified by the test)
  - **AND** the test `tests/unit/test_linkedin_scraper_auth.py::test_stealth_is_applied_when_provided` passes (mirrors Indeed `TestStealthIntegration`)

- **GIVEN** a `LinkedInPlaywrightScraper` constructed with `stealth=None` (the v1 default)
  - **WHEN** `search("react", "Madrid", limit=10)` runs
  - **THEN** the `apply_stealth_async` is NEVER called (the gate skips it)
  - **AND** the v1 behavior is preserved (35 v1 tests stay GREEN)
  - **AND** the test `tests/unit/test_linkedin_scraper_auth.py::test_stealth_is_not_applied_when_none` passes

#### REQ-LST-SCR-002 — `search()` injects all non-None cookies via `ctx.add_cookies` with the LinkedIn-shape Playwright dict
**Capability**: `linkedin-scraper`
**Statement**: When the multi-cookie port returns a non-`None` list, `search()` MUST call `await ctx.add_cookies([{...} for (n, v) in cookies])` AFTER `apply_stealth_async(ctx)` and BEFORE the first `paginated_search()` navigation, on the SAME `BrowserContext` instance. Each cookie dict MUST be `{"name": <n>, "value": <v.get_secret_value()>, "domain": ".linkedin.com", "path": "/", "httpOnly": True, "secure": True}` (the LinkedIn-shape contract per the v1 `REQ-LA-SCR-004` golden assertion, generalized to N cookies). When the port returns `None` (the v1 anonymous path), `add_cookies` is NOT called.
**Rationale**: Per-context injection (not per-page) matches the v1 pattern (per `REQ-LA-SCR-002` + `REQ-LA-SCR-006`). Generalizing from 1 to N cookies is a list comprehension; the per-cookie shape is byte-identical to the v1 (LinkedIn's issuance contract). The v1 `cookies: [{"name": "li_at", "value": ..., ...}]` golden assertion extends to `cookies: [{"name": n_i, "value": ..., "domain": ".linkedin.com", ...} for (n_i, v_i) in port.cookies()]`.
**Acceptance**:
- [ ] When `port.cookies()` returns a list, `search()` calls `await ctx.add_cookies([...])` with the full list
- [ ] Each cookie dict has keys `name`, `value`, `domain=".linkedin.com"`, `path="/"`, `httpOnly=True`, `secure=True`
- [ ] When `port.cookies() is None`, `add_cookies` is NOT called (v1 anonymous path preserved)
- [ ] The injection happens AFTER `apply_stealth_async(ctx)` and BEFORE the first `paginated_search()` navigation (per the closure lifecycle)

**Scenarios**:
- **GIVEN** a `LinkedInPlaywrightScraper` with `auth_cookies=MultiEnvLinkedInAuthCookiesAdapter(SecretStr("AQEAAAAQEAAA"), SecretStr("ajax:12345"), None, None)` (2 cookies) AND a `FakeBrowser` capturing `add_cookies` calls
  - **WHEN** `search("react", "Madrid", limit=10)` runs
  - **THEN** `add_cookies_calls[0] == [{"name": "li_at", "value": "AQEAAAAQEAAA", "domain": ".linkedin.com", "path": "/", "httpOnly": True, "secure": True}, {"name": "jsessionid", "value": "ajax:12345", "domain": ".linkedin.com", "path": "/", "httpOnly": True, "secure": True}]` (golden assertion on the full list)
  - **AND** the test `tests/unit/test_linkedin_scraper_auth.py::test_add_cookies_called_with_all_non_none_cookies` passes

- **GIVEN** the same scraper with `auth_cookies=MultiEnvLinkedInAuthCookiesAdapter(None, None, None, None)` (the v1 anonymous sentinel — all 4 None)
  - **WHEN** `search("react", "Madrid", limit=10)` runs
  - **THEN** `add_cookies` is NEVER called
  - **AND** the v1 anonymous path is preserved
  - **AND** the test `tests/unit/test_linkedin_scraper_auth.py::test_no_add_cookies_call_when_all_cookies_none` passes

#### REQ-LST-SCR-003 — `_make_fetch_one_page` closure precedence: `is_cloudflare_challenge` → `is_auth_wall` → `is_block_page` (cookie path) / `is_block_page` first (anonymous path)
**Capability**: `linkedin-scraper`
**Statement**: Inside `LinkedInPlaywrightScraper._make_fetch_one_page` closure, the per-page check order MUST be:
  - **Cookie-injection path** (`auth_cookies is not None` and `auth_cookies.cookies() is not None`): `is_cloudflare_challenge(soup)` checked FIRST (newest — soft path → WARNING + return `[]` if it fires and 0 cards), THEN `is_auth_wall(soup)` (v1 soft path → WARNING if it fires), THEN `is_block_page(soup)` (v1 hard path → raise `LinkedInBlockedError` if it fires — extremely rare, only a genuine hard block).
  - **Anonymous path** (`auth_cookies is None` OR `auth_cookies.cookies() is None`): `is_block_page(soup)` checked FIRST (the v1 hard-raise behavior is preserved byte-identical), `is_auth_wall` and `is_cloudflare_challenge` are NOT consulted (the v1 `test_search_raises_blocked_on_auth_wall` test is preserved unchanged).
**Rationale**: The newest-first precedence on the cookie path mirrors the v1 `is_auth_wall` design (per `REQ-LA-AWALL-005` archive note: "the cookie-injection path checks `is_auth_wall` FIRST, the anonymous path keeps `is_block_page` FIRST"). The new `is_cloudflare_challenge` is even SOFTER than `is_auth_wall` (Cloudflare's 302-loop is a network-layer event, not a soup-parseable page), so it gets the highest precedence (lowest threshold to fire) on the cookie path. The v1 anonymous path is preserved byte-identical (the 35 v1 tests stay GREEN — the v1 `test_search_raises_blocked_on_auth_wall` is the canonical regression check).
**Acceptance**:
- [ ] Cookie path: `is_cloudflare_challenge` checked FIRST (soft WARNING if True + 0 cards)
- [ ] Cookie path: `is_auth_wall` checked SECOND (soft WARNING if True — v1 behavior)
- [ ] Cookie path: `is_block_page` checked THIRD (hard raise if True — only on a genuine hard block that survived the soft filters)
- [ ] Anonymous path: `is_block_page` checked FIRST (hard raise — v1 behavior, byte-identical)
- [ ] Anonymous path: `is_auth_wall` is NOT consulted (v1 path is preserved)
- [ ] Anonymous path: `is_cloudflare_challenge` is NOT consulted (the v1 anonymous path does not need the new detector)

**Scenarios**:
- **GIVEN** a `LinkedInPlaywrightScraper` with `auth_cookies=MultiEnvLinkedInAuthCookiesAdapter(SecretStr("AQEAAAAQEAAA"), None, None, None)` (cookie path) AND a `FakeBrowser` that returns `CLOUDFLARE_CHALLENGE_HTML` (Cloudflare marker, 0 cards) for every page
  - **WHEN** `search("react", "Madrid", limit=10)` runs AND `caplog` is set to `WARNING`
  - **THEN** the closure emits the WARNING per `REQ-LST-SCR-004` (the Cloudflare-challenge message)
  - **AND** `search()` returns `[]` (the soft path, no raise)
  - **AND** the test `tests/unit/test_linkedin_scraper_auth.py::test_closure_warns_on_cloudflare_challenge_cookie_path` passes

- **GIVEN** the same scraper (cookie path) AND a `FakeBrowser` that returns `BLOCK_PAGE_HTML` (LinkedIn auth wall, 0 cards)
  - **WHEN** `search("react", "Madrid", limit=10)` runs
  - **THEN** the closure emits the v1 `is_auth_wall` WARNING (the soft path wins because `is_cloudflare_challenge` returned False on the LinkedIn auth wall)
  - **AND** `search()` returns `[]`
  - **AND** the test `tests/unit/test_linkedin_scraper_auth.py::test_closure_warns_on_auth_wall_after_cloudflare_false` passes

- **GIVEN** a `LinkedInPlaywrightScraper` with `auth_cookies=None` (anonymous path — v1 behavior) AND a `FakeBrowser` that returns `BLOCK_PAGE_HTML` for every page
  - **WHEN** `search("react", "Madrid", limit=10)` runs
  - **THEN** raises `LinkedInBlockedError` (the v1 hard-raise path is preserved)
  - **AND** `is_auth_wall` and `is_cloudflare_challenge` are NOT consulted (the v1 test `test_search_raises_blocked_on_auth_wall` is the regression check)
  - **AND** the 35 v1 tests stay GREEN

#### REQ-LST-SCR-004 — `is_cloudflare_challenge` WARNING log: soft path, no raise, returns `[]` on page-0 zero-cards
**Capability**: `linkedin-scraper`
**Statement**: When `is_cloudflare_challenge(soup) is True` AND the page yields 0 cards, the scraper MUST return `[]` (an empty list) — NOT raise a `LinkedInParseError`, NOT raise a `LinkedInBlockedError`. A single WARNING log line MUST be emitted with the message
`"LinkedIn Cloudflare challenge detected; stealth may be insufficient. Consider setting LINKEDIN_JSESSIONID, LINKEDIN_BCOOKIE, LINKEDIN_LI_GC in .env, or upgrading to a residential proxy."`
The closure continues parsing whatever cards exist (does NOT short-circuit on the marker). When the Cloudflare challenge is on page 0 AND 0 cards are parsed, the scraper returns `[]` (mirrors v1 `REQ-LA-AWALL-006`).
**Rationale**: Per Q4 in obs #365 §6: soft path mirrors v1 `is_auth_wall`. The WARNING is the operator signal that stealth is insufficient (and gives the operator a concrete action: add 3 more cookies or upgrade to a residential proxy). The response is degraded-but-not-500 (so a frontend can render a "Cloudflare challenge detected" UI rather than a generic 502 page).
**Acceptance**:
- [ ] When `is_cloudflare_challenge(soup) is True` AND 0 cards: WARNING + return `[]`, NO raise
- [ ] When `is_cloudflare_challenge(soup) is True` AND ≥1 card: NO WARNING (the "cards win" rule from `REQ-LST-CF-003`), returns the cards
- [ ] The WARNING message contains the substring `"LinkedIn Cloudflare challenge detected"` (for ops greppability)
- [ ] The WARNING message contains the substring `"LINKEDIN_JSESSIONID"` and `"LINKEDIN_BCOOKIE"` and `"LINKEDIN_LI_GC"` (operator-actionable)
- [ ] The closure continues to `_parse_cards` after the WARNING (does NOT short-circuit)

**Scenarios**:
- **GIVEN** a `LinkedInPlaywrightScraper` with `auth_cookies=MultiEnvLinkedInAuthCookiesAdapter(SecretStr("AQEAAAAQEAAA"), None, None, None)` AND a `FakeBrowser` that returns `CLOUDFLARE_CHALLENGE_HTML` (challenge marker, 0 cards) for every page
  - **WHEN** `search("react", "Madrid", limit=10)` runs AND `caplog` is set to `WARNING`
  - **THEN** exactly one WARNING log record contains `"LinkedIn Cloudflare challenge detected"` AND `"LINKEDIN_JSESSIONID"` AND `"LINKEDIN_BCOOKIE"` AND `"LINKEDIN_LI_GC"`
  - **AND** `search()` returns `[]` (empty list, NOT a `LinkedInBlockedError`)
  - **AND** the test `tests/unit/test_linkedin_scraper_auth.py::test_closure_warns_on_cloudflare_challenge_with_actionable_message` passes

- **GIVEN** a `FakeBrowser` that returns HTML with BOTH a Cloudflare marker AND 3 cards (cards win)
  - **WHEN** `search("react", "Madrid", limit=10)` runs
  - **THEN** NO Cloudflare WARNING is emitted (the "cards win" rule suppresses the false positive)
  - **AND** `search()` returns the 3 parsed jobs
  - **AND** the test `tests/unit/test_linkedin_scraper_auth.py::test_closure_does_not_warn_when_cards_present_even_with_cloudflare_marker` passes (false-positive suppression at the closure level)

---

### Capability: `linkedin-config` (EXTENDED)

**File anchors**: `backend/src/jobs_finder/infrastructure/config.py` (EXTEND `Settings` with 3 new `SecretStr | None` fields + reusable validator); `backend/tests/unit/test_linkedin_config.py` (EXTEND with tests for the 3 new fields).

#### REQ-LST-CFG-001 — 3 new optional `SecretStr | None` fields with `AliasChoices` env binding
**Capability**: `linkedin-config`
**Statement**: The `Settings` model MUST declare 3 new fields, each `SecretStr | None` with default `None`, each bound via `validation_alias=AliasChoices(<UPPER>, <lower>)`:
  - `linkedin_jsessionid: SecretStr | None` ↔ `LINKEDIN_JSESSIONID` (case-insensitive via pydantic-settings)
  - `linkedin_bcookie: SecretStr | None` ↔ `LINKEDIN_BCOOKIE`
  - `linkedin_li_gc: SecretStr | None` ↔ `LINKEDIN_LI_GC`
The 3 fields are placed adjacent to the v1 `linkedin_li_at` field (per `config.py:317-362`).
**Rationale**: Per Q2 in obs #365 §6: individual env vars matching the per-source `AliasChoices` precedent (Indeed/InfoJobs use individual env vars at `config.py:175-201`). Each field's `SecretStr | None` type preserves the v1 kill-switch semantic. The `AliasChoices` pattern (upper + lower) survives a future `env_prefix` rename.
**Acceptance**:
- [ ] `Settings()` with no env vars has `linkedin_jsessionid is None`, `linkedin_bcookie is None`, `linkedin_li_gc is None`
- [ ] `LINKEDIN_JSESSIONID=ajax:12345` env → `Settings().linkedin_jsessionid.get_secret_value() == "ajax:12345"`
- [ ] `LINKEDIN_BCOOKIE=v2_xyz` env → `Settings().linkedin_bcookie.get_secret_value() == "v2_xyz"`
- [ ] `LINKEDIN_LI_GC=gc_abc` env → `Settings().linkedin_li_gc.get_secret_value() == "gc_abc"`
- [ ] The v1 `linkedin_li_at` field is UNCHANGED (35 v1 tests stay GREEN)

**Scenarios**:
- **GIVEN** `LINKEDIN_JSESSIONID=ajax:12345` is in the process env
  - **WHEN** `Settings()` is constructed
  - **THEN** `settings.linkedin_jsessionid.get_secret_value() == "ajax:12345"`
  - **AND** the test `tests/unit/test_linkedin_config.py::test_settings_reads_linkedin_jsessionid_from_env` passes

- **GIVEN** no `LINKEDIN_JSESSIONID` env var is set
  - **WHEN** `Settings()` is constructed
  - **THEN** `settings.linkedin_jsessionid is None`
  - **AND** the test `tests/unit/test_linkedin_config.py::test_settings_linkedin_jsessionid_defaults_to_none` passes

- **GIVEN** `Settings(linkedin_bcookie=SecretStr("v2_xyz"), linkedin_li_gc=SecretStr("gc_abc"))` (programmatic)
  - **WHEN** the construction completes
  - **THEN** both fields are populated and the v1 `linkedin_li_at` is still `None` (no cross-coupling)
  - **AND** the test `tests/unit/test_linkedin_config.py::test_settings_programmatic_construction_of_new_fields` passes

#### REQ-LST-CFG-002 — Reusable validator (HARD on `len < 8` when present, soft `None` allowed) shared across all 4 fields
**Capability**: `linkedin-config`
**Statement**: Each of the 3 new `linkedin_*` fields MUST use the v1 validator pattern: HARD `ValueError` on `len < 8` characters when present, soft `None` allowed. The validator is a REUSABLE HELPER (a private function or a `field_validator` factory — the design can choose the exact shape) — the contract is that the same `len < 8` rejection + same `min < N>` error message format applies to all 4 cookie fields (`linkedin_li_at` + the 3 new). The constant `MIN_LI_AT_LENGTH = 8` (per `config.py:58`) is the single source of truth.
**Rationale**: Per the proposal (proposal §"What changes" + design rationale): "the proposal's recommendation to share it via a helper is a design-level concern, but the spec mandates the contract." All 4 fields use the same threshold (8 chars) and the same error message format. The design may extract a `_validate_cookie_min_length(cls, v: SecretStr | None, field_name: str) -> SecretStr | None` helper, or 4 individual `field_validator`s that share a constant — both shapes satisfy the contract.
**Acceptance**:
- [ ] `Settings(linkedin_jsessionid=SecretStr("abc"))` raises `ValidationError` with the message containing `"must be at least 8 characters"` AND `"got 3"`
- [ ] `Settings(linkedin_bcookie=SecretStr("1234567"))` (7 chars) raises (boundary `<8`)
- [ ] `Settings(linkedin_li_gc=SecretStr("12345678"))` (8 chars) succeeds (boundary inclusive)
- [ ] `Settings(linkedin_jsessionid=None)` does NOT raise (soft `None` allowed)
- [ ] The error message includes the field name (e.g. `"LINKEDIN_JSESSIONID"`) so the operator can self-diagnose which env var is wrong

**Scenarios**:
- **GIVEN** programmatic `Settings(linkedin_jsessionid=SecretStr("abc"))` (3 chars)
  - **WHEN** `Settings()` is constructed
  - **THEN** raises `pydantic.ValidationError` whose `__str__` contains `"LINKEDIN_JSESSIONID"`, `"must be at least 8 characters"`, and `"got 3"`
  - **AND** the test `tests/unit/test_linkedin_config.py::test_settings_rejects_short_jsessionid_with_field_name` passes

- **GIVEN** programmatic `Settings(linkedin_bcookie=SecretStr("1234567"))` (7 chars, boundary)
  - **WHEN** `Settings()` is constructed
  - **THEN** raises `ValidationError` (threshold inclusive `<8`)
  - **AND** the test `tests/unit/test_linkedin_config.py::test_settings_rejects_short_bcookie_7_chars` passes

- **GIVEN** programmatic `Settings(linkedin_li_gc=SecretStr("12345678"))` (8 chars, minimum valid)
  - **WHEN** `Settings()` is constructed
  - **THEN** succeeds; `settings.linkedin_li_gc.get_secret_value() == "12345678"`
  - **AND** the test `tests/unit/test_linkedin_config.py::test_settings_accepts_minimum_length_8_for_li_gc` passes

- **GIVEN** programmatic `Settings(linkedin_jsessionid=SecretStr(""))` (empty — defense-in-depth)
  - **WHEN** `Settings()` is constructed
  - **THEN** `settings.linkedin_jsessionid is None` (the v1 `mode="before"` empty→`None` normalization applies to all 4 fields)
  - **AND** the test `tests/unit/test_linkedin_config.py::test_settings_normalizes_empty_jsessionid_to_none` passes

#### REQ-LST-CFG-003 — `Settings.__repr__` does NOT include any of the 3 new field values
**Capability**: `linkedin-config`
**Statement**: `repr(Settings(linkedin_jsessionid=SecretStr("ajax:12345"), linkedin_bcookie=SecretStr("v2_xyz"), linkedin_li_gc=SecretStr("gc_abc")))` MUST NOT contain the substrings `"ajax:12345"`, `"v2_xyz"`, or `"gc_abc"`. The `SecretStr` type already enforces this at the field level (its `__repr__` masks to `SecretStr('**********')`), but a test MUST assert the contract at the `Settings` repr level (1 assertion per new field — defense in depth, mirrors v1 `REQ-LA-CFG-004`).
**Rationale**: AGENTS.md rule #7: no real cookies in the repo. The v1 `test_settings_repr_does_not_leak_cookie_value` pattern extends to all 4 fields. A future field that accidentally accepts plain `str` would fail the test immediately.
**Acceptance**:
- [ ] `repr(Settings(linkedin_jsessionid=SecretStr("ajax:12345")))` does NOT contain `"ajax:12345"`
- [ ] `repr(Settings(linkedin_bcookie=SecretStr("v2_xyz")))` does NOT contain `"v2_xyz"`
- [ ] `repr(Settings(linkedin_li_gc=SecretStr("gc_abc")))` does NOT contain `"gc_abc"`
- [ ] The v1 `repr(Settings(linkedin_li_at=SecretStr("AQEAAAAQEAAA")))` does NOT contain `"AQEAAAAQEAAA"` (35 v1 tests stay GREEN)

**Scenarios**:
- **GIVEN** `Settings(linkedin_jsessionid=SecretStr("ajax:12345"))`
  - **WHEN** `repr(settings)` is evaluated
  - **THEN** the returned string does NOT contain `"ajax:12345"`
  - **AND** the test `tests/unit/test_linkedin_config.py::test_settings_repr_does_not_leak_jsessionid` passes

- **GIVEN** `Settings(linkedin_bcookie=SecretStr("v2_xyz"), linkedin_li_gc=SecretStr("gc_abc"))`
  - **WHEN** `repr(settings)` is evaluated
  - **THEN** the returned string does NOT contain `"v2_xyz"` AND does NOT contain `"gc_abc"`
  - **AND** the test `tests/unit/test_linkedin_config.py::test_settings_repr_does_not_leak_bcookie_or_li_gc` passes (2 assertions, 1 test)

---

## 3. Out of scope (explicit, from proposal §"Out of scope")

- **Residential proxy integration** — the documented fallback path is `backend-linkedin-residential-proxy` (per obs #365 §4.6). NOT shipped in this change.
- **Browser real (non-headless) mode** — headless is the test default; real mode is a follow-up if Cloudflare-2026 escalates.
- **Automated cookie refresh** — the operator rotates manually; the `is_cloudflare_challenge` WARNING is the signal.
- **Retry/backoff with exponential backoff** — the existing `paginated_search` helper handles timeouts.
- **Circuit breaker for LinkedIn** — would require process-state that we deliberately do not add.
- **Detectors for other anti-bot vendors** (DataDome, PerimeterX, Akamai) — each new source/vendor is its own follow-up.
- **Modifying the other 2 scrapers (Indeed, InfoJobs)** — they already use stealth.
- **Live-network test against real LinkedIn** — AGENTS.md rule #1 forbids live scraping in tests.
- **Modifying the v1 `LinkedInAuthCookiePort` (singular) Protocol** — kept byte-identical for the 35 v1 tests.
- **Modifying the v1 `EnvLinkedInAuthCookieAdapter` (singular)** — kept byte-identical for the 35 v1 tests.
- **Replacing v1 `is_auth_wall` or `is_block_page`** — they coexist with the new `is_cloudflare_challenge`.
- **Modifying the v1 `Settings.linkedin_li_at` field or its 2 validators** — kept byte-identical.
- **Modifying the `JobSearchPort` Protocol** — the multi-cookie port is a NEW independent Protocol.
- **Modifying the `paginated_search` helper** — the stealth + multi-cookie work happens BEFORE the loop (per-context, per-search); the helper stays source-agnostic with the 7-keyword-only-param signature.
- **The `__init__.py` files** — `infrastructure/linkedin/__init__.py` stays docstring-only (AGENTS.md rule #4).

## 4. Acceptance summary

- **15 REQs total**: 3 NEW (`linkedin-anti-bot-detector`) + 5 EXTENDED (`linkedin-auth-cookie`) + 4 EXTENDED (`linkedin-scraper`) + 3 EXTENDED (`linkedin-config`).
- **Every REQ has 2-3 Given/When/Then scenarios** (positive + negative where applicable).
- The v1 single-cookie `EnvLinkedInAuthCookieAdapter(SecretStr("AQE..."))` ctor still works (35 v1 tests stay GREEN).
- The new `MultiEnvLinkedInAuthCookiesAdapter(None, None, None, None).cookies() is None` (soft mode preserved).
- `is_cloudflare_challenge` returns `True` on the new `CLOUDFLARE_CHALLENGE_HTML` fixture, `False` on the existing healthy SERP and `BLOCK_PAGE_HTML` fixtures.
- `_make_fetch_one_page` closure precedence: **`is_cloudflare_challenge` → `is_auth_wall` → `is_block_page`** when `auth_cookies` is non-`None`; **`is_block_page` only** (v1 byte-identical) when `auth_cookies` is `None`.
- `ruff check`, `mypy` (project-wide, the correct invocation per v1 verify-report), and `pytest` are all GREEN.
- New test count delta: **+20 to +30** tests (the change is smaller than the v1 cycle — 6 production files, 5 test files).
- **No real `li_at` (or any other LinkedIn cookie) in any committed file** — only the synthetic 12-byte `"AQEAAAAQEAAA"` placeholder + field/env-var names appear in test code (AGENTS.md rule #7).
- **No `Co-Authored-By:` trailers** (AGENTS.md rule #6).
- **Conventional commits** (scope: `linkedin-stealth` for T-001..T-005, `linkedin-anti-bot` for the detector, `composition` for the wire, `docs` for README/.env).
- **The `playwright-stealth` invocation is byte-identical to the Indeed+InfoJobs precedent** (code review parity at the integration site).
- **The 4 production files keep their `__init__.py` docstring-only** (AGENTS.md rule #4).

## 5. Risks (carry-forward from proposal §"Risks", with spec-level mitigations)

| # | Risk (from proposal) | L | Spec-level mitigation |
|---|---|---|---|
| 1 | `playwright-stealth` may NOT bypass the LinkedIn + Cloudflare-2026-302-loop (confidence 0.55) | HIGH | `REQ-LST-SCR-001` (stealth is opt-in via ctor kwarg; `stealth=None` preserves v1), `REQ-LST-SCR-004` (soft-path `is_cloudflare_challenge` surfaces the failure clearly), `REQ-LST-CFG-001..003` (3 new cookies give the operator a fallback configuration path). The change is fully reversible. |
| 2 | Multi-cookie partial injection (4 cookies vs operator's 19+) | HIGH | `REQ-LST-COOKIE-002` (the Protocol accepts an arbitrary list, future changes can add more cookies without code changes), `REQ-LST-SCR-004` (the WARNING message is operator-actionable: "Consider setting LINKEDIN_JSESSIONID, LINKEDIN_BCOOKIE, LINKEDIN_LI_GC..."). |
| 3 | Cloudflare challenge page evolves (2026 selectors → 2027) | MED | `REQ-LST-CF-002` pins the 2026 selector set in the `CLOUDFLARE_CHALLENGE_HTML` fixture; a future change is 1 fixture + 1 detector function. |
| 4 | Backward compat with v1 `EnvLinkedInAuthCookieAdapter(SecretStr)` ctor (35 v1 tests) | MED | `REQ-LST-COOKIE-001` (v1 Protocol is KEPT), `REQ-LST-COOKIE-004` (v1 `EnvLinkedInAuthCookieAdapter` is KEPT UNCHANGED — its `cookie()` method is the v1 contract). |
| 5 | `playwright-stealth` Python port maintenance | LOW | Already pinned at `playwright-stealth>=2.0,<3.0` in `pyproject.toml:25`; 2.x API is stable. |
| 6 | Future LinkedIn-cookie-set growth | LOW | `REQ-LST-COOKIE-001` (Protocol accepts an arbitrary `list[tuple[str, SecretStr]]`). |
| 7 | `__repr__` cookie-count side-channel | LOW | `REQ-LST-COOKIE-005` (acceptable 1-bit side-channel; the operator's `ls -la .env` is richer). |
| 8 | 3 new env vars leak via process listings | LOW | Same risk as `LINKEDIN_LI_AT`; mitigated by `direnv` (per v1 README). |
| 9 | `is_cloudflare_challenge` false positive on healthy SERP | LOW | `REQ-LST-CF-003` (3 negative scenarios: healthy SERP, LinkedIn auth wall, cards-win). A healthy SERP with cards never matches. |
| 10 | V1 lessons not applied (e.g. `__init__.py` re-export hub) | LOW | `REQ-LST-COOKIE-001` (the v1 conftest companion is extended in `conftest.py`, NOT in `__init__.py`); the new adapter module follows the v1 path import. |

## 6. Source of truth links

- **Delta spec source**: `openspec/changes/backend-linkedin-stealth/spec.md` (this file)
- **Proposal**: Engram obs #366 (read in full for the 4 capability contracts + Q1-Q5 auto-resolved decisions)
- **Exploration**: Engram obs #365 (the 0.55 confidence + the `playwright-stealth` precedent + the `BLOCKED_PAGE_HTML` fixture references)
- **Trigger**: Engram obs #364 (the live `ERR_TOO_MANY_REDIRECTS` with the 152-char `li_at` + 19+ cookie list)
- **Precedent cycle (v1)**: Engram obs #362 (archive) + obs #355 (spec) + obs #356 (design) + obs #357 (tasks) + obs #358 (apply) + obs #360 (verify)
- **Pre-existing main specs** (will be EXTENDED on archive sync, not modified in this PR):
  - `openspec/specs/linkedin-auth-cookie/spec.md` — 4 pre-existing `REQ-LA-COOKIE-*` (singular, kept)
  - `openspec/specs/linkedin-scraper/spec.md` — 4 pre-existing `REQ-LI-SCR-*` + 6 pre-existing `REQ-LA-SCR-*` (all kept)
  - `openspec/specs/linkedin-config/spec.md` — 4 pre-existing `REQ-LA-CFG-*` (kept)
  - `openspec/specs/linkedin-auth-wall-detector/spec.md` — 6 pre-existing `REQ-LA-AWALL-*` (kept)
- **Sibling NEW spec (will be created on archive sync)**: `openspec/specs/linkedin-anti-bot-detector/spec.md` (3 new `REQ-LST-CF-*`)

## 7. OpenSpec syncs (for `sdd-archive` to do — NOT this phase)

This delta is **multi-capability** (1 file with 4 sections, mirrors the v1 multi-capability-delta pattern in obs #362). The `sdd-archive` phase will:
1. Create `openspec/specs/linkedin-anti-bot-detector/spec.md` from §"Capability: `linkedin-anti-bot-detector` (NEW)" above (NEW foundational, 3 `REQ-LST-CF-*`).
2. Extend `openspec/specs/linkedin-auth-cookie/spec.md` by APPENDING 5 new `REQ-LST-COOKIE-*` (the v1 4 `REQ-LA-COOKIE-*` stay byte-identical).
3. Extend `openspec/specs/linkedin-scraper/spec.md` by APPENDING 4 new `REQ-LST-SCR-*` (the v1 4 `REQ-LI-SCR-*` + 6 `REQ-LA-SCR-*` stay byte-identical).
4. Extend `openspec/specs/linkedin-config/spec.md` by APPENDING 3 new `REQ-LST-CFG-*` (the v1 4 `REQ-LA-CFG-*` stay byte-identical).
5. The mixed namespace (`REQ-LI-*` for URL builder + `REQ-LA-*` for cookie injection + `REQ-LST-*` for stealth) is intentional (per the v1 archive convention).

**Total after archive**: 4 global spec files extended, 1 new global spec file created. 15 new `REQ-LST-*` promoted to the canonical source of truth.
