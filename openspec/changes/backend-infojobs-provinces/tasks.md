# Tasks: backend-infojobs-provinces

> **Status**: `tasks` (ready for `sdd-apply`) • **Mode**: `both` (OpenSpec + Engram) • **Strict TDD**: ACTIVE
> **Base**: `f41aa90` • **Baseline**: 1,142 passed / 13 skipped
> **Spec**: obs #334 • **Design**: obs #337 • **Forecast**: ~795 LOC • **PR**: single-pr

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~795 (range 750–1100) |
| 400-line budget risk | Low (~159 LOC/commit avg, 5 commits) |
| Chained PRs recommended | No |
| Suggested split | single PR (5 conventional commits) |
| Delivery strategy | ask-always |
| Chain strategy | size:exception (single PR) |
| Decision needed before apply | No (single PR approved at proposal) |
| Chained PRs recommended | No |
| Chain strategy | size:exception |
| 400-line budget risk | Low |

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| T-001 | Protocol + resolver + 9-entry mapping | PR 1 commit 1 | Foundation: dependencia de T-002 |
| T-002 | Scraper URL plumb + settings field | PR 1 commit 2 | Depends on T-001 |
| T-003 | Composition root wire + L607 bonus fix | PR 1 commit 3 | Depends on T-002 |
| T-004 | Docstring + README | PR 1 commit 4 | Docs only, independiente |
| T-005 | LIVE test gated + final verification | PR 1 commit 5 | Cierra el PR, valida speculative IDs |

## Resumen ejecutivo (work unit slicing)

El trabajo se parte en 5 work units secuenciales que respeta la disciplina **strict TDD** (RED → GREEN → refactor → full suite → mypy/ruff). Cada unit termina con un commit convencional. El forecast total es **~795 LOC** distribuidos en 5 commits (~159 LOC/commit promedio), bien dentro del budget de 400 líneas y del budget de review de 5000 líneas. La cadena de dependencias es estricta: T-001 (foundation) → T-002 (scraper usa resolver) → T-003 (composition wire) → T-004 (docs) → T-005 (live validation). El bug de shadowing de `app_factory.py:607` se corrige como bonus dentro de T-003 para garantizar que el test `test_resolver_shared_between_linkedin_and_infojobs` use `is` (mismo objeto) y no `==` (igual valor) — esto es REQ-PROV-004.

## Work units

### T-001: `LocationResolverPort` extendido con `resolve_infojobs` + `HardcodedLocationResolver` + 9-entry mapping

**Type**: feature + test-first
**Scope**:
- **RED tests first** en `backend/tests/unit/test_hardcoded_location_resolver.py`:
  - `test_resolve_infojobs_malaga_canonical`: `"malaga"` → `(34, 17)`
  - `test_resolve_infojobs_malaga_with_tilde`: `"Málaga"` → `(34, 17)` (NFD decompose + strip accents)
  - `test_resolve_infojobs_malaga_nfd_decomposed`: precomposed tilde → `(34, 17)`
  - `test_resolve_infojobs_madrid_speculative`: `"madrid"` → `(28, 17)` (INE 28)
  - `test_resolve_infojobs_barcelona_speculative`: `"barcelona"` → `(8, 17)`
  - `test_resolve_infojobs_valencia_speculative`: `"valencia"` → `(46, 17)`
  - `test_resolve_infojobs_sevilla_speculative`: `"sevilla"` → `(41, 17)`
  - `test_resolve_infojobs_remote_country_only`: `"remote"` → `(None, 17)`
  - `test_resolve_infojobs_espana_country_only`: `"españa"` → `(None, 17)`
  - `test_resolve_infojobs_spain_alias`: `"spain"` → `(None, 17)`
  - `test_resolve_infojobs_unmapped_returns_none_pair`: `"berlin"` → `(None, None)` + WARNING
  - `test_resolve_infojobs_empty_short_circuit`: `""` → `(None, None)` (sin WARNING)
  - `test_resolve_infojobs_custom_mapping_via_ctor`: ctor `infojobs_mapping={...}` se respeta
  - `test_protocol_has_resolve_infojobs_method`: `dir(LocationResolverPort)` incluye el método
  - `test_resolver_satisfies_extended_protocol`: asignación typed para que mypy --strict enforce
