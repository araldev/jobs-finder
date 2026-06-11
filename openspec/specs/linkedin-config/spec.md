# Spec: `linkedin-config` — `Settings.linkedin_li_at` (EXTENDED)

> **PROMOTED to source of truth on 2026-06-10** from
> `openspec/changes/backend-linkedin-auth/spec.md`
> §"Capability: `linkedin-config` (EXTENDED)" (Domain 3 of the
> multi-capability delta spec).
>
> This is a NEW foundational capability spec — no prior
> `openspec/specs/linkedin-config/spec.md` existed. The delta is
> promoted in full as the foundational spec for the capability,
> capturing the `Settings.linkedin_li_at` field, the
> `AliasChoices` env binding, the 2 `field_validator`s (Q1
> length check + empty→None normalization), and the `Settings`
> repr no-leak contract. Source observation IDs for
> traceability: explore #353, proposal #354, spec #355, design
> #356, tasks #357, apply-progress #358, verify-report #360.

## Purpose

The `Settings` pydantic-settings model (in
`backend/src/jobs_finder/infrastructure/config.py`) is the
process-wide configuration holder. It binds environment
variables to typed fields and validates them at boot. The
`linkedin-config` capability covers the new
`Settings.linkedin_li_at: SecretStr | None` field that the
operator uses to provide their personal `li_at` session cookie
(via the `LINKEDIN_LI_AT` env var) so the LinkedIn scraper
can authenticate against LinkedIn's SERP and resolve the full
job stream.

