# Spec: `location-resolver` — `LocationResolverPort` (LinkedIn + InfoJobs + Structured Fallback)

> **Promoted to source of truth on 2026-06-10** from two consecutive
> SDD changes (sister-first, this change second):
>
> 1. `openspec/changes/archive/2026-06-10-backend-infojobs-provinces/specs/location-resolver/spec.md`
>    — sibling change that introduced the dual-method Protocol
>    (`resolve` + `resolve_infojobs`).
> 2. `openspec/changes/archive/2026-06-10-backend-linkedin-location-fallback/specs/backend-linkedin-location-fallback/spec.md`
>    (Domain 1) — this change that added a third method
>    `resolve_structured`.
>
> This was a MODIFIED delta for each of the two sister changes — no
> prior `openspec/specs/location-resolver/spec.md` existed when the
> first sister change archived. The first sister change promoted its
> delta in full as the foundational spec; the second sister change
> (this archive) MERGES its delta into the same global spec file
> (append-only, no destructive edits).
>
> **Sister change coordination**: the sister change
> `backend-infojobs-provinces` and this change `backend-linkedin-location-fallback`
> BOTH extend `LocationResolverPort`. Their merge is non-conflicting at
> the file level (different method names on the same Protocol). This
> archive produces the merged spec reflecting BOTH extensions
> simultaneously — the post-merge source of truth.
>
> Source observation IDs for traceability:
> - Sister change: explore #330, proposal #331, spec #334, design #337,
>   tasks #339, apply-progress #341, verify-report #342.
> - This change: explore #332, proposal #333, spec #336, design #338,
>   tasks #340, apply-progress #345, verify-report #348, discoveries
>   #346 (L607 shadowing) and #347 (assertion quality audit).

## Purpose

`LocationResolverPort` (defined in `application/ports.py`) is the
seam between the application layer and the location-resolution
infrastructure. The composition root injects a SINGLE
`HardcodedLocationResolver` instance into BOTH the LinkedIn scraper,
the InfoJobs scraper, the chat use case, and `app.state`. As of
2026-06-10, the Protocol exposes THREE methods (chronological
addition):

1. `resolve(location) -> int | None` — original v1 method. Translates
   a city name to a LinkedIn `geoId` integer.
2. `resolve_infojobs(location) -> tuple[int | None, int | None]` —
   added by the sister change `backend-infojobs-provinces`.
   Translates a city name to an InfoJobs `(province_id, country_id)`
   tuple.
3. `resolve_structured(location) -> tuple[str, str, str] | None` —
   added by this change `backend-linkedin-location-fallback`.
   Translates a city name to a `(city, province, country)` triplet
   (Title Case, NFC with tildes) for the LinkedIn structured
   `?location=City,Province,Country` URL formula.

The pattern mirrors `LLMClientPort.complete` + `stream_complete` —
one Protocol, multiple methods, one concrete implementation. The
Protocol stays non-`@runtime_checkable`; structural conformance is
enforced at mypy --strict time, mirroring the v1 contract.

The pre-change `LocationResolverPort.resolve()` contract is
UNCHANGED. The method keeps its `-> int | None` return type, its
alias-normalization chain, and its WARNING-on-miss semantic. The
only changes are the ADDITIONS of two new methods (`resolve_infojobs`
from the sister change, `resolve_structured` from this change).

## Requirements

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
- **THEN** the Protocol has THREE methods: `resolve`, `resolve_infojobs`, and `resolve_structured`
- **AND** `resolve_infojobs` has the signature `(self, location: str) -> tuple[int | None, int | None]`
- **AND** the test `test_hardcoded_location_resolver.py::test_protocol_has_resolve_infojobs_method` passes (uses a `Protocol` introspection helper)

#### Scenario: `HardcodedLocationResolver` conforms to the extended Protocol (mypy --strict)

- **GIVEN** the `HardcodedLocationResolver` class implements BOTH `resolve_infojobs` and `resolve_structured` (in addition to the original `resolve`)
- **WHEN** mypy --strict is run
- **THEN** no errors are emitted (the class structurally conforms to the extended Protocol)
- **AND** the test `test_hardcoded_location_resolver.py::test_resolver_satisfies_extended_protocol` passes (uses a typed variable assignment to assert structural conformance)

