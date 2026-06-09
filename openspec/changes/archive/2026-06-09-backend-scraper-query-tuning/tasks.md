# Tasks: backend-scraper-query-tuning

> **Cambio**: `backend-scraper-query-tuning` • **Modo**: `both` (OpenSpec + Engram) • **Strict TDD**: ACTIVE
> **Fecha**: 2026-06-10 • **Status**: `tasked` (listo para `sdd-apply`)
> **Fuentes**: [proposal #322](../proposal.md), [spec #323](../specs/backend-scraper-query-tuning/spec.md), [design #324](design.md).
> **Idioma**: español para prosa; inglés para código, paths, identificadores, mensajes de commit.

## Work unit overview

Este cambio se entrega en **10 work units** con patrón **strict TDD (RED → GREEN → TRIANGULATE → REFACTOR)** por task. T-001 es un **bugfix pre-existente** descubierto en el design: el scraper de LinkedIn tiene `geo_id` en la firma de `_make_fetch_one_page` pero NUNCA lo pasa al closure desde `search()` (línea 231 de `backend/src/jobs_finder/infrastructure/linkedin/scraper.py`), por lo que el `geoId=` URL param añadido por `fix-linkedin-geoid` nunca llegó a producción. T-001 corrige ese bug + inyecta el resolver en el settings dataclass. T-002 y T-003 son **funciones puras independientes** (test-first). T-004 las compone en el aggregator. T-005 añade lógica defensiva de partial results. T-006 amplía la cache key. T-007 cablea el resolver en el composition root. T-008 introduce el env var opt-in. T-009 forwardea los 3 kwargs nuevos por la ruta. T-010 cierra con docs. **Total forecast: ~1340 LOC, single PR**.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1340 (rango 1000-1500) |
| 400-line budget risk | Low |
| 5000-line review budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR (~134 LOC avg/commit) |
| Delivery strategy | ask-always → single-pr (pre-confirmado) |
| Chain strategy | single-pr (1340 < 5000) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: single-pr
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | PR | Base branch |
|------|------|----|----|
| T-001 | Fix bug `geo_id` no-forward + inyectar resolver | PR 1 (commit 1) | main |
| T-002 | `keyword_score` pura + 8 tests | PR 1 (commit 2) | commit 1 |
| T-003 | `filter_infojobs_results` pura + 6 tests | PR 1 (commit 3) | commit 2 |
| T-004 | Aggregator integra filter + sort opt-in | PR 1 (commit 4) | commit 3 |
| T-005 | Aggregator defensivo (partial + 502) | PR 1 (commit 5) | commit 4 |
| T-006 | Cache key incluye `query_tokens` | PR 1 (commit 6) | commit 5 |
| T-007 | `app_factory` cablea resolver | PR 1 (commit 7) | commit 6 |
| T-008 | `ENABLE_KEYWORD_SCORING` env var | PR 1 (commit 8) | commit 7 |
| T-009 | Route forwardea 3 kwargs nuevos | PR 1 (commit 9) | commit 8 |
| T-010 | README + `.env.example` docs | PR 1 (commit 10) | commit 9 |

---

## Phase 0: Safety net (pre-T-001, obligatorio)

- [ ] 0.1 `cd backend && uv run pytest -q 2>&1 | tail -5` → guardar baseline "{N} tests passing"
- [ ] 0.2 Si hay fallos pre-existentes → STOP, reportar a orchestrator (NO fixear)
- [ ] 0.3 `cd backend && uv run mypy` + `cd backend && uv run ruff check` clean como baseline

---

## Phase 1: Bugfix foundation (T-001)

### T-001: Fix pre-existing `geo_id` kwarg bug + inyectar `location_resolver` en `LinkedInScraperSettings`

**Type**: bugfix + feature • **Layer**: Unit (existing files) • **Strict TDD**: ✅ • **Spec coverage**: REQ-LOC-001 (esc 1, 2, 4, 5), REQ-LOC-002 (esc 1, 2, 3)

- [ ] 1.0 Safety net: `cd backend && uv run pytest tests/unit/test_linkedin_scraper.py tests/unit/test_linkedin_settings.py -q` → baseline
- [ ] 1.1 RED: escribir 4 tests en `backend/tests/unit/test_linkedin_scraper.py` (con un `FakeLocationResolver` local): `test_search_uses_geoId_when_resolver_returns_int` (URL contiene `geoId=104401670`, NO `location=malaga`); `test_search_uses_location_when_resolver_returns_None` (URL con `location=Remote`); `test_search_uses_location_when_resolver_is_None` (scraper sin resolver → `location=malaga`); `test_resolver_called_once_per_search_not_per_page` (contador == 1 con `max_pages=3`)
- [ ] 1.2 RED: escribir 2 tests en `backend/tests/unit/test_linkedin_settings.py`: `test_settings_optional_resolver_defaults_to_None`; `test_settings_equality_includes_resolver`
- [ ] 1.3 Confirmar RED: `cd backend && uv run pytest tests/unit/test_linkedin_scraper.py -k geoId_or_resolver -v` → 6 FAIL
- [ ] 1.4 GREEN: en `backend/src/jobs_finder/infrastructure/linkedin/scraper.py:118` agregar `"location_resolver"` a `__slots__`
- [ ] 1.5 GREEN: agregar `location_resolver: LocationResolverPort | None = None` keyword-only al `__init__` de `LinkedInScraperSettings`; asignar `self.location_resolver = location_resolver`
- [ ] 1.6 GREEN: extender `__eq__` y `__hash__` para incluir `location_resolver`; agregar import de `LocationResolverPort`
- [ ] 1.7 GREEN: en `search()` (línea ~193-236), antes de `paginated_search(...)`, si `geo_id is None and self._settings.location_resolver is not None`, llamar `geo_id = self._settings.location_resolver.resolve(location)` UNA sola vez
- [ ] 1.8 GREEN (el fix): en línea 231, cambiar `fetch_one_page=self._make_fetch_one_page(keywords, location)` a `fetch_one_page=self._make_fetch_one_page(keywords, location, geo_id=geo_id)`
- [ ] 1.9 Confirmar GREEN: 6/6 PASS + tests pre-existentes GREEN
- [ ] 1.10 TRIANGULATE: el test 1.1.4 ya cubre 3 páginas; verificar que el contador es 1
- [ ] 1.11 REFACTOR: `cd backend && uv run ruff check src/ && cd backend && uv run ruff format --check src/ && cd backend && uv run mypy` → clean
- [ ] 1.12 Commit: `fix(linkedin): forward geo_id through pagination loop and inject location_resolver`

**Acceptance**: 6 tests nuevos GREEN; tests pre-existentes en `test_linkedin_scraper.py` y `test_linkedin_settings.py` siguen GREEN; mypy + ruff clean.

---

## Phase 2: Funciones puras (T-002, T-003)

### T-002: `keyword_score` puro + 8 tests

**Type**: feature • **Layer**: Unit (new file) • **Strict TDD**: ✅ • **Spec coverage**: REQ-SCORE-001 (esc 1-4), REQ-TEST-001 (8 tests)

- [ ] 2.0 Safety net: N/A (archivos nuevos)
- [ ] 2.1 RED: crear `backend/tests/unit/test_keyword_score.py` con 8 tests que importan `from jobs_finder.infrastructure.keyword_score import keyword_score`:
  - `test_title_match_returns_1` — query=["react"], title="React Developer" → 1.0
  - `test_partial_match_returns_proportional` — query=["python","react"], title="Senior Python Developer" → 0.5
  - `test_description_only_match_is_less_than_title` — query=["react"], title="Software Engineer", desc="Looking for React dev" → 0 < r < 1
  - `test_no_match_returns_0` — query=["react"], title="Recepcionista" → 0.0
  - `test_empty_query_returns_0` — query=[], title="React" → 0.0
  - `test_empty_title_returns_0_for_title_component` — query=["react"], title="" → solo desc
  - `test_unicode_preserves_accents` — query=["málaga"] matches "Ingeniero Málaga", NOT "Ingeniero Malaga"
  - `test_punctuation_and_whitespace_tokenize` — "  React, TypeScript!  " → {"react","typescript"}
- [ ] 2.2 Confirmar RED: `cd backend && uv run pytest tests/unit/test_keyword_score.py -v` → 8 ImportError
- [ ] 2.3 GREEN: crear `backend/src/jobs_finder/infrastructure/keyword_score.py` con `keyword_score(job: Job, query_tokens: set[str]) -> float`:
  - `if not query_tokens: return 0.0`
  - `title_rate = |tokenize(job.title) ∩ query_tokens| / |query_tokens|`
  - `desc_rate = |tokenize(job.description or "") ∩ query_tokens| / |query_tokens|`
  - Return `min(title_rate * 0.6 + desc_rate * 0.4, 1.0)`
- [ ] 2.4 Confirmar GREEN: 8/8 PASS
- [ ] 2.5 TRIANGULATE: tests 2.1 ya cubren 4 base + 4 edge
- [ ] 2.6 REFACTOR: si T-003 está hecho, importar `tokenize` de `aggregator_filters`; sino, inline temporal
- [ ] 2.7 `cd backend && uv run ruff check src/ && cd backend && uv run mypy` → clean
- [ ] 2.8 Commit: `feat(aggregator): add keyword_score pure function for opt-in relevance ranking`

**Acceptance**: 8 tests GREEN; función pura; retorna float en [0.0, 1.0]; Unicode-safe.

### T-003: `filter_infojobs_results` + `tokenize` helper + 6 tests

**Type**: feature • **Layer**: Unit (new file) • **Strict TDD**: ✅ • **Spec coverage**: REQ-FILTER-001 (esc 1-6), REQ-TEST-001 (6 tests)

- [ ] 3.0 Safety net: N/A (archivos nuevos)
- [ ] 3.1 RED: crear `backend/tests/unit/test_aggregator_filters.py` con 6 tests:
  - `test_filter_discards_zero_token_title` — query={"react","málaga"}, jobs=[Job(title="Recepcionista")] → []
  - `test_filter_keeps_partial_token_match` — query={"react"}, jobs=[Job(title="Desarrollador React")] → [job]
  - `test_filter_does_not_mutation_input` — input list identidad distinta al output
  - `test_filter_is_pure_same_input_same_output` — 100x llamada → output idéntico
  - `test_tokenize_normalizes_whitespace_and_punct` — "  React, TypeScript  " → {"react","typescript"}
  - `test_tokenize_unicode_preserves_accents` — "Málaga" → {"málaga"}; sin tilde NO matchea
- [ ] 3.2 Confirmar RED: 6 ImportError
- [ ] 3.3 GREEN: crear `backend/src/jobs_finder/infrastructure/aggregator_filters.py` con:
  - `tokenize(text: str) -> set[str]`: `text.casefold() → re.split(r'[\s\W_]+', ...) → filter(strip+non-empty) → set(...)` (sin `.normalize()`, NFC preservado)
  - `filter_infojobs_results(jobs: list[Job], query_tokens: set[str]) -> list[Job]`: `if not query_tokens: return list(jobs); return [j for j in jobs if tokenize(j.title) & query_tokens]`
- [ ] 3.4 Confirmar GREEN: 6/6 PASS
- [ ] 3.5 TRIANGULATE: tests 3.1 ya cubren 4 base + 2 edge
- [ ] 3.6 REFACTOR: `cd backend && uv run ruff check src/ && cd backend && uv run mypy` → clean
- [ ] 3.7 Commit: `feat(aggregator): add filter_infojobs_results and tokenize helpers`

**Acceptance**: 6 tests GREEN; `tokenize` Unicode-safe; `filter_infojobs_results` pura.

---

## Phase 3: Composición en el aggregator (T-004, T-005)

### T-004: Aggregator integra filter + sort opt-in

**Type**: feature • **Layer**: Unit (extend existing) • **Strict TDD**: ✅ • **Spec coverage**: REQ-FILTER-001 (aplicado), REQ-SCORE-001 (dispatch)

- [ ] 4.0 Safety net: `cd backend && uv run pytest tests/unit/test_aggregator.py -q` → baseline
- [ ] 4.1 RED: agregar 5 tests a `backend/tests/unit/test_aggregator.py`:
  - `test_aggregator_applies_infojobs_filter` — 1 InfoJobs 0-overlap + 1 LinkedIn → solo LinkedIn
  - `test_aggregator_does_not_filter_linkedin_or_indeed` — solo InfoJobs recibe el filtro
  - `test_aggregator_sorts_by_keyword_score_when_enabled` — score_A > score_B, `enable_keyword_scoring=True` → A primero
  - `test_aggregator_sorts_by_posted_at_when_disabled` — `enable_keyword_scoring=False` → sort por posted_at desc (existing)
  - `test_aggregator_forwards_query_tokens_to_filter` — asserta que el filtro recibe los tokens correctos
- [ ] 4.2 Confirmar RED: `cd backend && uv run pytest tests/unit/test_aggregator.py -k "filter or keyword_score" -v` → 5 FAIL
- [ ] 4.3 GREEN: en `backend/src/jobs_finder/application/aggregator.py`, agregar kwargs keyword-only a `search()`: `query_tokens: frozenset[str] = frozenset()` y `enable_keyword_scoring: bool = False`
- [ ] 4.4 GREEN: después del dedup, filtrar InfoJobs: `if query_tokens: jobs = filter_infojobs_results([j for j in jobs if j.source=="infojobs"], query_tokens) + [j for j in jobs if j.source!="infojobs"]` (o equivalente que solo filtre InfoJobs)
- [ ] 4.5 GREEN: dispatch de sort: `if enable_keyword_scoring: jobs = sorted(jobs, key=lambda j: (keyword_score(j, query_tokens), j.posted_at), reverse=True)` else: `rank_jobs(...)` (existing)
- [ ] 4.6 Confirmar GREEN: 5/5 PASS + tests pre-existentes GREEN
- [ ] 4.7 TRIANGULATE: con `query_tokens=set()` (default) NO se filtra nada (backward-compat)
- [ ] 4.8 REFACTOR: `cd backend && uv run ruff check src/ && cd backend && uv run mypy` → clean
- [ ] 4.9 Commit: `feat(aggregator): integrate infojobs filter and opt-in keyword_score sort`

**Acceptance**: 5 tests nuevos GREEN; tests pre-existentes GREEN; filtro SOLO InfoJobs; sort opt-in.

### T-005: Aggregator defensivo (partial + 502 + WARNING logs)

**Type**: feature • **Layer**: Integration (new test file) • **Strict TDD**: ✅ • **Spec coverage**: REQ-DEFENSIVE-001 (esc 1-4)

- [ ] 5.0 Safety net: `cd backend && uv run pytest tests/integration/test_aggregator.py -q` → baseline
- [ ] 5.1 RED: crear `backend/tests/integration/test_aggregator_defensive.py` con 3 tests:
  - `test_aggregator_returns_partial_results_on_indeed_failure` — 1 fail + 2 succeed → 200 + jobs parciales
  - `test_aggregator_returns_502_when_all_sources_fail` — 3 fails → 502
  - `test_aggregator_returns_200_on_partial_2_fail_1_succeed` — 1 succeed + 2 fail → 200
- [ ] 5.2 RED: agregar 1 test a `backend/tests/unit/test_exceptions.py`: `AllSourcesFailedError` hereda de `JobSearchError`
- [ ] 5.3 Confirmar RED: 4 FAIL
- [ ] 5.4 GREEN: en `backend/src/jobs_finder/domain/exceptions.py`, agregar `class AllSourcesFailedError(JobSearchError): """Mapped to HTTP 502."""`
- [ ] 5.5 GREEN: en `backend/src/jobs_finder/application/aggregator.py`, agregar `import logging; _logger = logging.getLogger(__name__)` y un `ContextVar` para `request_id` (`_SOURCE_REQUEST_ID`)
- [ ] 5.6 GREEN: en el `_call_one` actual, en el `except JobSearchError`, agregar `_logger.warning("source failed", extra={"request_id": _SOURCE_REQUEST_ID.get(""), "source": source, "error_type": type(exc).__name__})` (el bloque `try/except` ya existe; solo agregar el log)
- [ ] 5.7 GREEN: después del `asyncio.gather`, contar successes; si `success_count == 0`: raise `AllSourcesFailedError("all sources failed")`
- [ ] 5.8 GREEN: en `backend/src/jobs_finder/presentation/exception_handlers.py`, verificar que el handler de `JobSearchError` mapea a 502 (ya debería; si no, agregar mapping)
- [ ] 5.9 Confirmar GREEN: 4/4 PASS
- [ ] 5.10 TRIANGULATE: agregar test `test_failed_source_logged_once` — WARNING aparece 1 vez, no N veces por job
- [ ] 5.11 REFACTOR: `cd backend && uv run ruff check src/ && cd backend && uv run mypy` → clean
- [ ] 5.12 Commit: `feat(aggregator): add defensive partial-results handling with AllSourcesFailedError`

**Acceptance**: 4 tests nuevos GREEN (3 integration + 1 unit); partial → 200; all-fail → 502; WARNING logs con `request_id` + `source` + `error_type`.

---

## Phase 4: Cache + settings + wiring (T-006, T-007, T-008, T-009)

### T-006: Cache key incluye `query_tokens`

**Type**: feature • **Layer**: Unit (extend existing) • **Strict TDD**: ✅ • **Spec coverage**: REQ-CACHE-001 (4 escenarios)

- [ ] 6.0 Safety net: `cd backend && uv run pytest tests/unit/test_cached_job_search_use_case.py tests/unit/test_in_memory_ttl_cache.py -q` → baseline
- [ ] 6.1 RED: agregar 4 tests a `backend/tests/unit/test_cached_job_search_use_case.py`:
  - `test_cache_key_default_query_tokens_is_empty` — `JobSearchCacheKey("linkedin", "react", "malaga", 20)` 4 args → `query_tokens == ()`
  - `test_cache_key_includes_normalized_tokens` — misma query con distinto whitespace → mismo key
  - `test_cache_key_distinguishes_queries` — `("react",...)` vs `("python",...)` → keys distintos
  - `test_cache_separates_entries_by_query_tokens` — 2 keys distintos → segundo MISS
- [ ] 6.2 Confirmar RED: 4 FAIL
- [ ] 6.3 GREEN: en `backend/src/jobs_finder/application/ports.py`, agregar 6º campo a `JobSearchCacheKey` (NamedTuple): `query_tokens: tuple[str, ...] = ()`
- [ ] 6.4 GREEN: en `backend/src/jobs_finder/application/usecases/_cached_search.py`, agregar kwarg `query_tokens: tuple[str, ...] = ()` a `search()`; pasar `query_tokens=tuple(sorted(query_tokens))` al constructor de key; forward al `port.search(...)`
- [ ] 6.5 Confirmar GREEN: 4/4 PASS + tests pre-existentes GREEN (backward-compat)
- [ ] 6.6 TRIANGULATE: HIT preservado cuando se pasa el MISMO `query_tokens` (sorted tuple)
- [ ] 6.7 REFACTOR: `cd backend && uv run ruff check src/ && cd backend && uv run mypy` → clean
- [ ] 6.8 Commit: `feat(cache): include query_tokens in JobSearchCacheKey for better hit rate`

**Acceptance**: 4 tests nuevos GREEN; backward-compat preservado; tokens normalizados (lowercased, sorted, deduped, punct-stripped).

### T-007: `app_factory` cablea `HardcodedLocationResolver`

**Type**: feature • **Layer**: Integration (extend existing) • **Strict TDD**: ✅ • **Spec coverage**: REQ-LOC-002 (esc 1, 3)

- [ ] 7.0 Safety net: `cd backend && uv run pytest tests/integration/test_composition.py -q` → baseline
- [ ] 7.1 RED: agregar 2 tests a `backend/tests/integration/test_composition.py`:
  - `test_linkedin_scraper_has_resolver` — `app_factory.build_app()` → LinkedIn scraper tiene `location_resolver` no-`None`
  - `test_resolver_built_when_chat_disabled` — `chat_enabled=False, linkedin_enabled=True` → scraper tiene resolver
- [ ] 7.2 Confirmar RED: 2 FAIL
- [ ] 7.3 GREEN: en `backend/src/jobs_finder/presentation/app_factory.py`, agregar al inicio de `build_app()` (antes de `if use_case is None`): `location_resolver = HardcodedLocationResolver()`
- [ ] 7.4 GREEN: pasar `location_resolver=location_resolver` al `LinkedInScraperSettings(...)` (lugar exacto ~línea 229, verificar leyendo el archivo)
- [ ] 7.5 Confirmar GREEN: 2/2 PASS + tests pre-existentes GREEN
- [ ] 7.6 TRIANGULATE: legacy wiring (sin resolver) sigue funcionando sin deprecation warning (per design deviation #4)
- [ ] 7.7 REFACTOR: `cd backend && uv run ruff check src/ && cd backend && uv run mypy` → clean
- [ ] 7.8 Commit: `feat(app_factory): inject HardcodedLocationResolver into LinkedInScraperSettings`

**Acceptance**: 2 tests nuevos GREEN; `app_factory.build_app()` produce app con LinkedIn scraper que tiene resolver; legacy wiring sin warning.

### T-008: `ENABLE_KEYWORD_SCORING` env var

**Type**: feature • **Layer**: Unit (extend existing) • **Strict TDD**: ✅ • **Spec coverage**: REQ-SCORE-001 (esc 5, 6)

- [ ] 8.0 Safety net: `cd backend && uv run pytest tests/unit/test_aggregator_settings.py -q` → baseline
- [ ] 8.1 RED: agregar 2 tests a `backend/tests/unit/test_aggregator_settings.py`:
  - `test_keyword_scoring_disabled_by_default` — `Settings()` sin env var → `enable_keyword_scoring is False`
  - `test_keyword_scoring_enabled_via_env_var` — `os.environ["ENABLE_KEYWORD_SCORING"]="true"; Settings()` → `is True`
- [ ] 8.2 Confirmar RED: 2 FAIL
- [ ] 8.3 GREEN: en `backend/src/jobs_finder/infrastructure/config.py`, agregar `enable_keyword_scoring: bool = False` con `validation_alias=AliasChoices("ENABLE_KEYWORD_SCORING", "enable_keyword_scoring")`
- [ ] 8.4 GREEN: en `backend/src/jobs_finder/presentation/app_factory.py`, forwardar `enable_keyword_scoring=effective_settings.enable_keyword_scoring` al `SearchAllSourcesUseCase(...)`
- [ ] 8.5 Confirmar GREEN: 2/2 PASS + tests pre-existentes GREEN
- [ ] 8.6 TRIANGULATE: verificar que `AGGREGATOR_RANKING_STRATEGY` y `AGGREGATOR_PRIORITY_MAP` (env vars existentes) NO se ven afectados
- [ ] 8.7 REFACTOR: `cd backend && uv run ruff check src/ && cd backend && uv run mypy` → clean
- [ ] 8.8 Commit: `feat(config): add ENABLE_KEYWORD_SCORING env var for opt-in relevance ranking`

**Acceptance**: 2 tests nuevos GREEN; default = `False`; env var override funciona; env vars existentes NO se tocan.

### T-009: Route forwardea `query_tokens` + `enable_keyword_scoring` + `linkedin_geo_id`

**Type**: feature • **Layer**: Integration (extend existing) • **Strict TDD**: ✅ • **Spec coverage**: REQ-LOC-001, REQ-FILTER-001, REQ-CACHE-001, REQ-SCORE-001 (todos enrutados)

- [ ] 9.0 Safety net: `cd backend && uv run pytest tests/integration/test_aggregator_api.py -q` → baseline
- [ ] 9.1 RED: agregar 3 tests a `backend/tests/integration/test_aggregator_api.py`:
  - `test_aggregator_api_passes_query_tokens_to_use_case` — `GET /jobs?q=react&location=malaga` → use case recibe `query_tokens` con `{"react"}`
  - `test_aggregator_api_passes_enable_keyword_scoring_from_settings` — con `ENABLE_KEYWORD_SCORING=true` → use case recibe `enable_keyword_scoring=True`
  - `test_aggregator_api_resolves_linkedin_geo_id_from_resolver` — `GET /jobs?q=react&location=malaga` → LinkedIn use case recibe `linkedin_geo_id=104401670`
- [ ] 9.2 Confirmar RED: 3 FAIL
- [ ] 9.3 GREEN: en `backend/src/jobs_finder/presentation/routes/aggregator.py`, agregar import `from jobs_finder.infrastructure.aggregator_filters import tokenize`
- [ ] 9.4 GREEN: antes del `use_case.search(...)`, agregar `query_tokens = tokenize(query.q)` y `linkedin_geo_id = request.app.state.location_resolver.resolve(query.location)` (o `None`)
- [ ] 9.5 GREEN: setear el ContextVar `_SOURCE_REQUEST_ID.set(request.state.request_id)` (requiere definir el ContextVar en `application/aggregator.py` o módulo neutral)
- [ ] 9.6 GREEN: forwardar los 3 kwargs: `query_tokens=query_tokens, enable_keyword_scoring=request.app.state.settings.enable_keyword_scoring, linkedin_geo_id=linkedin_geo_id`
- [ ] 9.7 Confirmar GREEN: 3/3 PASS + tests pre-existentes GREEN
- [ ] 9.8 TRIANGULATE: query vacía (`q=""`) → `query_tokens=set()` y aggregator NO filtra
- [ ] 9.9 REFACTOR: `cd backend && uv run ruff check src/ && cd backend && uv run mypy` → clean
- [ ] 9.10 Commit: `feat(aggregator_route): forward query_tokens, enable_keyword_scoring, and linkedin_geo_id to use case`

**Acceptance**: 3 tests nuevos GREEN; HTTP response shape NO cambia; `X-Cache` y `X-Aggregator-Errors` headers siguen funcionando.

---

## Phase 5: Documentación (T-010)

### T-010: README + `.env.example` docs

**Type**: docs • **Layer**: N/A • **Strict TDD**: ➖ N/A

- [ ] 10.1 En `backend/.env.example`, agregar: `# ENABLE_KEYWORD_SCORING=false  # opt-in keyword relevance ranking (per-query score, sorts by score desc then posted_at desc)`
- [ ] 10.2 En `backend/README.md`, agregar en "Caching" section: 1 párrafo sobre el nuevo campo `query_tokens` en `JobSearchCacheKey`
- [ ] 10.3 En `backend/README.md`, agregar en "LinkedIn pagination" section: nota sobre que `geoId` se plumb cuando el resolver conoce la location (con link a `HardcodedLocationResolver._CANONICAL_MAPPING`)
- [ ] 10.4 En `backend/README.md`, agregar nueva sección "InfoJobs client-side filter" (~5 líneas)
- [ ] 10.5 En `backend/README.md`, agregar nueva sección "Defensive partial results" (~5 líneas)
- [ ] 10.6 En `backend/README.md`, agregar al final de "Ranking" section: `ENABLE_KEYWORD_SCORING=true` opt-in + descripción de la fórmula
- [ ] 10.7 Sanity: `cd backend && uv run pytest -q` sigue 100% GREEN
- [ ] 10.8 Commit: `docs(backend): document ENABLE_KEYWORD_SCORING, geoId plumb, InfoJobs filter, defensive partial results`

**Acceptance**: README cubre los 4 cambios visibles al usuario; `.env.example` documenta el nuevo var; sin cambios a código de producción.

---

## Pre-apply checklist

- [x] 10 work units con acceptance criteria claros
- [x] Orden de dependencias documentado (T-001 primero, T-010 último)
- [x] Single PR recomendado (1340 LOC < 5000 budget)
- [x] No code changes fuera de `backend/`
- [x] `backend/.env.example` actualizado (T-010.1)
- [x] `backend/README.md` actualizado (T-010.2-6)
- [x] Strict TDD discipline por task (per `_shared/strict-tdd.md`)
- [x] Pre-existing bug (geoId kwarg) en T-001 con RED test primero

## Work unit ordering (resumido)

```
T-001 (bugfix geoId + resolver injection)
  ↓
T-002 (keyword_score puro)        T-003 (filter_infojobs_results puro)
  ↓                                   ↓
  └──────── T-004 (aggregator los integra) ────────┐
                            ↓                        │
                       T-005 (defensivo)             │
                            ↓                        │
                       T-006 (cache key) ──────┐     │
                            ↓                   │     │
                       T-007 (app_factory)     │     │
                            ↓                   │     │
                       T-008 (env var)         │     │
                            ↓                   │     │
                       T-009 (route plumb) ────┴─────┘
                            ↓
                       T-010 (docs)
```

- **T-001** primero: sienta las bases (resolver injection + bug fix).
- **T-002 + T-003** independientes: funciones puras, `sdd-apply` puede ejecutar en cualquier orden.
- **T-004** depende de T-002 + T-003.
- **T-005** toca el mismo archivo que T-004 (`aggregator.py`) — si se ejecutan en paralelo, rebase al final.
- **T-006** depende de T-009 (la ruta pasa `query_tokens` al use case antes de computar la key).
- **T-007** depende de T-001 (resolver ya inyectado en settings).
- **T-008** independiente.
- **T-009** depende de T-006 + T-008.
- **T-010** último.

## Result contract

- `status`: `ok`
- `executive_summary`: 10 work units (incluyendo el bugfix pre-existente del `geo_id` kwarg en LinkedIn scraper) con orden estricto y strict TDD per-task. Forecast ~1340 LOC, single PR, < 5000 budget.
- `artifacts`: `openspec/changes/backend-scraper-query-tuning/tasks.md` + Engram `sdd/backend-scraper-query-tuning/tasks`
- `next_recommended`: `sdd-apply`
- `risks`: T-001 es bugfix pre-existente — el RED test debe escribirse ANTES de tocar la línea 231; el `FakeLocationResolver` local debe existir para el test. Mitigación: T-001 va primero.
- `skill_resolution`: `paths-injected` (orchestrator pre-injectó `_shared`, `sdd-apply/strict-tdd.md`, `work-unit-commits`)
- `task_count`: 10
- `loc_forecast`: 1340
- `pr_recommendation`: `single-pr`
