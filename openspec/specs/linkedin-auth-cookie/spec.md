# Spec: `linkedin-auth-cookie` — `LinkedInAuthCookiePort` + `EnvLinkedInAuthCookieAdapter`

> **Promoted to source of truth on 2026-06-10** from
> `openspec/changes/backend-linkedin-auth/spec.md` §"Capability:
> `linkedin-auth-cookie` (NEW)" (Domain 1 of the multi-capability
> delta spec).
>
> This is a NEW capability delta — no prior
> `openspec/specs/linkedin-auth-cookie/spec.md` existed. The delta
> is promoted in full as the foundational spec for the capability,
> capturing the `LinkedInAuthCookiePort` Protocol, the
> `EnvLinkedInAuthCookieAdapter`, and the `LinkedInScraperSettings`
> `__repr__` masking contract. Source observation IDs for
> traceability: explore #353, proposal #354, spec #355, design
> #356, tasks #357, apply-progress #358, verify-report #360.

## Purpose

The `LinkedInPlaywrightScraper` v1 runs anonymously: each
`search()` opens a `BrowserContext` with only `user_agent` +
`viewport`. LinkedIn responds to public SERPs with a hidden
sign-in modal in the HTML and a functional cap of ~3-5 jobs per
query — the rest of the stream sits behind an auth wall and is
ignored client-side. The `linkedin-auth-cookie` capability
plumbs the operator's `li_at` session cookie via a
`LINKEDIN_LI_AT` env var so the Playwright `BrowserContext`
carries an authenticated session and the full stream resolves.

