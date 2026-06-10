# Tasks: backend-linkedin-location-fallback

> **Change**: `backend-linkedin-location-fallback` • **Base**: `f41aa90` (post `backend-scraper-query-tuning`) • **Strict TDD**: ACTIVE
> **Artifact mode**: `both` (OpenSpec filesystem + Engram) • **Spec**: obs #336 • **Design**: obs #338
> **Resolver shape**: extender `LocationResolverPort` con `resolve_structured()` (Q5=A confirmado).

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~580 LOC across 4 work units |
| 400-line budget risk | Low (single PR, < 5000 budget) |
| Chained PRs recommended | No |
| Suggested split | single-pr |
| Delivery strategy | ask-always |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: single-pr
400-line budget risk: Low

**Rationale**: el cambio está acotado a 4 work units secuenciales con dependencia dura T-001 → T-002 → T-003 → T-004. ~580 LOC se distribuye en ~120 (resolver) + ~200 (scraper) + ~10 (composition verify) + ~50 (docs) + ~200 (tests nuevos). La composition root no agrega wiring nuevo (reuse de L185/L255). El `JobSearchPort` Protocol no se extiende (el tuple fluye por el closure).

### Suggested work units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| T-001 | Resolver foundation: Protocol + 10-city dict + `resolve_structured()` | PR 1 (commit C1) | Foundation; tests ship in the same commit. |
| T-002 | Scraper `_build_url` priority + URL encoding + closure plumb | PR 1 (commit C2) | Depends on T-001. |
| T-003 | Composition root verify + test doubles extension | PR 1 (commit C3) | No new code in `app_factory.py`; just extends 2 `FakeLocationResolver` doubles for Protocol conformance. |
| T-004 | README docs + LIVE test gated + final verification | PR 1 (commits C4+C5) | Closes the change. |

## Phase 1: Resolver Foundation (T-001)

- [ ] 1.1 **RED**: write `test_resolve_structured_antequera` en `backend/tests/unit/test_hardcoded_location_resolver.py` — input `"Antequera"` → `("Antequera", "Andalucía", "Spain")`. Run `cd backend && uv run pytest tests/unit/test_hardcoded_location_resolver.py::test_resolve_structured_antequera -x` y confirma RED (`AttributeError` o `TypeError`).
- [ ] 1.2 **RED**: write 9 tests más del resolver cubriendo: lowercase, uppercase, strip whitespace, NFC/NFD normalization, accentless input (`"Cadiz"` → `("Cádiz", …)`), unmapped → `None` (`"Berlin"`), empty string → `None`, country-level parametrized (`"España"` / `"Spain"` / `"Espana"`) → todos `None`, CCAA-level (`"Andalucía"`) → `None`, alias recurse (custom `_ALIASES` con `"ante" → "antequera"`).
- [ ] 1.3 **RED**: write `test_resolve_structured_all_10_cities` parametrized con los 10 inputs (antequera, fuengirola, marbella, toledo, salamanca, cadiz, granada, gijon, leon, vigo) y los triplets esperados.
- [ ] 1.4 **RED**: write `test_resolve_structured_madrid_returns_none` (geoId-only — Madrid NO en `_STRUCTURED_MAPPING`) y `test_resolve_structured_independence_from_resolve` (mismo input `"Antequera"` → `resolve` returns `None`, `resolve_structured` returns triplet).
- [ ] 1.5 **RED**: write `test_resolve_structured_ctor_default_mapping` (asserts `len(resolver._structured_mapping) == 10`) y `test_resolve_structured_ctor_custom_mapping` (custom dict via ctor kwarg).
- [ ] 1.6 Confirmar TODOS los 13+ tests RED antes de implementar.
- [ ] 1.7 Crear `backend/src/jobs_finder/infrastructure/location/_structured_mapping.py` con `_STRUCTURED_MAPPING: dict[str, tuple[str, str, str]]` (10 entries: 1 VERIFIED + 9 SPECULATIVE con comments inline) y docstring documenting the source provenance.
- [ ] 1.8 Modificar `backend/src/jobs_finder/application/ports.py` — agregar `def resolve_structured(self, location: str) -> tuple[str, str, str] | None: ...` al `LocationResolverPort` Protocol después de `resolve()` (L188). Mantener docstring consistent con `resolve()`.
- [ ] 1.9 Modificar `backend/src/jobs_finder/infrastructure/location/hardcoded_resolver.py` — agregar kwarg `structured_mapping` al `__init__` (default `_STRUCTURED_MAPPING`) e implementar `resolve_structured()` reusando `_normalize()` existente y `self._aliases` para alias recurse. Short-circuit empty string → `None`.
- [ ] 1.10 Confirmar GREEN: `cd backend && uv run pytest tests/unit/test_hardcoded_location_resolver.py -v` — 13+ tests pasan.
- [ ] 1.11 Run `cd backend && uv run mypy` y `cd backend && uv run ruff check` — clean.
- [ ] 1.12 Commit C1: `feat(location-resolver): add resolve_structured for 10-city triplet mapping` con tests.