### REQ-PROV-LOC-001-MOD — Protocol has THREE methods, all structurally conformant

(Previously: the Protocol had ONE method `resolve` returning `int | None`.
The `HardcodedLocationResolver` and all test doubles implemented only that
method. mypy --strict verified structural conformance. The sister
change extended the Protocol with `resolve_infojobs`; this change
extends it further with `resolve_structured`.)

#### Scenario: Protocol extension does not break pre-change call sites

- **GIVEN** the pre-change call sites for `LocationResolverPort.resolve()` (in `FilterJobsByIntentUseCase`, `LinkedInPlaywrightScraper.search()`, `app.state.location_resolver`, the chat wiring tests)
- **WHEN** the Protocol is extended with `resolve_infojobs` (sister change, additive) AND `resolve_structured` (this change, additive)
- **THEN** ALL pre-change call sites continue to work unchanged (the `resolve` method signature is byte-identical; the call sites do not need to be modified)
- **AND** `cd backend && uv run mypy --strict` is clean
- **AND** `cd backend && uv run pytest` is clean (1,142 existing tests continue to pass)

### REQ-PROV-LOC-002 — Test doubles grow the additional methods (backward-compat)

The pre-change test doubles:

- `FakeLocationResolver` in `tests/unit/test_filter_use_case.py` (line 955)
- `_FakeLocationResolver` in `tests/unit/test_linkedin_scraper.py` (line 277)

MUST each grow the second method (sister change: `resolve_infojobs`)
and the third method (this change: `resolve_structured`).

- `resolve_infojobs(self, location: str) -> tuple[int | None, int | None]`
  MUST return `(None, None)` (the unmapped sentinel) by default.
- `resolve_structured(self, location: str) -> tuple[str, str, str] | None`
  MUST return `None` (the unmapped sentinel) by default.

The defaults are the BACKWARD-COMPAT defaults: existing tests that
do not exercise the InfoJobs path or the structured-fallback path
do NOT need to construct a real mapping — the defaults make the
respective scrapers fall back to their v1 URL formulas, which are
byte-identical to the pre-change behavior.

> **Note**: the proposal's §6 Q1 mentions a `FakeLocationResolver`
> in `tests/conftest.py`. The actual location is split across
> 2 test files (no `conftest.py` entry). This delta is
> updated to reflect the real layout. A third test double
> (`_StubResolver` in `test_linkedin_settings.py`) was added by
> this change's T-001 commit to satisfy mypy --strict conformance
> for the extended Protocol.

#### Scenario: `FakeLocationResolver` in `test_filter_use_case.py` grows both `resolve_infojobs` and `resolve_structured`

- **GIVEN** the `FakeLocationResolver` class in `tests/unit/test_filter_use_case.py` originally has only `resolve`
- **WHEN** the class is extended with `def resolve_infojobs(self, location: str) -> tuple[int | None, int | None]: return (None, None)` (sister change) AND `def resolve_structured(self, location: str) -> tuple[str, str, str] | None: return None` (this change)
- **THEN** the existing tests in `test_filter_use_case.py` (which never call `resolve_infojobs` or `resolve_structured`) continue to pass (the new methods are no-ops for those tests)
- **AND** the test `test_filter_use_case.py::test_fake_resolver_has_resolve_infojobs_default` passes (asserts the new method exists and returns `(None, None)`)
- **AND** `mypy --strict` validates that the test double satisfies the extended Protocol

#### Scenario: `_FakeLocationResolver` in `test_linkedin_scraper.py` grows both new methods