- Crear `backend/src/jobs_finder/infrastructure/location/_infojobs_mapping.py` (NEW, sibling de `_mapping.py`) con:
  - `INFOJOBS_PROVINCE_COUNTRY_MAPPING: dict[str, tuple[int, int]]` — 9 entries (5 user-verified + 4 speculative)
  - `INFOJOBS_ALIASES: dict[str, str]` — vacío inicialmente
  - Comentarios inline marcando user-verified vs speculative
- Modificar `backend/src/jobs_finder/application/ports.py`:
  - Agregar `def resolve_infojobs(self, location: str) -> tuple[int | None, int | None]: ...` al `LocationResolverPort` Protocol después de `resolve()`
  - Docstring con semántica de 4 casos: `(int,int)`, `(None,int)`, `(int,None)`, `(None,None)`
- Modificar `backend/src/jobs_finder/infrastructure/location/hardcoded_resolver.py`:
  - Agregar ctor kwargs `infojobs_mapping` + `infojobs_aliases` (ambos `| None = None`, default al dict del módulo nuevo)
  - Agregar `def resolve_infojobs(self, location: str) -> tuple[int | None, int | None]`:
    - Empty short-circuit sin WARNING (simetría con `resolve()`)
    - Reusar `_normalize` (refactor a método de instancia)
    - Alias lookup → mapping lookup → `(None, None)` + WARNING si unmapped
- Confirmar RED (pytest falla), implementar hasta GREEN, correr full suite, mypy --strict, ruff

**Files**:
- `backend/src/jobs_finder/application/ports.py` (MODIFY)
- `backend/src/jobs_finder/infrastructure/location/_infojobs_mapping.py` (NEW)
- `backend/src/jobs_finder/infrastructure/location/hardcoded_resolver.py` (MODIFY)
- `backend/tests/unit/test_hardcoded_location_resolver.py` (MODIFY — +14 tests)

**Acceptance**:
- 14+ tests pasan (los 6 que el orchestrator pidió como mínimo, ampliados a 14 cubriendo todos los entries del dict)
- `LocationResolverPort.resolve_infojobs` existe y `HardcodedLocationResolver` lo satisface
- Mypy --strict limpio (Protocol conformance)
- Full suite (1,142+ tests) sigue verde

---

### T-002: `InfoJobsScraperSettings.location_resolver` + `InfoJobsPlaywrightScraper.search()` URL plumb

**Type**: feature + test-first
**Scope**:
- **RED tests first** en `backend/tests/unit/test_infojobs_scraper.py`:
  - `test_search_uses_province_country_ids_when_mapped`: `location="malaga"` con resolver real → URL incluye `&provinceIds=34&countryIds=17`
  - `test_search_omits_province_country_ids_when_unmapped`: `location="berlin"` → URL sin los params (legacy `?l=berlin`)
  - `test_search_omits_province_country_ids_when_empty`: `location=""` → URL sin los params
  - `test_search_country_only_emits_countryIds_only`: `location="remote"` → URL con `&countryIds=17` solamente
  - `test_resolver_called_once_per_search_not_per_page`: parametrizado con 1, 2, 3 pages; assert `resolver.calls == 1`
  - `test_explicit_infojobs_geo_kwarg_skips_resolver`: pasar `infojobs_geo=(34, 17)` directo → resolver NUNCA se llama
  - `test_legacy_wiring_without_resolver_logs_deprecation_warning`: settings sin resolver → `DeprecationWarning` loggeado, URL legacy
- **RED tests first** en `backend/tests/unit/test_infojobs_settings.py`:
  - `test_settings_accept_location_resolver`: ctor con kwarg funciona
  - `test_settings_default_location_resolver_is_none`: backward-compat
  - `test_settings_equality_includes_resolver_identity`: dos settings con distinto resolver → `!=`
  - `test_settings_hash_includes_resolver`: `hash()` estable, dos settings iguales → mismo hash
