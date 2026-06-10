# Delta for `location-resolver` — Extend `LocationResolverPort` with `resolve_infojobs`

> **Delta type**: MODIFIED. The base spec for `location-resolver`
> does NOT exist in `openspec/specs/`; this delta documents the
> Protocol extension on top of the pre-change
> `LocationResolverPort` contract (the v1 LinkedIn-only
> `resolve(location) -> int | None` method). The archive step
> will create the main `location-resolver` spec capturing the
> dual-method contract.

## Purpose

Extend `LocationResolverPort` (defined in
`application/ports.py`) with a second method
`resolve_infojobs(location: str) -> tuple[int | None, int | None]`
so the same `HardcodedLocationResolver` instance can serve BOTH
the LinkedIn path (via `resolve()`) and the InfoJobs path (via
`resolve_infojobs()`). The extension follows the same pattern as
`LLMClientPort.complete` + `LLMClientPort.stream_complete` — one
Protocol, two methods, one concrete implementation. The Protocol
stays non-`@runtime_checkable`; structural conformance is
enforced at mypy --strict time, mirroring the v1 contract.

## ADDED Requirements

### REQ-PROV-LOC-001 — `LocationResolverPort.resolve_infojobs` method

The `LocationResolverPort` Protocol MUST declare a second method
`resolve_infojobs(self, location: str) -> tuple[int | None, int | None]`
that returns the InfoJobs-specific `(province_id, country_id)`
tuple. The method is intentionally NOT `async` — it is a pure
in-process dict lookup, same as `resolve()`.

The Protocol's docstring MUST document the 4-tuple semantics
(`(int, int)` / `(None, int)` / `(int, None)` / `(None, None)`)
so a future Protocol consumer (e.g. a Glassdoor scraper) knows
what each `None` position means.

#### Scenario: `LocationResolverPort` declares `resolve_infojobs`

- **GIVEN** the Protocol is defined in `application/ports.py`
- **WHEN** the Protocol is introspected (via `dir(LocationResolverPort)` or mypy --strict)
- **THEN** the Protocol has TWO methods: `resolve` and `resolve_infojobs`
- **AND** `resolve_infojobs` has the signature `(self, location: str) -> tuple[int | None, int | None]`
- **AND** the test `test_hardcoded_location_resolver.py::test_protocol_has_resolve_infojobs_method` passes (uses a `Protocol` introspection helper)

#### Scenario: `HardcodedLocationResolver` conforms to the extended Protocol (mypy --strict)

- **GIVEN** the `HardcodedLocationResolver` class implements BOTH `resolve` and `resolve_infojobs`
- **WHEN** mypy --strict is run
- **THEN** no errors are emitted (the class structurally conforms to the extended Protocol)
- **AND** the test `test_hardcoded_location_resolver.py::test_resolver_satisfies_extended_protocol` passes (uses a typed variable assignment to assert structural conformance)

### REQ-PROV-LOC-002 — Test doubles grow the second method (backward-compat)

The pre-change test doubles:

- `FakeLocationResolver` in `tests/unit/test_filter_use_case.py` (line 955)
- `_FakeLocationResolver` in `tests/unit/test_linkedin_scraper.py` (line 277)

MUST each grow a `resolve_infojobs(self, location: str) -> tuple[int | None, int | None]`
method that returns `(None, None)` (the unmapped sentinel). The
default is the BACKWARD-COMPAT default: existing tests that do
not exercise the InfoJobs path do NOT need to construct a real
InfoJobs resolver — the default `(None, None)` makes the InfoJobs
scraper fall back to the v1 `?l=<str>` URL formula, which is
byte-identical to the pre-change behavior.

> **Note**: the proposal's §6 Q1 mentions a `FakeLocationResolver`
> in `tests/conftest.py`. The actual location is split across
> 2 test files (no `conftest.py` entry). This delta is
> updated to reflect the real layout.

#### Scenario: `FakeLocationResolver` in `test_filter_use_case.py` grows `resolve_infojobs`

- **GIVEN** the `FakeLocationResolver` class in `tests/unit/test_filter_use_case.py` has only `resolve`
- **WHEN** the class is extended with `def resolve_infojobs(self, location: str) -> tuple[int | None, int | None]: return (None, None)`
- **THEN** the existing tests in `test_filter_use_case.py` (which never call `resolve_infojobs`) continue to pass (the new method is a no-op for those tests)
- **AND** the test `test_filter_use_case.py::test_fake_resolver_has_resolve_infojobs_default` passes (asserts the new method exists and returns `(None, None)`)

#### Scenario: `_FakeLocationResolver` in `test_linkedin_scraper.py` grows `resolve_infojobs`