- **GIVEN** the `_FakeLocationResolver` class in `tests/unit/test_linkedin_scraper.py` originally has only `resolve`
- **WHEN** the class is extended with `def resolve_infojobs(self, location: str) -> tuple[int | None, int | None]: return (None, None)` (recording `self.calls_infojobs` for testability) AND `def resolve_structured(self, location: str) -> tuple[str, str, str] | None: return None` (recording `self.calls_structured` for testability)
- **THEN** the existing tests in `test_linkedin_scraper.py` continue to pass
- **AND** the new test `test_linkedin_scraper.py::test_fake_resolver_records_infojobs_calls` passes (asserts the new method is called and records the input)
- **AND** the new test `test_linkedin_scraper.py::test_fake_resolver_records_structured_calls` passes (asserts the new method is called and records the input)

#### Scenario: pre-change tests that do not touch the resolver still pass

- **GIVEN** the test doubles have the new `resolve_infojobs` and `resolve_structured` methods with the defaults `(None, None)` and `None` respectively
- **WHEN** `cd backend && uv run pytest` is run
- **THEN** ALL pre-change tests (the 51 existing tests in `test_hardcoded_location_resolver.py`, the existing tests in `test_filter_use_case.py`, `test_linkedin_scraper.py`, etc.) continue to pass
- **AND** the only NEW tests are the ~30+ tests for the InfoJobs path (sister change) and the ~24 tests for the structured-fallback path (this change)

### REQ-PROV-LOC-003 — Composition root wires the SAME resolver to BOTH scrapers

The `app_factory.build_app()` function MUST construct a SINGLE
`HardcodedLocationResolver` instance and inject it into BOTH:

1. `LinkedInScraperSettings(location_resolver=location_resolver)` (existing)
2. `InfoJobsScraperSettings(location_resolver=location_resolver)` (NEW in sister change)

The single-instance pattern is intentional: the resolver is a
read-only in-process dict lookup; sharing the instance costs
~50 bytes (the dict references) and keeps the composition root
explicit about the fact that the SAME `location` string is
translated to BOTH a LinkedIn `geoId` AND an InfoJobs
`(province_id, country_id)` tuple AND (after this change) a
LinkedIn `(city, province, country)` triplet by the SAME class.