- Modificar `backend/src/jobs_finder/infrastructure/infojobs/scraper.py`:
  - `InfoJobsScraperSettings`: agregar slot `location_resolver: LocationResolverPort | None = None`, kwarg en `__init__`, comparación en `__eq__`/`__hash__`, repr
  - `InfoJobsPlaywrightScraper.search()`: agregar kwarg scraper-internal `infojobs_geo: tuple[int | None, int | None] | None = None`
  - Lógica: `if infojobs_geo is None and self._settings.location_resolver is not None:` → resolver; `elif infojobs_geo is None and self._settings.location_resolver is None:` → `DeprecationWarning` logger
  - `_make_fetch_one_page(keywords, location, infojobs_geo)`: closure captura el tuple
  - `_build_url(keywords, location, page, *, infojobs_geo)`: append `&provinceIds=<id>` y `&countryIds=<id>` condicionalmente (3-line change, ver design §4.4)
- Confirmar RED → GREEN → full suite → mypy/ruff

**Files**:
- `backend/src/jobs_finder/infrastructure/infojobs/scraper.py` (MODIFY — settings + scraper)
- `backend/tests/unit/test_infojobs_scraper.py` (MODIFY — +7 tests)
- `backend/tests/unit/test_infojobs_settings.py` (MODIFY — +4 tests)

**Acceptance**:
- 11+ tests pasan
- URL incluye `provinceIds` y `countryIds` cuando mapeado
- URL los omite cuando unmapped/empty
- Resolver se llama **1 vez** por `search()` (parametrizado 1, 2, 3 pages)
- `DeprecationWarning` se loggea cuando no hay resolver
- El kwarg `infojobs_geo` permite tests sin depender del resolver

---

### T-003: Composition root wire + bonus fix del shadowing bug L607

**Type**: feature + bugfix
**Scope**:
- **RED test first** en `backend/tests/integration/test_composition.py`:
  - `test_resolver_shared_between_linkedin_and_infojobs`: `linkedin_port._settings.location_resolver is infojobs_port._settings.location_resolver` (uso de `is`, no `==`)
  - `test_resolver_in_app_state_is_same_as_scraper_settings`: `app.state.location_resolver is linkedin_port._settings.location_resolver`
- Modificar `backend/src/jobs_finder/presentation/app_factory.py`:
  - **Wire**: en la línea que construye `InfoJobsScraperSettings(...)`, agregar `location_resolver=location_resolver` (la misma variable que ya existe en línea ~185)
  - **Bonus fix**: eliminar la línea ~607 que reconstruye `location_resolver = HardcodedLocationResolver()` dentro del branch `chat_enabled` (shadowing bug pre-existente). La variable de línea 185 ya está en scope y se inyecta en el use case del chat en línea ~617.
  - Verificar con `git diff` que el fix es `-2 LOC` (la línea del shadow + su blank line) y `+1 LOC` (el kwarg nuevo en InfoJobsScraperSettings)
- Confirmar RED → GREEN → full suite → mypy/ruff

**Files**:
- `backend/src/jobs_finder/presentation/app_factory.py` (MODIFY — wire + fix L607)
- `backend/tests/integration/test_composition.py` (MODIFY — +2 tests)

**Acceptance**:
- 2+ tests pasan
- BOTH scrapers (LinkedIn + InfoJobs) reciben el **MISMO objeto** resolver (assert con `is`)
- El `app.state.location_resolver` es el mismo objeto que los settings
- El bug de shadowing de L607 está eliminado (verificable: el test pasa con `chat_enabled=True` Y `chat_enabled=False`)

---

### T-004: `filter_infojobs_results` docstring + `backend/README.md` sección nueva

**Type**: docs
**Scope**:
- Modificar `backend/src/jobs_finder/infrastructure/aggregator_filters.py`:
  - Actualizar el docstring de `filter_infojobs_results` (líneas ~75-94) para reflejar el nuevo rol: "defense-in-depth safety net for unmapped locations + future province/country ID drift. Primary relevance improvement comes from the URL plumb in `InfoJobsPlaywrightScraper._build_url`"
  - Mencionar que el primary fix es el URL plumb de T-002 y este filtro es el fallback
