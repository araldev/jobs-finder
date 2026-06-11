# Spec: `backend-linkedin-auth`

> **Status**: `spec` (ready for `sdd-design`)
> **Base**: `017d6fa` (HEAD on main; working tree clean; per `git status -s`)
> **Proposal**: Engram obs #354
> **Exploration**: Engram obs #353
> **Mode**: `both` (OpenSpec + Engram)
> **Strict TDD**: ACTIVE — `uv run pytest`; every scenario below is a real test, not a wish

## 1. Purpose

The `LinkedInPlaywrightScraper` v1 runs anonymously: each `search()` opens
a `BrowserContext` with only `user_agent` + `viewport`
(`infrastructure/linkedin/scraper.py:274-277`). LinkedIn responds to
public SERPs with a hidden sign-in modal in the HTML and a functional
cap of ~3-5 jobs per query — the rest of the stream sits behind an
auth wall and is ignored client-side. The operator (per user request
2026-06-10) wants to plumb their personal `li_at` session cookie via a
`LINKEDIN_LI_AT` env var so the Playwright `BrowserContext` carries an
authenticated session and the full stream resolves.

This change defines the CONTRACT for the cookie plumb: a new
`LinkedInAuthCookiePort` Protocol, a new `Settings.linkedin_li_at`
field with a Q1 (HARD `<8` chars, soft WARNING when absent) validator,
a per-context `ctx.add_cookies([...])` injection in
`LinkedInPlaywrightScraper.search()`, a `__repr__` masking contract
(no cookie value ever in logs), and a defensive `is_auth_wall(soup)`
detector that warns the operator when the SERP renders an auth-wall
variant despite a cookie having been injected. Out of scope:
programmatic login, auto-refresh, multi-account, DB persistence, OAuth,
and live-network testing.

## 2. Requirements

All requirements use the `REQ-LA-` namespace to make the delta easy to
grep across the repo. RFC 2119 keywords (MUST, SHALL, SHOULD, MAY) apply.
Every scenario is `Given/When/Then` and is mechanically testable
(returns a value, raises an exception, mutates an observable state, or
emits a log record).

---

### Capability: `linkedin-auth-cookie` (NEW)

**File anchors** (the spec REQUIRES these file locations, not the
implementation details inside them):
- Protocol declaration: `backend/src/jobs_finder/application/ports.py`
- Adapter: `backend/src/jobs_finder/infrastructure/linkedin/auth_cookie.py` (NEW)
- Scraper integration: `backend/src/jobs_finder/infrastructure/linkedin/scraper.py`

#### REQ-LA-COOKIE-001: `LinkedInAuthCookiePort` Protocol shape

**Capability**: `linkedin-auth-cookie`
**Statement**: The application layer MUST declare a
`LinkedInAuthCookiePort` Protocol with a single synchronous method
`def cookie(self) -> SecretStr | None` that returns the operator's
`li_at` session cookie value (a `pydantic.SecretStr` for log-masking)
or `None` when the operator has not configured one.

**Rationale**: The Protocol is the seam between application and
infrastructure; the sync signature mirrors `LocationResolverPort`
(per `location-resolver` spec §REQ-PROV-LOC-001) and keeps the
adapters trivially testable (no event loop required).

**Acceptance**:
- [ ] `LinkedInAuthCookiePort` lives in `application/ports.py` and has exactly one method: `def cookie(self) -> SecretStr | None: ...`
- [ ] `mypy --strict` validates that `EnvLinkedInAuthCookieAdapter` and `FakeLinkedInAuthCookiePort` both structurally conform to the Protocol
- [ ] The Protocol is NOT `@runtime_checkable` (mirrors the v1 `LocationResolverPort` choice)

**Scenarios**:

- **GIVEN** `EnvLinkedInAuthCookieAdapter` is constructed with a `SecretStr` value `"AQEAAAAQEAAA"` (12-byte ASCII synthetic, NOT a real `li_at`)
  - **WHEN** `adapter.cookie()` is called
  - **THEN** returns a `SecretStr` whose `get_secret_value() == "AQEAAAAQEAAA"`
  - **AND** the test `tests/unit/test_linkedin_auth_cookie.py::test_adapter_returns_cookie_when_set` passes

- **GIVEN** `EnvLinkedInAuthCookieAdapter` is constructed with `None`
  - **WHEN** `adapter.cookie()` is called
  - **THEN** returns `None` (the v1 anonymous-path sentinel)
  - **AND** the test `tests/unit/test_linkedin_auth_cookie.py::test_adapter_returns_none_when_unset` passes

- **GIVEN** a test double `FakeLinkedInAuthCookiePort(cookie=SecretStr("AQEAAAAQEAAA"))` is constructed
  - **WHEN** the test assigns `port: LinkedInAuthCookiePort = fake` (Protocol type annotation)
  - **THEN** `mypy --strict` is clean (structural conformance verified at type-check time)
  - **AND** the test `tests/unit/test_linkedin_auth_cookie.py::test_fake_double_conforms_to_protocol` passes

#### REQ-LA-COOKIE-002: `EnvLinkedInAuthCookieAdapter` returns `None` in soft mode

**Capability**: `linkedin-auth-cookie`
**Statement**: The adapter MUST return `None` (NOT raise, NOT log at
ERROR level) when the constructor receives `None` or when the
`Settings.linkedin_li_at` field is absent from the environment.

**Rationale**: Preserves v1 zero-config boot — an operator without a
`li_at` cookie MUST be able to start the app and run the scraper
anonymously (degraded but functional). The soft WARNING is logged at
the `app_factory.build_app()` startup, NOT inside the adapter (separation
of concerns).

**Acceptance**:
- [ ] `EnvLinkedInAuthCookieAdapter(None).cookie() is None`
- [ ] `EnvLinkedInAuthCookieAdapter(SecretStr("")).cookie() is None` (the `_normalize_empty_li_at` validator at `Settings` ctor coerces empty to `None` BEFORE the adapter sees it)
- [ ] The adapter does NOT import `logging` and does NOT emit log records of any level
- [ ] The adapter is a pure in-process value provider (no I/O, no `await`)

**Scenarios**:

- **GIVEN** `Settings()` is constructed with no `LINKEDIN_LI_AT` env var
  - **WHEN** `EnvLinkedInAuthCookieAdapter(effective_settings.linkedin_li_at).cookie()` is called
  - **THEN** returns `None`
  - **AND** the test `tests/unit/test_linkedin_auth_cookie.py::test_adapter_none_when_env_var_absent` passes
  - **AND** `app_factory.build_app()` emits a single WARNING log line "LinkedIn scraper running without auth cookie" (asserted in `tests/integration/test_linkedin_auth_cookie.py::test_startup_warning_when_cookie_absent`)