## Phase 2: Scraper URL plumb (T-002)

- [ ] 2.1 **RED**: write 7 tests en `backend/tests/unit/test_linkedin_scraper.py`:
  - `test_search_uses_geoId_over_structured_when_both_available` (priority test)
  - `test_search_uses_structured_format_when_no_geoId` (golden URL: `?keywords=react&location=Antequera%2CAndaluc%C3%ADa%2CSpain&start=0`)
  - `test_search_uses_legacy_fallback_when_no_resolutions` (`?location=Berlin`)
  - `test_resolver_called_once_per_search_not_per_page` (parametrized 1/2/3 pages)
  - `test_url_encoding_handles_tildes_and_commas` (golden assertions para `Cádiz` y `León,Castilla y León`)
  - `test_legacy_wiring_without_resolver_works` (`location_resolver=None` → no 500)
  - `test_structured_none_falls_back_to_legacy` (`resolve_structured` returns `None` para `"Berlin"`).
- [ ] 2.2 Confirmar RED — los 7 tests fallan con el signature actual de `_build_url` / `search()`.
- [ ] 2.3 Modificar `_build_url(keywords, location, start, *, geo_id, structured)` en `backend/src/jobs_finder/infrastructure/linkedin/scraper.py` — agregar kwarg `structured: tuple[str, str, str] | None = None` y la rama `priority 2: structured` que usa `urllib.parse.quote(f"{city},{province},{country}")`. Documentar el priority order en el docstring.
- [ ] 2.4 Modificar `search()` — capturar `structured = self._settings.location_resolver.resolve_structured(location)` UNA VEZ al inicio, y forward `structured=structured` al `_make_fetch_one_page(...)` closure factory.
- [ ] 2.5 Modificar `_make_fetch_one_page(keywords, location, *, geo_id, structured)` — agregar kwarg `structured`, forward a `_build_url(...)` en el closure body.
- [ ] 2.6 Confirmar GREEN: `cd backend && uv run pytest tests/unit/test_linkedin_scraper.py -v` — los 7 nuevos tests pasan + todos los existentes (1142+ baseline).
- [ ] 2.7 Run `cd backend && uv run mypy` y `cd backend && uv run ruff check` — clean.
- [ ] 2.8 Commit C2: `feat(linkedin-scraper): _build_url priority geoId > structured > raw`.

## Phase 3: Composition verify + test doubles (T-003)

- [ ] 3.1 **RED**: write `test_resolver_shared_with_linkedin_scraper_settings` en `backend/tests/integration/test_app_factory.py` (o `test_composition_root.py` si existe) — asserts `app.state.location_resolver is settings.location_resolver` (mismo instance fluye a la scraper). Confirmar RED.
- [ ] 3.2 Modificar `FakeLocationResolver` en `backend/tests/unit/test_filter_use_case.py` (L955) — agregar `def resolve_structured(self, location: str) -> tuple[str, str, str] | None: return None` para Protocol conformance.
- [ ] 3.3 Modificar `_FakeLocationResolver` en `backend/tests/unit/test_linkedin_scraper.py` (L277) — agregar `def resolve_structured(self, location: str) -> tuple[str, str, str] | None: return None` para Protocol conformance.
- [ ] 3.4 Verificar `app_factory.py:185` y `app_factory.py:255` — el mismo `HardcodedLocationResolver` instance fluye a `LinkedInScraperSettings` y `InfoJobsScraperSettings`. Verificar que `app_factory.py:607` NO shadow (el fix del parallel `backend-infojobs-provinces` debe persistir; si no persiste, coordinar merge con el parallel change).
- [ ] 3.5 Confirmar GREEN: `cd backend && uv run pytest -v` — 1142+ baseline + 20+ nuevos tests pasan, 0 regresiones.
- [ ] 3.6 Run `cd backend && uv run mypy` y `cd backend && uv run ruff check` — clean.
- [ ] 3.7 Commit C3: `test(composition): verify shared location_resolver instance + extend test doubles`.

