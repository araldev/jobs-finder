# Spec: `linkedin-structured-location-fallback` — `_STRUCTURED_MAPPING` + LIVE test gate

> **Promoted to source of truth on 2026-06-10** from
> `openspec/changes/archive/2026-06-10-backend-linkedin-location-fallback/specs/backend-linkedin-location-fallback/spec.md`
> (Domain 3, archived in `openspec/changes/archive/2026-06-10-backend-linkedin-location-fallback/`).
>
> This was a NEW capability delta. No prior
> `openspec/specs/linkedin-structured-location-fallback/spec.md`
> existed. The delta is promoted in full as the foundational spec
> for the capability, capturing the 10-city mapping, the
> VERIFIED/SPECULATIVE provenance, and the LIVE test gate. Source
> observation IDs for traceability: explore #332, proposal #333,
> spec #336, design #338, tasks #340, apply-progress #345,
> verify-report #348.

## Purpose

The `_STRUCTURED_MAPPING` is the dict complementario al
`_CANONICAL_MAPPING` in
`backend/src/jobs_finder/infrastructure/location/`:

- `_CANONICAL_MAPPING: dict[str, int]` — translates a canonical
  city/region name to a LinkedIn `geoId` integer. Used by
  `LocationResolverPort.resolve()` to produce
  `?geoId=<int>&start=...` URLs.
- `_STRUCTURED_MAPPING: dict[str, tuple[str, str, str]]` —
  translates a city name to a `(city, province, country)` triplet.
  Used by `LocationResolverPort.resolve_structured()` to produce
  `?location=<city>,<province>,<country>&start=...` URLs.

Both dicts live in `infrastructure/location/` (sibling modules
`_mapping.py` and `_structured_mapping.py`). They are READ-ONLY
in-process dicts loaded at module import time.

This capability defines the v1 content of the structured mapping
(10 Spanish cities), the VERIFIED/SPECULATIVE provenance of each
entry, and the LIVE test gate that validates the format against
real LinkedIn.

## Requirements

### REQ-LI-SFB-001 — `_STRUCTURED_MAPPING` v1 contiene 10 ciudades españolas

The dict `_STRUCTURED_MAPPING` (in
`backend/src/jobs_finder/infrastructure/location/_structured_mapping.py`)
MUST contain at least the 10 cities confirmed in the proposal
(`obs #333` §4.3). Each entry is
`dict[normalized_key, tuple[city, province, country]]` where the
keys are lowercase + no tildes (lookup) and the values are Title
Case with tildes (output).

| Key (lookup) | Value `city` | Value `province` | Value `country` |
|---|---|---|---|
| `antequera` | `"Antequera"` | `"Andalucía"` | `"Spain"` |
| `fuengirola` | `"Fuengirola"` | `"Málaga"` | `"Spain"` |
| `marbella` | `"Marbella"` | `"Málaga"` | `"Spain"` |
| `toledo` | `"Toledo"` | `"Castilla-La Mancha"` | `"Spain"` |
| `salamanca` | `"Salamanca"` | `"Castilla y León"` | `"Spain"` |
| `cadiz` | `"Cádiz"` | `"Andalucía"` | `"Spain"` |
| `granada` | `"Granada"` | `"Andalucía"` | `"Spain"` |
| `gijon` | `"Gijón"` | `"Asturias"` | `"Spain"` |
| `leon` | `"León"` | `"Castilla y León"` | `"Spain"` |
| `vigo` | `"Vigo"` | `"Galicia"` | `"Spain"` |

> **Provenance comment**: 9 entries are SPECULATIVE (province
> and country inferred from Spanish administrative divisions);
> only `antequera` is user-VERIFIED via the user-captured URL
> `https://www.linkedin.com/jobs/search?keywords=react&location=Antequera%2CAndaluc%C3%ADa%2CSpain`
> and the LIVE test gate (see REQ-LI-SFB-005).

#### Scenario: las 10 ciudades retornan triplet