- Modificar `backend/README.md`:
  - Sección existente "InfoJobs client-side filter": agregar nota "defense-in-depth safety net" + link a la nueva sección
  - **Nueva sección** "InfoJobs province/country IDs":
    - Lista los 9 entries del dict
    - Marca los 4 speculative (Madrid=28, BCN=8, VLC=46, SVQ=41) como "pending LIVE validation"
    - Documenta el fallback `?l=<str>` para unmapped
    - Documenta el LIVE test gate `LLM_LIVE_TESTS=1`
- **RED tests first** en `backend/tests/unit/test_aggregator_filters.py`:
  - `test_filter_infojobs_results_docstring_mentions_defense_in_depth`: assert `"defense-in-depth"` o `"safety net"` en el docstring
  - `test_readme_documents_infojobs_province_mapping`: grep el README por `"provinceIds"` y `"countryIds"`
  - `test_readme_marks_speculative_ids`: grep por `"speculative"` o `"pending"`

**Files**:
- `backend/src/jobs_finder/infrastructure/aggregator_filters.py` (MODIFY — docstring only)
- `backend/README.md` (MODIFY — sección nueva + nota en sección existente)
- `backend/tests/unit/test_aggregator_filters.py` (MODIFY — +3 tests)

**Acceptance**:
- 3+ tests pasan
- Docstring actualizado
- README tiene la nueva sección
- **Cero cambio de comportamiento** (docs + test de docstring solamente)

---

### T-005: LIVE test gated `LLM_LIVE_TESTS=1` + verificación final

**Type**: test
**Scope**:
- Crear `backend/tests/integration/test_infojobs_live.py` (NEW):
  - `test_live_malaga_returns_malaga_area_jobs`: hit real InfoJobs SERP con `q=react&location=malaga`, assert que el set de resultados es mayoritariamente Málaga-area (≥70% contienen "Málaga" en location, heurística simple)
  - Skip decorator: `@pytest.mark.skipif(not os.getenv("LLM_LIVE_TESTS"), reason="LIVE test gated by LLM_LIVE_TESTS=1")`
  - Test parametrizado para los 4 speculative IDs: `madrid`, `barcelona`, `valencia`, `sevilla` — cada uno skip por default
- Correr la suite completa UNA ÚLTIMA VEZ: `cd backend && uv run pytest` (debe pasar 1,142+ tests existentes + ~30 tests nuevos)
- Correr type/lint: `cd backend && uv run mypy --strict && uv run ruff check && uv run ruff format --check`
- Este es el **último commit** del PR ("wiring complete + LIVE validation scaffolding")

**Files**:
- `backend/tests/integration/test_infojobs_live.py` (NEW — +1 LIVE test parametrizado)

**Acceptance**:
- 1 LIVE test escrito (skip cuando `LLM_LIVE_TESTS` no está set)
- Full suite verde (1,142+ existentes + 30+ nuevos)
- mypy --strict limpio
- ruff limpio
- Conventional commit: `test(infojobs): add LLM_LIVE_TESTS-gated live validation for province/country IDs`

---

## Work unit ordering (dependency graph)

```
T-001 ──► T-002 ──► T-003
            │           │
            ▼           ▼
         (T-004) ◄── (independiente, docs)
            │
            ▼
         T-005 (final commit)
```

- **T-001 primero**: el resolver es la fundación. Sin él, T-002 no puede resolver IDs.
- **T-002 depende de T-001**: el scraper llama al resolver. El Protocol extension está en T-001.
- **T-003 depende de T-002**: la composition wire inyecta el resolver en `InfoJobsScraperSettings` (que es campo de T-002).
- **T-004 independiente en términos de código**: solo docstring + README + tests de docstring. Puede ir antes o después de T-003, pero se posiciona después para que el README refleje el estado wired completo.
- **T-005 último**: LIVE test + verificación final + cierre del PR.

## PR slice recommendation