## Phase 4: Docs + LIVE test + final verification (T-004)

- [ ] 4.1 Modificar `backend/README.md` — agregar sección "LinkedIn structured location fallback" (~30 LOC) con: priority order `geoId > structured > raw` (ASCII diagram), lista de las 10 cities con marca VERIFIED/SPECULATIVE inline, behavior del legacy fallback, nota "frontend sigue enviando `location=<raw>`", link al LIVE test gate (`LLM_LIVE_TESTS=1`).
- [ ] 4.2 **RED**: write 2 grep-style tests en `backend/tests/unit/test_aggregator_filters.py` (o donde lockeemos docs) que asserteen keywords como `"structured"`, `"VERIFIED"`, `"SPECULATIVE"`, `"LLM_LIVE_TESTS"` en el README. Confirmar RED → GREEN.
- [ ] 4.3 Crear `backend/tests/integration/test_linkedin_live.py` (NEW) con 1 test `test_live_antequera_returns_actual_antequera_jobs` gated por `os.environ.get("LLM_LIVE_TESTS") == "1"` — skip en CI per AGENTS.md rule #1. El test hit real LinkedIn con `?keywords=react&location=Antequera%2CAndaluc%C3%ADa%2CSpain&start=0` y assertea que al menos 1 de los primeros 5 resultados tiene un location field conteniendo `"Antequera"`, `"Málaga"`, o `"Andalucía"`.
- [ ] 4.4 Commit C4: `docs(linkedin): document structured location fallback + LIVE test gate`.
- [ ] 4.5 Run final full suite: `cd backend && bash scripts/check.sh` — ruff + mypy + pytest (1142+ baseline + 20+ nuevos + 1 LIVE skipped). Limpio.
- [ ] 4.6 Run final `cd backend && uv run mypy --strict` y `cd backend && uv run ruff format --check` — clean.
- [ ] 4.7 Commit C5 (chore): `chore(verify): full check.sh green for backend-linkedin-location-fallback` (o skip si no hay cambios adicionales).

## Work unit ordering

T-001 → T-002 → T-003 → T-004 (sequential, hard dependency).

T-001 es la foundation (Protocol + dict + method). T-002 depende de T-001 (el scraper llama el nuevo método). T-003 es composition verify + extender los test doubles para que conformen el Protocol extendido. T-004 cierra el change con docs + LIVE test + final verification.

## Pre-apply checklist

- [x] 4 work units identified
- [x] Dependency order documented (T-001 → T-002 → T-003 → T-004)
- [x] Single PR recommendation (~580 LOC, < 5000 budget)
- [x] No code changes outside `backend/`
- [x] `backend/README.md` updated (T-004 step 4.1)
- [x] Strict TDD discipline per `_shared/strict-tdd.md` (RED → GREEN → commit per task)
- [x] No shadowing bug in `app_factory.py` (T-003 step 3.4 — verify only, fix belongs to parallel change)

## Coordination with parallel `backend-infojobs-provinces`

Ambos cambios extienden `LocationResolverPort` con métodos nuevos (sin colisión de nombres). El merge order recomendado es **`backend-linkedin-location-fallback` first** (surface area más pequeña) → `backend-infojobs-provinces` second. El `app_factory.py:607` shadowing fix es bonus del parallel change; este change verifica que persiste post-merge.

## Strict TDD discipline (per task)

Para CADA task T-NNN:

1. Escribir los failing tests PRIMERO (RED).
2. `cd backend && uv run pytest` para confirmar RED (AttributeError, TypeError, o assertion miss).
3. Implementar el cambio más pequeño que los hace pasar (GREEN).
4. `cd backend && uv run pytest` para confirmar GREEN.
5. `cd backend && uv run mypy` y `cd backend && uv run ruff check` — clean.
6. Commit con conventional commits (sin `Co-Authored-By`).

## Notes

- El `JobSearchPort` Protocol NO se extiende: el `structured` tuple es scraper-internal (LinkedIn-specific), fluye por el closure `_make_fetch_one_page`, no por el Port. Mismo patrón que `geo_id` (obs #338 §3 decision #10).
- El HTTP contract NO cambia: el frontend sigue enviando `location=<raw>`; el resolver convierte internamente. Cero coordinación con el frontend team.
- Si un city speculative falla el LIVE test, se remueve del dict (1-line change, 0 LOC). El scraper cae al legacy fallback sin code change adicional.