- **GIVEN** the `_FakeLocationResolver` class in `tests/unit/test_linkedin_scraper.py` has only `resolve`
- **WHEN** the class is extended with `def resolve_infojobs(self, location: str) -> tuple[int | None, int | None]: return (None, None)` (recording `self.calls_infojobs` for testability)
- **THEN** the existing tests in `test_linkedin_scraper.py` continue to pass
- **AND** the new test `test_linkedin_scraper.py::test_fake_resolver_records_infojobs_calls` passes (asserts the new method is called and records the input)

#### Scenario: pre-change tests that do not touch the resolver still pass

- **GIVEN** the test doubles have the new `resolve_infojobs` method with the default `(None, None)`
- **WHEN** `cd backend && uv run pytest` is run
- **THEN** ALL pre-change tests (the 51 existing tests in `test_hardcoded_location_resolver.py`, the existing tests in `test_filter_use_case.py`, `test_linkedin_scraper.py`, etc.) continue to pass
- **AND** the only NEW tests are the ~30+ tests for the InfoJobs path

### REQ-PROV-LOC-003 — Composition root wires the SAME resolver to BOTH scrapers

The `app_factory.build_app()` function MUST construct a SINGLE
`HardcodedLocationResolver` instance and inject it into BOTH:

1. `LinkedInScraperSettings(location_resolver=location_resolver)` (existing)
2. `InfoJobsScraperSettings(location_resolver=location_resolver)` (NEW)

The single-instance pattern is intentional: the resolver is a
read-only in-process dict lookup; sharing the instance costs
~50 bytes (the dict references) and keeps the composition root
explicit about the fact that the SAME `location` string is
translated to BOTH a LinkedIn `geoId` AND an InfoJobs
`(province_id, country_id)` tuple by the SAME class.

#### Scenario: `app_factory` shares the resolver between LinkedIn and InfoJobs

- **GIVEN** `build_app()` is called with default settings
- **WHEN** the LinkedIn and InfoJobs scrapers are constructed
- **THEN** both `LinkedInScraperSettings.location_resolver` and `InfoJobsScraperSettings.location_resolver` are the SAME Python object (`is` comparison, not `==`)
- **AND** the test `test_composition.py::test_resolver_shared_between_linkedin_and_infojobs` passes

#### Scenario: `app_factory` fail-fasts on invalid resolver mapping

- **GIVEN** the `HardcodedLocationResolver` is constructed with an invalid mapping entry (e.g. `infojobs_mapping={"bad": (0, 0)}` — `province_id=0` violates the validation rule that IDs MUST be `>= 1`)
- **WHEN** `app_factory.build_app()` is called
- **THEN** `pydantic.ValidationError` (or a custom `ValueError` from the resolver ctor) is raised at startup
- **AND** the process does NOT start (fail-fast, same contract as the other Settings fields)
- **AND** the test `test_composition.py::test_invalid_infojobs_mapping_fails_fast` passes (if validation is enforced in the ctor; if not enforced, the test is marked as `xfail` and the change tracks it as a follow-up)

## MODIFIED Requirements

> The pre-change `LocationResolverPort.resolve()` contract is
> UNCHANGED. The method keeps its `-> int | None` return type,
> its alias-normalization chain, and its WARNING-on-miss
> semantic. The only change is the ADDITION of a second method
> to the same Protocol.

### REQ-PROV-LOC-001-MOD — Protocol has TWO methods, both structurally conformant

(Previously: the Protocol had ONE method `resolve` returning `int | None`.
The `HardcodedLocationResolver` and all test doubles implemented only that
method. mypy --strict verified structural conformance.)

#### Scenario: Protocol extension does not break pre-change call sites

- **GIVEN** the pre-change call sites for `LocationResolverPort.resolve()` (in `FilterJobsByIntentUseCase`, `LinkedInPlaywrightScraper.search()`, `app.state.location_resolver`, the chat wiring tests)
- **WHEN** the Protocol is extended with `resolve_infojobs` (additive, not breaking)
- **THEN** ALL pre-change call sites continue to work unchanged (the `resolve` method signature is byte-identical; the call sites do not need to be modified)
- **AND** `cd backend && uv run mypy --strict` is clean
- **AND** `cd backend && uv run pytest` is clean (1,142 existing tests continue to pass)

## REMOVED Requirements

None. No existing requirement is removed — only a second method
is added to the same Protocol.

## Out of scope

- Defining a separate `InfoJobsLocationResolverPort` Protocol — the user's Q1 answer (Approach A) is "extend the existing Protocol with a second method", mirroring the `LLMClientPort.complete` + `stream_complete` pattern.
- Renaming `resolve` to `resolve_linkedin` (the `resolve` name predates this change and is consumed by the LinkedIn use case; renaming would be a breaking change for the pre-WU call sites).
- Adding `@runtime_checkable` to the Protocol (mirrors the v1 choice; structural conformance is enforced at mypy --strict time only).
- Adding async/sync variants (the resolver is intentionally sync — pure in-process dict lookup).
