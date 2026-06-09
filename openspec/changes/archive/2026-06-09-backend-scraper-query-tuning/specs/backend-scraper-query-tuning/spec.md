# Spec: backend-scraper-query-tuning

**Change**: `backend-scraper-query-tuning` • **Mode**: `both` (OpenSpec + Engram) • **Strict TDD**: ACTIVE
**Date**: 2026-06-09 • **Status**: `specified` (listo para `sdd-design`)
**Spec type**: Consolidated — agrupa 7 requirements que afectan 4 dominios (`LinkedIn scraper`, `InfoJobs scraper`, `Aggregator ranking`, `Cache key`). Las capabilities son **nuevas** (no existen specs canónicas previas), por lo que se escriben como spec consolidado en lugar de deltas separados.

## Purpose

El endpoint `GET /jobs` del backend devuelve resultados ruidosos porque
LinkedIn ignora el parámetro `location=` (devuelve ofertas de "AI
Trainer" en "Washington" para queries en Málaga), InfoJobs trae roles
sin overlap de tokens con la query (recepcionista, pintor, ordenanza)
y el agregador ordena solo por `posted_at DESC` sin puntuar
relevancia. Este cambio cierra esas 3 brechas con 4 mejoras
independientes: (1) LinkedIn recibe `geoId=<int>` cuando el
`HardcodedLocationResolver` conoce la location, (2) el agregador
aplica un filtro client-side SOLO a InfoJobs que descarta ofertas
cuyo `title` no comparte tokens con la query, (3) una función pura
`keyword_score(job, query_tokens)` ofrece ranking opt-in por
relevancia via env var `ENABLE_KEYWORD_SCORING=true`, y (4) la cache
key por fuente incluye los tokens normalizados de la query para
mejor hit-rate en queries similares. La forma de la respuesta HTTP
NO cambia (backward-compatible con el frontend ya archivado).

## Requirements

### REQ-LOC-001: LinkedIn scraper usa `geoId` cuando el resolver devuelve un int

**Statement**: Cuando el `HardcodedLocationResolver` (inyectado en
el `LinkedInPlaywrightScraper`) devuelve un entero `geoId` para una
location dada, el método `search(keywords, location, limit)` MUST
construir la URL con `geoId=<int>` en lugar de `location=<string>`.
Cuando el resolver devuelve un string (no hay mapeo), la URL MUST
usar `location=<string>` (fallback backward-compatible). Cuando el
resolver no está inyectado (legacy wiring), la URL MUST usar
`location=<string>` y se emite un `DeprecationWarning` al logger
para empujar a los operadores a inyectar el resolver.

**Scenarios**:

#### Scenario: `location=malaga` se resuelve a `geoId=104401670`
- **Given** un `HardcodedLocationResolver` inyectado en el `LinkedInPlaywrightScraper`
- **And** el resolver devuelve `104401670` para input `"malaga"` (verificado en `infrastructure/location/_mapping.py:47`)
- **When** se llama a `LinkedInPlaywrightScraper.search("react", "malaga", 20)`
- **Then** la URL navegada es `https://www.linkedin.com/jobs/search?keywords=react&geoId=104401670&start=0` (NO contiene `location=malaga`)
- **And** el test `tests/unit/test_linkedin_scraper.py::test_search_uses_geoId_when_resolver_returns_int` pasa

#### Scenario: `location=Remote` (sin mapeo) cae a `location=`
- **Given** el resolver devuelve el string `"Remote"` para input `"Remote"`
- **When** se llama a `LinkedInPlaywrightScraper.search("react", "Remote", 20)`
- **Then** la URL es `https://www.linkedin.com/jobs/search?keywords=react&location=Remote&start=0` (comportamiento legacy, sin cambios)
- **And** el test `tests/unit/test_linkedin_scraper.py::test_search_uses_location_when_resolver_returns_string` pasa

#### Scenario: variantes de "Málaga" resuelven al mismo `geoId`
- **Given** el resolver recibe `"Málaga"` (U+00E1), `"Mál\u0301aga"` (NFD-decompuesto) y `"malaga"` (lowercase, sin tilde)
- **When** se llama al resolver
- **Then** los 3 inputs devuelven `104401670` (mapeo accent- y case-insensitive)
- **And** los tests existentes en `tests/unit/test_hardcoded_location_resolver.py::test_malaga_*` (líneas 81, 146, 148, 200-203) siguen GREEN

#### Scenario: backward-compat — scraper v1 sin resolver inyectado sigue funcionando
- **Given** el `LinkedInPlaywrightScraper` se construye SIN `HardcodedLocationResolver` (wiring legacy)
- **When** se llama a `LinkedInPlaywrightScraper.search("react", "malaga", 20)`
- **Then** la URL es `https://www.linkedin.com/jobs/search?keywords=react&location=malaga&start=0` (comportamiento v1, sin cambios)
- **And** un `DeprecationWarning` se emite al logger con `scraper="linkedin", missing="location_resolver"`
- **And** NO se lanza excepción

#### Scenario: el resolver se llama UNA vez por `search()` y el resultado se cachea
- **Given** un resolver spy que cuenta invocaciones
- **When** se llama a `search("react", "malaga", 20)` (que internamente pagina 1 página)
- **Then** `resolver.resolve("malaga")` se invoca exactamente 1 vez (no una vez por página)
- **And** el test `tests/unit/test_linkedin_scraper.py::test_resolver_called_once_per_search` pasa

### REQ-LOC-002: `HardcodedLocationResolver` wireado en `LinkedInPlaywrightScraper` via `app_factory`

**Statement**: El composition root en
`backend/src/jobs_finder/presentation/app_factory.py` MUST
construir una instancia de `HardcodedLocationResolver` y pasarla al
constructor de `LinkedInPlaywrightScraper` (vía su settings
dataclass). El campo `location_resolver` en el settings dataclass
MUST ser opcional (default `None`) para preservar el wiring legacy.

**Scenarios**:

#### Scenario: `app_factory` wirea el resolver
- **Given** `app_factory.build_app()` se llama con configuración válida
- **When** se construye el `LinkedInPlaywrightScraper`
- **Then** la instancia recibe un `HardcodedLocationResolver` (no `None`)
- **And** el test `tests/integration/test_composition.py::test_linkedin_scraper_has_resolver` pasa (test nuevo)

#### Scenario: settings dataclass acepta el resolver opcionalmente
- **Given** `LinkedInPlaywrightScraperSettings(...)` se construye
- **When** el campo `location_resolver` se omite del constructor
- **Then** el atributo es `None` (default backward-compatible)
- **And** el test `tests/unit/test_linkedin_settings.py::test_settings_optional_resolver` pasa (test nuevo)

#### Scenario: el resolver se construye SIEMPRE, no solo cuando `chat_enabled=True`
- **Given** `chat_enabled=False` y `linkedin_enabled=True`
- **When** se llama a `app_factory.build_app()`
- **Then** el `LinkedInPlaywrightScraper` resultante tiene un resolver (no `None`)
- **And** el test `tests/integration/test_composition.py::test_resolver_built_when_chat_disabled` pasa

### REQ-FILTER-001: filtro client-side de InfoJobs descarta títulos con 0 tokens en común

**Statement**: El agregador MUST aplicar un filtro client-side a
los resultados de InfoJobs: cualquier `Job` cuyo `title`
(lowercased, split por whitespace + puntuación) comparta CERO tokens
con la query (lowercased, split por whitespace) MUST descartarse
antes del paso de dedup. El filtro es una función pura
`filter_infojobs_results(jobs, query_tokens) -> list[Job]`.

**Scenarios**:

#### Scenario: `["react", "málaga"]` + InfoJobs `"Recepcionista"` se descarta
- **Given** el agregador recibe `keywords="react"`, `location="málaga"`
- **And** InfoJobs devuelve un job con `title="Recepcionista"`
- **When** el agregador procesa los resultados de InfoJobs
- **Then** ese job se descarta (0 tokens en común: `{"react", "málaga"}` vs `{"recepcionista"}`)
- **And** el test `tests/unit/test_aggregator.py::test_infojobs_filter_discards_zero_token_title` pasa

#### Scenario: `["react"]` + InfoJobs `"Desarrollador React"` se conserva
- **Given** el agregador recibe `keywords="react"`
- **And** InfoJobs devuelve un job con `title="Desarrollador React"`
- **When** el agregador procesa los resultados de InfoJobs
- **Then** ese job SE CONSERVA (1 token en común: `react`)
- **And** el test `tests/unit/test_aggregator.py::test_infojobs_filter_keeps_partial_token_match` pasa

#### Scenario: el filtro aplica SOLO a InfoJobs
- **Given** el agregador recibe `keywords="react"`
- **And** LinkedIn devuelve un job con `title="Senior Software Engineer"`
- **And** Indeed devuelve un job con `title="Frontend TypeScript Developer"`
- **And** InfoJobs devuelve un job con `title="Recepcionista"`
- **When** el agregador procesa los 3 sources
- **Then** los jobs de LinkedIn e Indeed SE CONSERVAN (filtro no aplica)
- **And** el job de InfoJobs SE DESCARTA
- **And** el test `tests/unit/test_aggregator.py::test_infojobs_filter_does_not_affect_linkedin_indeed` pasa

#### Scenario: el filtro es una función pura
- **Given** `filter_infojobs_results(jobs, query_tokens) -> list[Job]`
- **When** se llama 100 veces con los mismos inputs
- **Then** los 100 outputs son idénticos (no side effects, no I/O, no randomness)
- **And** el input `jobs` no se muta (la lista retornada es una nueva lista)
- **And** el test `tests/unit/test_aggregator.py::test_filter_infojobs_results_is_pure` pasa

#### Scenario: tokenización usa el mismo algoritmo que el resto del agregador
- **Given** el query es `"  React, TypeScript  "` (whitespace + comas)
- **When** se tokeniza
- **Then** los tokens son `{"react", "typescript"}` (lowercased, sin puntuación, sin duplicados)
- **And** un job con `title="React Developer"` se CONSERVA
- **And** el test `tests/unit/test_aggregator.py::test_tokenize_normalizes_whitespace_and_punct` pasa

#### Scenario: tokenización es Unicode-safe (acentos preservados)
- **Given** el query es `"Málaga"` (U+00E1)
- **When** se tokeniza
- **Then** los tokens son `{"málaga"}` (el acento se preserva en minúscula, NO se descompone a `málagu\u0301a` ni se strip-ea)
- **And** un job con `title="Ingeniero Málaga"` (también U+00E1) comparte 1 token y SE CONSERVA
- **And** un job con `title="Ingeniero Malaga"` (sin tilde) NO comparte tokens y se descarta
- **And** el test `tests/unit/test_aggregator.py::test_tokenize_unicode_preserves_accents` pasa

### REQ-SCORE-001: función `keyword_score` y ranking opt-in por env var

**Statement**: Una función pura
`keyword_score(job, query_tokens) -> float` MUST calcular un score
de relevancia en `[0.0, 1.0]`. El score es la razón de tokens
matched (en `title`, `company` o `description`) sobre el total de
query tokens, con un boost para matches en `title`. La estrategia de
ranking `keyword_match` MUST activarse opt-in via env var
`ENABLE_KEYWORD_SCORING=true` (default `false`, que preserva el
comportamiento v1 `posted_at desc`).

**Scenarios**:

#### Scenario: match completo en `title` devuelve 1.0
- **Given** `keyword_score({"title": "React Developer", "company": "Acme", "description": "We use JS"}, ["react"])`
- **When** se evalúa
- **Then** el resultado es `1.0` (1 de 1 token matched en title)
- **And** el test `tests/unit/test_keyword_score.py::test_title_match_returns_1` pasa

#### Scenario: match parcial en `title` devuelve score proporcional
- **Given** `keyword_score({"title": "Senior Python Developer", ...}, ["python", "react"])`
- **When** se evalúa
- **Then** el resultado es exactamente `0.5` (1 de 2 tokens matched en title)
- **And** el test `tests/unit/test_keyword_score.py::test_partial_match_returns_proportional` pasa

#### Scenario: match solo en `description` devuelve valor < 1.0
- **Given** `keyword_score({"title": "Software Engineer", "description": "Looking for Python dev with React experience"}, ["react"])`
- **When** se evalúa
- **Then** el resultado satisface `0.0 < result < 1.0` (match en description, menos peso que title)
- **And** el test `tests/unit/test_keyword_score.py::test_description_only_match_is_less_than_title` pasa

#### Scenario: cero matches devuelve 0.0
- **Given** `keyword_score({"title": "Recepcionista", "description": "Hotel frontline"}, ["react"])`
- **When** se evalúa
- **Then** el resultado es exactamente `0.0`
- **And** el test `tests/unit/test_keyword_score.py::test_no_match_returns_0` pasa

#### Scenario: `keyword_score` está deshabilitado por default
- **Given** `ENABLE_KEYWORD_SCORING` no está seteado (o es `false`)
- **When** se construye la `Settings` y se llama al agregador
- **Then** el ranking aplicado es `posted_at desc` (comportamiento v1, sin cambios)
- **And** el test `tests/unit/test_aggregator_settings.py::test_keyword_scoring_disabled_by_default` pasa

#### Scenario: `keyword_score` se activa con `ENABLE_KEYWORD_SCORING=true`
- **Given** `ENABLE_KEYWORD_SCORING=true` (env var, parseado por Pydantic)
- **When** se construye la `Settings` y se llama al agregador
- **Then** el ranking aplicado es `keyword_score desc, posted_at desc` (nuevo comportamiento)
- **And** el test `tests/unit/test_aggregator_settings.py::test_keyword_scoring_enabled_via_env_var` pasa

### REQ-CACHE-001: cache key incluye los tokens normalizados de la query

**Statement**: La cache key por fuente MUST incluir los query
tokens normalizados (lowercased, sorted, deduped, punctuation-stripped)
como un nuevo campo `query_tokens: tuple[str, ...] = ()` en el
`JobSearchCacheKey` NamedTuple. Esto permite que queries similares
compartan cache entries. El default `()` preserva el formato v1 para
callers que no pasan query tokens.

**Scenarios**:

#### Scenario: misma query, whitespace distinto, mismo cache key
- **Given** dos llamadas: `("  React ", "Madrid", 20)` y `("react", "Madrid", 20)`
- **When** se computa la cache key
- **Then** ambas llamadas producen la misma cache key (whitespace normalizado)
- **And** la segunda llamada devuelve `cache_status: HIT` (la primera calentó el cache)
- **And** el test `tests/unit/test_in_memory_ttl_cache.py::test_cache_key_includes_normalized_tokens` pasa

#### Scenario: queries distintas producen cache keys distintas
- **Given** dos llamadas: `("react", "Madrid", 20)` y `("python", "Madrid", 20)`
- **When** se computa la cache key
- **Then** las dos llamadas producen cache keys DIFERENTES
- **And** la segunda llamada NO hace hit del cache
- **And** el test `tests/unit/test_in_memory_ttl_cache.py::test_cache_key_distinguishes_queries` pasa

#### Scenario: backward-compat — el `JobSearchCacheKey` con 5 args sigue funcionando
- **Given** un caller posicional existente que construye `JobSearchCacheKey(source, location, limit, geo_id, ...)` con 5 args
- **When** se construye el key
- **Then** el campo `query_tokens` toma el default `()` (tuple vacío)
- **And** los tests existentes en `tests/unit/test_cached_job_search_use_case.py` siguen GREEN
- **And** el test `tests/unit/test_cached_job_search_use_case.py::test_cache_key_default_query_tokens_is_empty` pasa (test nuevo)

#### Scenario: el cache in-memory usa el nuevo key format
- **Given** el `InMemoryTTLCache` recibe dos keys con distinto `query_tokens`
- **When** se hace `get()` con el primer key
- **Then** se devuelve la entry cacheada (HIT)
- **When** se hace `get()` con el segundo key
- **Then** se devuelve `None` (MISS, key no presente)
- **And** el test `tests/unit/test_in_memory_ttl_cache.py::test_cache_separates_entries_by_query_tokens` pasa

### REQ-DEFENSIVE-001: el agregador devuelve resultados parciales ante falla de un source

**Statement**: Si un solo source falla (e.g. Indeed lanza
`IndeedTimeoutError`, o InfoJobs lanza `InfoJobsParseError`), el
agregador MUST continuar con los otros sources y devolver los
resultados parciales. El error del source fallido MUST loguearse a
nivel WARNING con `request_id` y `source=<name>`. El HTTP status code
permanece `200` cuando al menos 1 source devuelve resultados. Si los
3 sources fallan, el status es `502` y el body es `{"jobs":[]}`.

**Scenarios**:

#### Scenario: Indeed falla, LinkedIn + InfoJobs devuelven resultados
- **Given** el agregador llama los 3 sources
- **And** Indeed lanza `IndeedTimeoutError` después de 30s
- **And** LinkedIn devuelve 15 jobs
- **And** InfoJobs devuelve 8 jobs (post-filtro client-side)
- **When** el agregador procesa los resultados
- **Then** la respuesta tiene 23 jobs (LinkedIn + InfoJobs, Indeed excluido)
- **And** el HTTP status es `200`
- **And** un WARNING log se emite con `request_id=<uuid>`, `source="indeed"`, `error_type="IndeedTimeoutError"`
- **And** el test `tests/integration/test_aggregator.py::test_aggregator_returns_partial_results_on_indeed_failure` pasa

#### Scenario: los 3 sources fallan
- **Given** LinkedIn, Indeed e InfoJobs lanzan sus respectivos timeout errors
- **When** el agregador procesa los resultados
- **Then** la respuesta tiene 0 jobs (lista vacía)
- **And** el HTTP status es `502`
- **And** un WARNING log se emite para cada source (3 logs en total)
- **And** el test `tests/integration/test_aggregator.py::test_aggregator_returns_502_when_all_sources_fail` pasa

#### Scenario: 2 sources fallan, 1 devuelve resultados
- **Given** LinkedIn devuelve 10 jobs
- **And** Indeed e InfoJobs ambos lanzan timeout errors
- **When** el agregador procesa los resultados
- **Then** la respuesta tiene 10 jobs
- **And** el HTTP status es `200` (parcial > nada)
- **And** el test `tests/integration/test_aggregator.py::test_aggregator_returns_200_on_partial_results` pasa

#### Scenario: el source fallido se loguea UNA sola vez, no una por job
- **Given** LinkedIn devuelve 25 jobs
- **And** Indeed lanza `IndeedBlockedError` (single failure)
- **When** el agregador procesa los resultados
- **Then** el log de WARNING para `source="indeed"` aparece exactamente 1 vez (no 25 veces)
- **And** el test `tests/integration/test_aggregator.py::test_failed_source_logged_once` pasa

### REQ-TEST-001: cobertura de tests completa de la nueva lógica (Strict TDD)

**Statement**: Todo código nuevo MUST escribirse test-first
(Strict TDD). El desglose mínimo de tests es:

| Componente | Tests mínimos | Cobertura |
|---|---|---|
| `keyword_score` (pura) | 8 unit | 4 escenarios base + 4 edge cases (empty query, empty title, punctuation, Unicode) |
| `filter_infojobs_results` (pura) | 6 unit | 4 escenarios base + 2 edge cases (empty list, all-match) |
| `LinkedInPlaywrightScraper` `geoId` plumbing | 4 unit | 4 escenarios de REQ-LOC-001 |
| `app_factory` wiring del resolver | 2 integration | ambos escenarios de REQ-LOC-002 |
| `Cache` key con `query_tokens` | 4 unit | 3 escenarios de REQ-CACHE-001 + 1 integration con `CachedJobSearchUseCase` |
| Aggregator defensive partial results | 4 integration | 3 escenarios de REQ-DEFENSIVE-001 + 1 edge case (source raises mid-aggregation) |
| `ENABLE_KEYWORD_SCORING` env var | 2 tests | default false + env var true |

**Total mínimo**: ~30 tests nuevos, todos GREEN antes de mergear.

**Scenarios**:

#### Scenario: suite completa de `keyword_score` cubre los 4 escenarios base
- **Given** los 4 tests en `tests/unit/test_keyword_score.py` (`test_title_match_returns_1`, `test_partial_match_returns_proportional`, `test_description_only_match_is_less_than_title`, `test_no_match_returns_0`)
- **When** se ejecuta `cd backend && uv run pytest tests/unit/test_keyword_score.py -v`
- **Then** los 4 tests pasan

#### Scenario: suite de `filter_infojobs_results` cubre los 4 escenarios base
- **Given** los 4 tests en `tests/unit/test_aggregator.py` (`test_infojobs_filter_discards_zero_token_title`, `test_infojobs_filter_keeps_partial_token_match`, `test_infojobs_filter_does_not_affect_linkedin_indeed`, `test_filter_infojobs_results_is_pure`)
- **When** se ejecuta `cd backend && uv run pytest tests/unit/test_aggregator.py -v`
- **Then** los 4 tests pasan

#### Scenario: suite de `LinkedInPlaywrightScraper` cubre los 4 escenarios de geoId
- **Given** los 4 tests en `tests/unit/test_linkedin_scraper.py` (4 escenarios de REQ-LOC-001)
- **When** se ejecuta `cd backend && uv run pytest tests/unit/test_linkedin_scraper.py -v`
- **Then** los 4 tests pasan

#### Scenario: suite de cache key cubre los 3 escenarios de query tokens
- **Given** los 3 tests en `tests/unit/test_in_memory_ttl_cache.py` (3 escenarios de REQ-CACHE-001)
- **When** se ejecuta `cd backend && uv run pytest tests/unit/test_in_memory_ttl_cache.py -v`
- **Then** los 3 tests pasan

#### Scenario: suite de aggregator defensive cubre los 3 escenarios parciales
- **Given** los 3 tests en `tests/integration/test_aggregator.py` (3 escenarios de REQ-DEFENSIVE-001)
- **When** se ejecuta `cd backend && uv run pytest tests/integration/test_aggregator.py -v`
- **Then** los 3 tests pasan

#### Scenario: ningún test existente se rompe (regression check)
- **Given** el suite completo del backend (1036+ tests previos)
- **When** se ejecuta `cd backend && uv run pytest -v` después del cambio
- **Then** los 1036+ tests previos siguen GREEN + los 30 nuevos tests pasan

## Out of scope

- Agregar un 4° source (e.g. Glassdoor) — cambio separado.
- Cambiar la forma de la respuesta HTTP — el frontend ya consume la forma canónica.
- Cambiar el comportamiento del LLM filter — el chat filter es un capability separado.
- Construir un modelo ML de ranking — el `keyword_score` heurístico es suficiente para v1.
- Stemming / lemmatization en `keyword_score` — futuro trabajo (REQ-NOT-Q3-A del proposal).
- Manual ranking overrides (admin UI para boostear ciertas empresas) — no necesario en v1.
- Aplicar el filtro client-side a LinkedIn/Indeed — solo InfoJobs en v1 (LinkedIn ya tiene `geoId` y Indeed ya devuelve resultados relevantes).
- `geoId` resolution para un 4° source — out of scope, solo LinkedIn en v1.
- Caching del cálculo de `keyword_score` por job — micro-optimización, no necesario en v1.
- Cambiar el signature del `HardcodedLocationResolver` a async — el resolver ya es sync y es lo que se quiere en v1.

## Open questions

**None** — todas las decisiones se resolvieron en la fase `sdd-propose` + las 3 Open Questions del proposal confirmadas por el orchestrator en el launch prompt.

Decisiones confirmadas:

1. `keyword_score` ranking es opt-in via `ENABLE_KEYWORD_SCORING=true` (default `false` preserva `posted_at desc` v1).
2. Filtro client-side aplica SOLO a InfoJobs.
3. NO stemming en `keyword_score` (match exacto de tokens).
4. `geoId` plumb para LinkedIn es always-active (no opt-in).
5. Cache key MUST incluir query tokens (breaking change, no-issue in-memory).
6. NO API shape change.
7. Forecast ~1000-1500 LOC.

## Acceptance criteria

- [ ] Todos los escenarios `REQ-*` están cubiertos por tests que pasan.
- [ ] `cd backend && uv run pytest -v` muestra los nuevos tests GREEN.
- [ ] La suite completa del backend (1036+ tests previos) sigue GREEN — 0 regresiones.
- [ ] `cd backend && uv run mypy` clean (sin nuevos errores `strict`).
- [ ] `cd backend && uv run ruff check && cd backend && uv run ruff format --check` clean.
- [ ] Smoke test manual: `curl "http://localhost:8000/jobs?q=react&location=malaga&limit=20"` devuelve MÁS resultados relevantes que el comportamiento actual (LinkedIn devuelve Málaga/España, no Washington; InfoJobs descarta 0-token-title).
- [ ] v1 backward-compat: los tests existentes de `/jobs` pasan sin modificación (REQ-LOC-001 scenario 4: legacy wiring sin resolver sigue funcionando).
- [ ] Cache hit rate (observado en dev con queries repetidas) es MAYOR que el comportamiento actual (REQ-CACHE-001).
- [ ] Los 4 quality gates pasan: `uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest`.
- [ ] `sdd-verify` PASS con 0 critical findings.
