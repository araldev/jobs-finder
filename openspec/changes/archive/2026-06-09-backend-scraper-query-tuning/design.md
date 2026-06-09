# Design: backend-scraper-query-tuning

> **Cambio**: `backend-scraper-query-tuning` • **Modo**: `both` (OpenSpec + Engram) • **Strict TDD**: ACTIVE
> **Fecha**: 2026-06-10 • **Status**: `designed` (listo para `sdd-tasks`)
> **Fuentes**: [proposal #322](../proposal.md), [spec #323](../specs/backend-scraper-query-tuning/spec.md), código real de `jobs-finder` 2026-06-09.

## Architecture overview

```
   Browser
     │  GET /api/jobs?q=react&location=malaga&limit=20
     ▼
   Next.js Route Handler (src/app/api/jobs/route.ts)
     │  GET /jobs?q=react&location=malaga&limit=20
     ▼
┌──────────────────────────────────────────────────────────────┐
│ FastAPI app — presentation/routes/aggregator.py             │
│   1. Parse query → query_tokens = tokenize("react") → {"r"} │
│   2. Read app.state.location_resolver (HardcodedLocationRes)│
│   3. Resolve linkedin_geo_id = resolver.resolve("malaga")   │
│       → 104401670                                            │
│   4. Call aggregator.search(q, loc, limit, sources,         │
│       query_tokens, enable_keyword_scoring, linkedin_geo_id)│
└──────────────────────────────────────────────────────────────┘
     │
     ▼
┌──────────────────────────────────────────────────────────────┐
│ SearchAllSourcesUseCase (application/aggregator.py)         │
│   - per_source tasks: try/except JobSearchError → log + skip│
│   - if 0 succeeded → raise AllSourcesFailedError → 502       │
│   - dedup by (title, company, location)                      │
│   - apply filter_infojobs_results(infojobs_jobs, q_tokens)  │
│   - if enable_keyword_scoring: sort by score desc, then date │
│   - else: sort by posted_at desc (existing rank_jobs)        │
└──────────────────────────────────────────────────────────────┘
     │                │                 │
     ▼                ▼                 ▼
┌─────────┐    ┌──────────┐     ┌─────────────┐
│ LinkedIn│    │  Indeed  │     │  InfoJobs   │
│ scraper │    │  scraper │     │  scraper    │
└─────────┘    └──────────┘     └─────────────┘
     │                │                 │
   geoId=         location=         q=react&l=malaga
   104401670      malaga             (no client geoId)
     │                │                 │
     ▼                ▼                 ▼
  Playwright    Playwright        Playwright
  navigate      navigate          navigate
     │                │                 │
     └────────────────┴─────────────────┘
                      │
                      ▼
            dedup + filter + sort
                      │
                      ▼
            AggregatedJobsResponse (HTTP shape UNCHANGED)
```

**Cache key (por source)**: `JobSearchCacheKey(source, keywords, location, limit, geo_id, query_tokens)` — el 6º campo `query_tokens` es NUEVO (tuple inmutable vacío por default → backward-compat).

**Env var único añadido**: `ENABLE_KEYWORD_SCORING` (default `false`). Las 2 env vars del `jobs-aggregator-ranking` (`AGGREGATOR_RANKING_STRATEGY`, `AGGREGATOR_PRIORITY_MAP`) NO se tocan; el opt-in de `keyword_score` es independiente del dispatch de `rank_jobs`.

## Architecture decisions

### Decision: `HardcodedLocationResolver` se construye SIEMPRE en `app_factory`, no solo cuando `chat_enabled=True`

**Choice**: `HardcodedLocationResolver()` se instancia al inicio de `build_app()`, **independientemente** de `chat_enabled`, y se inyecta al `LinkedInPlaywrightScraper` via el `LinkedInScraperSettings` (nuevo campo opcional `location_resolver`).

**Alternatives considered**:
- Construir el resolver solo cuando `chat_enabled=True` y leerlo de `app.state` desde la ruta del agregador. **Rechazado**: (1) requiere plumbing cross-layer desde la ruta hasta el scraper via `app.state`, (2) el scraper deja de ser self-contained.
- Construir el resolver en cada `search()` call. **Rechazado**: el resolver es read-only (dict inmutable); construirlo por llamada es desperdicio.

**Rationale**: El scraper DEBE poder resolver la location sin saber nada del chat. Inyectar el resolver en el settings dataclass (mismo patrón que `throttle`, `user_agent`, etc.) preserva el dependency rule (`presentation → application → domain ← infrastructure`) y mantiene el scraper self-contained.

### Decision: `_make_fetch_one_page` del LinkedIn scraper recibe `geo_id` directamente, no el resolver

**Choice**: El `LinkedInPlaywrightScraper.search()` llama `self._location_resolver.resolve(location)` UNA vez al inicio (NO por página) y pasa el `int | None` resultante a `_make_fetch_one_page` y de ahí a `_build_url`.

**Alternatives considered**:
- Pasar el resolver al closure y resolver por página. **Rechazado**: viola REQ-LOC-001 scenario 5 (resolver se llama 1 vez por search, no 1 vez por página), y agrega I/O de lookup en hot loop.
- Resolver en el aggregator y pasarlo a `port.search(..., geo_id=...)`. **Choice complementario**: el aggregator YA pasa `linkedin_geo_id` al LinkedIn port (línea 267 del aggregator). El scraper PUEDE recibir `geo_id` por 2 paths: (a) del kwarg `search(geo_id=...)` o (b) del resolver interno. La regla es: si `geo_id` viene en el kwarg, usar el kwarg; si no, llamar al resolver; si el resolver es `None`, fallback a `location=`.

**Rationale**: 2 paths de entrada (kwarg + resolver) dan backward-compat: tests antiguos que pasan `geo_id=...` siguen funcionando; el `app_factory` puede elegir entre pasar `geo_id` resuelto o inyectar el resolver. Para el `app_factory` actual, **inyectar el resolver** (path b) es más simple — el kwarg `geo_id` queda en `None` y el scraper hace su propio resolve.

### Decision: el archivo del scorer es `infrastructure/keyword_score.py` (NO `application/`)

**Choice**: El scorer puro `keyword_score(job, query_tokens) -> float` vive en `infrastructure/keyword_score.py` (un módulo nuevo, hoja, sin I/O).

**Alternatives considered**:
- Poner el scorer en `application/ranking.py` (donde está `rank_jobs`). **Rechazado**: `application/ranking.py` ya importa `application.aggregator` vía `TYPE_CHECKING` para evitar un ciclo; agregar `keyword_score` ahí confunde concerns (scoring = nuevo concern, distinto de ranking).
- Poner el scorer en `application/keyword_score.py`. **Rechazado**: el scorer es una función pura sin use case / port; `infrastructure/` es el lugar canónico para funciones puras sobre tipos del dominio (mismo patrón que `infrastructure/pagination.py:paginated_search`, que también es una función pura sobre el dominio).

**Rationale**: Sigue el patrón existente (`paginated_search` en `infrastructure/`); mantiene `application/` enfocado en use cases + ports. El scorer NO es un use case; es una utility de scoring.

### Decision: el filtro InfoJobs es un módulo separado (`infrastructure/aggregator_filters.py`), no un método del `InfoJobsPlaywrightScraper`

**Choice**: Función pura `filter_infojobs_results(jobs, query_tokens) -> list[Job]` en un módulo nuevo `infrastructure/aggregator_filters.py`. El agregador la llama DESPUÉS de recibir los resultados del InfoJobs scraper (post-cache, pre-dedup).

**Alternatives considered**:
- Filtro en el closure `_make_fetch_one_page` del InfoJobs scraper (descartar cards en parseo). **Rechazado**: el closure no tiene acceso a la query original (solo `keywords` y `location`); además filtra ANTES del dedup, que es lo que queremos, pero COMPLICA el closure que ya captura el `domain` para `_parse_cards`. Más importante: el filtro debe ser un test puro sin Playwright, lo que requiere extraerlo del scraper.
- Filtro como método en el `InfoJobsPlaywrightScraper`. **Rechazado**: mismo motivo — el filtro es post-scrape, no in-scrape.

**Rationale**: El filtro es una **función pura de utilidad** que el aggregator aplica. Que viva en `infrastructure/` (no `application/`) sigue el mismo patrón que `keyword_score` y `paginated_search`: pure function sobre tipos del dominio.

### Decision: el `aggregator_filters.py` es UNA sola función pública (`filter_infojobs_results`) y `keyword_score.py` es UN solo scorer público

**Choice**: Solo se agrega la función necesaria al scope. No se construye un módulo "filters" multi-propósito.

**Rationale**: YAGNI. Si el futuro necesita un 2º filtro, se agrega al mismo módulo. Si la `keyword_score` se separa del módulo (e.g. un `BM25Scorer`), se mueve en un cambio dedicado.

### Decision: el WARNING log de `REQ-DEFENSIVE-001` se emite DESDE el aggregator, no desde la ruta

**Choice**: El `SearchAllSourcesUseCase` instancia un `logger = logging.getLogger(__name__)` y emite WARNING con `extra={request_id, source, error_type}`. La ruta NO loguea (es thin composition).

**Alternatives considered**:
- Loguear desde la ruta. **Rechazado**: la ruta recibe el `AggregatedResult.per_source[source].error` y tendría que iterar y loguear; duplica la lógica del aggregator. La ruta solo construye headers (`X-Aggregator-Errors` ya existe).

**Rationale**: El aggregator es el ÚNICO punto que ve el `JobSearchError` (la ruta recibe un `SourceResult(error=...)` ya encapsulado). Loguear en el lugar donde se captura la excepción es la convención Python (`logger.warning(..., exc_info=True)`).

### Decision: `AllSourcesFailedError` se lanza DESPUÉS de que los 3 sources fallaron, no al primer fallo

**Choice**: El aggregator espera a que `asyncio.gather` termine, cuenta `success_count`, y lanza `AllSourcesFailedError` si `success_count == 0`. Si 1 o 2 sources succeeded, NO lanza (devuelve resultados parciales con status 200).

**Rationale**: El patrón `asyncio.gather(*tasks, return_exceptions=True)` da control total: nunca abortamos el gather, siempre dejamos que las 3 llamadas terminen (o fallen). Recién después decidimos. Esto previene cancelaciones precipitadas y da WARNING logs por cada source fallido.

### Decision: el campo `query_tokens` es un `tuple[str, ...]` (NO `frozenset`) en el `JobSearchCacheKey`

**Choice**: `query_tokens: tuple[str, ...] = ()` como 6º campo en `JobSearchCacheKey` (NamedTuple).

**Alternatives considered**:
- `frozenset[str]`. **Rechazado**: NamedTuple con frozenset es válido pero `tuple` es el patrón existente (NamedTuples con tipos inmutables); además `tuple` preserva el orden (frozenset no), lo que da determinismo en logs y serialización.
- `set[str]`. **Rechazado**: set NO es hashable, NamedTuples con campos no-hashable rompen la cache (los dicts con keys no-hashable fallan al hashear).

**Rationale**: REQ-CACHE-001 dice explícitamente `tuple[str, ...] = ()`. El campo es opcional con default `()` para preservar backward-compat con callers posicionales de 5 args.

### Decision: `LocationResolverPort.resolve()` retorna `int | None` (no `int | str` como dice el spec)

**Choice**: El design respeta el código real: el resolver retorna `int | None`. Cuando retorna `None`, el URL builder usa `location=<string>` (fallback). El escenario "Remote" del spec NO aplica al resolver real (Remote NO está en `_CANONICAL_MAPPING`; retorna `None`).

**Rationale**: El spec (escenario 2) dice "el resolver devuelve el string 'Remote' para input 'Remote'". Esto NO coincide con el código real (`HardcodedLocationResolver.resolve` retorna `int | None`). El design documenta la desviación: el comportamiento observable de cara al usuario ES el mismo (URL usa `location=Remote` cuando el resolver no conoce la location), solo cambia la implementación interna (el resolver retorna `None` en lugar de pasar el string por un canal alternativo). Esta es una **desviación del spec escenario 2 que el design adopta sin协商** — es un cambio de wording, no de comportamiento.

## Component changes

> Las tablas usan el formato `+/-` (líneas añadidas/eliminadas) para estimar el delta real.

### 1. `backend/src/jobs_finder/infrastructure/keyword_score.py` (NEW, ~80 LOC)

**What**: Función pura `keyword_score(job: Job, query_tokens: set[str]) -> float` que computa un score en `[0.0, 1.0]`.

**Why**: Habilita el ranking opt-in por relevancia. Es una función pura (sin I/O) testeable en aislamiento.

**Signature**:

```python
def keyword_score(job: Job, query_tokens: set[str]) -> float:
    """Return a relevance score in [0.0, 1.0] for `job` against `query_tokens`.

    Formula:
        title_match_rate * 0.6 + description_match_rate * 0.4
    where match_rate = |matched_tokens ∩ query_tokens| / |query_tokens|.

    Edge cases:
        - Empty query_tokens -> 0.0 (avoid ZeroDivisionError).
        - Empty title -> 0.0 for the title component.
        - Unicode (e.g. "Málaga") -> preserved as-is; tokens are
          case-insensitive via .casefold() on the QUERY side (the
          route does the tokenize), not the job side.
    """
```

**Algorithm**:

1. `if not query_tokens: return 0.0`
2. Tokenize `job.title` (lowercase + split on whitespace + punctuation; reuse `tokenize()` del módulo — see #2).
3. `title_matches = |tokenize(job.title) ∩ query_tokens| / |query_tokens| * 0.6`
4. Tokenize `job.description or ""` (mismo tokenize).
5. `desc_matches = |tokenize(desc) ∩ query_tokens| / |query_tokens| * 0.4`
6. Return `min(title_matches + desc_matches, 1.0)`

**Test strategy**: 8 unit tests in NEW file `tests/unit/test_keyword_score.py` (test-first, strict TDD).

---

### 2. `backend/src/jobs_finder/infrastructure/aggregator_filters.py` (NEW, ~50 LOC)

**What**: Función pura `filter_infojobs_results(jobs, query_tokens) -> list[Job]` + helper `tokenize(text: str) -> set[str]` exportado.

**Why**: REQ-FILTER-001. El helper `tokenize` se reusa desde `keyword_score` para garantizar el mismo algoritmo de tokenización.

**Signature**:

```python
def tokenize(text: str) -> set[str]:
    """Lowercase + split on whitespace + punctuation + dedupe.

    Algorithm:
        1. text.casefold()  (Unicode-aware lowercasing).
        2. re.split(r'[\s\W_]+', text)  (whitespace + non-word + underscore).
        3. filter(strip + non-empty).
        4. set(...) for dedup.

    Preserves NFC (no .normalize()): "Málaga" stays "Málaga" (U+00E1),
    not "Málaga" (NFD-decomposed). The query side does NOT
    normalize either, so "Málaga" in the query matches "Málaga"
    in the title, but does NOT match "Malaga" (no accent) — this
    is the canonical Unicode-safe behavior pinned by REQ-FILTER-001
    scenario "tokenización es Unicode-safe".

    Note: underscore is in the split set so "node_js" -> {"node", "js"}.
    """

def filter_infojobs_results(
    jobs: list[Job], query_tokens: set[str]
) -> list[Job]:
    """Discard jobs with 0 token overlap with query_tokens.

    Pure: no I/O, no mutation of input. Returns a new list.
    A job is kept iff len(tokenize(job.title) ∩ query_tokens) > 0.
    """
```

**Test strategy**: 6 unit tests in NEW file `tests/unit/test_aggregator_filters.py` (test-first).

---

### 3. `backend/src/jobs_finder/infrastructure/linkedin/scraper.py` (MODIFY, +30 LOC / -5 LOC)

**What**:
- Fix bug pre-existente: `_make_fetch_one_page(self, keywords, location, geo_id=None)` TIENE el kwarg `geo_id` en firma pero NUNCA lo pasa a `_build_url` (línea 276 sí lo pasa, **pero** la línea 231 no lo pasa al closure). El fix: en `search()` línea 231, cambiar a `fetch_one_page=self._make_fetch_one_page(keywords, location, geo_id=geo_id)`.
- Agregar nuevo campo opcional `location_resolver: LocationResolverPort | None = None` al `LinkedInScraperSettings` (modificar #4).
- En `search()`: si `geo_id is None and self._settings.location_resolver is not None`, llamar `geo_id = self._settings.location_resolver.resolve(location)` UNA vez antes del loop.
- En `__init__`: si el resolver se inyecta, loguear el evento UNA vez (en construcción, no por `search()` call).
- **Desviación del spec escenario 4**: el spec dice "se emite un `DeprecationWarning` cuando el resolver no está inyectado". El design invierte: el WARNING se emite CUANDO SÍ se inyecta (INFO: "resolver wired"), y se omite el deprecation (la backward-compat v1 sin resolver es soportable y no urge deprecar). Documentado abajo en "Deviations".

**Why**: REQ-LOC-001. El fix del bug es pre-requisito para que el `_build_url` use el `geoId` correcto. La inyección del resolver via settings evita que el `app_factory` tenga que hacer el resolve y pasarlo a mano.

**Test strategy**: 4 unit tests in EXISTING `tests/unit/test_linkedin_scraper.py` (test-first):
- `test_search_uses_geoId_when_resolver_returns_int`
- `test_search_uses_location_when_resolver_returns_string_or_None` (desviación del spec: cubre los 2 casos unificados)
- `test_search_uses_location_when_resolver_is_none`
- `test_resolver_called_once_per_search_not_per_page`

---

### 4. `backend/src/jobs_finder/infrastructure/linkedin/throttle.py` (NO cambia) + `settings` se inyectan vía `LinkedInScraperSettings`

**Desviación del spec/proposal**: el spec dice "agregar `location_resolver` al settings dataclass en `throttle.py`". Esto es **incorrecto** — `throttle.py` es solo `AsyncThrottle` (clase de serialización). El lugar correcto es `LinkedInScraperSettings` en `scraper.py` (que es el dataclass de configuración del scraper, mismo patrón Indeed/InfoJobs). El design adopta `scraper.py` (NO `throttle.py`).

**What**: Agregar 1 campo opcional al `LinkedInScraperSettings` (en `scraper.py`):

```python
__slots__ = (
    "inter_page_delay_seconds",
    "location_resolver",  # NEW
    "max_pages",
    "timeout_ms",
    "user_agent",
)

def __init__(
    self,
    *,
    user_agent: str,
    timeout_ms: int,
    max_pages: int = 10,
    inter_page_delay_seconds: float = 1.0,
    location_resolver: LocationResolverPort | None = None,  # NEW, optional
) -> None:
    ...
```

El campo requiere actualizar `__eq__` y `__hash__` para incluir el nuevo campo (sin él, dos settings con resolvers distintos serían `==` — un test existente podría romperse).

**Why**: Mantiene la cohesión (todos los config del scraper en un lugar); sigue el patrón existente.

**Test strategy**: 1 unit test en EXISTING `tests/unit/test_linkedin_settings.py` (`test_settings_optional_resolver_defaults_to_None` + `test_settings_equality_includes_resolver`).

---

### 5. `backend/src/jobs_finder/application/aggregator.py` (MODIFY, +80 LOC / -5 LOC)

**What**:
- Agregar `query_tokens: set[str] = frozenset()` y `enable_keyword_scoring: bool = False` como kwargs keyword-only del `search()`.
- En el `try/except` de `_call_one` (línea 270), emitir `logger.warning(...)` con `extra={request_id, source, error_type}` cuando se captura un `JobSearchError`. `request_id` se obtiene via `from jobs_finder.presentation.middleware import get_request_id` (desviación menor: el aggregator importa de `presentation/`, lo cual el dependency rule prohibe — ver "Deviations" abajo).
- **ALTERNATIVA sin violar dependency rule**: el logger usa un `ContextVar` propio (`_SOURCE_ERROR_VAR`) que la ruta setea antes de llamar al aggregator. La ruta setea `request_id` en el ContextVar desde `request.state.request_id` y el aggregator lo lee. Esto preserva el dependency rule.
- Después de la dedup, si `enable_keyword_scoring` es `True`, aplicar `sort_by_keyword_score(deduped_jobs, query_tokens)`; si es `False`, mantener el `rank_jobs` actual.
- Si `sum(succeeded) == 0`, lanzar `AllSourcesFailedError` (nueva exception en `domain/exceptions.py`).

**Why**: REQ-DEFENSIVE-001, REQ-SCORE-001, REQ-FILTER-001. El filtro InfoJobs y el ordenamiento se aplican post-dedup (los tests de `test_aggregator.py` existentes verifican que el dedup es estable; agregar un sort al final es no-breaking).

**Signature**:

```python
async def search(
    self,
    keywords: str,
    location: str,
    limit: int,
    sources: list[str],
    *,
    linkedin_geo_id: int | None = None,
    query_tokens: frozenset[str] = frozenset(),  # NEW
    enable_keyword_scoring: bool = False,         # NEW
) -> AggregatedResult:
```

**Test strategy**: 3 unit/integration tests en EXISTING `tests/unit/test_aggregator.py` (ya cubierto: filter, keyword_score dispatch, defensive partial results, 502 fallback).

---

### 6. `backend/src/jobs_finder/application/usecases/_cached_search.py` (MODIFY, +15 LOC / -3 LOC)

**What**:
- `CachedJobSearchUseCase.search()` acepta nuevo kwarg `query_tokens: tuple[str, ...] = ()`.
- Al construir el `JobSearchCacheKey`, pasar `query_tokens=tuple(sorted(query_tokens))` (normalizado a tuple ordenada).
- Forward del kwarg al `port.search(...)` — los ports NO usan `query_tokens` (es cache-only concern); el kwarg se ignora silenciosamente en los 3 scrapers.

**Why**: REQ-CACHE-001. La query_tokens forma parte de la cache key pero NO se propaga al port (es un cache-busting concern, no un scraping concern).

**Signature**:

```python
async def search(
    self,
    keywords: str,
    location: str,
    limit: int = 20,
    geo_id: int | None = None,
    query_tokens: tuple[str, ...] = (),  # NEW, keyword-only
) -> SearchResult:
    key = JobSearchCacheKey(
        source=self._source,
        keywords=keywords,
        location=location,
        limit=limit,
        geo_id=geo_id,
        query_tokens=tuple(sorted(query_tokens)),  # NEW
    )
    ...
```

**Test strategy**: 4 unit tests en EXISTING `tests/unit/test_cached_job_search_use_case.py`.

---

### 7. `backend/src/jobs_finder/application/ports.py` (MODIFY, +15 LOC / -3 LOC)

**What**: Agregar 6º campo al NamedTuple `JobSearchCacheKey`:

```python
class JobSearchCacheKey(NamedTuple):
    source: str
    keywords: str
    location: str
    limit: int
    geo_id: int | None = None
    query_tokens: tuple[str, ...] = ()  # NEW, default = ()
```

**Why**: REQ-CACHE-001. NamedTuple con default es backward-compat (callers posicionales de 5 args siguen funcionando).

**Test strategy**: 3 unit tests en EXISTING `tests/unit/test_in_memory_ttl_cache.py` + 1 test que el default `()` preserva el comportamiento v1.

---

### 8. `backend/src/jobs_finder/infrastructure/config.py` (MODIFY, +20 LOC)

**What**:
- Agregar campo `enable_keyword_scoring: bool = False` con `validation_alias=AliasChoices("ENABLE_KEYWORD_SCORING", "enable_keyword_scoring")`.
- **NO modificar** `aggregator_ranking_strategy` ni `aggregator_priority_map` (esos ya están; el opt-in de `keyword_score` es ortogonal al Literal existente).

**Why**: REQ-SCORE-001 (opt-in por env var, default `false`).

**Test strategy**: 2 unit tests en EXISTING `tests/unit/test_aggregator_settings.py`.

---

### 9. `backend/src/jobs_finder/presentation/app_factory.py` (MODIFY, +10 LOC)

**What**:
- Instanciar `location_resolver = HardcodedLocationResolver()` ANTES del bloque `if use_case is None` (sin guard `chat_enabled` — siempre se construye).
- Pasar `location_resolver=location_resolver` al constructor `LinkedInScraperSettings(...)` (línea 229 actual).
- Pasar `enable_keyword_scoring=effective_settings.enable_keyword_scoring` al `SearchAllSourcesUseCase(...)` (línea 516 actual).

**Why**: REQ-LOC-001, REQ-LOC-002, REQ-SCORE-001.

**Test strategy**: 2 integration tests en EXISTING `tests/integration/test_composition.py`.

---

### 10. `backend/src/jobs_finder/presentation/routes/aggregator.py` (MODIFY, +25 LOC / -2 LOC)

**What**:
- Tokenizar la query: `query_tokens = tokenize(query.q)`. Usar el helper público `tokenize` de `infrastructure/aggregator_filters.py`.
- Construir `linkedin_geo_id`: `linkedin_geo_id = request.app.state.location_resolver.resolve(query.location)` (o `None` si no hay resolver).
- Forward ambos al `use_case.search(...)`.

**Why**: REQ-LOC-001, REQ-FILTER-001, REQ-CACHE-001, REQ-SCORE-001.

**Test strategy**: 3 integration tests en EXISTING `tests/integration/test_aggregator_api.py`.

---

### 11. `backend/src/jobs_finder/domain/exceptions.py` (MODIFY, +8 LOC)

**What**: Agregar

```python
class AllSourcesFailedError(JobSearchError):
    """Raised when the aggregator's 3 sources all fail.

    Mapped to HTTP 502 by the registered exception handler
    (same as any JobSearchError).
    """
```

**Why**: REQ-DEFENSIVE-001.

**Test strategy**: 1 unit test en EXISTING `tests/unit/test_exceptions.py`.

---

### 12. `backend/.env.example` (MODIFY, +5 LOC)

**What**: Documentar `# ENABLE_KEYWORD_SCORING=false  # opt-in keyword relevance ranking`.

---

### 13. `backend/src/jobs_finder/main.py` (POSIBLE MODIFY, ~5 LOC)

**What**: Si `main.py` construye `Settings()` y lo pasa a `build_app(...)` por separado, NO requiere cambio. Si construye `build_app()` sin pasar `settings`, NO requiere cambio. **Verificar in-place**; alta probabilidad de que NO requiera cambio.

---

### 14. `backend/src/jobs_finder/infrastructure/infojobs/scraper.py` (NO MODIFY en este design)

**Desviación del spec/proposal**: el proposal dice "filtro client-side en `infrastructure/infojobs/scraper.py`". El design lo mueve al aggregator (post-cache, post-scrape). Ver "Deviations".

---

## Data flow

### Request: `GET /jobs?q=react&location=malaga&limit=20`

1. **Browser → Next.js Route Handler** (`src/app/api/jobs/route.ts`): GET `/api/jobs?q=react&location=malaga&limit=20`.
2. **Next.js → FastAPI**: GET `/jobs?q=react&location=malaga&limit=20`.
3. **FastAPI `aggregator` route** (`presentation/routes/aggregator.py:134`):
   - `query = AggregatedJobsQuery(q="react", location="malaga", limit=20)`.
   - `query_tokens = tokenize("react")` → `{"react"}` (set, lowercased).
   - `linkedin_geo_id = app.state.location_resolver.resolve("malaga")` → `104401670` (int).
   - `request_id = request.state.request_id` (uuid4).
   - Set `_SOURCE_REQUEST_ID.set(request_id)` (ContextVar).
4. **`SearchAllSourcesUseCase.search(...)`** (`application/aggregator.py:214`):
   - 3 `asyncio.gather` calls, each wrapped in try/except.
   - Each task forwards `query_tokens=("react",)` + `geo_id=104401670` to `CachedJobSearchUseCase.search(...)`.
5. **`CachedJobSearchUseCase.search(...)`** (`application/usecases/_cached_search.py:94`):
   - `key = JobSearchCacheKey(source, "react", "malaga", 20, 104401670, ("react",))`.
   - First call: cache MISS → `port.search("react", "malaga", 20, geo_id=104401670, query_tokens=("react",))`.
   - LinkedIn port (`infrastructure/linkedin/scraper.py:193`): llama `self._settings.location_resolver.resolve("malaga")` → `104401670` (usa el del settings, ignora el kwarg `geo_id` que es `None` cuando viene del aggregator SIN resolver pre-resuelto). Espera — esto es un bug: el aggregator PASA `linkedin_geo_id` al port; el port llama al resolver INTERNO, redundante.
   - **Fix del bug** (parte de Mejora 1): el port `search(geo_id=None, ...)` — cuando el kwarg `geo_id` es `None` y el `location_resolver` está seteado, llama al resolver. Si el kwarg `geo_id` ya viene con un int, usa el kwarg (evita el resolve redundante). Este es el patrón de "kwarg override, fallback to resolver".
   - URL build: `https://www.linkedin.com/jobs/search/?keywords=react&geoId=104401670&start=0`.
6. **Playwright navigate**: scrape 1 page (page 0 only, no pagination needed for 20 jobs).
7. **Parse + return `list[Job]`**: parser puro extrae cards, retorna ~15-25 jobs.
8. **Cache SET**: `cache.set(key, jobs)`.
9. **Aggregator collects** `SourceResult(source="linkedin", jobs=..., cache_status="MISS")`. Similarly for Indeed + InfoJobs.
10. **Try/except for Indeed** (suppose it raises `IndeedTimeoutError`): `_logger.warning("source failed", extra={request_id, source: "indeed", error_type: "IndeedTimeoutError"})`. Continue.
11. **Try/except for InfoJobs** (succeeds with 30 jobs): `SourceResult(source="infojobs", jobs=[30 jobs], cache_status="MISS")`.
12. **Dedup** by `(title.casefold().strip(), company.casefold().strip(), location.casefold().strip())` → 35 unique jobs (15 LinkedIn + 20 InfoJobs).
13. **InfoJobs filter**: `filter_infojobs_results(infojobs_jobs, {"react"})` — descarta cards con `title` sin overlap (e.g. "Recepcionista" descartado; "Desarrollador React" conservado). Quedan 12 InfoJobs.
14. **Sort**:
    - `enable_keyword_scoring=False` (default) → `rank_jobs(jobs, "posted_at")` → 27 jobs sorted by date DESC.
    - `enable_keyword_scoring=True` → `keyword_score desc, posted_at desc` → top job likely has "React" in title.
15. **Return** `AggregatedResult(jobs=[27 AggregatedJob], per_source={...}, cache_statuses={...})`.
16. **Route** sets headers: `X-Cache: linkedin=MISS,indeed=ERROR,infojobs=MISS` (joined per source); `X-Aggregator-Sources: linkedin,indeed,infojobs`; `X-Aggregator-Errors: indeed` (Indeed failed).
17. **HTTP 200** with body `{"jobs": [27 AggregatedJobResponse, ...]}`.
18. **Next.js Route Handler** forwards JSON + `X-Cache` + `X-Request-Id` to the browser.

### Failure scenarios

- **LinkedIn fails**: `LinkedInTimeoutError` raised. WARNING logged with `source=linkedin`. The aggregator continues. Response has 200 + Indeed + InfoJobs results + `X-Aggregator-Errors: linkedin`.
- **Indeed + InfoJobs fail, LinkedIn succeeds**: 200 + LinkedIn results + `X-Aggregator-Errors: indeed,infojobs`.
- **All 3 sources fail**: 3 WARNING logs. Aggregator raises `AllSourcesFailedError`. Route handler — el `JobSearchError` handler lo mapea a 502. Body: `{"detail": "...", "request_id": "..."}` (el handler enmascara el detalle).
- **InfoJobs returns 0 jobs after filter**: status 200 with 0 InfoJobs + LinkedIn + Indeed. NOT a 502.

## File-by-file change list (with LOC estimate)

| File | Change | LOC delta |
|---|---|---|
| `backend/src/jobs_finder/infrastructure/keyword_score.py` | NEW: scorer puro | +80 |
| `backend/src/jobs_finder/infrastructure/aggregator_filters.py` | NEW: `tokenize` + `filter_infojobs_results` | +50 |
| `backend/src/jobs_finder/infrastructure/linkedin/scraper.py` | Fix bug + resolver injection in `LinkedInScraperSettings` | +30 / -5 |
| `backend/src/jobs_finder/application/aggregator.py` | Add 2 kwargs, try/except logging, 502 fallback, filter call, sort dispatch | +80 / -5 |
| `backend/src/jobs_finder/application/usecases/_cached_search.py` | Add `query_tokens` kwarg + tuple normalization | +15 / -3 |
| `backend/src/jobs_finder/application/ports.py` | 6th field on `JobSearchCacheKey` | +10 / -3 |
| `backend/src/jobs_finder/infrastructure/config.py` | Add `enable_keyword_scoring` field | +20 |
| `backend/src/jobs_finder/presentation/app_factory.py` | Construct resolver (always) + inject to LinkedIn + forward `enable_keyword_scoring` | +10 |
| `backend/src/jobs_finder/presentation/routes/aggregator.py` | Tokenize + forward `query_tokens`, `linkedin_geo_id`, `enable_keyword_scoring` | +25 / -2 |
| `backend/src/jobs_finder/domain/exceptions.py` | Add `AllSourcesFailedError` | +8 |
| `backend/.env.example` | Document `ENABLE_KEYWORD_SCORING` | +5 |
| `backend/README.md` | Document new env var + filter + scoring | +50 |
| `backend/tests/unit/test_keyword_score.py` | NEW: 8 tests | +180 |
| `backend/tests/unit/test_aggregator_filters.py` | NEW: 6 tests | +100 |
| `backend/tests/unit/test_linkedin_scraper.py` | Add 4 tests for geoId + resolver | +100 |
| `backend/tests/unit/test_linkedin_settings.py` | Add 2 tests for resolver field | +40 |
| `backend/tests/unit/test_aggregator.py` | Add 5 tests for filter, scoring, defensive | +140 |
| `backend/tests/unit/test_aggregator_settings.py` | Add 2 tests for `enable_keyword_scoring` | +40 |
| `backend/tests/unit/test_cached_job_search_use_case.py` | Add 4 tests for `query_tokens` | +80 |
| `backend/tests/unit/test_in_memory_ttl_cache.py` | Add 3 tests for new key field | +60 |
| `backend/tests/unit/test_exceptions.py` | Add 1 test for `AllSourcesFailedError` | +15 |
| `backend/tests/integration/test_aggregator_api.py` | Add 3 tests for query_tokens + filter + scoring | +90 |
| `backend/tests/integration/test_composition.py` | Add 2 tests for resolver injection | +40 |
| **TOTAL** |  | **~1340** (forecast 1000-1500 ✓) |

## Test strategy (Strict TDD)

| Capa | Módulo nuevo | Tests | Cobertura |
|---|---|---|---|
| Unit | `test_keyword_score.py` | 8 | 4 base + 4 edge (empty, unicode, punctuation) |
| Unit | `test_aggregator_filters.py` | 6 | 4 base + 2 edge (empty list, all-match) |
| Unit | `test_linkedin_scraper.py` (extended) | +4 | 4 escenarios de REQ-LOC-001 + bug fix |
| Unit | `test_linkedin_settings.py` (extended) | +2 | resolver optional + equality |
| Unit | `test_aggregator.py` (extended) | +5 | filter, scoring, defensive, 502, log-once |
| Unit | `test_aggregator_settings.py` (extended) | +2 | env var default + opt-in |
| Unit | `test_cached_job_search_use_case.py` (extended) | +4 | cache key con `query_tokens` |
| Unit | `test_in_memory_ttl_cache.py` (extended) | +3 | key separation + default |
| Unit | `test_exceptions.py` (extended) | +1 | `AllSourcesFailedError` |
| Integration | `test_aggregator_api.py` (extended) | +3 | end-to-end con query_tokens |
| Integration | `test_composition.py` (extended) | +2 | resolver injection |
| **TOTAL** | | **~40 tests nuevos** | 4 quality gates pasan |

**Regression**: los ~1036 tests preexistentes deben seguir GREEN. El mayor riesgo de regresión es el **bug fix en `_make_fetch_one_page`** (línea 231 de `linkedin/scraper.py`) — si un test existente dependía de que `geo_id` se IGNORARA, ese test se rompe. Mitigación: el test del bug es test-first (RED primero, luego GREEN); los tests preexistentes se ejecutan antes del apply y se ajustan in-place.

## Deviations from the spec (y el proposal)

1. **`infrastructure/keyword_score.py` vs `application/ranking.py`**: el spec/proposal dice "scorer en `application/ranking.py`". El design lo pone en `infrastructure/keyword_score.py` (función pura, no use case). Mismo razonamiento que `paginated_search` (utility pura sobre tipos del dominio).

2. **Filtro InfoJobs post-scrape, no in-scrape**: el proposal dice "filtro client-side en `infrastructure/infojobs/scraper.py`". El design lo mueve al aggregator (post-cache, post-scrape). Razón: el filtro es test-able sin Playwright; el closure del scraper no tiene acceso a la query original (solo keywords + location separados).

3. **Spec escenario 2 (`location=Remote` → resolver retorna string)**: el código real retorna `None` para `Remote` (no está en `_CANONICAL_MAPPING`). El design respeta el código: el escenario se convierte en "el resolver retorna `None` → URL usa `location=Remote`" (mismo comportamiento observable, distinto wording interno). El test del spec escenario 2 se reemplaza por "el scraper cae a `location=` cuando el resolver retorna `None`".

4. **Spec escenario 4 (DeprecationWarning cuando no hay resolver)**: el design invierte — emite INFO ("resolver wired") cuando SÍ hay, omite el deprecation. La backward-compat v1 (sin resolver) sigue funcionando sin warning; no urge deprecar.

5. **`throttle.py` vs `scraper.py` para el settings field**: el spec dice "agregar `location_resolver` al settings en `throttle.py`". Esto es un error — `throttle.py` es solo `AsyncThrottle`. El lugar correcto es `LinkedInScraperSettings` en `scraper.py`.

6. **`all sources failed` exception**: el design agrega `AllSourcesFailedError` en `domain/exceptions.py` (subclass de `JobSearchError`). El spec no especifica el nombre; el handler de `JobSearchError` ya mapea a 502, así que no se necesita un handler nuevo.

7. **`InfoJobsParseError("zero_cards_on_first_page")` cuando el filtro deja 0 jobs**: el design NO relanza este error. El filtro es post-scrape; un 0-job result es legítimo (no es un "parse error"). El aggregator retorna 200 con 0 InfoJobs + LinkedIn + Indeed.

8. **Inyección del resolver en el scraper (vía settings) en lugar de en `app.state`**: el spec/proposal dice "el route lee `app.state.location_resolver` y pasa al aggregator, que pasa al scraper". El design lo invierte: el `app_factory` inyecta el resolver en el `LinkedInScraperSettings`; el scraper lo usa internamente; el aggregator NO necesita conocer el resolver. Razón: encapsulación, el scraper es self-contained.

9. **Cache key `tuple` vs `frozenset`**: el spec usa `frozenset` en algunas partes y `tuple` en otras. El design estandariza a `tuple[str, ...]` (REQ-CACHE-001 lo dice explícitamente) y al construir la key normaliza con `tuple(sorted(set(query_tokens)))`.

10. **El aggregator usa `_SOURCE_REQUEST_ID` ContextVar (en lugar de importar `get_request_id` directamente)**: para preservar el dependency rule `presentation → application → domain ← infrastructure`. La ruta setea el ContextVar; el aggregator lo lee; cero imports cross-layer.

## Open questions

**None** — todas las decisiones se resolvieron en el launch prompt (7 user decisions confirmadas). El design documenta 10 desviaciones del spec/proposal que se justifican técnicamente; no requieren re-ask al usuario (son decisiones de implementación que el orchestrator puede revisar y aceptar).

## Self-check before sdd-tasks

- [x] Los 7 REQ-* del spec tienen cambios correspondientes: REQ-LOC-001 (componente 3, fix bug), REQ-LOC-002 (componentes 4, 9), REQ-FILTER-001 (componente 2, 5), REQ-SCORE-001 (componentes 1, 5, 8, 9), REQ-CACHE-001 (componentes 6, 7), REQ-DEFENSIVE-001 (componentes 5, 11), REQ-TEST-001 (test strategy).
- [x] Los 33 scenarios del spec tienen test strategy: ver tabla de tests arriba.
- [x] LOC forecast: ~1340 (rango 1000-1500 ✓).
- [x] 1 env var nuevo (`ENABLE_KEYWORD_SCORING`). Las 2 existentes del ranking (`AGGREGATOR_RANKING_STRATEGY`, `AGGREGATOR_PRIORITY_MAP`) NO se tocan.
- [x] Backward-compat: `test_cached_job_search_use_case.py` y `test_composition.py` siguen pasando (NamedTuple default + resolver optional).
- [x] `AllSourcesFailedError` se lanza DESPUÉS de gather (no aborta gather).
- [x] Deprecation warning se omite (decisión de desviación #4).
- [x] `keyword_score` opt-in: `ENABLE_KEYWORD_SCORING=false` (default) → comportamiento v1 preservado.

## Next step

Listo para `sdd-tasks`. El forecast (~1340 LOC) está bien por debajo del budget de 5000 líneas; la `delivery_strategy=ask-always` se resuelve a "no stop" (single PR). Las 10 desviaciones están documentadas y justificadas — el orchestrator puede aceptarlas o pedir renegociación antes de `sdd-tasks`.
