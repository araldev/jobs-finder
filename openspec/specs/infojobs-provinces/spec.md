# Spec: `infojobs-provinces` — Location → (province_id, country_id) resolver

> **Promoted to source of truth on 2026-06-10** from
> `openspec/changes/backend-infojobs-provinces/specs/infojobs-provinces/spec.md`
> (archived in `openspec/changes/archive/2026-06-10-backend-infojobs-provinces/`).
>
> This was a NEW capability — no prior
> `openspec/specs/infojobs-provinces/spec.md` existed. The delta spec
> is promoted in full as the foundational spec for the capability.
> Source observation IDs for traceability: explore #330, proposal #331,
> spec #334, design #337, tasks #339, apply-progress #341,
> verify-report #342.

## Purpose

Define the InfoJobs-specific location resolver that translates the
`location` string sent by the frontend (and accepted by every
per-source route verbatim) into the `(province_id, country_id)` tuple
that InfoJobs's SERP accepts as `?provinceIds=<id>&countryIds=<id>`.
The resolver is the InfoJobs counterpart of the existing
LinkedIn `geoId` resolver: it shares the same alias-normalization
chain (NFC + casefold + strip + remove-accents), the same
in-process dict look-up, and the same composition-root injection
seam. The unknown-location sentinel is `(None, None)` (vs. `None`
for the LinkedIn `int` return), so the InfoJobs scraper knows to
fall back to the v1 `?l=<str>` URL formula without province/country
IDs.

This is a NEW capability. No previous `infojobs-provinces` spec
exists (the project has 2 base specs in `openspec/specs/`: only
`chat-streaming` and `frontend-scaffold`).

---

## Requirements

### REQ-PROV-001 — `HardcodedLocationResolver.resolve_infojobs`

The `HardcodedLocationResolver` (in
`infrastructure/location/hardcoded_resolver.py`) MUST gain a second
method `resolve_infojobs(location: str) -> tuple[int | None, int | None]`
that returns the InfoJobs-specific `(province_id, country_id)` tuple
for known locations, or `(None, None)` for unmapped / empty inputs.

The method MUST follow the same alias-normalization chain as the
existing `resolve()`: NFC + casefold + strip + NFD-strip-accents
+ alias-to-canonical recurse. The method MUST be a pure in-process
dict lookup (no I/O, no `await`).

The return type semantics:

| `province_id` | `country_id` | Meaning                                                |
| ------------- | ------------ | ------------------------------------------------------ |
| `int`         | `int`        | Both known — emit `provinceIds=<id>&countryIds=<id>`.  |
| `None`        | `int`        | Country-only (e.g. "Remote", "España") — emit `countryIds=<id>` only. |
| `int`         | `None`       | Province-only (e.g. future province without country) — emit `provinceIds=<id>` only. |
| `None`        | `None`       | Unmapped / empty — omit both params (legacy `?l=<str>` fallback). |

#### Scenario: `location=malaga` returns `(34, 17)` (canonical, NFC lowercased)

- **GIVEN** the resolver is built with the default 9-entry InfoJobs mapping
- **WHEN** `resolve_infojobs("malaga")` is called
- **THEN** returns `(34, 17)` (the user-confirmed Málaga=34, España=17 IDs)
- **AND** the alias normalization chain is exercised (NFC + casefold + strip + accent-strip)
- **AND** the unit test `tests/unit/test_infojobs_province_resolver.py::test_resolve_infojobs_malaga` passes

#### Scenario: `location=Málaga` (U+00E1, Title Case, with leading/trailing whitespace) returns `(34, 17)`

- **GIVEN** the resolver receives `"  MÁLAGA  "` (NFC composed á + uppercase + padding)
- **WHEN** `resolve_infojobs("  MÁLAGA  ")` is called
- **THEN** returns `(34, 17)` (alias normalization is accent- + case- + whitespace-insensitive)
- **AND** the test `test_resolve_infojobs_malaga_with_tilde_and_padding` passes

#### Scenario: `location=Madrid` returns `(28, 17)` (speculative INE — LIVE test validates)

- **GIVEN** the resolver receives `"Madrid"`
- **WHEN** `resolve_infojobs("Madrid")` is called
- **THEN** returns `(28, 17)` (the speculative INE code; the LIVE test gated `LLM_LIVE_TESTS=1` validates against the real InfoJobs SERP)
- **AND** if the LIVE test fails for Madrid, the dict entry MAY be removed without affecting the rest of the resolver (a missing entry falls back to `(None, None)`)
- **AND** the unit test `test_resolve_infojobs_madrid` passes
- **AND** the LIVE test `test_resolve_infojobs_madrid_live` (skipped unless `LLM_LIVE_TESTS=1`) is the formal gate

#### Scenario: `location=Barcelona` returns `(8, 17)` (speculative — LIVE test validates)

- **GIVEN** the resolver receives `"Barcelona"`
- **WHEN** `resolve_infojobs("Barcelona")` is called
- **THEN** returns `(8, 17)` (speculative; LIVE test gates)
- **AND** the test `test_resolve_infojobs_barcelona` passes

