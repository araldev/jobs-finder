# Design: backend-infojobs-provinces

> **Status**: `design` (ready for `sdd-tasks`) • **Mode**: `both` (OpenSpec + Engram) • **Strict TDD**: ACTIVE
> **Base**: `f41aa90` (feature/backend-infojobs-provinces) • **Baseline**: 1,142 passed / 13 skipped
> **Spec**: obs #334 • **Upstream**: obs #331 (proposal) + 4 delta specs (obs #334 §2)

## 1. Resumen ejecutivo

Este cambio es la corrección REAL del bug "InfoJobs devuelve resultados de toda España para `?l=malaga`". El fix de `backend-scraper-query-tuning` (PR #4) parcheó el síntoma con un filtro client-side; este cambio corrige la CAUSA: el scraper ahora añade `provinceIds=<id>&countryIds=<id>` a la URL cuando el `HardcodedLocationResolver.resolve_infojobs(location)` devuelve un tuple no-`None`. El `LocationResolverPort` crece con un segundo método (`resolve_infojobs`), el scraper resuelve UNA VEZ por `search()` (no por página), y el `filter_infojobs_results` se mantiene como red de seguridad. El cambio es 100% backwards-compat: ciudades no mapeadas caen al `?l=<str>` legacy.

## 2. Architecture overview

```
                                     ┌──────────────────────────────────────────────┐
                                     │  Frontend (Next.js 15 — /jobs route handler) │
                                     │  GET /api/jobs?q=react&location=malaga&...   │
                                     └──────────────────┬───────────────────────────┘
                                                        │ (mismo origen, vía Route Handler)
                                                        ▼
                              ┌──────────────────────────────────────────────────┐
                              │  FastAPI: GET /jobs (aggregator route)           │
                              │  SearchAllSourcesUseCase.aggregate(q, loc, lim)  │
                              └──────────────────┬───────────────────────────────┘
                                                 │ asyncio.gather (3 sources en paralelo)
                ┌────────────────────────────────┼────────────────────────────────┐
                ▼                                ▼                                ▼
  ┌───────────────────────┐    ┌───────────────────────────┐    ┌───────────────────────────────┐
  │  LinkedIn scraper     │    │  Indeed scraper           │    │  InfoJobs scraper (MODIFIED)  │
  │  (UNTOUCHED)          │    │  (UNTOUCHED)              │    │  _build_url() ADDED params    │
  │                       │    │                           │    │                               │
  │  resolve() ──┐        │    │  (no resolver)            │    │  resolve_infojobs() ─┐        │
  │              ▼        │    │                           │    │                     ▼        │
  │  geoId=<n>  en URL    │    │  ?l=malaga  (no change)   │    │  provinceIds + countryIds    │
  └───────────────┬───────┘    └───────────────────────────┘    └────────────┬────────────────┘
                  │                                                            │
                  │         MISMO INSTANCE (compartido por el app_factory)     │
                  └────────────────┐                                           ┘
                                   ▼
                  ┌─────────────────────────────────────────┐
                  │  HardcodedLocationResolver              │
                  │  (infrastructure/location/...py)        │
                  │                                          │
                  │  .resolve(loc) -> int | None            │
                  │  .resolve_infojobs(loc) ->              │
                  │      tuple[int|None, int|None]          │
                  │                                          │
                  │  Mapeos:                                 │
                  │  - _CANONICAL_MAPPING (LinkedIn, 34)    │
                  │  - _INFOJOBS_MAPPING (InfoJobs, 9) NEW  │
                  └─────────────────────────────────────────┘

  ──────────────────────────────────────────────────────────────────────────────
  Defense-in-depth: SearchAllSourcesUseCase.aggregate()
    └── filter_infojobs_results(jobs, tokens)  ← sigue activo, NO se elimina
        └── Remueve jobs InfoJobs con 0 token overlap (defensa para mapeos
            incompletos + drift futuro de IDs)
  ──────────────────────────────────────────────────────────────────────────────
```

**Puntos clave**:

- UNA sola instancia de `HardcodedLocationResolver` se construye en `app_factory.build_app()` (línea 185) y se inyecta en BOTH `LinkedInScraperSettings` y `InfoJobsScraperSettings`. Esta es la **misma** instancia que ya usa LinkedIn (REQ-LOC-002).
- El resolver ejecuta `resolve_infojobs()` EXACTAMENTE una vez por `search()` (no por página). El tuple se captura en el closure `_make_fetch_one_page` y se reusa en cada iteración del `paginated_search` loop.
- Para ciudades NO mapeadas (`Berlin`, futuras adiciones) el resolver devuelve `(None, None)` → el URL builder OMITE ambos params → fallback al `?l=<str>` legacy (byte-identical al pre-change). Cero regresión.
- `filter_infojobs_results` permanece sin cambios. Su rol cambia de "primary mitigation" a "safety net for unmapped locations + future ID drift".

## 3. Architecture decisions

### Decisión 1: Extender `LocationResolverPort` con segundo método (no crear `InfoJobsLocationResolverPort`)

| | |
|---|---|
| **Elección** | Agregar `def resolve_infojobs(location: str) -> tuple[int | None, int | None]` al Protocol existente |
| **Alternativas** | (A) Protocol nuevo `InfoJobsLocationResolverPort`; (B) Un solo método `resolve()` con `Union` discriminada por `infojobs: bool` |
| **Rationale** | El user confirmó Q1 = A en el proposal. El Protocol es el mismo seam, dos métodos paralelos — el patrón canónico del proyecto (`LLMClientPort.complete` + `stream_complete` en `application/ports.py:374-451`). Mypy --strict enforce la conformidad estructural sin runtime cost. Naming `resolve_infojobs` (no `resolve_provinces`) refleja que devuelve DOS IDs (provincia + país), y el prefijo `infojobs_` espeja el kwarg `infojobs_geo` del scraper. |

### Decisión 2: Resolver llamado UNA VEZ por `search()`, no por página

| | |
|---|---|
| **Elección** | `search()` resuelve el tuple al inicio, lo captura en el closure `_make_fetch_one_page(keywords, location, infojobs_geo=tuple)`, y `_build_url(keywords, location, page, *, infojobs_geo)` lo consume en cada iteración |
| **Alternativas** | (A) Resolver en cada página dentro del closure; (B) Resolver en `_build_url` directamente y aceptar el `LocationResolverPort` en la signature del helper |
| **Rationale** | (A) haría 3+ llamadas inútiles (la info es invariante durante la paginación) + violaría REQ-PROV-002 scenario 5 ("resolver called exactly once per search"). (B) acoplaría el `paginated_search` helper (source-agnostic) con InfoJobs — exactamente lo que el helper explícitamente evita (ver `infrastructure/pagination.py`). El patrón de captura-en-closure espeja LinkedIn (scraper.py:249-250 + 261). |

### Decisión 3: `infojobs_geo` como kwarg scraper-internal, no en `JobSearchPort`

| | |
|---|---|
| **Elección** | `InfoJobsPlaywrightScraper.search(..., infojobs_geo: tuple[int | None, int | None] | None = None)`. El `JobSearchPort` Protocol queda intocado |
| **Alternativas** | (A) Extender `JobSearchPort.search()` con un `infojobs_geo` kwarg; (B) Mover la resolución al use case + cache wrapper |
| **Rationale** | (A) obligaría a LinkedIn + Indeed a aceptar (e ignorar) el kwarg — coupling en el Port. (B) duplicaría la lógica en 3 sitios (LinkedIn ya lo hace en scraper; sacar el patrón lo rompe). El kwarg es NON-PORT: aggregators/use cases/cache wrapper NO lo pasan. El `JobSearchCacheKey` NamedTuple tampoco cambia (el tuple viaja por closure, no por cache key — ver spec §4). |

### Decisión 4: `filter_infojobs_results` SE MANTIENE (defense-in-depth, Q3 = KEEP)

| | |
|---|---|
| **Elección** | Cero cambios al filtro. Solo se actualiza el docstring para reflejar el nuevo rol. |
| **Alternativas** | (A) Eliminar el filtro; (B) Refactorizar a no-op condicional; (C) Moverlo al scraper en lugar del aggregator |
| **Rationale** | El user confirmó Q3 = KEEP. Análisis costo/beneficio del proposal §6 Q3: el filtro cuesta ~100 LOC, ~5ms de overhead (es `O(n)` sobre el slice InfoJobs, típicamente n≤20), y cubre 3 escenarios donde el URL plumb puede fallar: (i) ciudades no mapeadas, (ii) IDs que cambien (drift futuro de InfoJobs), (iii) bugs en la inyección del resolver. El costo de re-desplegarlo si lo necesitamos de nuevo es mayor. |

### Decisión 5: `HardcodedLocationResolver` (no JSON file, no `HybridInfoJobsResolver`)

| | |
|---|---|
| **Elección** | 9-entry dict en `_infojobs_mapping.py` (sibling de `_mapping.py`). Constructor con `infojobs_mapping` kwarg para tests + futura hibridación. |
| **Alternativas** | (A) JSON file (`infojobs_provinces.json`); (B) `HybridInfoJobsResolver` con API de geocoding; (C) Compartir el dict existente `_CANONICAL_MAPPING` |
| **Rationale** | (A) añade I/O en startup sin beneficio (los 9 entries son estáticos hasta que InfoJobs cambie el dominio). (B) es out of scope (proposal §6 Q1). (C) los dicts tienen semánticas distintas: `_CANONICAL_MAPPING[str] = int` (LinkedIn), `_INFOJOBS_MAPPING[str] = tuple[int, int]` (InfoJobs). Mezclarlos confunde el reader. El kwarg `infojobs_mapping=` es el seam para un futuro `HybridInfoJobsResolver` que componga con un API fallback (mismo patrón que `HardcodedLocationResolver(mapping=...)` ya en uso). |

## 4. Component changes

### 4.1 `application/ports.py` (MODIFY) — Protocol extension

| | |
|---|---|
| **Cambio** | Agregar `def resolve_infojobs(self, location: str) -> tuple[int | None, int | None]: ...` al `LocationResolverPort` Protocol, después de `resolve()` (línea 188) |
| **Por qué** | El Protocol es el seam application-layer; extenderlo es la opción del user (Q1 = A). Documentar la semántica de 4-tuplas en el docstring para futuros consumers (e.g. Glassdoor, computrabajo) |
| **Signature** | `def resolve_infojobs(self, location: str) -> tuple[int \| None, int \| None]: ...` |
| **Test strategy** | (a) `test_protocol_has_resolve_infojobs_method` — `dir(LocationResolverPort)` introspection; (b) `test_resolver_satisfies_extended_protocol` — typed variable assignment para que mypy --strict enforce la conformidad |

**Docstring del nuevo método** (4-tuple semantics):

```python
def resolve_infojobs(self, location: str) -> tuple[int | None, int | None]:
    """Translate a free-form `location` into an InfoJobs (province_id, country_id) tuple.

    Return semantics (4 cases):
        (int, int)  → both known; emit provinceIds=<id>&countryIds=<id>
        (None, int) → country-only (e.g. "Remote"); emit countryIds=<id> only
        (int, None) → province-only; emit provinceIds=<id> only
        (None, None) → unmapped / empty; omit both (legacy ?l=<str> fallback)
    """
```

### 4.2 `infrastructure/location/_infojobs_mapping.py` (NEW)

| | |
|---|---|
| **Cambio** | Crear el archivo nuevo con `INFOJOBS_PROVINCE_COUNTRY_MAPPING` (9 entries) y `INFOJOBS_ALIASES` (vacío por ahora, mismo patrón que `_ALIASES`) |
| **Por qué** | Separar el mapping de InfoJobs del de LinkedIn (semánticas distintas: tuple vs int). El spec §3 REQ-PROV-001 scenario 11 fija el conteo en 9 (cualquier adición es un cambio deliberado) |
| **Contenido** | 9 keys canónicas (lowercased, accents stripped, NFC composed) → `(province_id, country_id)` tuples. Comentarios inline marcan cuáles son **user-verified** (Málaga=34, España=17) vs **speculative** (Madrid=28, BCN=8, VLC=46, SVQ=41 — pendiente de LIVE test) |
| **Test strategy** | (a) `test_default_mapping_has_nine_entries` — `len() == 9`; (b) tests parametrizados verifican cada entry; (c) `test_speculative_ids_have_marker_comment` — `pytest.mark.parametrize` sobre IDs con `pytest.mark.speculative` para que la LIVE test los pueda skip/re-run selectivamente |

**Estructura del dict** (9 entries):

```python
_INFOJOBS_PROVINCE_COUNTRY_MAPPING: dict[str, tuple[int, int]] = {
    # === user-verified via manual URL capture (2026-06-10) ===
    "malaga": (34, 17),       # USER-VERIFIED: Málaga=34, España=17
    "espana": (None, 17),     # USER-VERIFIED: country-only sentinel
    "spain": (None, 17),      # alias for espana (accent-stripped)
    "remote": (None, 17),     # USER-VERIFIED: country-only, no province
    "teletrabajo": (None, 17),  # alias for remote
    # === SPECULATIVE — pending LIVE test validation (LLM_LIVE_TESTS=1) ===
    "madrid": (28, 17),       # SPECULATIVE: INE 28 (Madrid province)
    "barcelona": (8, 17),     # SPECULATIVE: INE 8 (Barcelona province)
    "valencia": (46, 17),     # SPECULATIVE: INE 46 (Valencia province)
    "sevilla": (41, 17),      # SPECULATIVE: INE 41 (Sevilla province)
}
```

### 4.3 `infrastructure/location/hardcoded_resolver.py` (MODIFY) — Resolver implementation

| | |
|---|---|
| **Cambio** | Agregar `def resolve_infojobs(self, location: str) -> tuple[int | None, int | None]` como segundo método público. Refactor: extraer `_normalize` (línea 132) a método de instancia para reuso. Agregar ctor kwarg `infojobs_mapping: Mapping[str, tuple[int, int]] | None = None` y `infojobs_aliases: Mapping[str, str] | None = None` |
| **Por qué** | La implementación es SIMÉTRICA a `resolve()`: mismo alias-normalization chain (NFC + casefold + strip + NFD-strip-accents), mismo flat dict lookup, mismo short-circuit para empty. Compartir `_normalize` evita duplicación |
| **Signature** | `def resolve_infojobs(self, location: str) -> tuple[int \| None, int \| None]: ...` |
| **Test strategy** | (a) 5+ tests unitarios nuevos en `test_hardcoded_location_resolver.py` (parametrizados): malaga canonical, malaga with tilde/padding, 4 speculative cities, remote, espana, spain, empty short-circuit, unmapped (berlin), custom mapping via ctor; (b) `test_protocol_satisfaction` — mypy --strict + typed variable assignment |

**Implementation sketch**:

```python
def resolve_infojobs(self, location: str) -> tuple[int | None, int | None]:
    # Empty short-circuit (no WARNING, matches resolve() invariant).
    if not location:
        return (None, None)
    normalized = self._normalize(location)
    # Alias-to-canonical recurse (1 step, same as resolve()).
    canonical_key = self._infojobs_aliases.get(normalized, normalized)
    if canonical_key in self._infojobs_mapping:
        return self._infojobs_mapping[canonical_key]
    # Unmapped → WARNING + fallback sentinel.
    _logger.warning(
        "HardcodedLocationResolver: could not resolve location %r to InfoJobs province/country IDs. "
        "Falling back to ?l=<str>.",
        location,
    )
    return (None, None)
```

### 4.4 `infrastructure/infojobs/scraper.py` (MODIFY) — URL plumb + settings

| | |
|---|---|
| **Cambio** | (a) `InfoJobsScraperSettings`: agregar `location_resolver: LocationResolverPort | None = None` slot, kwarg en `__init__`, comparación en `__eq__`/`__hash__`, repr. (b) `InfoJobsPlaywrightScraper.search()`: agregar `infojobs_geo: tuple[int | None, int | None] | None = None` kwarg; resolver al inicio si el kwarg es `None` y el resolver está presente; loggear `DeprecationWarning` si el resolver es `None` (legacy wiring). (c) `_make_fetch_one_page(keywords, location, infojobs_geo)`: capturar el tuple en el closure. (d) `_build_url(keywords, location, page, *, infojobs_geo)`: append `&provinceIds=...&countryIds=...` cuando aplique |
| **Por qué** | El kwarg `infojobs_geo` permite tests (pass explicit tuple, skip resolver) y deja un seam de escape para callers no-aggregator. El closure capture es el patrón LinkedIn (scraper.py:249-261) — simetría entre fuentes. El `DeprecationWarning` es un nudge para ops, no un error |
| **Signatures** | `def __init__(self, *, ..., location_resolver: LocationResolverPort \| None = None)` y `async def search(self, keywords, location, limit=20, geo_id=None, *, infojobs_geo: tuple[int \| None, int \| None] \| None = None) -> list[Job]` |
| **Test strategy** | (a) 4+ tests nuevos en `test_infojobs_scraper.py`: URL con mapped location, URL con country-only, URL con unmapped (legacy), URL con empty, resolver called once (parametrizado 1, 2, 3 pages), legacy wiring logs warning, explicit `infojobs_geo` skips resolver; (b) 2+ tests en `test_infojobs_settings.py`: accept resolver, default None, equality con resolver identity |

**`_build_url` extension** (3-line change):

```python
def _build_url(
    self, keywords: str, location: str, page: int, *,
    infojobs_geo: tuple[int | None, int | None] | None = None,
) -> str:
    base = f"https://{self._settings.domain}/ofertas-trabajo?q={quote(keywords)}&l={quote(location)}&page={page}"
    province_id, country_id = (None, None) if infojobs_geo is None else infojobs_geo
    if province_id is not None:
        base += f"&provinceIds={province_id}"
    if country_id is not None:
        base += f"&countryIds={country_id}"
    return base
```

### 4.5 `presentation/app_factory.py` (MODIFY) — Wire SAME resolver to BOTH scrapers

| | |
|---|---|
| **Cambio** | Línea 333 (InfoJobs `InfoJobsScraperSettings(...)`): agregar `location_resolver=location_resolver` (la misma variable de línea 185) |
| **Por qué** | El test `test_resolver_shared_between_linkedin_and_infojobs` (spec §3 REQ-PROV-004) exige que sea `is` (mismo objeto), no `==` (igual valor). El resolver ya está construido en línea 185 — reusar la misma referencia es trivial |
| **Bonus fix** | Línea 607 reconstruye `location_resolver = HardcodedLocationResolver()` dentro del branch `chat_enabled` — esto es un **bug pre-existente** que SHADOWS la variable de línea 185. El fix correcto: eliminar la línea 607 (la variable de línea 185 ya está en scope y se inyecta en el use case del chat en línea 617). El test de spec REQ-PROV-004 NUNCA verificaría `is` con la variable shadowed — debe ser el mismo objeto |
| **Test strategy** | 1+ test nuevo en `test_composition.py`: `test_resolver_shared_between_linkedin_and_infojobs` — `port._settings.location_resolver is infojobs_port._settings.location_resolver` (uso de `is`, no `==`); bonus: test que verifica que el `app.state.location_resolver` es el mismo objeto que los settings |

### 4.6 `infrastructure/aggregator_filters.py` (MODIFY) — Docstring only

| | |
|---|---|
| **Cambio** | Actualizar el docstring de `filter_infojobs_results` (líneas 75-94) para reflejar el nuevo rol: "defense-in-depth safety net for unmapped locations + future province/country ID drift. Primary relevance improvement comes from the URL plumb in `InfoJobsPlaywrightScraper._build_url`." |
| **Por qué** | El user confirmó Q3 = KEEP. La función NO cambia. El docstring sí — la documentación del rol es parte del spec REQ-PROV-AGG-001-MOD scenario 1 |
| **Test strategy** | 0 cambios al código. 1 test nuevo: `test_filter_infojobs_results_docstring_updated` — assert que el docstring contiene "defense-in-depth" o "safety net" |

### 4.7 `backend/README.md` (MODIFY) — Documentation

| | |
|---|---|
| **Cambio** | (a) Sección "InfoJobs client-side filter" — agregar nota "defense-in-depth safety net" + link a nueva sección. (b) Nueva sección "InfoJobs province/country IDs" — lista los 9 entries, marca los 4 speculative, documenta el fallback `?l=<str>` y el LIVE test gate |
| **Por qué** | REQ-PROV-AGG-002-MOD lo exige. La doc es parte del deliverable |
| **Test strategy** | 2+ tests nuevos en `test_aggregator_filters.py` (grep-style): `test_readme_documents_defense_in_depth`, `test_readme_lists_infojobs_mapping` |

### 4.8 NO CAMBIOS: `backend/.env.example`, `JobSearchPort`, `JobSearchCacheKey`, `AggregatedJobsQuery`, `InfoJobsJobsQuery`, `paginated_search` helper

| | |
|---|---|
| **Razón** | El HTTP shape se preserva. No hay env vars nuevos (los IDs son estáticos en el dict). El Port, la cache key, y la schema de query no cambian — el tuple `infojobs_geo` es scraper-internal, viaja por closure, no por cache key. El helper de paginación es source-agnostic. |

## 5. Data flow

### 5.1 Request: `GET /jobs?q=react&location=malaga&limit=20`

1. **Frontend** (Next.js Route Handler `/api/jobs`): forward a FastAPI.
2. **FastAPI** (`GET /jobs` aggregator route): parsea `q="react"`, `location="malaga"`, `limit=20`.
3. **Aggregator** (`SearchAllSourcesUseCase.aggregate`):
   - Compute cache key (UNCHANGED — sin campo `infojobs_geo`).
   - `asyncio.gather` 3 sources.
4. **InfoJobs branch** (MODIFIED):
   - `infojobs_use_case.search("react", "malaga", 20)` → cache wrapper → raw use case → `InfoJobsPlaywrightScraper.search("react", "malaga", 20)`.
   - **Inside `search()`**:
     - `infojobs_geo = (None, None)` (default, no explicit kwarg).
     - `if infojobs_geo is None and self._settings.location_resolver is not None:` → `infojobs_geo = self._settings.location_resolver.resolve_infojobs("malaga")` → `(34, 17)`.
     - Resolver count: **1 call** (recorded in `_FakeLocationResolver.calls`).
     - `paginated_search(..., fetch_one_page=self._make_fetch_one_page("react", "malaga", infojobs_geo=(34, 17)))`.
   - **Inside `_make_fetch_one_page` closure**:
     - Captura `(34, 17)` por closure.
     - En cada iteración: `url = self._build_url("react", "malaga", page_index + 1, infojobs_geo=(34, 17))` → `...?q=react&l=malaga&page=1&provinceIds=34&countryIds=17`.
5. **filter_infojobs_results STILL APPLIES** (defense-in-depth, sin cambios). Para `q=react` con jobs InfoJobs reales, todos los títulos contienen "react" → 0 removidos → no-op.
6. **Aggregator** dedup + sort + return. Frontend recibe el JSON.

### 5.2 Backwards-compat: `location=Berlin` (unmapped)

1. `resolve_infojobs("Berlin")` → normaliza → `berlin` → NOT in `_INFOJOBS_MAPPING` → WARNING log + return `(None, None)`.
2. `_build_url(..., infojobs_geo=(None, None))` → omite ambos params → URL = `...?q=react&l=Berlin&page=1` (byte-identical a pre-change).
3. InfoJobs devuelve resultados all-Spain (legacy behavior).
4. `filter_infojobs_results` aplica: si la query es `q=react`, filtra los que NO contengan "react" en el título → mejora la relevancia parcialmente.

### 5.3 Legacy wiring: scraper sin resolver (caller test)

1. `InfoJobsScraperSettings(location_resolver=None)` (default, no kwarg).
2. `search()`: `if self._settings.location_resolver is None:` → WARNING log (DeprecationWarning) + `infojobs_geo = (None, None)`.
3. URL = `...?q=react&l=malaga&page=1` (legacy, byte-identical a pre-change).

## 6. File-by-file change list

| File | Action | LOC est. | Test strategy |
|---|---|---|---|
| `application/ports.py` | MODIFY: +`resolve_infojobs` to `LocationResolverPort` | +18 | `test_hardcoded_location_resolver.py::test_protocol_*` (2 tests) |
| `infrastructure/location/_infojobs_mapping.py` | NEW: 9-entry dict + aliases | +40 | `test_infojobs_province_resolver.py` (12 scenarios parametrized) |
| `infrastructure/location/hardcoded_resolver.py` | MODIFY: +`resolve_infojobs` + ctor kwarg + reuse `_normalize` | +45 | `test_hardcoded_location_resolver.py` (5+ tests), `test_infojobs_province_resolver.py` (12+ tests) |
| `infrastructure/infojobs/scraper.py` (scraper) | MODIFY: search() resolves once, _build_url extended, _make_fetch_one_page closure | +60 | `test_infojobs_scraper.py` (4+ tests, parametrized 1/2/3 pages) |
| `infrastructure/infojobs/scraper.py` (settings) | MODIFY: `location_resolver` field + `__eq__`/`__hash__` | +10 | `test_infojobs_settings.py` (3 tests) |
| `presentation/app_factory.py` | MODIFY: wire `location_resolver` into InfoJobsScraperSettings; remove shadowed re-init at L607 | +5, -2 | `test_composition.py::test_resolver_shared_*` (1 test) |
| `infrastructure/aggregator_filters.py` | MODIFY: docstring only | +4, -2 | `test_aggregator_filters.py::test_*_docstring` (1 test) |
| `backend/.env.example` | NO CHANGE | 0 | n/a |
| `backend/README.md` | MODIFY: section update + new section | +50 | `test_aggregator_filters.py::test_readme_*` (2 tests) |
| `tests/unit/test_hardcoded_location_resolver.py` | MODIFY: 5+ tests for Protocol extension | +60 | (the tests) |
| `tests/unit/test_infojobs_province_resolver.py` | NEW: 12 tests for the resolver method | +250 | (the tests) |
| `tests/unit/test_infojobs_scraper.py` | MODIFY: 4+ tests for URL plumb | +120 | (the tests) |
| `tests/unit/test_infojobs_settings.py` | MODIFY: 3 tests for resolver field | +40 | (the tests) |
| `tests/unit/test_filter_use_case.py` | MODIFY: 1 test (`FakeLocationResolver.resolve_infojobs` default) | +10 | (the test) |
| `tests/unit/test_linkedin_scraper.py` | MODIFY: 1 test (`_FakeLocationResolver.resolve_infojobs` default) | +10 | (the test) |
| `tests/integration/test_composition.py` | MODIFY: 1 test (resolver shared) | +25 | (the test) |
| `tests/integration/test_infojobs_live.py` (NEW) | 1 LIVE test gated `LLM_LIVE_TESTS=1` | +50 | (the test) |
| **TOTAL** | | **~795** | (within 750-1100 forecast) |

## 7. Test strategy (Strict TDD)

### 7.1 Unit tests (test-first)

| Test file | New tests | Coverage |
|---|---|---|
| `test_infojobs_province_resolver.py` (NEW) | 12 | All REQ-PROV-001 scenarios: canonical happy path (5), country-only (3), unmapped+empty (2), custom mapping (1), 9-entry count lock (1) |
| `test_hardcoded_location_resolver.py` | 5+ | Protocol extension (2), ctor `infojobs_mapping` kwarg (1), `_normalize` shared (1), backward-compat with `resolve()` unchanged (1) |
| `test_infojobs_scraper.py` | 4+ | URL with mapped (1), URL country-only (1), URL unmapped (1), URL empty (1), resolver called once per search parametrized 1/2/3 pages (1), legacy wiring + DeprecationWarning (1), explicit `infojobs_geo` skips resolver (1) |
| `test_infojobs_settings.py` | 3 | accept resolver (1), default None backward-compat (1), equality includes resolver identity (1) |
| `test_filter_use_case.py` | 1 | `FakeLocationResolver.resolve_infojobs` default returns `(None, None)` |
| `test_linkedin_scraper.py` | 1 | `_FakeLocationResolver.resolve_infojobs` default returns `(None, None)`, records calls in `calls_infojobs` |
| `test_aggregator_filters.py` | 3 | docstring updated (1), README mentions defense-in-depth (1), README lists 9-entry mapping (1) |

**Total new unit tests: ~30** (matches spec REQ-PROV-006).

### 7.2 Integration tests

| Test file | New tests | Coverage |
|---|---|---|
| `test_composition.py` | 1 | SAME resolver instance (`is`) shared between LinkedIn + InfoJobs + `app.state.location_resolver` |
| `test_infojobs_live.py` (NEW) | 1 | LIVE test gated `LLM_LIVE_TESTS=1`: real InfoJobs SERP for Málaga returns mostly Málaga-area jobs; parametrized for the 4 speculative IDs |

### 7.3 Test-first sequencing (per sdd-tasks T-NNN)

For each task, el patrón es:
1. Write the failing test FIRST (RED).
2. Confirm RED: `cd backend && uv run pytest <test_file>::<test_name>` exits non-zero.
3. Implement the smallest change to make the test pass (GREEN).
4. Confirm GREEN: `cd backend && uv run pytest <test_file>::<test_name>` exits zero.
5. Run full suite: `cd backend && uv run pytest` (1,142+ pre-change tests + ~30 new tests, all green).
6. Run type/lint: `cd backend && uv run mypy --strict && uv run ruff check && uv run ruff format --check`.

**Strict TDD gate**: per the spec REQ-PROV-006, the change is NOT considered "done" until ALL 1,142+ pre-change tests + ~30 new tests pass AND mypy --strict is clean AND ruff is clean.

## 8. Migration / Rollout

**No data migration required.** The change is:
- **Backwards-compat**: ciudades no mapeadas caen al `?l=<str>` legacy. Comportamiento byte-identical al pre-change para esas queries.
- **No new env vars**: los IDs son estáticos en el dict (`_infojobs_mapping.py`).
- **No new dependencies**: solo stdlib + los imports ya existentes.
- **No frontend changes**: el `location` query param es el mismo; el resolver corre internamente.
- **No DB migration**: in-process dict lookup.

**Rollout plan** (single PR per user decision):
1. Merge a `feature/backend-infojobs-provinces`.
2. Manual smoke test: `curl "http://localhost:8000/jobs?q=react&location=malaga&limit=20"` — confirmar que el response tiene más jobs Málaga-area que el pre-change.
3. Deploy.
4. Si un speculative ID falla el LIVE test, **removerlo del dict** (1-line change, 0 LOC). El resolver cae a `(None, None)` para esa ciudad (legacy `?l=<str>`). El filter `filter_infojobs_results` provee defensa secundaria.

**Rollback**: revert del merge commit. Sin DB state, sin env vars, sin migraciones.

## 9. Deviations from the spec

**None.** El spec es internamente consistente y el design lo implementa 1:1:

- Los 6 REQ-PROV-* tienen un component change documentado.
- Los 30+ scenarios tienen un test strategy.
- El Protocol extension (`resolve_infojobs`) sigue el patrón canónico (`LLMClientPort.complete` + `stream_complete`).
- El `infojobs_geo` kwarg es scraper-internal (NO en el Port, NO en el cache key).
- El `filter_infojobs_results` se mantiene (Q3 = KEEP) con docstring actualizado.
- El LIVE test gate (`LLM_LIVE_TESTS=1`) valida los 4 speculative IDs (Madrid=28, BCN=8, VLC=46, SVQ=41).

**Una corrección detectada durante el design** (no es deviation, es fix de bug pre-existente): la línea 607 de `app_factory.py` reconstruye `location_resolver = HardcodedLocationResolver()` dentro del branch `chat_enabled`, SHADOWING la variable de línea 185. Si NO se elimina, el test `test_resolver_shared_between_linkedin_and_infojobs` (REQ-PROV-004) podría pasar por accidente con el chat OFF, pero fallaría con el chat ON (dos instancias distintas). El fix correcto: eliminar la línea 607, reusar la variable de línea 185. Doc en §4.5.

## 10. Open questions

**None — all decisions resolved by the user (Q1=A, Q2=A, Q3=A keep, Q4=A LIVE test).** El design implementa el spec 1:1. Los 4 speculative IDs están gated por el LIVE test (`LLM_LIVE_TESTS=1`) con un fallback graceful (remove from dict → `(None, None)` legacy).

## 11. Self-check before sdd-tasks

- [x] All 6 REQ-PROV-* in the spec have a corresponding component change documented
- [x] All 30+ scenarios have a test strategy
- [x] The single-PR forecast (~795 LOC) holds (within 750-1100)
- [x] No new env vars
- [x] v1 backwards-compat: locations not in the mapping still work (fallback to `?l=<str>`)
- [x] The aggregator's `filter_infojobs_results` continues to work as defense-in-depth
- [x] The LIVE test gated `LLM_LIVE_TESTS=1` validates the speculative IDs
- [x] The `infojobs_geo` kwarg is scraper-internal (Port, cache key, schema unchanged)
- [x] The Protocol extension follows the canonical `LLMClientPort.complete` + `stream_complete` pattern
- [x] The pre-existing line 607 shadowing bug is fixed as a bonus

## 12. Coordination with parallel `backend-linkedin-location-fallback`

- Both changes extend `LocationResolverPort` with NEW methods (`resolve_infojobs` vs `resolve_structured`).
- No name collision: different method names.
- The orchestrator coordinates the merge order. The conflict in `LocationResolverPort` (if both PRs touch the same line range) is resolved manually in the merge PR — see obs #330 + parallel proposal §1.
- Both changes also need the same `_FakeLocationResolver` + `FakeLocationResolver` test doubles to grow — the merge PR handles the two additive methods.

## 13. Next step

Ready for `sdd-tasks`. The orchestrator will launch `sdd-tasks` to break this design into 5 commits (per the user's forecast):

1. **Commit 1** — Protocol + resolver + mapping (~120 LOC, 1 task T-001)
2. **Commit 2** — Settings field + scraper URL plumb (~200 LOC, 1 task T-002)
3. **Commit 3** — Composition root wire + bonus fix line 607 (~30 LOC, 1 task T-003)
4. **Commit 4** — Docstring + README update (~60 LOC, 1 task T-004)
5. **Commit 5** — LIVE test + final verification (~50 LOC, 1 task T-005)

Total: 5 commits, single PR, single rollback unit, defense-in-depth preserved.