The capability is the **configuration seam** between
process-boot (env read + validation) and the LinkedIn scraper
(consumer of the `SecretStr | None`). The Q1 validator
catches operator typos at boot (HARD error on `len < 8`); the
empty-string normalization preserves the v1 kill-switch
semantic (`None` = anonymous scraper). The capability does
NOT cover the Protocol seam (that's `linkedin-auth-cookie`)
or the scraper-side injection (that's `linkedin-scraper`).

## Requirements

### REQ-LA-CFG-001 — `Settings.linkedin_li_at` env var binding

The `Settings` model MUST declare a new field
`linkedin_li_at: SecretStr | None` (default `None`) bound to
env var `LINKEDIN_LI_AT` (case-insensitive, per
pydantic-settings standard) via
`validation_alias=AliasChoices("LINKEDIN_LI_AT", "linkedin_li_at")`.

The model-level `env_prefix="LINKEDIN_"` would resolve the
same env var but the explicit `AliasChoices` survives a
future prefix rename (per the `linkedin_max_pages` precedent
at `config.py:283-286`).

The `SecretStr | None` type enables the kill-switch semantic
(the `None` path = anonymous scraper) and the log-masking
contract (the `SecretStr` path masks `__repr__`).

Mirrors the v1 `llm_api_key` pattern at `config.py:714-743`
(the `SecretStr` + `AliasChoices` + empty-string
normalization chain).

#### Scenario: settings reads linkedin_li_at from env

- **GIVEN** `LINKEDIN_LI_AT=AQEAAAAQEAAA` is in the process env
- **WHEN** `Settings()` is constructed
- **THEN** `settings.linkedin_li_at.get_secret_value() == "AQEAAAAQEAAA"`
- **AND** the test `tests/unit/test_linkedin_config.py::test_settings_reads_linkedin_li_at_from_env` passes

#### Scenario: settings defaults to None when env var absent

- **GIVEN** no `LINKEDIN_LI_AT` env var is set
- **WHEN** `Settings()` is constructed
- **THEN** `settings.linkedin_li_at is None`
- **AND** the test `tests/unit/test_linkedin_config.py::test_settings_linkedin_li_at_defaults_to_none` passes

#### Scenario: programmatic construction accepts SecretStr

- **GIVEN** programmatic `Settings(linkedin_li_at=SecretStr("AQEAAAAQEAAA"))`
- **WHEN** the construction completes
- **THEN** `settings.linkedin_li_at.get_secret_value() == "AQEAAAAQEAAA"` (the second choice in `AliasChoices` accepts the programmatic form)
- **AND** the test `tests/unit/test_linkedin_config.py::test_settings_linkedin_li_at_programmatic_construction` passes

### REQ-LA-CFG-002 — Q1 validator rejects values with `len < 8` characters

A `field_validator('linkedin_li_at', mode="after")` on the
`Settings` model MUST raise `pydantic.ValidationError` (which
surfaces as `ValueError` in the v1 callers) when the value is
present and has fewer than 8 characters, with the message
`"LINKEDIN_LI_AT must be at least 8 characters (got <N>); check for
typos or unset the variable to run the scraper anonymously."`.

The threshold of 8 chars catches operator typos
(`LINKEDIN_LI_AT=abc`) while accepting every realistic real
cookie (real `li_at` values are ~150 chars).

Q1 option C in the proposal. The HARD error at boot fails
fast and surfaces the typo in the operator's first log line;
the SOFT WARNING at startup when the value is absent
preserves v1 zero-config boot (the WARNING is emitted by
`app_factory.build_app()`, not by the validator — see
`linkedin-scraper` §REQ-LA-SCR-003). The 8-char threshold is
arbitrary but conservative (real cookies are much longer).

#### Scenario: 3-char value rejected (clear typo)

- **GIVEN** programmatic `Settings(linkedin_li_at=SecretStr("abc"))` (3 chars, a clear typo)
- **WHEN** `Settings()` is constructed
- **THEN** raises `pydantic.ValidationError` whose `__str__` contains the substring `"must be at least 8 characters"` AND the substring `"got 3"`
- **AND** the test `tests/unit/test_linkedin_config.py::test_settings_rejects_short_li_at_3_chars` passes

#### Scenario: 7-char value rejected (boundary < 8)

- **GIVEN** programmatic `Settings(linkedin_li_at=SecretStr("1234567"))` (7 chars, the boundary)
- **WHEN** `Settings()` is constructed
- **THEN** raises `pydantic.ValidationError` (the threshold is inclusive `<8`, so 7 is rejected)
- **AND** the test `tests/unit/test_linkedin_config.py::test_settings_rejects_short_li_at_7_chars` passes

#### Scenario: 8-char value accepted (minimum valid)

- **GIVEN** programmatic `Settings(linkedin_li_at=SecretStr("12345678"))` (8 chars, the minimum valid)
- **WHEN** `Settings()` is constructed
- **THEN** succeeds; `settings.linkedin_li_at.get_secret_value() == "12345678"`
- **AND** the test `tests/unit/test_linkedin_config.py::test_settings_accepts_minimum_length_8` passes

### REQ-LA-CFG-003 — The validator is a no-op when the value is `None` and normalizes empty inputs

The Q1 `mode="after"` validator MUST return
`v: SecretStr | None` unchanged when `v is None` (the v1
zero-config default). Similarly, a `mode="before"` validator
MUST normalize empty-string inputs (`""`, `SecretStr("")`) to
`None` so the kill-switch contract holds at the adapter
boundary.

The v1 `llm_api_key` pattern (`config.py:714-743`) is the
precedent. An empty env var (`LINKEDIN_LI_AT=`) MUST behave
the same as a missing env var (no `LINKEDIN_LI_AT` at all)
so the operator can comment-out the var by setting it to empty
(a common ops pattern).

#### Scenario: None value passes (no exception)

- **GIVEN** `Settings(linkedin_li_at=None)`
- **WHEN** the construction completes
- **THEN** `settings.linkedin_li_at is None` (no exception)
- **AND** the test `tests/unit/test_linkedin_config.py::test_settings_accepts_none_li_at` passes

#### Scenario: empty SecretStr normalized to None

- **GIVEN** `Settings(linkedin_li_at=SecretStr(""))` (the 2nd shape: SecretStr wrapping empty string)
- **WHEN** the construction completes
- **THEN** `settings.linkedin_li_at is None` (the `_normalize_empty_li_at` mode=before validator coerces to `None`)
- **AND** the test `tests/unit/test_linkedin_config.py::test_settings_normalizes_empty_secret_to_none` passes

#### Scenario: empty plain string normalized to None

- **GIVEN** `Settings(linkedin_li_at="")` (the 3rd shape: plain empty string)
- **WHEN** the construction completes
- **THEN** `settings.linkedin_li_at is None` (same normalization path)
- **AND** the test `tests/unit/test_linkedin_config.py::test_settings_normalizes_empty_string_to_none` passes

### REQ-LA-CFG-004 — `Settings.__repr__` does not include the cookie value

`repr(Settings(linkedin_li_at=SecretStr("AQEAAAAQEAAA")))`
MUST NOT contain the substring `"AQEAAAAQEAAA"`. The
`SecretStr` type already enforces this at the field level
(its `__repr__` masks to `SecretStr('**********')`), but a
test MUST assert the contract at the `Settings` repr level
(in case a future field accidentally accepts a plain `str`).

Defense in depth — the field-level `SecretStr` is the primary
guarantee; the `Settings`-repr assertion is the regression
check. A test that fails immediately on a plain-`str`
regression is cheaper than tracing a leaked cookie through 6
months of log lines.

#### Scenario: settings repr does not leak cookie value (negative assertion)

- **GIVEN** `Settings(linkedin_li_at=SecretStr("AQEAAAAQEAAA"))` (programmatic)
- **WHEN** `repr(settings)` is evaluated
- **THEN** the returned string does NOT contain the substring `"AQEAAAAQEAAA"`
- **AND** the test `tests/unit/test_linkedin_config.py::test_settings_repr_does_not_leak_cookie_value` passes

## Out of scope

- **The `LinkedInAuthCookiePort` Protocol and
  `EnvLinkedInAuthCookieAdapter`** — owned by the
  `linkedin-auth-cookie` capability spec.
- **The per-context `ctx.add_cookies` injection in `search()`**
  — owned by the `linkedin-scraper` capability spec.
- **The `is_auth_wall` defensive detector** — owned by the
  `linkedin-auth-wall-detector` capability spec.
- **The startup WARNING at `app_factory.build_app()` when
  `linkedin_li_at is None`** — owned by the
  `linkedin-scraper` capability spec (`REQ-LA-SCR-003`). The
  validator is a no-op in the `None` path (REQ-LA-CFG-003);
  the WARNING is emitted by the composition root, not by the
  validator.
- **The `LinkedInScraperSettings.auth_cookie` field and its
  `__repr__` masking** — owned by the `linkedin-auth-cookie`
  capability spec (`REQ-LA-COOKIE-004`).
- **The `llm_api_key` field and its validators** — pre-existing
  v1, untouched by this change.
- **The `linkedin_max_pages` and `linkedin_inter_page_delay_seconds`
  fields** — pre-existing v1 (introduced by
  `backend-scraper-query-tuning`), untouched by this change.
- **The `linkedin_request_timeout_ms` and `linkedin_user_agent`
  fields** — pre-existing v1, untouched by this change.
- **Modifying the `Settings` model-level `env_prefix` or any
  other pre-existing field** — out of scope.

## Source of truth links

- **Delta spec source**: `openspec/changes/archive/2026-06-10-backend-linkedin-auth/spec.md` (Domain 3 of the multi-capability delta)
- **Sibling capabilities** (also extended in the same archive):
  - `openspec/specs/linkedin-auth-cookie/spec.md` — NEW with `REQ-LA-COOKIE-001..004`
  - `openspec/specs/linkedin-scraper/spec.md` — EXTENDED with `REQ-LA-SCR-001..006` (cookie injection in `search()`)
  - `openspec/specs/linkedin-auth-wall-detector/spec.md` — NEW with `REQ-LA-AWALL-001..006`

---

## Stealth extension requirements (added 2026-06-11 from `backend-linkedin-stealth` archive)

> **EXTENDED on 2026-06-11** from
> `openspec/changes/archive/2026-06-11-backend-linkedin-stealth/spec.md`
> §"Capability: `linkedin-config` (EXTENDED)" (Domain 4 of
> the multi-capability delta spec).
>
> The v1 cycle added 4 `REQ-LA-CFG-001..004` for the
> `Settings.linkedin_li_at` field. This delta ADDS 3
> `REQ-LST-CFG-001..003` (the 3 new optional
> `Settings.linkedin_{jsessionid,bcookie,li_gc}` fields + the
> shared validator + the repr no-leak contract) on top of the
> pre-existing 4 `REQ-LA-CFG-001..004`. The pre-existing REQs
> and the v1 `linkedin_li_at` field are preserved verbatim
> above. Source observation IDs for this delta: explore #365,
> proposal #366, spec #367, design #368, tasks #369,
> apply-progress #370, verify-report #371.
>
> The mixed namespace (`REQ-LA-*` for the v1 `linkedin_li_at`
> field + `REQ-LST-*` for the 3 new cookie fields) is
> intentional; all 4 fields share the same v1 validator
> pattern (HARD on `len < 8` when present, soft `None`
> allowed) and the same `MIN_LI_AT_LENGTH = 8` constant.

### REQ-LST-CFG-001 — 3 new optional `SecretStr | None` fields with `AliasChoices` env binding

The `Settings` model MUST declare 3 new fields, each
`SecretStr | None` with default `None`, each bound via
`validation_alias=AliasChoices(<UPPER>, <lower>)`:

- `linkedin_jsessionid: SecretStr | None` ↔
  `LINKEDIN_JSESSIONID` (case-insensitive via
  pydantic-settings)
- `linkedin_bcookie: SecretStr | None` ↔
  `LINKEDIN_BCOOKIE`
- `linkedin_li_gc: SecretStr | None` ↔
  `LINKEDIN_LI_GC`

The 3 fields are placed adjacent to the v1 `linkedin_li_at`
field (per `config.py:317-362`).

Per `explore` obs #365 §6 Q2: individual env vars matching
the per-source `AliasChoices` precedent (Indeed/InfoJobs use
individual env vars at `config.py:175-201`). Each field's
`SecretStr | None` type preserves the v1 kill-switch
semantic. The `AliasChoices` pattern (upper + lower) survives
a future `env_prefix` rename.

#### Scenario: settings reads jsessionid from env

- **GIVEN** `LINKEDIN_JSESSIONID=ajax:12345` is in the process
  env
- **WHEN** `Settings()` is constructed
- **THEN**
  `settings.linkedin_jsessionid.get_secret_value() == "ajax:12345"`
- **AND** the test
  `tests/unit/test_linkedin_config.py::TestLinkedInStealthCookies::test_settings_env_alias_binds_uppercase`
  passes

#### Scenario: settings defaults to None when jsessionid env var absent

- **GIVEN** no `LINKEDIN_JSESSIONID` env var is set
- **WHEN** `Settings()` is constructed
- **THEN** `settings.linkedin_jsessionid is None`
- **AND** the test
  `tests/unit/test_linkedin_config.py::TestLinkedInStealthCookies::test_settings_jsessionid_defaults_to_none`
  passes

#### Scenario: programmatic construction accepts SecretStr for new fields

- **GIVEN** programmatic
  `Settings(linkedin_bcookie=SecretStr("v2_xyz_padded"), linkedin_li_gc=SecretStr("gc_abc_padded"))`
  (the 13-char padded sentinels used in T-005 integration
  tests to satisfy the v1 validator's 8-char minimum)
- **WHEN** the construction completes
- **THEN** both fields are populated and the v1 `linkedin_li_at`
  is still `None` (no cross-coupling)
- **AND** the test
  `tests/unit/test_linkedin_config.py::TestLinkedInStealthCookies::test_settings_programmatic_construction_of_new_fields`
  passes

#### Scenario: settings normalizes empty bcookie to None

- **GIVEN** `Settings(linkedin_bcookie=SecretStr(""))` (empty
  string — defense-in-depth)
- **WHEN** the construction completes
- **THEN** `settings.linkedin_bcookie is None` (the v1
  `mode="before"` empty→`None` normalization applies to all 4
  fields)
- **AND** the test
  `tests/unit/test_linkedin_config.py::TestLinkedInStealthCookies::test_settings_normalizes_empty_bcookie_to_none`
  passes

### REQ-LST-CFG-002 — Reusable validator (HARD on `len < 8` when present, soft `None` allowed) shared across all 4 fields

Each of the 3 new `linkedin_*` fields MUST use the v1
validator pattern: HARD `ValueError` on `len < 8` characters
when present, soft `None` allowed. The validator is a
REUSABLE HELPER (a private function or a `field_validator`
factory — the design can choose the exact shape) — the
contract is that the same `len < 8` rejection + same
`min < N>` error message format applies to all 4 cookie
fields (`linkedin_li_at` + the 3 new). The constant
`MIN_LI_AT_LENGTH = 8` (per `config.py:58`) is the single
source of truth.

The threshold of 8 chars catches operator typos
(`LINKEDIN_JSESSIONID=abc`) while accepting every realistic
real cookie. The error message includes the field name
(e.g. `"LINKEDIN_JSESSIONID"`) so the operator can
self-diagnose which env var is wrong.

#### Scenario: settings rejects short jsessionid with field name

- **GIVEN** programmatic
  `Settings(linkedin_jsessionid=SecretStr("abc"))` (3 chars)
- **WHEN** `Settings()` is constructed
- **THEN** raises `pydantic.ValidationError` whose `__str__`
  contains `"LINKEDIN_JSESSIONID"`, `"must be at least 8 characters"`,
  and `"got 3"`
- **AND** the test
  `tests/unit/test_linkedin_config.py::TestLinkedInStealthCookies::test_settings_rejects_short_jsessionid_with_field_name`
  passes

#### Scenario: settings accepts 8-char jsessionid (boundary inclusive)

- **GIVEN** programmatic
  `Settings(linkedin_jsessionid=SecretStr("12345678"))` (8 chars,
  the minimum valid)
- **WHEN** `Settings()` is constructed
- **THEN** succeeds;
  `settings.linkedin_jsessionid.get_secret_value() == "12345678"`
- **AND** the test
  `tests/unit/test_linkedin_config.py::TestLinkedInStealthCookies::test_settings_accepts_minimum_length_8_for_jsessionid`
  passes

#### Scenario: settings rejects 7-char bcookie (boundary `<8`)

- **GIVEN** programmatic
  `Settings(linkedin_bcookie=SecretStr("1234567"))` (7 chars,
  the boundary)
- **WHEN** `Settings()` is constructed
- **THEN** raises `ValidationError` (threshold inclusive `<8`,
  so 7 is rejected)
- **AND** the test
  `tests/unit/test_linkedin_config.py::TestLinkedInStealthCookies::test_settings_rejects_short_bcookie_7_chars`
  passes

### REQ-LST-CFG-003 — `Settings.__repr__` does NOT include any of the 3 new field values

`repr(Settings(linkedin_jsessionid=SecretStr("ajax:12345"), linkedin_bcookie=SecretStr("v2_xyz"), linkedin_li_gc=SecretStr("gc_abc")))`
MUST NOT contain the substrings `"ajax:12345"`, `"v2_xyz"`, or
`"gc_abc"`. The `SecretStr` type already enforces this at the
field level (its `__repr__` masks to `SecretStr('**********')`),
but a test MUST assert the contract at the `Settings` repr
level (1 assertion per new field — defense in depth, mirrors
v1 `REQ-LA-CFG-004`).

AGENTS.md rule #7: no real cookies in the repo. The v1
`test_settings_repr_does_not_leak_cookie_value` pattern
extends to all 4 fields. A future field that accidentally
accepts plain `str` would fail the test immediately.

#### Scenario: settings repr does not leak jsessionid value (negative assertion)

- **GIVEN** `Settings(linkedin_jsessionid=SecretStr("ajax:12345"))`
- **WHEN** `repr(settings)` is evaluated
- **THEN** the returned string does NOT contain `"ajax:12345"`
- **AND** the test
  `tests/unit/test_linkedin_config.py::TestLinkedInStealthCookies::test_settings_repr_does_not_leak_jsessionid_value`
  passes

#### Scenario: settings repr does not leak bcookie or li_gc values

- **GIVEN**
  `Settings(linkedin_bcookie=SecretStr("v2_xyz"), linkedin_li_gc=SecretStr("gc_abc"))`
- **WHEN** `repr(settings)` is evaluated
- **THEN** the returned string does NOT contain `"v2_xyz"`
  AND does NOT contain `"gc_abc"`
- **AND** the test
  `tests/unit/test_linkedin_config.py::TestLinkedInStealthCookies::test_settings_repr_does_not_leak_bcookie_or_li_gc`
  passes (2 assertions, 1 test)

## Source of truth links (extensions)

- **Delta spec source (this extension)**:
  `openspec/changes/archive/2026-06-11-backend-linkedin-stealth/spec.md`
  (Domain 4 of the multi-capability delta)
- **Sibling capabilities** (also promoted in the stealth archive):
  - `openspec/specs/linkedin-anti-bot-detector/spec.md` —
    NEW with `REQ-LST-CF-001..003` (the defensive
    `is_cloudflare_challenge` detector)
  - `openspec/specs/linkedin-auth-cookie/spec.md` —
    EXTENDED with `REQ-LST-COOKIE-001..005` (the multi-cookie
    Protocol + `MultiEnvLinkedInAuthCookiesAdapter` +
    deterministic order + repr mask)
  - `openspec/specs/linkedin-scraper/spec.md` — EXTENDED
    with `REQ-LST-SCR-001..004` (stealth injection +
    multi-cookie + closure precedence + Cloudflare WARNING)