- **GIVEN** `Settings()` is constructed with `LINKEDIN_LI_AT=` (empty in `.env`)
  - **WHEN** the same adapter construction runs
  - **THEN** returns `None` (the empty-string path is the second acceptance bullet above)
  - **AND** the test `tests/unit/test_linkedin_auth_cookie.py::test_adapter_none_when_env_var_empty` passes

#### REQ-LA-COOKIE-003: `EnvLinkedInAuthCookieAdapter` returns a `SecretStr` value object

**Capability**: `linkedin-auth-cookie`
**Statement**: When `Settings.linkedin_li_at` is a non-empty
`SecretStr` (with `len(secret_value) >= 8`, per the Q1 validator in
REQ-LA-CFG-002), the adapter MUST return it as-is. The value object
MUST be a `pydantic.SecretStr` (NOT a plain `str`) so that `repr()` /
`str()` mask the value automatically.

**Rationale**: AGENTS.md rule #7 forbids `li_at` cookies from leaking
into the repo. `SecretStr` is the type-level enforcement: any code
path that does `print(settings.linkedin_li_at)` will print `**********`
instead of the real value. Returning the `SecretStr` (not the
unwrapped `str`) preserves that guarantee at the adapter boundary.

**Acceptance**:
- [ ] `EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA")).cookie()` returns a `SecretStr` instance
- [ ] `repr(adapter.cookie())` is `SecretStr('**********')` (the pydantic default masked form), NOT `'AQEAAAAQEAAA'`
- [ ] The adapter is `__slots__`-based (`__slots__ = ("_cookie",)`) for memory efficiency, matching the v1 `EnvLinkedInAuthCookieAdapter` style

**Scenarios**:

- **GIVEN** `Settings(linkedin_li_at=SecretStr("AQEAAAAQEAAA"))` (12 chars, valid per validator)
  - **WHEN** `adapter = EnvLinkedInAuthCookieAdapter(settings.linkedin_li_at)` is constructed
  - **THEN** `adapter.cookie()` returns a `SecretStr`
  - **AND** `adapter.cookie().get_secret_value() == "AQEAAAAQEAAA"`
  - **AND** `repr(adapter.cookie()) == "SecretStr('**********')"` (NOT the raw value)
  - **AND** the test `tests/unit/test_linkedin_auth_cookie.py::test_adapter_returns_secretstr_with_masked_repr` passes

- **GIVEN** the adapter is constructed with a 8-char `SecretStr` (the minimum-valid length)
  - **WHEN** the adapter is asked for the cookie
  - **THEN** returns the `SecretStr` (the boundary is inclusive: `len >= 8`)
  - **AND** the test `tests/unit/test_linkedin_auth_cookie.py::test_adapter_returns_secretstr_at_minimum_length_8` passes

#### REQ-LA-COOKIE-004: `LinkedInScraperSettings.__repr__` masks the cookie

**Capability**: `linkedin-auth-cookie`
**Statement**: `LinkedInScraperSettings.__repr__` MUST return a
string that contains `"<set>"` when `auth_cookie is not None` and
`"<unset>"` when it is. The string MUST NOT contain the cookie's
secret value, even as a substring. The same masking applies to the
`__repr__` of `LinkedInPlaywrightScraper` (the pre-change repr inherits
the settings repr by default, so the settings repr is the load-bearing
contract).

**Rationale**: The scraper's `__repr__` flows into exception tracebacks,
debug log lines, and `RequestIdLogFilter` output. A regression to a
plain `str` cookie would silently leak the value to operators reading
the log — the `SecretStr` type prevents the leak at the value-object
level, and the `__repr__` override prevents it at the settings-object
level (defense in depth).

**Acceptance**:
- [ ] `repr(LinkedInScraperSettings(user_agent=..., timeout_ms=..., auth_cookie=SecretStr("AQEAAAAQEAAA")))` contains `"<set>"` AND does NOT contain `"AQEAAAAQEAAA"`
- [ ] `repr(LinkedInScraperSettings(user_agent=..., timeout_ms=..., auth_cookie=None))` contains `"<unset>"`
- [ ] `LinkedInScraperSettings.__eq__` and `__hash__` include `auth_cookie` in their comparison/hash inputs (so two settings with different cookies are NOT equal)

**Scenarios**:

- **GIVEN** `LinkedInScraperSettings(user_agent="ua", timeout_ms=10000, auth_cookie=SecretStr("AQEAAAAQEAAA"))`
  - **WHEN** `repr(settings)` is called
  - **THEN** the returned string contains `"auth_cookie=<set>"` AND does NOT contain `"AQEAAAAQEAAA"` (the synthetic test value)
  - **AND** the test `tests/unit/test_linkedin_auth_cookie.py::test_settings_repr_masks_set_cookie` passes

- **GIVEN** `LinkedInScraperSettings(user_agent="ua", timeout_ms=10000, auth_cookie=None)`
  - **WHEN** `repr(settings)` is called
  - **THEN** the returned string contains `"auth_cookie=<unset>"`
  - **AND** the test `tests/unit/test_linkedin_auth_cookie.py::test_settings_repr_masks_unset_cookie` passes