The capability is the **application-layer seam** between
infrastructure (the env read) and the LinkedIn scraper (the
cookie consumer). The Protocol is the contract; the adapter is
the v1 implementation. The capability does NOT cover the
scraper-side injection (that's `linkedin-scraper`), the
`Settings` field (that's `linkedin-config`), or the auth-wall
detector (that's `linkedin-auth-wall-detector`).

## Requirements

### REQ-LA-COOKIE-001 — `LinkedInAuthCookiePort` Protocol shape

The application layer MUST declare a
`LinkedInAuthCookiePort` Protocol (in
`backend/src/jobs_finder/application/ports.py`) with a single
synchronous method `def cookie(self) -> SecretStr | None` that
returns the operator's `li_at` session cookie value (a
`pydantic.SecretStr` for log-masking) or `None` when the
operator has not configured one.

The Protocol is NOT `@runtime_checkable` (mirrors the v1
`LocationResolverPort` choice). The sync signature mirrors
`LocationResolverPort` (per `location-resolver` spec
§REQ-PROV-LOC-001) and keeps the adapters trivially testable
(no event loop required). `mypy --strict` MUST validate that
`EnvLinkedInAuthCookieAdapter` and `FakeLinkedInAuthCookiePort`
both structurally conform to the Protocol.

#### Scenario: adapter returns cookie when set

- **GIVEN** `EnvLinkedInAuthCookieAdapter` is constructed with a
  `SecretStr` value `"AQEAAAAQEAAA"` (12-byte ASCII synthetic,
  NOT a real `li_at`)
- **WHEN** `adapter.cookie()` is called
- **THEN** returns a `SecretStr` whose `get_secret_value() == "AQEAAAAQEAAA"`
- **AND** the test `tests/unit/test_linkedin_auth_cookie.py::test_adapter_returns_cookie_when_set` passes

#### Scenario: adapter returns None when unset

- **GIVEN** `EnvLinkedInAuthCookieAdapter` is constructed with `None`
- **WHEN** `adapter.cookie()` is called
- **THEN** returns `None` (the v1 anonymous-path sentinel)
- **AND** the test `tests/unit/test_linkedin_auth_cookie.py::test_adapter_returns_none_when_unset` passes

#### Scenario: test double conforms to Protocol

- **GIVEN** a test double `FakeLinkedInAuthCookiePort(cookie=SecretStr("AQEAAAAQEAAA"))` is constructed
- **WHEN** the test assigns `port: LinkedInAuthCookiePort = fake` (Protocol type annotation)
- **THEN** `mypy --strict` is clean (structural conformance verified at type-check time)
- **AND** the test `tests/unit/test_linkedin_auth_cookie.py::test_fake_double_conforms_to_protocol` passes

### REQ-LA-COOKIE-002 — `EnvLinkedInAuthCookieAdapter` returns `None` in soft mode

The adapter MUST return `None` (NOT raise, NOT log at ERROR
level) when the constructor receives `None` or when the
`Settings.linkedin_li_at` field is absent from the environment.
The adapter MUST NOT import `logging` and MUST NOT emit log
records of any level. The adapter is a pure in-process value
provider (no I/O, no `await`).

Preserves v1 zero-config boot — an operator without a `li_at`
cookie MUST be able to start the app and run the scraper
anonymously (degraded but functional). The soft WARNING is
logged at the `app_factory.build_app()` startup, NOT inside the
adapter (separation of concerns).

#### Scenario: empty SecretStr at the adapter ctor is normalized to None

- **GIVEN** `EnvLinkedInAuthCookieAdapter(SecretStr(""))` is constructed
  (defense-in-depth: the `_normalize_empty_li_at` validator at
  `Settings` ctor coerces empty to `None` BEFORE the adapter
  sees it, but the adapter ALSO normalizes for tests that
  construct the adapter directly)
- **WHEN** `adapter.cookie()` is called
- **THEN** returns `None`
- **AND** the test `tests/unit/test_linkedin_auth_cookie.py::test_adapter_returns_none_when_empty_secret` passes

#### Scenario: adapter None when env var absent

- **GIVEN** `Settings()` is constructed with no `LINKEDIN_LI_AT` env var
- **WHEN** `EnvLinkedInAuthCookieAdapter(effective_settings.linkedin_li_at).cookie()` is called
- **THEN** returns `None`
- **AND** `app_factory.build_app()` emits a single WARNING log
  line "LinkedIn scraper running without auth cookie" (asserted
  in `tests/integration/test_linkedin_auth_cookie.py::test_startup_warning_when_cookie_absent`)

### REQ-LA-COOKIE-003 — `EnvLinkedInAuthCookieAdapter` returns a `SecretStr` value object

When `Settings.linkedin_li_at` is a non-empty `SecretStr` (with
`len(secret_value) >= 8`, per the Q1 validator in
`linkedin-config` §REQ-LA-CFG-002), the adapter MUST return it
as-is. The value object MUST be a `pydantic.SecretStr` (NOT a
plain `str`) so that `repr()` / `str()` mask the value
automatically.

AGENTS.md rule #7 forbids `li_at` cookies from leaking into the
repo. `SecretStr` is the type-level enforcement: any code path
that does `print(settings.linkedin_li_at)` will print
`**********` instead of the real value. Returning the
`SecretStr` (not the unwrapped `str`) preserves that guarantee
at the adapter boundary.

The adapter MUST be `__slots__`-based
(`__slots__ = ("_cookie",)`) for memory efficiency, matching
the v1 `EnvLinkedInAuthCookieAdapter` style.

#### Scenario: adapter returns SecretStr with masked repr

- **GIVEN** `Settings(linkedin_li_at=SecretStr("AQEAAAAQEAAA"))` (12 chars, valid per validator)
- **WHEN** `adapter = EnvLinkedInAuthCookieAdapter(settings.linkedin_li_at)` is constructed
- **THEN** `adapter.cookie()` returns a `SecretStr`
- **AND** `adapter.cookie().get_secret_value() == "AQEAAAAQEAAA"`
- **AND** `repr(adapter.cookie()) == "SecretStr('**********')"` (NOT the raw value)
- **AND** the test `tests/unit/test_linkedin_auth_cookie.py::test_adapter_returns_secretstr_with_masked_repr` passes

#### Scenario: adapter returns SecretStr at minimum length 8 (boundary inclusive)

- **GIVEN** the adapter is constructed with a 8-char `SecretStr` (the minimum-valid length)
- **WHEN** the adapter is asked for the cookie
- **THEN** returns the `SecretStr` (the boundary is inclusive: `len >= 8`)
- **AND** the test `tests/unit/test_linkedin_auth_cookie.py::test_adapter_returns_secretstr_at_minimum_length_8` passes

### REQ-LA-COOKIE-004 — `LinkedInScraperSettings.__repr__` masks the cookie

`LinkedInScraperSettings.__repr__` MUST return a string that
contains `"<set>"` when `auth_cookie is not None` and
`"<unset>"` when it is. The string MUST NOT contain the
cookie's secret value, even as a substring. The same masking
applies to the `__repr__` of `LinkedInPlaywrightScraper` (the
pre-change repr inherits the settings repr by default, so the
settings repr is the load-bearing contract).

`LinkedInScraperSettings.__eq__` and `__hash__` MUST include
`auth_cookie` in their comparison/hash inputs (so two settings
with different cookies are NOT equal).

The scraper's `__repr__` flows into exception tracebacks, debug
log lines, and `RequestIdLogFilter` output. A regression to a
plain `str` cookie would silently leak the value to operators
reading the log — the `SecretStr` type prevents the leak at the
value-object level, and the `__repr__` override prevents it at
the settings-object level (defense in depth).

#### Scenario: settings repr masks set cookie

- **GIVEN** `LinkedInScraperSettings(user_agent="ua", timeout_ms=10000, auth_cookie=SecretStr("AQEAAAAQEAAA"))`
- **WHEN** `repr(settings)` is called
- **THEN** the returned string contains `"auth_cookie=<set>"` AND does NOT contain `"AQEAAAAQEAAA"` (the synthetic test value)
- **AND** the test `tests/unit/test_linkedin_auth_cookie.py::test_settings_repr_masks_set_cookie` passes

#### Scenario: settings repr masks unset cookie

- **GIVEN** `LinkedInScraperSettings(user_agent="ua", timeout_ms=10000, auth_cookie=None)`
- **WHEN** `repr(settings)` is called
- **THEN** the returned string contains `"auth_cookie=<unset>"`
- **AND** the test `tests/unit/test_linkedin_auth_cookie.py::test_settings_repr_masks_unset_cookie` passes

#### Scenario: settings __eq__ and __hash__ include auth_cookie

- **GIVEN** two `LinkedInScraperSettings` instances differing only in `auth_cookie` (one with `SecretStr("AQEAAAAQEAAA")`, one with `SecretStr("DIFF_VAL_AQXQ"))`
- **WHEN** `settings_a == settings_b` is evaluated
- **THEN** returns `False` (the `__eq__` includes `auth_cookie`)
- **AND** `hash(settings_a) != hash(settings_b)` (the `__hash__` includes `auth_cookie`)
- **AND** the test `tests/unit/test_linkedin_auth_cookie.py::test_settings_eq_hash_includes_auth_cookie` passes

## Out of scope

- **Programmatic login** (navigate to `linkedin.com/login`, fill
  form, submit) — the operator provides the cookie via env var;
  the scraper does NOT obtain it.
- **Auto-refresh of the cookie** — when `li_at` expires
  (typical: ~1 year), the scraper degrades to v1 anonymous
  behavior and the `linkedin-auth-wall-detector` emits a
  WARNING.
- **Multi-account / multi-cookie** — one `LINKEDIN_LI_AT` per
  process instance.
- **DB / Redis persistence of the cookie** — env var is the
  only source of truth.
- **OAuth flow** — LinkedIn does not expose OAuth for
  first-party job scraping.
- **Modifying the `JobSearchPort` Protocol** — the cookie is
  injected via `LinkedInScraperSettings` (additive kwarg), not
  via the Port signature.
- **The `Settings.linkedin_li_at` field** — owned by the
  `linkedin-config` capability.
- **The per-context `ctx.add_cookies` injection in `search()`**
  — owned by the `linkedin-scraper` capability.
- **The `is_auth_wall` defensive detector** — owned by the
  `linkedin-auth-wall-detector` capability.
- **Committing a real `li_at`** — AGENTS.md rule #7; the test
  uses the synthetic 12-byte value `"AQEAAAAQEAAA"`.

---

## Extension requirements (added 2026-06-11 from `backend-linkedin-stealth` archive)

> **EXTENDED on 2026-06-11** from
> `openspec/changes/archive/2026-06-11-backend-linkedin-stealth/spec.md`
> §"Capability: `linkedin-auth-cookie` (EXTENDED)" (Domain 2
> of the multi-capability delta spec).
>
> The v1 cycle added the singular `LinkedInAuthCookiePort`
> Protocol + `EnvLinkedInAuthCookieAdapter` for the operator's
> `li_at` cookie. This delta ADDS 5 REQ-LST-COOKIE-001..005
> (the plural `LinkedInAuthCookiesPort` Protocol +
> `MultiEnvLinkedInAuthCookiesAdapter` for the 4-cookie
> `li_at` + `JSESSIONID` + `bcookie` + `li_gc` set) on top of
> the pre-existing 4 REQ-LA-COOKIE-001..004. The pre-existing
> REQs and the v1 adapter are preserved verbatim above. Source
> observation IDs for this delta: explore #365, proposal #366,
> spec #367, design #368, tasks #369, apply-progress #370,
> verify-report #371.
>
> The mixed namespace (`REQ-LA-*` for the v1 single-cookie
> contract + `REQ-LST-*` for the new multi-cookie contract) is
> intentional; both Protocols coexist (the v1 singular is KEPT
> byte-identical for the 35 v1 backward-compat tests; the new
> plural is the production contract).

### REQ-LST-COOKIE-001 — `LinkedInAuthCookiesPort` (plural) Protocol declares `cookies()` method

A new `LinkedInAuthCookiesPort` (plural) Protocol MUST be
declared in `backend/src/jobs_finder/application/ports.py`
with a single synchronous method
`def cookies(self) -> list[tuple[str, SecretStr]] | None`
that returns either `None` (no cookies configured — the v1
anonymous sentinel) OR a `list` of `(name, value)` pairs for
every non-None cookie. The Protocol is NOT
`@runtime_checkable` (mirrors v1 `LinkedInAuthCookiePort`).
`mypy --strict` MUST validate that
`MultiEnvLinkedInAuthCookiesAdapter` and
`FakeLinkedInAuthCookiesPort` both structurally conform.

Per `explore` obs #365 §6 Q1 (auto-resolved): the multi-cookie
shape is `list[tuple[str, SecretStr]]` (not a `dict`, not a
value object). The Protocol stays minimal (1 method). The v1
`LinkedInAuthCookiePort` (singular) is KEPT for backward compat
(35 v1 tests construct `EnvLinkedInAuthCookieAdapter(SecretStr("AQE..."))`
directly); the new `LinkedInAuthCookiesPort` is ADDITIVE.

#### Scenario: MultiEnv adapter conforms structurally

- **GIVEN**
  `MultiEnvLinkedInAuthCookiesAdapter(SecretStr("li_at_val"), None, None, None)`
  is constructed (1 cookie configured)
- **WHEN** `port.cookies()` is called
- **THEN** returns a `list` of length 1:
  `[("li_at", SecretStr("li_at_val"))]`
- **AND** `mypy --strict` validates
  `port: LinkedInAuthCookiesPort = adapter` (structural
  conformance)
- **AND** the test
  `tests/unit/test_linkedin_stealth.py::TestPortProtocolStructuralConformance::test_port_protocol_exists_in_application_ports`
  passes

#### Scenario: v1 EnvAdapter still works (backward compat)

- **GIVEN** the v1
  `EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA"))`
  is constructed (the v1 single-cookie shape, KEPT for
  backward compat)
- **WHEN** `adapter.cookie()` is called (the v1 method,
  unchanged)
- **THEN** returns `SecretStr("AQEAAAAQEAAA")` (the v1
  contract is preserved)
- **AND** the 35 v1 tests stay GREEN (regression check)

### REQ-LST-COOKIE-002 — `MultiEnvLinkedInAuthCookiesAdapter` ctor accepts 4 independently optional `SecretStr | None` params

The new `MultiEnvLinkedInAuthCookiesAdapter` class (in
`infrastructure/linkedin/auth_cookie.py` next to the v1
`EnvLinkedInAuthCookieAdapter`) MUST accept 4 keyword-only
`SecretStr | None` params: `li_at`, `jsessionid`, `bcookie`,
`li_gc`. Each is independently optional. The class MUST be
`__slots__`-based
(`__slots__ = ("_li_at", "_jsessionid", "_bcookie", "_li_gc")`)
and MUST NOT import `logging` (no log records emitted).

Per `explore` obs #365 §6 Q2: individual env vars matching
the per-source `AliasChoices` precedent at
`config.py:175-201` (Indeed/InfoJobs use individual env vars
per source, not a JSON blob). Each cookie's `SecretStr | None`
type preserves the v1 `li_at` kill-switch semantic
(`None` = skip that cookie).

#### Scenario: adapter accepts 4 independently optional params

- **GIVEN**
  `MultiEnvLinkedInAuthCookiesAdapter(li_at=SecretStr("AQEAAAAQEAAA"), jsessionid=SecretStr("ajax:12345"), bcookie=None, li_gc=SecretStr("gc_xyz"))`
  (3 cookies present, 1 absent)
- **WHEN** the construction completes
- **THEN** no exception is raised
- **AND** the test
  `tests/unit/test_linkedin_stealth.py::TestMultiEnvAdapter::test_cookies_filters_out_none_values`
  passes

#### Scenario: adapter accepts all-None constructor (anonymous sentinel)

- **GIVEN**
  `MultiEnvLinkedInAuthCookiesAdapter(li_at=None, jsessionid=None, bcookie=None, li_gc=None)`
  (all 4 absent — v1 anonymous sentinel)
- **WHEN** the construction completes
- **THEN** no exception is raised
- **AND** the test
  `tests/unit/test_linkedin_stealth.py::TestMultiEnvAdapter::test_cookies_returns_none_when_all_unset`
  passes

### REQ-LST-COOKIE-003 — `cookies()` returns `None` when all 4 are `None`; otherwise returns the list of non-None cookies

The `cookies()` method MUST return `None` when ALL 4 ctor
params are `None` (the v1 anonymous-path sentinel — soft mode
preserved). When at least one cookie is `non-None`, it MUST
return a `list[tuple[str, SecretStr]]` containing ONLY the
non-None cookies (the `None` entries are filtered out, NOT
included as `None` in the list).

The v1 `EnvLinkedInAuthCookieAdapter.cookie()` returned `None`
when no cookie was configured; the multi-cookie version
preserves that semantic. The list is filtered (not a sparse
4-tuple) so the scraper's loop can iterate over the cookies
without null-checking each entry.

#### Scenario: cookies() returns None when all 4 are None

- **GIVEN**
  `MultiEnvLinkedInAuthCookiesAdapter(li_at=None, jsessionid=None, bcookie=None, li_gc=None)`
  (the v1 anonymous sentinel)
- **WHEN** `adapter.cookies()` is called
- **THEN** returns `None` (the soft mode)
- **AND** the test
  `tests/unit/test_linkedin_stealth.py::TestMultiEnvAdapter::test_cookies_returns_none_when_all_unset`
  passes

#### Scenario: cookies() returns filtered list when partial

- **GIVEN**
  `MultiEnvLinkedInAuthCookiesAdapter(li_at=SecretStr("AQEAAAAQEAAA"), jsessionid=None, bcookie=None, li_gc=None)`
  (only `li_at`)
- **WHEN** `adapter.cookies()` is called
- **THEN** returns
  `[("li_at", SecretStr("AQEAAAAQEAAA"))]`
  (1-element list, NOT a 4-tuple with `None`s)
- **AND** the test
  `tests/unit/test_linkedin_stealth.py::TestMultiEnvAdapter::test_cookies_filters_out_none_values`
  passes

#### Scenario: cookies() filters None entries from 3-set-1-absent

- **GIVEN**
  `MultiEnvLinkedInAuthCookiesAdapter(li_at=SecretStr("AQE..."), jsessionid=SecretStr("ajax:12345"), bcookie=None, li_gc=SecretStr("gc_xyz"))`
  (3 set, 1 absent)
- **WHEN** `adapter.cookies()` is called
- **THEN** returns a 3-element list (the `None` `bcookie` is
  filtered out)
- **AND** the test
  `tests/unit/test_linkedin_stealth.py::TestMultiEnvAdapter::test_cookies_filters_out_none_values`
  passes

### REQ-LST-COOKIE-004 — `cookies()` returns deterministic order `li_at` → `jsessionid` → `bcookie` → `li_gc`

When the returned list is non-None, the cookie pairs MUST be
ordered deterministically as
`li_at` → `jsessionid` → `bcookie` → `li_gc` (the canonical
LinkedIn-session order). The v1 single-cookie
`EnvLinkedInAuthCookieAdapter(SecretStr("AQE..."))` ctor is
PRESERVED UNCHANGED (the 35 v1 tests stay GREEN); its
`cookie()` method (singular) returns the `SecretStr` as-is.

Deterministic order is load-bearing for the test (the order
is the contract). The order matches LinkedIn's
"session-establishing" cookie precedence — `li_at` first (the
auth token), then the JSESSIONID/GC support cookies, then
`bcookie` (browser fingerprint) last. A future change that
re-orders would break the closure precedence test.

#### Scenario: cookies() returns deterministic order

- **GIVEN**
  `MultiEnvLinkedInAuthCookiesAdapter(li_at=SecretStr("A"), jsessionid=SecretStr("B"), bcookie=SecretStr("C"), li_gc=SecretStr("D"))`
  (all 4 set)
- **WHEN** `adapter.cookies()` is called
- **THEN** returns
  `[("li_at", SecretStr("A")), ("jsessionid", SecretStr("B")), ("bcookie", SecretStr("C")), ("li_gc", SecretStr("D"))]`
  (exact canonical order)
- **AND** the test
  `tests/unit/test_linkedin_stealth.py::TestMultiEnvAdapter::test_cookies_returns_deterministic_order`
  passes

#### Scenario: v1 single-cookie adapter is preserved (regression check)

- **GIVEN** the v1
  `EnvLinkedInAuthCookieAdapter(SecretStr("AQEAAAAQEAAA"))`
  (the 35 v1 tests' construction pattern)
- **WHEN** `adapter.cookie()` is called (the v1 method,
  UNCHANGED)
- **THEN** returns `SecretStr("AQEAAAAQEAAA")` (v1 contract
  preserved)
- **AND** the v1 tests `tests/unit/test_linkedin_auth_cookie.py`
  all stay GREEN (regression check)

### REQ-LST-COOKIE-005 — `MultiEnvLinkedInAuthCookiesAdapter.__repr__` masks cookie count, not values

`MultiEnvLinkedInAuthCookiesAdapter.__repr__` MUST return a
string that does NOT contain any cookie value (defense in
depth — `SecretStr` already masks `repr()` of the values).
The repr MAY show the cookie count
(e.g. `"MultiEnvLinkedInAuthCookiesAdapter(<set: 3 cookies>)"`
or `"<unset>"` when all 4 are `None`); a 1-bit side-channel
on "is the operator fully configured" is acceptable (per
`explore` obs #365 risk #7). The 4 v1 `__repr__` no-leak
assertions (per v1 `REQ-LA-CFG-004`) extend to the 3 new
fields.

The `SecretStr` type masks `repr()` at the value-object
level; the adapter-level `__repr__` is defense-in-depth. The
count-only side-channel is acceptable (the operator's own
`ls -la .env` is a richer side-channel).

#### Scenario: repr does not leak li_at value

- **GIVEN**
  `MultiEnvLinkedInAuthCookiesAdapter(li_at=SecretStr("AQEAAAAQEAAA"), jsessionid=None, bcookie=None, li_gc=None)`
- **WHEN** `repr(adapter)` is evaluated
- **THEN** the returned string does NOT contain the substring
  `"AQEAAAAQEAAA"` (the synthetic test value)
- **AND** the test
  `tests/unit/test_linkedin_stealth.py::TestMultiEnvAdapterReprMask::test_repr_marks_set_count_when_at_least_one_set`
  passes

#### Scenario: repr does not leak jsessionid value (defense in depth)

- **GIVEN**
  `MultiEnvLinkedInAuthCookiesAdapter(li_at=None, jsessionid=SecretStr("ajax:99999"), bcookie=None, li_gc=None)`
  (only `jsessionid` set, sensitive substring)
- **WHEN** `repr(adapter)` is evaluated
- **THEN** the returned string does NOT contain the substring
  `"ajax:99999"`
- **AND** the test
  `tests/unit/test_linkedin_stealth.py::TestMultiEnvAdapterReprMask::test_repr_marks_set_count_when_at_least_one_set`
  passes (the mask asserts no leak of any of the 4 synthetic
  values; the same assertion covers `jsessionid`)

#### Scenario: repr marks unset when all 4 are None

- **GIVEN**
  `MultiEnvLinkedInAuthCookiesAdapter(li_at=None, jsessionid=None, bcookie=None, li_gc=None)`
- **WHEN** `repr(adapter)` is evaluated
- **THEN** the returned string contains the substring
  `"<unset>"` (or equivalent unset marker) AND does NOT
  contain any of the 4 cookie value placeholders
- **AND** the test
  `tests/unit/test_linkedin_stealth.py::TestMultiEnvAdapterReprMask::test_repr_marks_unset_when_all_none`
  passes

## Source of truth links

- **Delta spec source (v1)**:
  `openspec/changes/archive/2026-06-10-backend-linkedin-auth/spec.md`
  (Domain 1 of the multi-capability delta)
- **Delta spec source (this extension)**:
  `openspec/changes/archive/2026-06-11-backend-linkedin-stealth/spec.md`
  (Domain 2 of the multi-capability delta)
- **Sibling capabilities** (also promoted in the v1 archive):
  - `openspec/specs/linkedin-scraper/spec.md` — EXTENDED with
    `REQ-LA-SCR-001..006` (cookie injection in `search()`)
  - `openspec/specs/linkedin-config/spec.md` — EXTENDED with
    `REQ-LA-CFG-001..004` (`Settings.linkedin_li_at` field +
    2 validators)
  - `openspec/specs/linkedin-auth-wall-detector/spec.md` —
    NEW with `REQ-LA-AWALL-001..006` (the defensive
    `is_auth_wall` detector)
- **Sibling capabilities** (also promoted in the stealth archive):
  - `openspec/specs/linkedin-anti-bot-detector/spec.md` —
    NEW with `REQ-LST-CF-001..003` (the defensive
    `is_cloudflare_challenge` detector)
  - `openspec/specs/linkedin-scraper/spec.md` — EXTENDED
    with `REQ-LST-SCR-001..004` (stealth injection + multi-cookie
    + closure precedence + Cloudflare WARNING)
  - `openspec/specs/linkedin-config/spec.md` — EXTENDED
    with `REQ-LST-CFG-001..003` (3 new optional SecretStr
    fields + shared validator + repr no-leak)