> **L607 shadowing bug**: discovered in this change's T-003 (obs #346).
> On the pre-sister-merge base (`f41aa90`), `app_factory.py` had a
> second `HardcodedLocationResolver()` constructor call at line 607
> inside the chat-filter wiring, shadowing the line-185 instance
> for the chat path. The sister change's T-003 commit
> (`eec2526 fix(app_factory): share location_resolver instance + remove L607 shadow`)
> REMOVED the L607 line. This change VERIFIES that the L607 fix
> persists post-merge: the composition test `test_resolver_shared_with_linkedin_scraper_settings`
> (added in this change's T-003 commit) PASSES on `f41aa90` because
> the L185 → LinkedInScraperSettings → app.state chain is intact
> (the L607 shadow only affects the chat-filter path, which is
> not exercised by this change's test). The orchestrator coordinates
> the PR merge so that BOTH: (a) the L185 instance sharing for the
> LinkedIn fallback change, AND (b) the L607 removal for the
> sister change's chat-filter correctness, land in `main`.

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

### REQ-LI-LOC-001 — `LocationResolverPort.resolve_structured` method (THIS CHANGE)

The `LocationResolverPort` Protocol MUST declare a third method
`resolve_structured(self, location: str) -> tuple[str, str, str] | None`
that returns the LinkedIn-specific `(city, province, country)`
triplet in Title Case with tildes (NFC) for cities with structured
mapping but no `geoId`. The method is intentionally NOT `async` —
it is a pure in-process dict lookup, same as `resolve()` and
`resolve_infojobs`.

The Protocol's docstring MUST document that:

- The triplet format is `(city, province, country)` where each is
  Title Case with NFC composed tildes (e.g. `("Antequera",
  "Andalucía", "Spain")`).
- The method returns `None` for inputs that are not city-level
  (e.g. country-level `"España"`, CCAA-level `"Andalucía"`,
  unknown city `"Berlin"`, empty string).
- The method is INDEPENDENT of `resolve()`: a city can have
  `geoId` only (e.g. `Madrid`), `structured` only (e.g.
  `Antequera`), both, or neither. The decision of which
  format to use is the consumer's (LinkedIn scraper's), not
  the resolver's.

#### Scenario: `LocationResolverPort` declares all THREE methods

- **GIVEN** the Protocol is defined in `application/ports.py`
- **WHEN** `inspect.getmembers(LocationResolverPort)` lists the methods
- **THEN** the list contains `resolve` AND `resolve_infojobs` AND `resolve_structured` (all three declared explicitly)
- **AND** `mypy --strict` no reports `Definition of "__call__" in protocol "LocationResolverPort" is missing in some class` for `HardcodedLocationResolver`, `FakeLocationResolver`, `_FakeLocationResolver`, or `_StubResolver`

#### Scenario: `HardcodedLocationResolver` implements `resolve_structured`

- **GIVEN** `HardcodedLocationResolver()` is instantiated with no args (uses the `_STRUCTURED_MAPPING` default)
- **WHEN** `resolver.resolve_structured("Antequera")` is called
- **THEN** returns `("Antequera", "Andalucía", "Spain")` (Title Case with NFC tildes)
- **AND** the test `test_hardcoded_location_resolver.py::test_resolve_structured_antequera` passes

#### Scenario: `FakeLocationResolver` (test double) implements the third method with default `None`

- **GIVEN** `FakeLocationResolver()` is instantiated in `tests/conftest.py` (or `test_filter_use_case.py`)
- **WHEN** `fake.resolve_structured("anything")` is called
- **THEN** returns `None` (default)
- **AND** `mypy --strict` validates that `FakeLocationResolver` satisfies the triple-method Protocol
- **AND** the pre-existing tests that use `FakeLocationResolver` continue to pass without modification (the default `None` is the unmapped sentinel)

### REQ-LI-LOC-002 — Normalización 4-step del input (THIS CHANGE)

`resolve_structured` MUST reusar la misma cadena de normalización
4-step que `resolve`: (1) NFC compose vía
`unicodedata.normalize("NFC", ...)`, (2) `casefold()`, (3)
`strip()`, (4) remove accents vía
`unicodedata.normalize("NFD", x).encode("ascii", "ignore").decode("ascii")`.
El lookup key es `normalized` (lowercase + sin tildes + sin
espacios extra); el value retornado preserva Title Case + tildes
NFC.

#### Scenario: input con tildes (NFD decompuesto) normaliza a NFC

- **GIVEN** el resolver aplica `unicodedata.normalize("NFC", ...)` como step 1
- **WHEN** se llama `resolve_structured("Ante\u0301ra")` (NFD: `Ante` + combining acute)
- **THEN** el lookup normaliza a `"antequera"` y retorna `("Antequera", "Andalucía", "Spain")`
- **AND** el test `test_hardcoded_location_resolver.py::test_resolve_structured_nfd_normalized` pasa

#### Scenario: input en mayúsculas matchea el dict lowercase

- **GIVEN** el lookup key es `casefold()` del input normalizado
- **WHEN** se llama `resolve_structured("ANTEQUERA")`
- **THEN** el lookup key es `"antequera"`, matchea el dict, retorna `("Antequera", "Andalucía", "Spain")`
- **AND** el test `test_hardcoded_location_resolver.py::test_resolve_structured_uppercase` pasa

#### Scenario: input con whitespace extra se trimea

- **GIVEN** el lookup key se trimea con `strip()`
- **WHEN** se llama `resolve_structured("  Antequera  ")`
- **THEN** el lookup key es `"antequera"`, retorna el triplet esperado
- **AND** el test `test_hardcoded_location_resolver.py::test_resolve_structured_strip` pasa

#### Scenario: input sin tildes matchea el value con tildes

- **GIVEN** el step 4 remueve accents del lookup key pero el value del dict preserva tildes
- **WHEN** se llama `resolve_structured("Cadiz")` (input ASCII)
- **THEN** el lookup key es `"cadiz"`, matchea, retorna `("Cádiz", "Andalucía", "Spain")` (value con tilde)
- **AND** el test `test_hardcoded_location_resolver.py::test_resolve_structured_no_accent_input` pasa

### REQ-LI-LOC-003 — Alias-to-canonical recurse (THIS CHANGE)

`resolve_structured` MUST respetar la misma lógica de `_ALIASES`
que `resolve`: si el normalized input no está en el dict directo,
intenta `canonical_key = self._aliases.get(normalized, normalized)`
y busca el `canonical_key` en `_STRUCTURED_MAPPING`. Esto permite
que un alias en español (ej. `"ante" → "antequera"`) resuelva al
triplet completo.

#### Scenario: alias en `_ALIASES` se expande al canonical

- **GIVEN** `_ALIASES = {"ante": "antequera"}` (alias agregado en este change; debe existir)
- **WHEN** se llama `resolve_structured("ante")`
- **THEN** `canonical_key = "antequera"`, retorna `("Antequera", "Andalucía", "Spain")`
- **AND** el test `test_hardcoded_location_resolver.py::test_resolve_structured_alias_recurse` pasa

#### Scenario: alias encadenado (alias → alias → canonical)

- **GIVEN** `_ALIASES` defines a chain (e.g. `{"ante": "ante", "antequera_canonical": "antequera"}` — hypothetical)
- **WHEN** se llama `resolve_structured("ante")` con un chain
- **THEN** el recurse itera hasta encontrar `"antequera"` en el dict, retorna el triplet
- **AND** el test `test_hardcoded_location_resolver.py::test_resolve_structured_alias_chain` pasa (parametrized: chain 1-hop y 2-hop)

### REQ-LI-LOC-004 — `None` semantic para inputs sin mapping (THIS CHANGE)

`resolve_structured` MUST retornar `None` (NO raise) en estos casos:

1. Input vacío (`""`).
2. Ciudad no presente en `_STRUCTURED_MAPPING` ni en `_ALIASES` (ej. `"Berlin"`, `"Tokio"`, `"Atlantis"`).
3. Input country-level (ej. `"España"`, `"Spain"`, `"Espana"`) — el dict es city-level.
4. Input CCAA-level (ej. `"Andalucía"`) — el dict es city-level, no region-level.
5. Input whitespace-only (ej. `"   "`).

> **Spec author decision**: For country-level inputs ("España",
> "Spain"), the resolver returns `None`. We do NOT return
> `("Madrid", "Madrid", "Spain")` nor `("", "", "Spain")`. Reasons:
> (a) the dict is city-level, a country is another category; (b)
> returning the capital would be an undocumented heuristic; (c)
> returning `("", "", "Spain")` would break the downstream
> `urllib.parse.quote()` which requires a non-empty city. The
> legacy fallback `?location=España` (raw) is LinkedIn's
> responsibility, not the resolver's.

#### Scenario: ciudad desconocida retorna `None`

- **GIVEN** `_STRUCTURED_MAPPING` no contiene `"berlin"`
- **WHEN** se llama `resolve_structured("Berlin")`
- **THEN** retorna `None` (sin warning — el log de warning aplica a scraper, no al resolver)
- **AND** el test `test_hardcoded_location_resolver.py::test_resolve_structured_unknown_city` pasa

#### Scenario: string vacío retorna `None` (defensivo)

- **GIVEN** el input es `""`
- **WHEN** se llama `resolve_structured("")`
- **THEN** retorna `None` (defensivo, antes de normalizar)
- **AND** el test `test_hardcoded_location_resolver.py::test_resolve_structured_empty` pasa

#### Scenario: input country-level retorna `None` (NO es city-level)

- **GIVEN** el input es `"España"`, `"Spain"`, o `"Espana"`
- **WHEN** se llama `resolve_structured` con cualquiera de los 3
- **THEN** retorna `None` (no es una ciudad, es un país; el dict es city-level)
- **AND** el test `test_hardcoded_location_resolver.py::test_resolve_structured_country_input` pasa (parametrized: 3 cases)

#### Scenario: input CCAA-level retorna `None`

- **GIVEN** el input es `"Andalucía"` o `"Cataluña"`
- **WHEN** se llama `resolve_structured("Andalucía")`
- **THEN** retorna `None` (no es city-level, es CCAA)
- **AND** el test `test_hardcoded_location_resolver.py::test_resolve_structured_region_input` pasa

### REQ-LI-LOC-005 — `HardcodedLocationResolver.__init__` acepta `structured_mapping` (THIS CHANGE)

El ctor MUST aceptar un nuevo kwarg
`structured_mapping: Mapping[str, tuple[str, str, str]] | None = None`.
Si se omite, usa el dict default importado de
`_structured_mapping._STRUCTURED_MAPPING`. Esto MUST matchear el
patrón del kwarg `mapping` existente (para `geoIds`).

#### Scenario: ctor sin args usa el dict default

- **GIVEN** `HardcodedLocationResolver()` se instancia
- **WHEN** se inspecciona `resolver._structured_mapping`
- **THEN** es el dict default importado de `_structured_mapping._STRUCTURED_MAPPING`
- **AND** contiene al menos 10 entries (las confirmadas en REQ-LI-LOC-D11)

#### Scenario: ctor con `structured_mapping` custom lo usa

- **GIVEN** un dict custom `{"foo": ("Foo", "Bar", "Spain")}`
- **WHEN** se instancia `HardcodedLocationResolver(structured_mapping=custom_dict)`
- **THEN** `resolver._structured_mapping is custom_dict`
- **AND** `resolve_structured("foo")` retorna `("Foo", "Bar", "Spain")` (NO `"antequera"`)
- **AND** el test `test_hardcoded_location_resolver.py::test_ctor_custom_structured_mapping` pasa

#### Scenario: `mapping` y `structured_mapping` son independientes

- **GIVEN** dos dicts `m1` (geoIds) y `s1` (structured) separados
- **WHEN** se instancia `HardcodedLocationResolver(mapping=m1, structured_mapping=s1)`
- **THEN** cambiar `m1` post-construcción NO afecta `s1` (y viceversa) — cada uno es una referencia separada en `self`
- **AND** el test `test_hardcoded_location_resolver.py::test_mappings_independent` pasa

### REQ-LI-LOC-006 — Indepencia entre `resolve()`, `resolve_infojobs()` y `resolve_structured()` (THIS CHANGE)

Los tres métodos MUST ser completamente independientes: una
ciudad puede tener uno, otro, todos, o ninguno. El
`_CANONICAL_MAPPING`, `_INFOJOBS_MAPPING` y `_STRUCTURED_MAPPING`
son dicts separados.

#### Scenario: ciudad con `geoId` NO duplica en structured

- **GIVEN** v1 tiene `Madrid` en `_CANONICAL_MAPPING` (geoId) pero NO en `_STRUCTURED_MAPPING` (per Q2 del proposal: "NO. El geoId es LinkedIn's preferred format y siempre gana")
- **WHEN** se inspecciona `_STRUCTURED_MAPPING`
- **THEN** `"madrid"` NO está presente
- **AND** el test `test_hardcoded_location_resolver.py::test_madrid_not_in_structured_mapping` pasa (lock-in de la decisión)

## Out of scope

- Defining a separate `InfoJobsLocationResolverPort` Protocol — the
  user's Q1 answer (Approach A) is "extend the existing Protocol
  with a second method", mirroring the `LLMClientPort.complete` +
  `stream_complete` pattern.
- Renaming `resolve` to `resolve_linkedin` (the `resolve` name
  predates the sister change and is consumed by the LinkedIn use
  case; renaming would be a breaking change for the pre-WU call
  sites).
- Adding `@runtime_checkable` to the Protocol (mirrors the v1
  choice; structural conformance is enforced at mypy --strict time
  only).
- Adding async/sync variants (the resolver is intentionally sync —
  pure in-process dict lookup).
- The structured mapping's city coverage beyond the 10 cities in
  the v1 dict (user can extend in a follow-up PR; same pattern as
  `_CANONICAL_MAPPING`).
- Non-Spanish cities (e.g. `Tokio`, `Berlin`) — the legacy
  fallback `?location=<raw>` covers them; adding triplets is
  trivial in a follow-up.
- Modifying the v1 chat-filter path (`_execute_v1`) — the v1 path
  does not call the resolver; modifying it is a separate follow-up.