- **Estrategia**: `single-pr` (5 commits convencionales)
- **Review burden**: ~795 LOC total, ~159 LOC/commit promedio → bien dentro del budget de 400 líneas
- **Orden de commits = orden de T-NNN**:
  1. `feat(resolver): add resolve_infojobs to LocationResolverPort + 9-entry mapping` (T-001, ~120 LOC)
  2. `feat(infojobs): plumb provinceIds/countryIds in scraper URL via resolver` (T-002, ~200 LOC)
  3. `feat(composition): wire shared resolver to InfoJobs + fix L607 shadowing` (T-003, ~30 LOC)
  4. `docs(infojobs): update filter docstring + README province/country section` (T-004, ~60 LOC)
  5. `test(infojobs): add LLM_LIVE_TESTS-gated live validation` (T-005, ~50 LOC)
- **Single rollback unit**: revert del merge commit. Sin DB state, sin env vars nuevos, sin migraciones.

## Strict TDD discipline (per `_shared/strict-tdd.md`)

Para CADA task T-NNN, el executor DEBE:

1. **RED**: escribir los tests listados PRIMERO. Confirmar que fallan con `cd backend && uv run pytest <test_file>::<test_name> -x` (exit non-zero).
2. **GREEN**: implementar el cambio mínimo que hace pasar los tests. Confirmar con el mismo comando (exit zero).
3. **No regression**: correr `cd backend && uv run pytest` (suite completa, debe seguir verde).
4. **Type/lint**: `cd backend && uv run mypy --strict && uv run ruff check && uv run ruff format --check` (debe estar limpio).
5. **Commit**: conventional commits SIN `Co-Authored-By` ni atribución AI.
   - Tests: `test(<scope>): <subject>`
   - Features: `feat(<scope>): <subject>`
   - Bugfix: `fix(<scope>): <subject>`
   - Docs: `docs(<scope>): <subject>`

## Pre-apply checklist

- [x] 5 tasks identificados con acceptance criteria claros
- [x] Dependency order documentado (T-001 → T-002 → T-003 → T-004 → T-005)
- [x] Single PR recomendado (~795 LOC < 400-line budget, < 5000-line review budget)
- [x] Cero cambios fuera de `backend/`
- [x] `backend/README.md` actualizado (T-004)
- [x] Strict TDD discipline por task (RED → GREEN → suite → mypy/ruff)
- [x] L607 shadowing bug fix como bonus en T-003

## Files affected (resumen)

| File | Action | LOC est. |
|---|---|---|
| `backend/src/jobs_finder/application/ports.py` | MODIFY: +`resolve_infojobs` Protocol | +18 |
| `backend/src/jobs_finder/infrastructure/location/_infojobs_mapping.py` | NEW: 9-entry dict + aliases | +40 |
| `backend/src/jobs_finder/infrastructure/location/hardcoded_resolver.py` | MODIFY: +`resolve_infojobs` + ctor kwargs | +45 |
| `backend/src/jobs_finder/infrastructure/infojobs/scraper.py` | MODIFY: settings field + search() + _build_url | +70 |
| `backend/src/jobs_finder/presentation/app_factory.py` | MODIFY: wire + L607 fix | +1, -2 |
| `backend/src/jobs_finder/infrastructure/aggregator_filters.py` | MODIFY: docstring | +4, -2 |
| `backend/README.md` | MODIFY: sección nueva + nota | +50 |
| `backend/tests/unit/test_hardcoded_location_resolver.py` | MODIFY: +14 tests | +180 |
| `backend/tests/unit/test_infojobs_scraper.py` | MODIFY: +7 tests | +120 |
| `backend/tests/unit/test_infojobs_settings.py` | MODIFY: +4 tests | +50 |
| `backend/tests/unit/test_aggregator_filters.py` | MODIFY: +3 tests | +40 |
| `backend/tests/integration/test_composition.py` | MODIFY: +2 tests | +30 |
| `backend/tests/integration/test_infojobs_live.py` | NEW: 1 LIVE test | +50 |
| **TOTAL** | | **~795** |

## Coordination notes

- Cambio paralelo `backend-linkedin-location-fallback` también extiende `LocationResolverPort` con `resolve_structured`. Sin colisión de nombres (métodos distintos). El merge PR coordinará las dos adiciones.
- Los `FakeLocationResolver` / `_FakeLocationResolver` test doubles necesitan crecer con `resolve_infojobs` que devuelva `(None, None)` por default. Esto se hace dentro de T-001 + T-002 (ver tests listados).