- **GIVEN** el mapping default está cargado
- **WHEN** se itera `for key, expected in 10_test_cases:` y se llama `resolve_structured(key)`
- **THEN** cada uno retorna el triplet esperado (parametrized test, 10 cases)
- **AND** el test `test_hardcoded_location_resolver.py::test_all_10_cities_in_mapping` pasa (parametrized)

#### Scenario: `Madrid` NO está en el structured mapping (decision de la propuesta)

- **GIVEN** `Madrid` está en `_CANONICAL_MAPPING` (geoId) pero NO en `_STRUCTURED_MAPPING` (per Q2 de la propuesta: NO duplicar — el geoId es siempre preferred)
- **WHEN** se llama `resolve_structured("Madrid")`
- **THEN** retorna `None` (no es un fallo — `Madrid` usa el camino `geoId`)
- **AND** el test `test_hardcoded_location_resolver.py::test_madrid_not_in_structured_mapping` pasa (lock-in de la decisión)

### REQ-LI-SFB-002 — Provenance: 1 VERIFIED (Antequera) + 9 SPECULATIVE

The module `_structured_mapping.py` MUST contain an inline
comment on each entry distinguishing VERIFIED (user-captured URL
+ LIVE test gate) from SPECULATIVE (province/country inferred
from Spanish administrative divisions, pending LIVE validation).

- `"antequera"`: **VERIFIED** (the user captured the actual URL
  on LinkedIn: `?keywords=react&location=Antequera%2CAndaluc%C3%ADa%2CSpain`).
- `"fuengirola"`, `"marbella"`, `"toledo"`, `"salamanca"`, `"cadiz"`,
  `"granada"`, `"gijon"`, `"leon"`, `"vigo"`: **SPECULATIVE**
  (province/country were inferred; the LIVE test gate
  validates them in a follow-up iteration).

The pattern is the same as the pre-change `_CANONICAL_MAPPING`:
each entry has an inline `# VERIFIED` or `# SPECULATIVE` comment.

#### Scenario: comment inline marca VERIFIED vs SPECULATIVE

- **GIVEN** el archivo `_structured_mapping.py` se carga
- **WHEN** se lee el módulo
- **THEN** cada entry tiene un comment `# VERIFIED` o `# SPECULATIVE` inline
- **AND** el test `test_hardcoded_location_resolver.py::test_mapping_has_verified_comments` pasa (asserts via `ast` parse o `inspect.getsource`)

### REQ-LI-SFB-003 — Country en inglés (`"Spain"`) + alias español

The `country` field in all 10 triplets MUST be `"Spain"` (English,
matching the user-captured real URL). The `_ALIASES` dict
(`hardcoded_resolver.py`) MUST normalize the Spanish variants
`"España"` and `"Espana"` to `"spain"`.

**However**: since `_STRUCTURED_MAPPING` is city-level, a
country-level input (e.g. `"España"`) returns `None` (see
`REQ-LI-LOC-004` in the `location-resolver` spec). The alias
chain applies for the input that COMBINES city + country (e.g. a
future `"Madrid, Spain"`); for city-level input, the alias is
irrelevant because the dict keys are city names only.

#### Scenario: alias `españa` mapea a `spain` en `_ALIASES`

- **GIVEN** `_ALIASES = {"españa": "spain", "espana": "spain"}` (alias chain)
- **WHEN** se llama `resolve_structured("España")` (country-only input)
- **THEN** retorna `None` (no es city-level)
- **AND** el test `test_hardcoded_location_resolver.py::test_country_alias_returns_none_for_country_input` pasa

#### Scenario: triplet value es siempre `"Spain"` (inglés)

- **GIVEN** los 10 triplets del mapping
- **WHEN** se inspecciona `triplet[2]` (el country)
- **THEN** es exactamente `"Spain"` (Title Case, inglés, sin tilde) en los 10
- **AND** el test `test_hardcoded_location_resolver.py::test_country_value_is_english_spain` pasa (parametrized: 10 cases)

### REQ-LI-SFB-004 — Province accent preservation (canonical Title Case con tildes)

Las provinces en el value MUST preservar tildes: `"Andalucía"`
(con `í`), `"Castilla y León"` (con `ó`), `"Castilla-La Mancha"`
(con `-` entre palabras), `"Galicia"` (sin tildes), etc. El
`_normalize` las remueve del lookup key pero el value las
preserva.