- **GIVEN** two `LinkedInScraperSettings` instances differing only in `auth_cookie` (one with `SecretStr("AQEAAAAQEAAA")`, one with `SecretStr("DIFF_VAL_AQXQ"))`
  - **WHEN** `settings_a == settings_b` is evaluated
  - **THEN** returns `False` (the `__eq__` includes `auth_cookie`)
  - **AND** `hash(settings_a) != hash(settings_b)` (the `__hash__` includes `auth_cookie`)
  - **AND** the test `tests/unit/test_linkedin_auth_cookie.py::test_settings_eq_hash_includes_auth_cookie` passes

---

### Capability: `linkedin-scraper` (EXTENDED)

**File anchors**:
- `backend/src/jobs_finder/infrastructure/linkedin/scraper.py` (per-context injection in `search()` + `is_auth_wall` integration in `_make_fetch_one_page` closure)
- `backend/src/jobs_finder/infrastructure/linkedin/parsers.py` (NEW `is_auth_wall` pure function)

#### REQ-LA-SCR-001: `search()` reads the cookie from the injected port (not from env, not from globals)

**Capability**: `linkedin-scraper`
**Statement**: `LinkedInPlaywrightScraper.search()` MUST read the
`li_at` cookie from `self._settings.auth_cookie.cookie()` — never
from `os.environ`, never from a module-level global, never from a
hardcoded constant. The injected `LinkedInAuthCookiePort` is the only
source of truth.

**Rationale**: Mirrors the v1 `location_resolver` injection pattern
(per `linkedin-structured-location-fallback` spec). The
composition root wires the port; tests inject test doubles. Reading
from `os.environ` inside `search()` would make the scraper
non-deterministic and untestable (the env var is process-global).

**Acceptance**:
- [ ] `search()` calls `self._settings.auth_cookie.cookie()` (not `os.environ.get("LINKEDIN_LI_AT")`)
- [ ] `search()` does NOT import `os` or `os.environ` for the cookie lookup
- [ ] A test that swaps `self._settings.auth_cookie` with a `FakeLinkedInAuthCookiePort(SecretStr("SYNTHETIC"))` observes the SYNTHETIC value reaching `ctx.add_cookies`, NOT the real env var

**Scenarios**:

- **GIVEN** `LinkedInPlaywrightScraper` is constructed with `settings=LinkedInScraperSettings(..., auth_cookie=EnvLinkedInAuthCookieAdapter(SecretStr("SYNTHETIC_FROM_PORT")))` AND `LINKEDIN_LI_AT="REAL_ENV_VALUE"` is set in the process environment
  - **WHEN** `search("react", "Madrid")` runs against a `FakeBrowser`
  - **THEN** `fake_browser.new_context_calls[0]["cookies"]` contains `{"name": "li_at", "value": "SYNTHETIC_FROM_PORT", ...}` — NOT `"REAL_ENV_VALUE"`
  - **AND** the test `tests/unit/test_linkedin_scraper.py::test_search_reads_cookie_from_injected_port_not_env` passes

#### REQ-LA-SCR-002: `ctx.add_cookies` is called BEFORE the first navigation on the SAME `BrowserContext`

**Capability**: `linkedin-scraper`
**Statement**: When the port returns a non-None cookie,
`search()` MUST call `await ctx.add_cookies([{...}])` immediately
after `await self._browser.new_context(...)` returns and BEFORE the
first `paginated_search()` navigation, on the SAME `BrowserContext`
instance the loop uses. The injection MUST NOT happen on a new context
(cookie would not travel) and MUST NOT happen per-page in the loop
(cookie already travels with the context's cookie store).

**Rationale**: Playwright's `BrowserContext` shares the cookie store
with all pages in the context. One `add_cookies` call on the context
makes the cookie available to every page request the loop issues.
Doing it per-page would be wasteful and would not change the
semantic.

**Acceptance**:
- [ ] The `add_cookies` call is between `new_context()` and `paginated_search()` (per `scraper.py:274-295` — exact line numbers per the existing implementation)
- [ ] The `add_cookies` call uses the `ctx` returned by `new_context()` (not a separate context)
- [ ] The cookie shape passed to `add_cookies` is `{"name": "li_at", "value": <secret>, "domain": ".linkedin.com", "path": "/", "httpOnly": True, "secure": True}` (per Playwright `BrowserContext.add_cookies` API contract)

**Scenarios**:

- **GIVEN** `LinkedInPlaywrightScraper` is constructed with `auth_cookie=SecretStr("AQEAAAAQEAAA")` and a `FakeBrowser`/`FakePage` test double
  - **WHEN** `search("react", "Madrid", limit=10)` runs (limit=10 forces 1 page, not 2)
  - **THEN** `fake_browser.new_context_calls[0]["cookies"] == [{"name": "li_at", "value": "AQEAAAAQEAAA", "domain": ".linkedin.com", "path": "/", "httpOnly": True, "secure": True}]` (exact shape match)
  - **AND** `fake_browser.new_context_calls[0]` is the SAME context object that `fake_browser.new_context_calls[0].new_page_calls[0].page` came from
  - **AND** the test `tests/unit/test_linkedin_scraper.py::test_add_cookies_called_with_correct_shape` passes

#### REQ-LA-SCR-003: Soft mode (port returns `None`) skips `add_cookies` and logs a single WARNING

**Capability**: `linkedin-scraper`
**Statement**: When the port returns `None`, `search()` MUST NOT call
`ctx.add_cookies(...)` and MUST proceed to the pagination loop with
the v1 anonymous behavior. A single WARNING log line MUST be emitted
at `app_factory.build_app()` startup (NOT inside `search()` — startup
warning avoids per-search log spam) with the message
`"LinkedIn scraper running without auth cookie; SERP will hit the
auth wall and return a reduced list"`.

**Rationale**: The WARNING is an operator signal that the auth path
is OFF. The startup-only emission (vs. per-search) keeps the log
volume predictable. The auth-wall message in the warning primes the
operator to expect degraded results.

**Acceptance**:
- [ ] When `auth_cookie.cookie() is None`, the `add_cookies` call is skipped (no exception, no fallback to a hardcoded value)
- [ ] The startup WARNING is emitted ONCE per process start (not per `search()` call)
- [ ] The startup WARNING text contains the exact substring `"running without auth cookie"` (for ops greppability)
- [ ] The startup WARNING does NOT include the cookie value (the value is `None` in this path, but the assertion pins the negative case)

**Scenarios**:

- **GIVEN** `LinkedInPlaywrightScraper` is constructed with `auth_cookie=None`
  - **WHEN** `search("react", "Madrid", limit=10)` runs
  - **THEN** `fake_browser.new_context_calls[0]` does NOT have a `"cookies"` key (the legacy path is preserved)
  - **AND** the test `tests/unit/test_linkedin_scraper.py::test_no_add_cookies_call_when_auth_cookie_none` passes

- **GIVEN** `build_app()` is called with no `LINKEDIN_LI_AT` env var
  - **WHEN** the startup phase completes
  - **THEN** exactly one WARNING log record with `msg == "LinkedIn scraper running without auth cookie; SERP will hit the auth wall and return a reduced list"` is emitted
  - **AND** the test `tests/integration/test_linkedin_auth_cookie.py::test_startup_warning_when_cookie_absent` passes

#### REQ-LA-SCR-004: Cookie shape matches LinkedIn's issuance contract

**Capability**: `linkedin-scraper`
**Statement**: The cookie passed to `add_cookies` MUST set
`domain=".linkedin.com"` (the leading dot makes it match all
subdomains — `www.linkedin.com`, `es.linkedin.com`, etc.),
`path="/"` (applies to all paths), `http_only=True` (the cookie is
NOT exposed to JS — LinkedIn's `li_at` is server-side only), and
`secure=True` (HTTPS-only).

**Rationale**: LinkedIn issues `li_at` with these exact flags. A
different shape (e.g. `domain="linkedin.com"` without the leading dot)
would NOT match the subdomain the SERP actually uses, and the cookie
would silently not be sent. The `http_only` and `secure` flags match
the real cookie semantics — a regression here would either break the
auth (if `secure=True` is dropped, the browser may reject it) or
expose the cookie to JS (if `http_only=False`, the cookie is in
`document.cookie` and any XSS exposes it).

**Acceptance**:
- [ ] `add_cookies` payload contains `domain=".linkedin.com"` (NOT `"linkedin.com"`, NOT `"www.linkedin.com"`)
- [ ] `add_cookies` payload contains `path="/"`
- [ ] `add_cookies` payload contains `http_only=True`
- [ ] `add_cookies` payload contains `secure=True`
- [ ] The cookie `name` is exactly `"li_at"` (lowercase, the canonical name LinkedIn uses)

**Scenarios**:

- **GIVEN** a `LinkedInPlaywrightScraper` with `auth_cookie=SecretStr("AQEAAAAQEAAA")` and a `FakeBrowser` capturing the `add_cookies` call
  - **WHEN** `search()` runs
  - **THEN** the captured cookie dict equals `{"name": "li_at", "value": "AQEAAAAQEAAA", "domain": ".linkedin.com", "path": "/", "httpOnly": True, "secure": True}` (exact key set + value match)
  - **AND** the test `tests/unit/test_linkedin_scraper.py::test_add_cookies_shape_matches_linkedin_contract` passes (golden assertion)

#### REQ-LA-SCR-005: `search()` does NOT log the cookie value at any level

**Capability**: `linkedin-scraper`
**Statement**: `LinkedInPlaywrightScraper.search()` and its closure
`_make_fetch_one_page` MUST NOT log the cookie value at any level
(DEBUG/INFO/WARNING/ERROR). A test MUST capture all log records
emitted during a `search()` call (using `caplog` or an injected
`LogCapture` handler) and assert that no record's `message` or
`args` contains the synthetic test cookie string `"AQEAAAAQEAAA"`.

**Rationale**: AGENTS.md rule #7 forbids `li_at` cookies in the repo,
and the `SecretStr` type only protects `__repr__`/`__str__` — explicit
`logger.info("cookie=%s", cookie)` would unwrap the `SecretStr` and
leak. The test pins the no-leak contract at the integration boundary.

**Acceptance**:
- [ ] No code path in `LinkedInPlaywrightScraper.search()`, `_make_fetch_one_page`, or `_navigate_and_wait` calls `logger.<level>(..., cookie)` or `logger.<level>(f"...{cookie}...")` with a non-masked cookie value
- [ ] A test using `caplog` captures all log records during `search()` and asserts no record contains the synthetic cookie string

**Scenarios**:

- **GIVEN** `LinkedInPlaywrightScraper` with `auth_cookie=SecretStr("AQEAAAAQEAAA")` AND a `FakeBrowser` that emits one INFO log line per request
  - **WHEN** `search("react", "Madrid", limit=10)` runs AND `caplog` is set to level `DEBUG`
  - **THEN** no captured log record's `message` or `args` contains the substring `"AQEAAAAQEAAA"`
  - **AND** the test `tests/unit/test_linkedin_scraper.py::test_search_does_not_log_cookie_value` passes

#### REQ-LA-SCR-006: Cookie is injected ONCE per `search()` (per-context, not per-page)

**Capability**: `linkedin-scraper`
**Statement**: `search()` MUST call `add_cookies` exactly ONCE per
invocation (per the `new_context()` lifecycle), NOT per page in the
pagination loop. Two calls to `search()` MUST each call `add_cookies`
exactly once (so the per-search lifecycle is observable). The cookie
travels with every page request in the loop automatically because
Playwright's `BrowserContext` shares the cookie store with all pages
in the context.

**Rationale**: The per-context injection is the v1 pattern; doing it
per-page would be wasteful and would not change the observable
behavior. The per-search count is the load-bearing contract for ops
debugging (e.g. when monitoring how many cookie injections happen
over a window of time).

**Acceptance**:
- [ ] 1 call to `search()` → exactly 1 call to `add_cookies` (regardless of `limit` or `max_pages`)
- [ ] 2 calls to `search()` → exactly 2 calls to `add_cookies` (one per `new_context` lifecycle)
- [ ] The injection happens INSIDE the `try:` block of `search()` (before `paginated_search()`), so an exception during the loop does NOT leave the cookie set on a context that is then closed

**Scenarios**:

- **GIVEN** `LinkedInPlaywrightScraper` with `auth_cookie=SecretStr("AQEAAAAQEAAA")` and a `FakeBrowser` that returns 25 cards per page for 3 pages
  - **WHEN** `search("react", "Madrid", limit=50)` runs (forcing 2 pages)
  - **THEN** `len(fake_browser.add_cookies_calls) == 1` (one per `search()`, NOT per page)
  - **AND** the test `tests/unit/test_linkedin_scraper.py::test_add_cookies_called_once_per_search` passes

- **GIVEN** the same scraper and `FakeBrowser`
  - **WHEN** `await search("react", "Madrid", limit=10)` runs twice in sequence
  - **THEN** `len(fake_browser.add_cookies_calls) == 2` (one per `search()` invocation)
  - **AND** the test `tests/unit/test_linkedin_scraper.py::test_add_cookies_called_once_per_search_for_multiple_searches` passes

---

### Capability: `linkedin-config` (EXTENDED)

**File anchors**:
- `backend/src/jobs_finder/infrastructure/config.py` (new `linkedin_li_at` field + 2 `field_validator`s)

#### REQ-LA-CFG-001: `Settings.linkedin_li_at` env var binding

**Capability**: `linkedin-config`
**Statement**: The `Settings` model MUST declare a new field
`linkedin_li_at: SecretStr | None` (default `None`) bound to env var
`LINKEDIN_LI_AT` (case-insensitive, per pydantic-settings standard)
via `validation_alias=AliasChoices("LINKEDIN_LI_AT", "linkedin_li_at")`.
The model-level `env_prefix="LINKEDIN_"` would resolve the same env
var but the explicit `AliasChoices` survives a future prefix rename
(per the `linkedin_max_pages` precedent at `config.py:283-286`).

**Rationale**: Mirrors the v1 `llm_api_key` pattern at
`config.py:714-743` (the `SecretStr` + `AliasChoices` + empty-string
normalization chain). The `SecretStr | None` type enables the
kill-switch semantic (the `None` path = anonymous scraper) and the
log-masking contract (the `SecretStr` path masks `__repr__`).

**Acceptance**:
- [ ] `Settings(linkedin_li_at=SecretStr("AQEAAAAQEAAA")).linkedin_li_at.get_secret_value() == "AQEAAAAQEAAA"`
- [ ] `Settings()` (no env var) has `linkedin_li_at is None`
- [ ] When `LINKEDIN_LI_AT=AQEAAAAQEAAA` is in the process env, `Settings().linkedin_li_at.get_secret_value() == "AQEAAAAQEAAA"`
- [ ] When `linkedin_li_at=abc` (programmatic), the validator raises `ValueError` (covered by REQ-LA-CFG-002)

**Scenarios**:

- **GIVEN** `LINKEDIN_LI_AT=AQEAAAAQEAAA` is in the process env
  - **WHEN** `Settings()` is constructed
  - **THEN** `settings.linkedin_li_at.get_secret_value() == "AQEAAAAQEAAA"`
  - **AND** the test `tests/unit/test_linkedin_config.py::test_settings_reads_linkedin_li_at_from_env` passes

- **GIVEN** no `LINKEDIN_LI_AT` env var is set
  - **WHEN** `Settings()` is constructed
  - **THEN** `settings.linkedin_li_at is None`
  - **AND** the test `tests/unit/test_linkedin_config.py::test_settings_linkedin_li_at_defaults_to_none` passes

- **GIVEN** programmatic `Settings(linkedin_li_at=SecretStr("AQEAAAAQEAAA"))`
  - **WHEN** the construction completes
  - **THEN** `settings.linkedin_li_at.get_secret_value() == "AQEAAAAQEAAA"` (the second choice in `AliasChoices` accepts the programmatic form)
  - **AND** the test `tests/unit/test_linkedin_config.py::test_settings_linkedin_li_at_programmatic_construction` passes

#### REQ-LA-CFG-002: Q1 validator rejects values with `len < 8` characters

**Capability**: `linkedin-config`
**Statement**: A `field_validator('linkedin_li_at', mode="after")` on
the `Settings` model MUST raise `pydantic.ValidationError` (which
surfaces as `ValueError` in the v1 callers) when the value is present
and has fewer than 8 characters, with the message
`"LINKEDIN_LI_AT must be at least 8 characters (got <N>); check for
typos or unset the variable to run the scraper anonymously."`. The
threshold of 8 chars catches operator typos (`LINKEDIN_LI_AT=abc`)
while accepting every realistic real cookie (real `li_at` values are
~150 chars).

**Rationale**: Q1 option C in the proposal. The HARD error at boot
fails fast and surfaces the typo in the operator's first log line;
the SOFT WARNING at startup when the value is absent preserves v1
zero-config boot. The 8-char threshold is arbitrary but conservative
(real cookies are much longer).

**Acceptance**:
- [ ] `Settings(linkedin_li_at=SecretStr("abc"))` raises `ValidationError` with the message containing `"must be at least 8 characters"`
- [ ] `Settings(linkedin_li_at=SecretStr("1234567"))` (7 chars) raises
- [ ] `Settings(linkedin_li_at=SecretStr("12345678"))` (8 chars) succeeds
- [ ] `Settings(linkedin_li_at=SecretStr("AQEAAAAQEAAA"))` (12 chars) succeeds
- [ ] The validator's error message includes the actual length (`"got 3"`, `"got 7"`) so the operator can self-diagnose

**Scenarios**:

- **GIVEN** programmatic `Settings(linkedin_li_at=SecretStr("abc"))` (3 chars, a clear typo)
  - **WHEN** `Settings()` is constructed
  - **THEN** raises `pydantic.ValidationError` whose `__str__` contains the substring `"must be at least 8 characters"` AND the substring `"got 3"`
  - **AND** the test `tests/unit/test_linkedin_config.py::test_settings_rejects_short_li_at_3_chars` passes

- **GIVEN** programmatic `Settings(linkedin_li_at=SecretStr("1234567"))` (7 chars, the boundary)
  - **WHEN** `Settings()` is constructed
  - **THEN** raises `pydantic.ValidationError` (the threshold is inclusive `<8`, so 7 is rejected)
  - **AND** the test `tests/unit/test_linkedin_config.py::test_settings_rejects_short_li_at_7_chars` passes

- **GIVEN** programmatic `Settings(linkedin_li_at=SecretStr("12345678"))` (8 chars, the minimum valid)
  - **WHEN** `Settings()` is constructed
  - **THEN** succeeds; `settings.linkedin_li_at.get_secret_value() == "12345678"`
  - **AND** the test `tests/unit/test_linkedin_config.py::test_settings_accepts_minimum_length_8` passes

#### REQ-LA-CFG-003: The validator is a no-op when the value is `None`

**Capability**: `linkedin-config`
**Statement**: The Q1 `mode="after"` validator MUST return
`v: SecretStr | None` unchanged when `v is None` (the v1 zero-config
default). Similarly, a `mode="before"` validator MUST normalize
empty-string inputs (`""`, `SecretStr("")`) to `None` so the
kill-switch contract holds at the adapter boundary.

**Rationale**: The v1 `llm_api_key` pattern (`config.py:714-743`) is
the precedent. An empty env var (`LINKEDIN_LI_AT=`) MUST behave the
same as a missing env var (no `LINKEDIN_LI_AT` at all) so the
operator can comment-out the var by setting it to empty (a common
ops pattern).

**Acceptance**:
- [ ] `Settings(linkedin_li_at=None).linkedin_li_at is None` (the `None` path is preserved)
- [ ] `Settings(linkedin_li_at=SecretStr("")).linkedin_li_at is None` (the empty-SecretStr path is normalized)
- [ ] `Settings(linkedin_li_at="").linkedin_li_at is None` (the empty-string path is normalized)
- [ ] When `LINKEDIN_LI_AT=` (empty) is in the env, `Settings().linkedin_li_at is None`

**Scenarios**:

- **GIVEN** `Settings(linkedin_li_at=None)`
  - **WHEN** the construction completes
  - **THEN** `settings.linkedin_li_at is None` (no exception)
  - **AND** the test `tests/unit/test_linkedin_config.py::test_settings_accepts_none_li_at` passes

- **GIVEN** `Settings(linkedin_li_at=SecretStr(""))` (the 2nd shape: SecretStr wrapping empty string)
  - **WHEN** the construction completes
  - **THEN** `settings.linkedin_li_at is None` (the `_normalize_empty_li_at` mode=before validator coerces to `None`)
  - **AND** the test `tests/unit/test_linkedin_config.py::test_settings_normalizes_empty_secret_to_none` passes

- **GIVEN** `Settings(linkedin_li_at="")` (the 3rd shape: plain empty string)
  - **WHEN** the construction completes
  - **THEN** `settings.linkedin_li_at is None` (same normalization path)
  - **AND** the test `tests/unit/test_linkedin_config.py::test_settings_normalizes_empty_string_to_none` passes

#### REQ-LA-CFG-004: `Settings.__repr__` does not include the cookie value

**Capability**: `linkedin-config`
**Statement**: `repr(Settings(linkedin_li_at=SecretStr("AQEAAAAQEAAA")))`
MUST NOT contain the substring `"AQEAAAAQEAAA"`. The `SecretStr` type
already enforces this at the field level (its `__repr__` masks to
`SecretStr('**********')`), but a test MUST assert the contract at the
`Settings` repr level (in case a future field accidentally accepts a
plain `str`).

**Rationale**: Defense in depth — the field-level `SecretStr` is the
primary guarantee; the `Settings`-repr assertion is the regression
check. A test that fails immediately on a plain-`str` regression is
cheaper than tracing a leaked cookie through 6 months of log lines.

**Acceptance**:
- [ ] `repr(Settings(linkedin_li_at=SecretStr("AQEAAAAQEAAA")))` does NOT contain `"AQEAAAAQEAAA"`
- [ ] The test asserts the negative: it searches for the synthetic value as a substring and asserts `False`

**Scenarios**:

- **GIVEN** `Settings(linkedin_li_at=SecretStr("AQEAAAAQEAAA"))` (programmatic)
  - **WHEN** `repr(settings)` is evaluated
  - **THEN** the returned string does NOT contain the substring `"AQEAAAAQEAAA"`
  - **AND** the test `tests/unit/test_linkedin_config.py::test_settings_repr_does_not_leak_cookie_value` passes

---

### Capability: `linkedin-auth-wall-detector` (NEW)

**File anchors**:
- `backend/src/jobs_finder/infrastructure/linkedin/parsers.py` (NEW `is_auth_wall(soup)` pure function)
- `backend/src/jobs_finder/infrastructure/linkedin/scraper.py` (integration in `_make_fetch_one_page` closure)

#### REQ-LA-AWALL-001: `is_auth_wall(soup)` is a pure function

**Capability**: `linkedin-auth-wall-detector`
**Statement**: The function `is_auth_wall(soup: BeautifulSoup) -> bool`
MUST be a pure function in
`backend/src/jobs_finder/infrastructure/linkedin/parsers.py`. Pure
means: no I/O, no `await`, no module-level mutable state, no logging
side-effects. The function's only inputs are its `soup` argument; its
only output is a `bool`.

**Rationale**: Mirrors the v1 `is_block_page` precedent (lines 213-242
of `parsers.py`). A pure function is trivially testable with the
existing `BLOCK_PAGE_HTML` and `SEARCH_PAGE_HTML` fixtures (no
Playwright, no async). The semantic split between `is_block_page`
(0 cards + auth signals = 502 path) and `is_auth_wall` (auth-wall
class + 0 cards = WARNING path) is load-bearing for the operator
observability value (per Q3 in the proposal).

**Acceptance**:
- [ ] `is_auth_wall` lives in `parsers.py` next to `is_block_page`
- [ ] The function signature is `def is_auth_wall(soup: BeautifulSoup) -> bool`
- [ ] The function does NOT import `logging` or emit log records
- [ ] The function does NOT mutate the input `soup` (pure read)

**Scenarios**:

- **GIVEN** `is_auth_wall` is imported from `jobs_finder.infrastructure.linkedin.parsers`
  - **WHEN** `inspect.signature(is_auth_wall)` is introspected
  - **THEN** returns `(soup: BeautifulSoup) -> bool`
  - **AND** the test `tests/unit/test_linkedin_auth_wall.py::test_is_auth_wall_signature` passes

- **GIVEN** `is_auth_wall(BeautifulSoup(BLOCK_PAGE_HTML))` is called
  - **WHEN** the result is captured
  - **THEN** it returns `True` (the BLOCK_PAGE_HTML fixture has `<body class="auth-wall">`)
  - **AND** the input `soup` is NOT mutated (`soup.prettify()` after the call returns the same bytes as before)
  - **AND** the test `tests/unit/test_linkedin_auth_wall.py::test_is_auth_wall_is_pure_no_mutation` passes

#### REQ-LA-AWALL-002: `is_auth_wall` returns `True` for the `BLOCK_PAGE_HTML` fixture

**Capability**: `linkedin-auth-wall-detector`
**Statement**: `is_auth_wall(BeautifulSoup(BLOCK_PAGE_HTML))` MUST
return `True`. The existing `BLOCK_PAGE_HTML` fixture
(`backend/tests/fixtures/linkedin_search.py:80-98`) has
`<body class="auth-wall">` AND zero job cards — both conditions
required by the new detector.

**Rationale**: The fixture is the canonical "auth wall with no
results" representation. Reusing the fixture for the new detector
(the v1 `is_block_page` already uses it) keeps the test suite
consistent and proves the two functions are testing distinct semantics
on the same HTML.

**Acceptance**:
- [ ] `is_auth_wall(BeautifulSoup(BLOCK_PAGE_HTML)) is True`
- [ ] The test asserts the positive: it parses the fixture, calls the function, asserts `True`

**Scenarios**:

- **GIVEN** the `BLOCK_PAGE_HTML` string from `tests/fixtures/linkedin_search.py`
  - **WHEN** `is_auth_wall(BeautifulSoup(BLOCK_PAGE_HTML, "html.parser"))` is called
  - **THEN** returns `True`
  - **AND** the test `tests/unit/test_linkedin_auth_wall.py::test_is_auth_wall_true_for_block_page_fixture` passes

#### REQ-LA-AWALL-003: `is_auth_wall` returns `False` for a healthy SERP

**Capability**: `linkedin-auth-wall-detector`
**Statement**: `is_auth_wall(BeautifulSoup(SEARCH_PAGE_HTML))` MUST
return `False`. The existing `SEARCH_PAGE_HTML` fixture (per
`tests/fixtures/linkedin_search.py:21-78`) is a healthy SERP with
multiple `<div data-entity-urn="...">` job cards and NO
`<body class="auth-wall">` — the detector's "cards win, no false
positive" rule returns `False`.

**Rationale**: The semantic split between `is_block_page` (502 path)
and `is_auth_wall` (WARNING path) requires that healthy SERPs do NOT
trigger the new detector. The `SEARCH_PAGE_HTML` fixture is the
canonical healthy SERP and the contract anchor.

**Acceptance**:
- [ ] `is_auth_wall(BeautifulSoup(SEARCH_PAGE_HTML)) is False`
- [ ] The test asserts the negative: parses the healthy fixture, calls the function, asserts `False`

**Scenarios**:

- **GIVEN** the `SEARCH_PAGE_HTML` string from `tests/fixtures/linkedin_search.py`
  - **WHEN** `is_auth_wall(BeautifulSoup(SEARCH_PAGE_HTML, "html.parser"))` is called
  - **THEN** returns `False` (no `auth-wall` class on the body; job cards present, so the `body.auth-wall` selector matches nothing relevant)
  - **AND** the test `tests/unit/test_linkedin_auth_wall.py::test_is_auth_wall_false_for_healthy_serp` passes

#### REQ-LA-AWALL-004: `is_auth_wall` returns `False` when cards are present even with auth-wall class (cards win)

**Capability**: `linkedin-auth-wall-detector`
**Statement**: When the parsed HTML has BOTH a `body.auth-wall` (or
`.auth-wall` descendant) AND at least one job card (`<div
data-entity-urn="...">`), the function MUST return `False` — cards
win, the auth-wall class is a false positive (defensive markup from
LinkedIn on a session that DOES see results).

**Rationale**: The pre-change `is_block_page` already pins this
"cards win" rule (per `parsers.py:233-234` and its scenario
`test_is_block_page_false_when_cards_present`). The new `is_auth_wall`
MUST use the same rule so the two functions share semantics and
produce consistent verdicts on the same HTML. The rule prevents
false-positive WARNINGs on healthy SERPs that happen to render the
`auth-wall` class on a sub-element.

**Acceptance**:
- [ ] `is_auth_wall(BeautifulSoup('<body class="auth-wall"><div data-entity-urn="urn:li:jobPosting:1"></div></body>'))` returns `False`
- [ ] The "cards win" rule is the same rule used in `is_block_page` (consistency)
- [ ] The test pins the false-positive suppression

**Scenarios**:

- **GIVEN** an HTML fragment `<body class="auth-wall"><div data-entity-urn="urn:li:jobPosting:1"></div></body>` (auth-wall class + 1 card)
  - **WHEN** `is_auth_wall(BeautifulSoup(fragment, "html.parser"))` is called
  - **THEN** returns `False` (cards win, the auth-wall signal is a false positive)
  - **AND** the test `tests/unit/test_linkedin_auth_wall.py::test_is_auth_wall_false_when_cards_present_even_with_auth_wall_class` passes

#### REQ-LA-AWALL-005: `is_auth_wall` WARNING log inside `_make_fetch_one_page`

**Capability**: `linkedin-auth-wall-detector`
**Statement**: Inside `LinkedInPlaywrightScraper._make_fetch_one_page`,
AFTER `is_block_page(soup)` returns `False` (so the page is not a
hard block) AND BEFORE `_parse_cards(soup, remaining)` is called, the
closure MUST check `is_auth_wall(soup)` and emit a single WARNING log
line when it returns `True`. The WARNING message MUST be
`"LinkedIn SERP appears auth-walled despite cookie injection; cookie
may be expired. Returning <N> jobs from this page (degraded)."` where
`<N>` is `len(jobs)` from the parsed page (the value the page WOULD
return). The closure MUST continue parsing and return the parsed
jobs (does NOT raise, does NOT short-circuit).

**Rationale**: The WARNING is the operator signal that the cookie
may be expired (the auth wall is showing despite the cookie). The
scraper still returns the partial results so the user sees
degraded-but-not-empty responses (matching the v1 partial-results
contract on rate-limit responses). The "log after block-page check,
before parse" position ensures the WARNING fires only on pages that
ALSO have results (so the operator sees "degraded" not "0 results").

**Acceptance**:
- [ ] When `is_auth_wall(soup) is True` and `is_block_page(soup) is False`, a WARNING log is emitted with the exact message prefix `"LinkedIn SERP appears auth-walled despite cookie injection"`
- [ ] When `is_auth_wall(soup) is True`, the closure still calls `_parse_cards` and returns its result (does NOT raise)
- [ ] The WARNING message contains the count of jobs from the page (so the operator sees `"Returning <N> jobs"`)
- [ ] The WARNING is emitted ONCE per page that triggers it (not per `search()` — a multi-page search can hit the wall on a subset of pages)

**Scenarios**:

- **GIVEN** a `LinkedInPlaywrightScraper` with `auth_cookie=SecretStr("AQEAAAAQEAAA")` AND a `FakeBrowser` that returns `BLOCK_PAGE_HTML`-shaped HTML with 0 cards (auth wall with 0 cards)
  - **WHEN** `search()` runs AND `caplog` is set to level `WARNING`
  - **THEN** the closure logs the WARNING `"LinkedIn SERP appears auth-walled despite cookie injection; cookie may be expired. Returning 0 jobs from this page (degraded)."`
  - **AND** `search()` returns `[]` (the empty list, NOT an exception)
  - **AND** the test `tests/unit/test_linkedin_scraper.py::test_closure_warns_on_auth_wall_zero_cards` passes

- **GIVEN** a `FakeBrowser` that returns `BLOCK_PAGE_HTML`-shaped HTML with 3 cards (the edge case: auth wall signal + cards present)
  - **WHEN** `search()` runs
  - **THEN** NO WARNING is emitted (the "cards win" rule from REQ-LA-AWALL-004)
  - **AND** `search()` returns the 3 parsed jobs
  - **AND** the test `tests/unit/test_linkedin_scraper.py::test_closure_does_not_warn_when_cards_present_with_auth_wall_class` passes (false-positive suppression at the closure level)

#### REQ-LA-AWALL-006: `is_auth_wall` does NOT raise; an auth-walled page returns whatever was collected

**Capability**: `linkedin-auth-wall-detector`
**Statement**: When `is_auth_wall(soup) is True` AND the page yields
0 cards, the scraper MUST return `[]` (an empty list) — NOT raise a
`LinkedInParseError`, NOT raise a `LinkedInBlockedError`. The
WARNING is the operator signal; the empty list is the response
contract.

**Rationale**: This is a deviation from `is_block_page`'s
`LinkedInBlockedError` raise (the 502 path). The deviation is
intentional: an auth wall detected despite a cookie injection is a
soft failure (operator can rotate the cookie); the `LinkedInBlockedError`
raise would be a hard failure (route returns 502). The spec
deliberately keeps the response graceful — the user gets an empty
list (matching the v1 anonymous-path behavior) instead of a 502.

**Acceptance**:
- [ ] `search()` on an auth-walled page (auth wall + 0 cards) returns `[]` (empty list), does NOT raise
- [ ] The WARNING log is the only signal — no exception type is added to the LinkedIn exception hierarchy for this path
- [ ] The behavior is consistent with the v1 anonymous-path contract (anonymous search hitting the auth wall returns `[]` with no WARNING; auth-cookie search hitting the auth wall returns `[]` WITH WARNING)

**Scenarios**:

- **GIVEN** a `LinkedInPlaywrightScraper` with `auth_cookie=SecretStr("AQEAAAAQEAAA")` AND a `FakeBrowser` that returns `BLOCK_PAGE_HTML` HTML (auth wall, 0 cards) for every page
  - **WHEN** `search("react", "Madrid", limit=20)` runs
  - **THEN** returns `[]` (an empty list, not an exception)
  - **AND** the test `tests/unit/test_linkedin_scraper.py::test_closure_returns_empty_list_on_auth_wall_no_raise` passes

---

## 3. Out of scope (explicit, from proposal §2.2)

- **Programmatic login** (navigate to `linkedin.com/login`, fill form, submit) — the operator provides the cookie via env var; the scraper does NOT obtain it.
- **Auto-refresh of the cookie** — when `li_at` expires (typical: ~1 year), the scraper degrades to v1 anonymous behavior and `is_auth_wall` emits a WARNING.
- **Multi-account / multi-cookie** — one `LINKEDIN_LI_AT` per process instance.
- **DB / Redis persistence of the cookie** — env var is the only source of truth.
- **OAuth flow** — LinkedIn does not expose OAuth for first-party job scraping.
- **Modifying the `JobSearchPort` Protocol** — the cookie is injected via `LinkedInScraperSettings` (additive kwarg), not via the Port signature.
- **Modifying the `paginated_search` helper** — the cookie is per-context, applied before the loop; the helper stays source-agnostic.
- **Modifying the other 2 scrapers (Indeed, InfoJobs)** — their anti-bot measures are different (Distil, Geetest); the cookie pattern does not apply directly.
- **Replacing `is_block_page` with `is_auth_wall`** — they have distinct semantics and coexist; `is_block_page` is preserved untouched.
- **Committing a real `li_at`** — AGENTS.md rule #7; the test uses the synthetic 12-byte value `"AQEAAAAQEAAA"`.
- **Changing the frontend HTTP contract** — `GET /jobs?q=...&location=...` is byte-identical; the cookie is internal to the scraper.
- **Live test against real LinkedIn** — NOT required; the cookie is validated offline via the `ctx.add_cookies` call shape (per the Q5 decision in the proposal).

## 4. Acceptance summary

| Gate | Expected |
|---|---|
| New capabilities | 2 (`linkedin-auth-cookie`, `linkedin-auth-wall-detector`) |
| Modified capabilities | 2 (`linkedin-scraper`, `linkedin-config`) |
| New requirements | 20 (4 for `linkedin-auth-cookie` + 6 for `linkedin-scraper` + 4 for `linkedin-config` + 6 for `linkedin-auth-wall-detector`; the §2 body has 20 REQ-LA-*, including REQ-LA-AWALL-006; the original summary table off-by-one was fixed in archive cleanup) |
| Scenarios per requirement | ≥2 (positive + negative) |
| New test files | 4 (`tests/unit/test_linkedin_auth_cookie.py`, `tests/unit/test_linkedin_auth_wall.py`, `tests/integration/test_linkedin_auth_cookie.py`, plus the extended `tests/unit/test_linkedin_scraper.py`) |
| Estimated new tests | 14-18 (9 port + 3 detector + 4 scraper-extend + 1-2 integration) |
| Quality gates | `ruff check` + `ruff format --check` + `mypy --strict` + `pytest` all GREEN |
| Baseline preserved | 1,142+ existing tests continue to pass (no regressions) |
| Sensitive data in repo | NO real `li_at` value; only the 12-byte synthetic `"AQEAAAAQEAAA"` appears in test code |

## 5. Risks (carry-forward from proposal §8, with spec-level mitigations)

| # | Risk | Spec mitigation |
|---|---|---|
| 1 | Real `li_at` cookie leaks into the repo (AGENTS.md rule #7) | REQ-LA-COOKIE-001 (Protocol uses `SecretStr`), REQ-LA-COOKIE-003 (adapter returns `SecretStr`), REQ-LA-COOKIE-004 (settings `__repr__` masks), REQ-LA-SCR-005 (no log leak), REQ-LA-CFG-004 (settings repr no leak) |
| 2 | Expired cookie produces degraded results without operator awareness | REQ-LA-AWALL-002 (detector returns True on the BLOCK_PAGE_HTML fixture), REQ-LA-AWALL-005 (WARNING log emitted at the closure), REQ-LA-AWALL-006 (returns empty list, does not raise) |
| 3 | LinkedIn changes the cookie name (e.g. `JSESSIONID`) | REQ-LA-SCR-004 pins the cookie name to `"li_at"` and the shape to LinkedIn's issuance contract; a future change would update both the spec and the `scraper.py` call site |
| 4 | `add_cookies` API change in Playwright | REQ-LA-SCR-002 pins the exact shape; the test is a golden assertion that fails on any shape drift |
| 5 | Q1 validator threshold (8 chars) too aggressive for future cookies | REQ-LA-CFG-002 makes the threshold explicit; the message includes the actual length so operators can self-diagnose; a follow-up change can lower the threshold |
| 6 | Test doubles in pre-change tests don't conform to the new Protocol | REQ-LA-COOKIE-001 acceptance bullet covers `mypy --strict` conformance; the new `FakeLinkedInAuthCookiePort` companion in `tests/conftest.py` is the default for new tests |
| 7 | Concurrent `search()` calls share state | REQ-LA-SCR-002 pins the per-context lifecycle; each `search()` opens a fresh `new_context()` and the `add_cookies` is inside the per-search `try` block |
| 8 | `is_auth_wall` false positives on incidental `class="auth-wall"` elements | REQ-LA-AWALL-004 pins the "cards win" rule; REQ-LA-AWALL-005 scenario covers the false-positive suppression at the closure level |
| 9 | Operator configures `LINKEDIN_LI_AT` with an expired value | REQ-LA-AWALL-005 WARNING is the operator signal; the README FAQ "what if my cookie expires" links to the detector |
| 10 | `Settings` repr leaks the cookie via a future plain-`str` regression | REQ-LA-CFG-004 pins the no-leak contract with a test that searches for the synthetic value as a substring |