#### Scenario: `location=Valencia` returns `(46, 17)` (speculative — LIVE test validates)

- **GIVEN** the resolver receives `"Valencia"`
- **WHEN** `resolve_infojobs("Valencia")` is called
- **THEN** returns `(46, 17)` (speculative; LIVE test gates)
- **AND** the test `test_resolve_infojobs_valencia` passes

#### Scenario: `location=Sevilla` returns `(41, 17)` (speculative — LIVE test validates)

- **GIVEN** the resolver receives `"Sevilla"`
- **WHEN** `resolve_infojobs("Sevilla")` is called
- **THEN** returns `(41, 17)` (speculative; LIVE test gates)
- **AND** the test `test_resolve_infojobs_sevilla` passes

#### Scenario: `location=Remote` returns `(None, 17)` (country-only)

- **GIVEN** the resolver receives `"remote"` (lowercased)
- **WHEN** `resolve_infojobs("remote")` is called
- **THEN** returns `(None, 17)` (no province — country-only sentinel)
- **AND** the scraper emits `countryIds=17` but NOT `provinceIds`
- **AND** the test `test_resolve_infojobs_remote_returns_country_only` passes

#### Scenario: `location=España` (or `"Spain"`) returns `(None, 17)` (country-only)

- **GIVEN** the resolver receives `"España"` or `"Spain"` (or `"spain"`, `"espana"`, with or without accent)
- **WHEN** `resolve_infojobs("España")` is called
- **THEN** returns `(None, 17)` (country-only — no province filter)
- **AND** the test `test_resolve_infojobs_espana_returns_country_only` passes

#### Scenario: `location=Berlin` returns `(None, None)` (unmapped, graceful fallback)

- **GIVEN** the resolver receives `"Berlin"` (no InfoJobs mapping)
- **WHEN** `resolve_infojobs("Berlin")` is called
- **THEN** returns `(None, None)` (sentinel: omit both params, use legacy `?l=<str>`)
- **AND** a WARNING is logged (observable for ops to spot stale geographic intent)
- **AND** the test `test_resolve_infojobs_unmapped_returns_none_none` passes

#### Scenario: empty `location=""` returns `(None, None)` without WARNING

- **GIVEN** the resolver receives `""` (empty string — the canonical "no location" sentinel)
- **WHEN** `resolve_infojobs("")` is called
- **THEN** returns `(None, None)` (defensive: empty location = no filter)
- **AND** NO WARNING is logged (matches the `resolve()` invariant — empty is not an "unknown" signal)
- **AND** the test `test_resolve_infojobs_empty_short_circuits` passes

#### Scenario: custom mapping via ctor (test seam for the future `HybridInfoJobsResolver`)

- **GIVEN** the resolver is built with a custom `infojobs_mapping={"custom_city": (99, 17)}` ctor kwarg
- **WHEN** `resolve_infojobs("custom_city")` is called
- **THEN** returns `(99, 17)` (the custom mapping REPLACES the default — same override semantic as the LinkedIn `mapping` ctor kwarg)
- **AND** the test `test_resolve_infojobs_custom_mapping` passes

#### Scenario: 9-entry default mapping is the source of truth

- **GIVEN** the resolver is built with no ctor args
- **WHEN** the default mapping is inspected
- **THEN** it contains exactly 9 entries: `malaga`, `madrid`, `barcelona`, `valencia`, `sevilla`, `espana`, `spain`, `remote`, `teletrabajo`
- **AND** the test `test_default_mapping_has_nine_entries` passes (locks the count so a future addition is a deliberate code change)

---

## Notes for downstream phases

- The mapping is sourced from the user's manual smoke test (Málaga=34, España=17 confirmed via real URL capture) and the InfoJobs public-facing documentation for the other 4 cities. The 4 speculative IDs (Madrid=28, Barcelona=8, Valencia=46, Sevilla=41) are the official Spanish INE province codes; InfoJobs MAY use a different internal ID — the LIVE test verifies each one. Wrong IDs fall back to `(None, None)`; they do not 500.
- The custom-mapping ctor seam is the analog of the LinkedIn resolver's `mapping=` kwarg (see `hardcoded_resolver.py:57-75`). It is the seam for a future `HybridInfoJobsResolver` that adds a geocoding API fallback.
- The resolver is a value-holder, not a stateful cache. It holds two read-only `Mapping` references; no per-call mutation, no I/O.
- The 9-entry default is committed. Adding a 10th entry (e.g. a new city) is a 1-line dict edit + a test.
- The method name is `resolve_infojobs` (not `resolve_province_ids`) — it returns BOTH a province ID and a country ID, and the `infojobs_` prefix mirrors the source name, mirroring the `infojobs_geo` kwarg in the scraper. If a future 4th source needs a different ID shape, add another method (mirroring `LLMClientPort.complete` + `stream_complete`).