#### Scenario: `Andalucía` se preserva en el output

- **GIVEN** el input `"andalucia"` (sin tilde)
- **WHEN** se llama `resolve_structured("andalucia")`
- **THEN** retorna `("Antequera", "Andalucía", "Spain")` (value con tilde, no `Andalucia` sin tilde)
- **AND** el test `test_hardcoded_location_resolver.py::test_province_accent_preserved_andalucia` pasa

#### Scenario: `Castilla y León` con espacio y tilde se preserva

- **GIVEN** el input `"castilla y leon"` (sin tildes)
- **WHEN** se llama `resolve_structured("castilla y leon")`
- **THEN** retorna `("Salamanca", "Castilla y León", "Spain")` (value con espacio y `ó`)
- **AND** el test `test_hardcoded_location_resolver.py::test_province_multiword_preserved` pasa

#### Scenario: `Castilla-La Mancha` con guion se preserva

- **GIVEN** el input `"toledo"`
- **WHEN** se llama `resolve_structured("toledo")`
- **THEN** retorna `("Toledo", "Castilla-La Mancha", "Spain")` (province con guion)
- **AND** el test `test_hardcoded_location_resolver.py::test_province_hyphen_preserved` pasa

### REQ-LI-SFB-005 — LIVE test gated `LLM_LIVE_TESTS=1` (no CI)

Un test de integración LIVE en
`backend/tests/integration/test_linkedin_live.py` MUST validar
que la URL `?keywords=react&location=Antequera%2CAndaluc%C3%ADa%2CSpain`
retorna ofertas en Antequera/Málaga/Andalucía contra LinkedIn
real. MUST estar gated por env var `LLM_LIVE_TESTS=1` (no en CI
per AGENTS.md rule #1: "No live scraping in tests").

> **Why gated**: a LIVE test hitting real LinkedIn is fragile
> (anti-bot protections, network availability, legal/scope
> concerns). The gate keeps the CI green by default; a developer
> with `LLM_LIVE_TESTS=1` in their local env can opt in to
> validate the format against real LinkedIn.

#### Scenario: LIVE test gated skipped en CI

- **GIVEN** `LLM_LIVE_TESTS` no está seteado (default CI)
- **WHEN** `pytest` corre sin env var
- **THEN** el LIVE test se SKIP (no se ejecuta contra LinkedIn)
- **AND** el test `test_linkedin_live.py::test_live_antequera_structured_url_returns_andalucia_jobs` reporta `SKIPPED`

#### Scenario: LIVE test gated runs cuando se habilita

- **GIVEN** `LLM_LIVE_TESTS=1` y network disponible
- **WHEN** `pytest tests/integration/test_linkedin_live.py` corre
- **THEN** el test hace una request real a LinkedIn con la URL estructurada
- **AND** verifica que ≥1 de los primeros 5 resultados contiene `"Antequera"`, `"Málaga"`, o `"Andalucía"` en el location (assertion flexible — LinkedIn puede devolver la city exacta o la province o el country)

## Out of scope

- Adding more cities to `_STRUCTURED_MAPPING` (user can extend in
  a follow-up PR; same pattern as `_CANONICAL_MAPPING`).
- Non-Spanish cities (e.g. `Tokio`, `Berlin`, etc.) — the legacy
  fallback `?location=<raw>` covers them; adding triplets is
  trivial in a follow-up.
- Cities that ALREADY have a `geoId` in `_CANONICAL_MAPPING`
  (e.g. `Madrid`, `Barcelona`) — the geoId is always preferred
  (REQ-LI-LOC-006 in the `location-resolver` spec).
- Migrating the dict to a JSON file or DB — same hardcoded
  pattern as `_CANONICAL_MAPPING`.
- Auto-detecting the country from the input — always hardcoded
  in the dict.
- LIVE test coverage of the 9 SPECULATIVE entries — deferred to
  a follow-up change (one LIVE test per city, gated
  `LLM_LIVE_TESTS=1`).
