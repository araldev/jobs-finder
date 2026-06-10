# Design: `backend-linkedin-location-fallback`

> **Change**: `backend-linkedin-location-fallback` • **Base**: `f41aa90` (post `backend-scraper-query-tuning`) • **Strict TDD**: ACTIVE
> **Artifact mode**: `both` (OpenSpec filesystem + Engram) • **Spec**: obs #336
> **Resolver strategy**: extender `LocationResolverPort` con un segundo método `resolve_structured` (Q5=A, Q6=C, Q7=C confirmados por el user).

## 1. Resumen ejecutivo

Este cambio cierra el **gap residual** que dejó `backend-scraper-query-tuning` (PR #4): el `HardcodedLocationResolver` traduce 34 strings canónicos a un `geoId` numérico (`?geoId=<int>`) y para todo lo demás el scraper cae al fallback legacy `?location=<raw_str>` — que LinkedIn silently ignora y devuelve resultados sin filtro de ubicación. Para ciudades **NO** en ese mapping de 34 (ej. `Antequera`, `Fuengirola`, `Marbella`, `Toledo`) el usuario capturó una URL real de LinkedIn que muestra un tercer formato soportado: `?location=<city>,<province>,<country>`. Este cambio agrega una rama intermedia al URL builder para esas ciudades (10 entries en un nuevo `_STRUCTURED_MAPPING` v1), preservando el fallback legacy para todo lo demás. Cero cambio en el HTTP contract — el frontend sigue enviando `location=<raw>`; el resolver convierte internamente. El cambio es 100% backwards-compat: `Berlin`, `Tokio`, ciudades sin triplet caen al mismo `?location=<str>` legacy. **Single PR, ~580 LOC** (forecast del user: 380–550; ajustado al alza por el LIVE test + tests parametrizados).

## 2. Architecture overview

```
  Frontend (Next.js) ── GET /jobs?q=react&location=Antequera&limit=20
         │
         ▼
  FastAPI aggregator (SearchAllSourcesUseCase)
         │
         ├── asyncio.gather (3 sources) ─────────────────────────────┐
         │                                                            │
         ▼                                                            ▼
  LinkedInPlaywrightScraper.search("react", "Antequera", 20)   Indeed + InfoJobs (UNTOUCHED)
         │
         ├── _build_url() priority: geoId > structured > raw
         │       1. resolve() == int       → ?keywords=...&geoId=<n>&start=<s>   (existing)
         │       2. resolve_structured()    → ?keywords=...&location=City,Province,Country&start=<s>  (NEW)
         │       3. ambos None              → ?keywords=...&location=<raw>&start=<s>  (legacy fallback)
         │
         ▼
  paginated_search (helper) ── throttle acquired ONCE around the loop
         │
         ▼
  Playwright navigates the URL, returns list[Job]
         │
         ▼
  aggregator dedup + sort + return (UNCHANGED)


  Composition root wiring (app_factory.py:185-256):
  ┌──────────────────────────────────────────────────────────┐
  │  HardcodedLocationResolver()  ◄── UNIQUE instance        │
  │    .resolve()             → int | None                   │
  │    .resolve_structured()  → tuple[str, str, str] | None  │  ← NEW
  │    Mappings:                                               │
  │      _CANONICAL_MAPPING  (34 entries, geoId)              │
  │      _STRUCTURED_MAPPING  (10 entries, triplet)  ← NEW    │
  │      _ALIASES             (5 entries, shared)             │
  └──────────────────────────────────────────────────────────┘
            │ injected into LinkedInScraperSettings (L255)
            │ injected into FilterJobsByIntentUseCase (L617)
            │ exposed on app.state.location_resolver (L522)

  ──────────────────────────────────────────────────────────────────
  Bonus fix (carried over from backend-infojobs-provinces, obs #337):
  app_factory.py:607 currently rebuilds location_resolver inside the
  chat_enabled branch (shadowing L185). The parallel change fixes that
  line. This change reuses the SAME instance — no new shadowing risk.
  ──────────────────────────────────────────────────────────────────
```

**Puntos clave**:

- **Mismo `HardcodedLocationResolver` instance** que ya está inyectado en el LinkedIn scraper (`app_factory.py:255`) — no hay nuevo wiring en el composition root.
- El scraper llama `resolve()` Y `resolve_structured()` **EXACTAMENTE una vez** por `search()` (no por página). El tuple se captura en el closure `_make_fetch_one_page`.
- Para `Antequera` (mapped en `_STRUCTURED_MAPPING` pero NO en `_CANONICAL_MAPPING`): el scraper cae al nuevo branch `?location=Antequera%2CAndaluc%C3%ADa%2CSpain` — más cerca de la URL real capturada por el user.
- Para `Berlin`, `Tokio` (mapped en ningún dict): el scraper cae al fallback legacy `?location=<str>` — idéntico al pre-change. **Cero regresión**.
- Para `Madrid` (mapped en `_CANONICAL_MAPPING` con `geoId=103374081`): el branch `geoId` gana (priority 1 > 2). `?geoId=103374081&start=0` — el camino v1 sin cambios.

## 3. Architecture decisions

| # | Elección | Rationale |
|---|---|---|
| 1 | Extender `LocationResolverPort` con `resolve_structured` (NO nuevo Protocol) | Q5=A confirmada por user. Patrón canónico: `LLMClientPort.complete` + `stream_complete` (`application/ports.py:384-451`). |
| 2 | `_STRUCTURED_MAPPING` en módulo sibling `_structured_mapping.py` (sibling de `_mapping.py`) | Spec obs #336 §"Domain 1 Requirement: HardcodedLocationResolver.__init__ acepta structured_mapping". Mismo patrón que el cambio paralelo: `_infojobs_mapping.py` (obs #337 §4.2). |
| 3 | `resolve_structured()` reutiliza `_normalize()` existente (private static method) | El spec §"Domain 1: Normalización 4-step del input" requiere reuso del 4-step chain. La función `_normalize` ya es `@staticmethod`; `resolve_structured` la llama directamente. |
| 4 | `_build_url` priority `geoId > structured > raw` | Spec §"Domain 2 Requirement: _build_url prioridad geoId > structured > raw". El `geoId` es LinkedIn's preferred format y siempre gana (decisión Q2 del proposal). |
| 5 | Resolver se llama UNA VEZ por `search()` (no por página) | Spec §"Domain 2 Requirement: search() consulta resolve_structured una vez". Patrón LinkedIn existente (`scraper.py:249-261`). El tuple se captura en el closure. |
| 6 | `urllib.parse.quote` para URL encoding (no `quote_plus`, no encoding manual) | `quote` es el path-of-record (`scraper.py:55`, `scraper.py:355`). Tildes NFC se encodean como `%C3%AD` (UTF-8 multibyte); comas como `%2C`; espacios como `%20`. Reproduce byte-for-byte la URL capturada por el user. |
| 7 | Country-only inputs (`"España"`, `"Spain"`) retornan `None` (NO triplet) | Decisión del spec author (obs #336 §"Spec author decision"). El dict es city-level; un país es otra categoría. NO heurística ("devolver la capital"), NO tuple vacío (rompería el `quote()` downstream). El fallback legacy `?location=España` es responsabilidad de LinkedIn. |
| 8 | 9 ciudades speculative (no LIVE-verified), 1 VERIFIED (`Antequera`) | Spec §"Domain 3 Requirement: Solo Antequera es user-verified". El LIVE test gated `LLM_LIVE_TESTS=1` valida los 9 speculative en una iteración posterior. Si un ID falla, se remueve del dict (1-line change, 0 LOC). |
| 9 | `_ALIASES` se comparte entre `resolve()` y `resolve_structured()` | El spec §"Domain 1 Requirement: Alias-to-canonical recurse" requiere reuso. Mismo `_ALIASES` instance, mismo `_normalize()` instance. El `HardcodedLocationResolver` ctor acepta `aliases` kwarg (existente); se reusa sin cambios. |
| 10 | NO extender `JobSearchPort` Protocol (el tuple es scraper-internal) | Mismo patrón que `geo_id` (`application/ports.py:39-60`): el kwarg `structured` fluye por el closure de `_make_fetch_one_page`, no por el Port. `JobSearchCacheKey` tampoco cambia (el tuple es LinkedIn-specific, no cross-source). |
| 11 | NO extender `AggregatedJobsQuery` / `InfoJobsJobsQuery` (HTTP shape preservada) | El frontend sigue enviando `location=<raw>`. El `resolve_structured` es una transformación interna. El contract HTTP no cambia. |
| 12 | Bonus: verificar que `app_factory.py:607` no shadow el `location_resolver` de L185 | El cambio paralelo `backend-infojobs-provinces` (obs #337 §4.5) ya planeó arreglar este bug. Este change reusa el mismo instance, así que no se duplica el bug — pero se documenta en §10 "Coordinación con cambios paralelos" como dependencia. |
| 13 | El `LIVE test` es gated `LLM_LIVE_TESTS=1` (NO en CI) | AGENTS.md rule #1: "No live scraping in tests". El LIVE test valida los 9 speculative IDs contra LinkedIn real; corre solo en local con `LLM_LIVE_TESTS=1`. |

## 4. Component changes

### 4.1 `application/ports.py` (MODIFY) — Protocol extension

**Cambio**: agregar `def resolve_structured(self, location: str) -> tuple[str, str, str] | None: ...` al `LocationResolverPort` Protocol después de `resolve()` (L188).

**Por qué**: el spec §"Domain 1 Requirement: `LocationResolverPort.resolve_structured`" requiere que el Protocol declare AMBOS métodos. `mypy --strict` enforce la conformancia estructural.

**Firma** (Python pseudocode):

```python
class LocationResolverPort(Protocol):
    def resolve(self, location: str) -> int | None:  # existing
        """Translate a free-form `location` string into a LinkedIn `geoId`."""

    def resolve_structured(self, location: str) -> tuple[str, str, str] | None:  # NEW
        """Translate into a (city, province, country) triplet (Title Case + NFC tildes).

        Returns `None` on miss (unknown / country-level / CCAA-level / empty).
        """
        ...
```

**Test strategy**: 2 tests (Protocol introspection + mypy --strict satisfaction).

### 4.2 `infrastructure/location/_structured_mapping.py` (NEW) — 10-entry dict

**Cambio**: crear el módulo nuevo `_structured_mapping.py` con `_STRUCTURED_MAPPING: dict[str, tuple[str, str, str]]` y `_ALIASES_STRUCTURED: dict[str, str]` (alias-to-canonical para el structured lookup, si se necesitan).

**Por qué**: spec §"Domain 3 Requirement: `_STRUCTURED_MAPPING` v1 contiene 10 ciudades españolas". Sibling de `_mapping.py` (L40); mismo patrón que el cambio paralelo (`_infojobs_mapping.py` en obs #337 §4.2).

**Contenido**:

```python
_STRUCTURED_MAPPING: dict[str, tuple[str, str, str]] = {
    # === VERIFIED (user-captured URL on 2026-06-08) ===
    "antequera": ("Antequera", "Andalucía", "Spain"),
    # === SPECULATIVE (province/country inferred, LIVE test will validate) ===
    "fuengirola": ("Fuengirola", "Málaga", "Spain"),
    "marbella":   ("Marbella", "Málaga", "Spain"),
    "toledo":     ("Toledo", "Castilla-La Mancha", "Spain"),
    "salamanca":  ("Salamanca", "Castilla y León", "Spain"),
    "cadiz":      ("Cádiz", "Andalucía", "Spain"),
    "granada":    ("Granada", "Andalucía", "Spain"),
    "gijon":      ("Gijón", "Asturias", "Spain"),
    "leon":       ("León", "Castilla y León", "Spain"),
    "vigo":       ("Vigo", "Galicia", "Spain"),
}

# Madrid NO está aquí — usa el camino geoId (Q2 del proposal).
```

**Test strategy**: 1 unit test (count lock: 10 entries), 1 parametrized test (10 entries × 1 city each returns the expected triplet).

### 4.3 `infrastructure/location/hardcoded_resolver.py` (MODIFY) — `resolve_structured` method

**Cambio**: agregar `def resolve_structured(self, location: str) -> tuple[str, str, str] | None` como segundo método de instancia. Ctor acepta `structured_mapping` kwarg (default = `_STRUCTURED_MAPPING`).

**Por qué**: spec §"Domain 1 Requirement: `HardcodedLocationResolver.__init__` acepta `structured_mapping`" y §"Requirement: `HardcodedLocationResolver` implementa `resolve_structured`".

**Firma** (Python pseudocode):

```python
class HardcodedLocationResolver(LocationResolverPort):
    def __init__(
        self,
        *,
        mapping: Mapping[str, int] | None = None,
        aliases: Mapping[str, str] | None = None,
        structured_mapping: Mapping[str, tuple[str, str, str]] | None = None,  # NEW
    ) -> None:
        self._mapping = mapping if mapping is not None else _CANONICAL_MAPPING
        self._aliases = aliases if aliases is not None else _ALIASES
        self._structured_mapping = (
            structured_mapping if structured_mapping is not None
            else _STRUCTURED_MAPPING  # NEW
        )

    def resolve_structured(self, location: str) -> tuple[str, str, str] | None:  # NEW
        # Short-circuit empty (same as resolve()).
        if not location:
            return None
        normalized = self._normalize(location)  # REUSE 4-step chain
        canonical_key = self._aliases.get(normalized, normalized)
        if canonical_key in self._structured_mapping:
            return self._structured_mapping[canonical_key]
        # Unknown / country-level / CCAA-level. No WARNING — same
        # semantic as resolve() but for the structured dict.
        return None
```

**Test strategy**: 10+ tests nuevos en `test_hardcoded_location_resolver.py` (10 cities parametrized, normalization 4-step, alias recurse, None semantic, ctor override).

### 4.4 `infrastructure/linkedin/scraper.py` (MODIFY) — `_build_url` priority + URL encoding

**Cambio**: modificar `_build_url(keywords, location, start, *, geo_id, structured)` para aceptar el nuevo kwarg `structured` y agregarlo como segunda rama (priority media entre `geoId` y `raw`).

**Por qué**: spec §"Domain 2 Requirement: `_build_url` prioridad `geoId > structured > raw`" y §"Requirement: URL encoding con tildes (NFC)".

**Firma** (Python pseudocode):

```python
@staticmethod
def _build_url(
    keywords: str,
    location: str,
    start: int,
    *,
    geo_id: int | None = None,
    structured: tuple[str, str, str] | None = None,  # NEW
) -> str:
    base = "https://www.linkedin.com/jobs/search/"
    kw = f"keywords={quote(keywords)}"
    start_q = f"start={start}"
    # Priority 1: geoId wins.
    if geo_id is not None:
        return f"{base}?{kw}&geoId={geo_id}&{start_q}"
    # Priority 2: structured triplet (NEW).
    if structured is not None:
        city, province, country = structured
        # quote() encodes tildes as UTF-8 (%C3%AD), commas as %2C,
        # spaces as %20. Reproduces the user-captured URL byte-for-byte.
        loc = quote(f"{city},{province},{country}")
        return f"{base}?{kw}&location={loc}&{start_q}"
    # Priority 3: legacy fallback (unchanged).
    return f"{base}?{kw}&location={quote(location)}&{start_q}"
```

**`search()` modification** (Python pseudocode):

```python
async def search(
    self,
    keywords: str,
    location: str,
    limit: int = 20,
    geo_id: int | None = None,
) -> list[Job]:
    if geo_id is None and self._settings.location_resolver is not None:
        geo_id = self._settings.location_resolver.resolve(location)  # existing
    structured: tuple[str, str, str] | None = None
    if self._settings.location_resolver is not None:  # NEW
        structured = self._settings.location_resolver.resolve_structured(location)
    # ... rest unchanged
    return await paginated_search(
        page=page,
        throttle=self._throttle,
        fetch_one_page=self._make_fetch_one_page(
            keywords, location, geo_id=geo_id, structured=structured  # NEW kwarg
        ),
        limit=limit,
        max_pages=self._settings.max_pages,
        inter_page_delay_seconds=self._settings.inter_page_delay_seconds,
        timeout_exc_type=LinkedInTimeoutError,
    )
```

**`_make_fetch_one_page` modification** (Python pseudocode):

```python
def _make_fetch_one_page(
    self,
    keywords: str,
    location: str,
    *,
    geo_id: int | None = None,
    structured: tuple[str, str, str] | None = None,  # NEW
) -> Callable[[Any, int, int], Awaitable[list[Job]]]:
    async def fetch_one_page(page, page_index, remaining):
        url = self._build_url(  # NEW: forward structured
            keywords, location, page_index * 25,
            geo_id=geo_id, structured=structured,
        )
        # ... rest unchanged
    return fetch_one_page
```

**Test strategy**: 7+ tests en `test_linkedin_scraper.py`:
- `test_search_uses_geoId_over_structured_when_both_available` (priority test)
- `test_search_uses_structured_format_when_no_geoId` (e.g. Antequera → `?location=Antequera%2CAndaluc%C3%ADa%2CSpain`)
- `test_search_uses_legacy_fallback_when_no_resolutions` (e.g. Berlin → `?location=Berlin`)
- `test_resolver_called_once_per_search_not_per_page` (parametrized 1/2/3 pages)
- `test_url_encoding_handles_tildes_and_commas` (golden assertion vs user-captured URL)
- `test_legacy_wiring_without_resolver_works` (location_resolver=None)
- `test_structured_none_falls_back_to_legacy` (FakeLocationResolver with `resolve_structured.return_value = None`)

### 4.5 `infrastructure/linkedin/throttle.py` (NO CHANGE)

**Por qué**: `LinkedInScraperSettings.location_resolver` ya está inyectado (de `backend-scraper-query-tuning`). Este change reusa el mismo field; no requiere nuevos slots.

### 4.6 `presentation/app_factory.py` (VERIFY ONLY) — Composition root

**Verificación**: el composition root ya construye `HardcodedLocationResolver()` en L185 y la inyecta en `LinkedInScraperSettings(location_resolver=location_resolver)` en L255. **NO se requiere nuevo wiring** para este change.

**Bonus coordination**: `app_factory.py:607` actualmente reconstruye `location_resolver = HardcodedLocationResolver()` dentro del branch `chat_enabled` (shadowing L185). El cambio paralelo `backend-infojobs-provinces` (obs #337 §4.5) ya planeó arreglar este bug. Este change reusa el mismo instance; cuando se mergeen ambos PRs el fix del bug en L607 debe persistir (ver §10 "Coordinación con cambios paralelos").

**Test strategy**: 1 test de composición: `test_resolver_shared_with_linkedin_scraper_settings` (asserts `app.state.location_resolver is settings.location_resolver` — la misma instance fluye a la scraper).

### 4.7 `backend/.env.example` (NO CHANGE)

**Por qué**: no hay env vars nuevos. Los 10 cities son hardcoded en el dict.

### 4.8 `backend/README.md` (MODIFY) — Documentation

**Cambio**: agregar una sección "LinkedIn structured location fallback" (~30 LOC) que documente:

- El priority order `geoId > structured > raw` con un ASCII diagram.
- Los 10 cities en `_STRUCTURED_MAPPING` (1 VERIFIED + 9 SPECULATIVE, marcados inline).
- El behavior del fallback legacy para unmapped cities.
- La nota: "El frontend sigue enviando `location=<raw>`; el resolver convierte internamente."
- Link al LIVE test gate (`LLM_LIVE_TESTS=1`).

**Test strategy**: 2 grep-style tests en `test_aggregator_filters.py` (lockeando keywords como "structured", "VERIFIED", "SPECULATIVE" en el README).

## 5. Data flow

### 5.1 `GET /jobs?q=react&location=Antequera&limit=20`

1. Frontend (Next.js) → `GET /api/jobs?q=react&location=Antequera&limit=20`.
2. Frontend Route Handler → `GET http://localhost:8000/jobs?q=react&location=Antequera&limit=20`.
3. FastAPI aggregator route: `aggregator.aggregate("react", "Antequera", 20)`.
4. `asyncio.gather` 3 sources. LinkedIn branch:
   - `LinkedInPlaywrightScraper.search("react", "Antequera", 20)` se invoca.
   - `geo_id = self._settings.location_resolver.resolve("Antequera")` → `"Antequera"` (str, NO mapping) → returns `None`.
   - `structured = self._settings.location_resolver.resolve_structured("Antequera")` → `("Antequera", "Andalucía", "Spain")`.
   - `geo_id is None`, `structured is not None` → URL builder uses the structured branch.
   - URL: `?keywords=react&location=Antequera%2CAndaluc%C3%ADa%2CSpain&start=0` (byte-for-byte el pattern de la URL real del user).
   - `paginated_search` loop acquires the throttle ONCE, iterates page 0..N with `start=0, 25, 50, ...`.
5. Playwright navigates each URL, parses cards, returns `list[Job]` (Antequera-area + Málaga-area).
6. Aggregator dedup + sort + return (UNCHANGED).

### 5.2 Backwards-compat: `location=Berlin` (unmapped)

- `resolve("Berlin")` returns `None` (no WARNING, just miss).
- `resolve_structured("Berlin")` returns `None` (no WARNING, just miss).
- URL: `?keywords=react&location=Berlin&start=0` (legacy fallback, byte-identical to pre-change).
- Result: 0 jobs or noisy (same as v1 behavior, no regression).

### 5.3 GeoId path takes priority: `location=Madrid` (has geoId)

- `resolve("Madrid")` returns `103374081` (int, in `_CANONICAL_MAPPING`).
- `resolve_structured("Madrid")` returns `None` (Madrid NOT in `_STRUCTURED_MAPPING` per Q2).
- URL: `?keywords=react&geoId=103374081&start=0` (geoId path, no change).
- Result: Madrid-area jobs (unchanged from `backend-scraper-query-tuning`).

### 5.4 Country-only: `location=España`

- `resolve("España")` returns `None` + WARNING.
- `resolve_structured("España")` returns `None` (NO triplet — spec author's decision).
- URL: `?keywords=react&location=Espa%C3%B1a&start=0` (legacy fallback).
- Result: 0 jobs (LinkedIn ignores the string param, returns globally-distributed results — same v1 broken behavior, no regression).

## 6. File-by-file change list (~580 LOC total)

| File | Action | LOC | Rationale |
|---|---|---|---|
| `application/ports.py` | MODIFY: +resolve_structured Protocol method | +10 | Spec §Domain 1 Requirement: Protocol tiene AMBOS métodos |
| `infrastructure/location/_structured_mapping.py` | NEW: 10-entry dict + docstring | +50 | Spec §Domain 3 Requirement: `_STRUCTURED_MAPPING` v1 contiene 10 ciudades |
| `infrastructure/location/hardcoded_resolver.py` | MODIFY: +resolve_structured + ctor kwarg | +60 | Spec §Domain 1 Requirement: HardcodedLocationResolver implementa resolve_structured |
| `infrastructure/linkedin/scraper.py` | MODIFY: _build_url priority + URL encoding + search() resolves structured + closure kwarg | +40 | Spec §Domain 2 Requirements: _build_url prioridad, URL encoding, search() consulta una vez |
| `infrastructure/linkedin/throttle.py` (or settings) | NO CHANGE | 0 | Reuse `location_resolver` field |
| `presentation/app_factory.py` | VERIFY: no shadowing bug; no new wiring | +0 to +10 | Bonus coord with parallel change |
| `backend/.env.example` | NO CHANGE | 0 | No new env vars |
| `backend/README.md` | MODIFY: +section "LinkedIn structured location fallback" | +30 | Document priority order + 10 cities + LIVE gate |
| `tests/unit/test_hardcoded_location_resolver.py` | MODIFY: +6+ new tests | +180 | Spec §Domain 1 test coverage |
| `tests/unit/test_linkedin_scraper.py` | MODIFY: +7+ new tests | +200 | Spec §Domain 2 test coverage |
| `tests/integration/test_linkedin_live.py` | MODIFY (or NEW): +1 LIVE test gated | +50 | Spec §Domain 3 LIVE test |
| `tests/unit/test_filter_use_case.py` (FakeLocationResolver) | MODIFY: +resolve_structured method | +5 | Spec §Domain 1: FakeLocationResolver implementa el segundo método |
| `tests/unit/test_linkedin_scraper.py` (_FakeLocationResolver) | MODIFY: +resolve_structured method | +5 | Same |
| **TOTAL** | | **~580** | (slightly above user forecast 380-550 due to LIVE test + parametrized tests) |

## 7. Test strategy (Strict TDD)

### 7.1 Unit tests (test-first per strict TDD)

**`tests/unit/test_hardcoded_location_resolver.py`** (MODIFY, +6+ tests):

- `test_resolve_structured_antequera`: returns `("Antequera", "Andalucía", "Spain")`.
- `test_resolve_structured_lowercase_antequera`: same result (casefold).
- `test_resolve_structured_uppercase_antequera`: `("ANTEQUERA")` → same.
- `test_resolve_structured_strip_whitespace`: `("  Antequera  ")` → same.
- `test_resolve_structured_nfd_normalized`: input `"Ante\u0301ra"` (NFD) → same.
- `test_resolve_structured_accentless_input_matches_tilde_value`: input `"Cadiz"` (ASCII) → `("Cádiz", ...)`.
- `test_resolve_structured_unmapped_returns_none`: input `"Berlin"` → `None`.
- `test_resolve_structured_empty_string_returns_none`: input `""` → `None` (no warning).
- `test_resolve_structured_country_level_returns_none`: `("España", "Spain", "Espana")` parametrized → all `None` (spec author's decision).
- `test_resolve_structured_ccaa_level_returns_none`: `("Andalucía",)` → `None`.
- `test_resolve_structured_alias_recurse`: `_ALIASES = {"ante": "antequera"}` → `("ante")` → `("Antequera", "Andalucía", "Spain")`.
- `test_resolve_structured_all_10_cities`: parametrized 10 cities × 1 input each (e.g. `("fuengirola", ("Fuengirola", "Málaga", "Spain"))`).
- `test_resolve_structured_madrid_returns_none`: `("Madrid")` → `None` (Madrid is geoId-only, NOT in structured).
- `test_resolve_structured_ctor_custom_mapping`: `HardcodedLocationResolver(structured_mapping={"foo": ("Foo", "Bar", "Baz")})` → `("foo")` → `("Foo", "Bar", "Baz")`.
- `test_resolve_structured_ctor_default_mapping`: `HardcodedLocationResolver()` (no args) → uses default 10-entry dict (asserts `len(resolver._structured_mapping) == 10`).
- `test_resolve_structured_independence_from_resolve`: same input "Antequera" → `resolve_structured` returns triplet, `resolve` returns None (independent methods).

**`tests/unit/test_linkedin_scraper.py`** (MODIFY, +7+ tests):

- `test_search_uses_geoId_over_structured_when_both_available`:
  - `FakeLocationResolver` with `resolve.return_value = 103374081` (Madrid geoId) and `resolve_structured.return_value = ("Madrid", "Madrid", "Spain")`.
  - URL must contain `geoId=103374081` and NOT `location=`.
- `test_search_uses_structured_format_when_no_geoId`:
  - `FakeLocationResolver` with `resolve.return_value = None` and `resolve_structured.return_value = ("Antequera", "Andalucía", "Spain")`.
  - URL must be `?keywords=react&location=Antequera%2CAndaluc%C3%ADa%2CSpain&start=0` (byte-for-byte the user-captured pattern).
- `test_search_uses_legacy_fallback_when_no_resolutions`:
  - `FakeLocationResolver` with `resolve.return_value = None` and `resolve_structured.return_value = None`.
  - URL must be `?keywords=react&location=Berlin&start=0`.
- `test_resolver_called_once_per_search_not_per_page` (parametrized 1, 2, 3 pages):
  - Drive the closure 1x, 2x, 3x.
  - Assert `fake.resolve.call_count == 1` and `fake.resolve_structured.call_count == 1`.
- `test_url_encoding_handles_tildes_and_commas`:
  - `structured = ("Cádiz", "Andalucía", "Spain")` → URL contains `location=C%C3%A1diz%2CAndaluc%C3%ADa%2CSpain`.
  - `structured = ("León", "Castilla y León", "Spain")` → URL contains `location=Le%C3%B3n%2CCastilla%20y%20Le%C3%B3n%2CSpain`.
- `test_legacy_wiring_without_resolver_works`:
  - `LinkedInScraperSettings(location_resolver=None)` → URL is `?location=Antequera` (legacy, no 500).
- `test_structured_none_falls_back_to_legacy`:
  - `FakeLocationResolver` with `resolve_structured.return_value = None` for `"Berlin"` → URL is `?location=Berlin`.

**`tests/unit/test_filter_use_case.py`** (MODIFY the existing `FakeLocationResolver` class, L955):

- Add `def resolve_structured(self, location: str) -> tuple[str, str, str] | None: ...` returning `None` by default.
- Asserts the 51+ existing tests still pass with the extended Protocol (mypy --strict validates structural conformance).

**`tests/unit/test_linkedin_scraper.py`** (MODIFY the existing `_FakeLocationResolver` class, L277):

- Add `def resolve_structured(self, location: str) -> tuple[str, str, str] | None: ...` returning `None` by default.
- Same backward-compat invariant.

### 7.2 Integration test (LIVE gated)

**`tests/integration/test_linkedin_live.py`** (NEW or MODIFY existing, +1 LIVE test):

- `test_live_antequera_returns_actual_antequera_jobs` (gated by `LLM_LIVE_TESTS=1`):
  - Hits real LinkedIn with `?keywords=react&location=Antequera%2CAndaluc%C3%ADa%2CSpain&start=0`.
  - Asserts at least 1 of the first 5 results has a location field containing `"Antequera"`, `"Málaga"`, or `"Andalucía"`.
  - Skipped when `LLM_LIVE_TESTS` is not set (per AGENTS.md rule #1).

### 7.3 Test-first sequencing

For each task T-NNN (planned in sdd-tasks):

1. Write the failing test FIRST.
2. Confirm RED (`uv run pytest` reports failure).
3. Implement the smallest change.
4. Confirm GREEN (`uv run pytest` passes).
5. Run full suite + `mypy --strict` + `ruff check` + `ruff format --check`.
6. Commit (per work-unit-commits).

## 8. Migration / Rollout

**No data migration, no env vars, no frontend changes, no DB migration.**

**Rollout**: single PR per user decision. Manual smoke: `curl /jobs?q=react&location=Antequera` returns more Antequera-area jobs (vs. the current 100%-broken `?location=Antequera` path that returns globally-distributed results).

**If a speculative city fails the LIVE test**: remove from `_STRUCTURED_MAPPING` (1-line change, 0 LOC). The resolver returns `None` and the scraper falls back to the legacy `?location=<str>` path. No code change required.

**Rollback**: revert the merge commit. No state to clean up.

## 9. Deviations from the spec

**None.** The spec is internally consistent and the design implements it 1:1. The spec author's decision (country-only inputs return `None`, NOT a triplet) is implemented exactly. The 9 speculative cities in the mapping are validated by the LIVE test gated `LLM_LIVE_TESTS=1`.

**Minor design additions** (not deviations, design clarifications):

- §4.3 "Ctor override" detail: the new `structured_mapping` kwarg is keyword-only and defaults to `_STRUCTURED_MAPPING`. This is a future-proofing seam (a `HybridLocationResolver` could inject a custom dict), not a deviation.
- §4.6 "Composition root verify": this change does NOT add new wiring. The `HardcodedLocationResolver` is already injected; the new `resolve_structured` method rides on the same instance.

## 10. Open questions

**None — all decisions resolved by the user.**

- Q5: Resolver shape = A (extend Protocol with second method) — confirmed.
- Q6: Country alias = C (spain / españa / espana → Spain) — confirmed.
- Q7: Province accent preservation = C (NFC + lowercase for matching, Title Case with tildes for output) — confirmed.
- Country-only inputs return `None` (NOT a triplet) — spec author's decision, documented explicitly in spec §"Spec author decision".

## 11. Self-check (sdd-tasks readiness)

- All 7 REQ-* in the spec have a corresponding component change documented (§4.1–4.8).
- All 24+ scenarios have a test strategy (§7.1–7.3).
- The single-PR forecast (~580 LOC) holds.
- No new env vars (§4.7).
- The v1 backwards-compat: unmapped locations (Berlin, Tokio) fall back to `?location=<raw_string>` (§5.2).
- The geoId path takes priority over the structured path (§5.3, §3 decision #4).
- The LIVE test gated `LLM_LIVE_TESTS=1` validates the structured format end-to-end (§7.2).
- The parallel `backend-infojobs-provinces` change doesn't conflict (different method names on the same Protocol — `resolve_infojobs` vs `resolve_structured`).
- The bonus bug at `app_factory.py:607` is fixed by the parallel change (obs #337 §4.5); this change verifies it remains fixed after merge (§4.6).
- The `_FakeLocationResolver` (in `test_linkedin_scraper.py`) and `FakeLocationResolver` (in `test_filter_use_case.py`) both need a `resolve_structured` method added with default `None` for backward compat.

## 12. Coordination with parallel `backend-infojobs-provinces`

Both changes extend `LocationResolverPort` with NEW methods:

- `backend-infojobs-provinces` adds `resolve_infojobs() -> tuple[int | None, int | None]`.
- `backend-linkedin-location-fallback` (THIS) adds `resolve_structured() -> tuple[str, str, str] | None`.

**No name collision** — the methods are independent. The merge PR handles any Protocol class conflict (the 2 additions are both keyword methods, both `def`, both sync).

**Shared test doubles**: BOTH `FakeLocationResolver` (in `tests/unit/test_filter_use_case.py`) and `_FakeLocationResolver` (in `tests/unit/test_linkedin_scraper.py`) need to grow to satisfy the extended Protocol. Since both PRs add to the same `FakeLocationResolver` class, the merge PR must reconcile. Strategy: the SECOND PR to merge adds the second method on top of the first. The FIRST PR's test for Protocol conformance already passes a `FakeLocationResolver` with BOTH methods, so the SECOND PR's addition does not break the FIRST PR's tests.

**Shared `app_factory.py:607` bug fix**: the parallel change already plans to fix this (obs #337 §4.5 "BONUS FIX"). This change does NOT duplicate the fix; it just verifies the fix persists after both PRs merge. If `backend-infojobs-provinces` merges first, this change inherits the fix. If this change merges first, `backend-infojobs-provinces` must still do the fix.

**Recommended merge order**: `backend-linkedin-location-fallback` (this one) first → `backend-infojobs-provinces` second. Rationale: this change has a smaller surface area (1 new method + 1 new file) and a cleaner test (LIVE gated). The parallel change has the L607 bug fix as a bonus; merging it second keeps the bonus fix attributable to a single PR.

**Alternatively**: both changes can merge in either order as long as the Protocol class has BOTH methods after merge. The merge PR resolves any conflict.

## 13. Next step: `sdd-tasks` (5 commits, single PR)

1. **C1** — Protocol + resolver + structured mapping (~120 LOC, T-001): `ports.py` + `_structured_mapping.py` + `hardcoded_resolver.py` + 10 unit tests.
2. **C2** — Scraper URL plumb (~200 LOC, T-002): `scraper.py` `_build_url` priority + `search()` + closure + 7+ unit tests.
3. **C3** — Composition root verify + test double extension (~10 LOC, T-003): `app_factory.py` verify, extend `FakeLocationResolver` + `_FakeLocationResolver`.
4. **C4** — Docs + composition test (~60 LOC, T-004): `backend/README.md` section + 2 grep tests + 1 composition test.
5. **C5** — LIVE test + final verification (~50 LOC, T-005): `tests/integration/test_linkedin_live.py` + 1 LIVE test gated + final check.sh.
