# Proposal: backend-scraper-query-tuning

> **Cambio**: `backend-scraper-query-tuning` • **Modo**: `both` • **Strict TDD**: ACTIVE
> **Fecha**: 2026-06-09 • **Status**: `proposed` (listo para `sdd-spec`)

## 1. Intención

El usuario reportó que `GET /jobs?q=react&location=Málaga` devuelve
resultados muy ruidosos: 8+ ofertas de LinkedIn de "DataAnnotation"
títuladas "Frontend Developer - AI Trainer" en "Washington, United
States", 5 ofertas de InfoJobs sin relación con "react"
(recepcionista, pintor, ordenanza, técnico de farmacia), y solo
unas pocas ofertas realmente relevantes de Indeed (Talan, Hero
Gaming, Fuxiona, LeoVegas, MONEI, B12).

El problema NO está en el frontend (que renderiza correctamente) ni
en los parsers (los datos extraídos son correctos) — está **aguas
arriba**, en 3 puntos del backend:

1. La ruta `GET /jobs` **NO resuelve `location` a `geoId`** antes de
   llamar al scraper de LinkedIn (el resolver existe, está plumbed
   en el chat 2-stage, pero no en el agregador).
2. El agregador **NO filtra por relevancia** — devuelve
   `posted_at DESC` por defecto sin puntuar match con la query.
3. InfoJobs tiene **filtrado server-side débil** — su URL
   `?q=react&l=Málaga` rankea por keyword pero NO excluye
   resultados sin token overlap.

Este cambio cierra esas 3 brechas con 4 mejoras pequeñas y aisladas.
La forma de la respuesta HTTP **NO cambia** (backward-compatible
con el frontend `frontend-scaffold` ya archivado).

## 2. Alcance

### 2.1 In scope

| # | Mejora | Archivos | Esfuerzo |
|---|---|---|---|
| 1 | Plumb `linkedin_geo_id` en la ruta `GET /jobs` | `presentation/routes/aggregator.py`, `presentation/app_factory.py` | ~50 LOC prod + 30 tests |
| 2 | Nueva estrategia de ranking `keyword_match` con scorer puro | `application/ranking.py` (extender `Literal`) | ~100 LOC prod + 200 tests |
| 3 | Filtro client-side en InfoJobs que descarta cards sin token overlap con la query | `infrastructure/infojobs/scraper.py` | ~30 LOC prod + 60 tests |
| 4 | `query_tokens` en `JobSearchCacheKey` para mejor cache hit rate en queries similares | `application/ports.py`, `application/usecases/_cached_search.py` | ~20 LOC prod + 40 tests |

**Total estimado**: ~200 LOC prod + ~330 LOC tests = **~530 LOC netos**
(~1000-1500 LOC con docstrings + integration tests). Bien por debajo
del presupuesto de 5000 líneas del orchestrator.

### 2.2 Out of scope

- Agregar 4ª fuente; cambiar la forma de la respuesta HTTP;
  cambiar el LLM filter behavior; construir ranking ML; aplicar
  el filtro client-side a LinkedIn/Indeed (solo InfoJobs en v1);
  cambiar los otros 5 campos de `JobSearchCacheKey`; mover
  `HardcodedLocationResolver` a patrón async.

## 3. Capabilities (contrato con `sdd-spec`)

### 3.1 New

- `query-relevance-ranking`: scoring client-side de jobs contra
  la query, con la estrategia opt-in `keyword_match` y la función
  pura `keyword_score(Job, q, location) -> float`.

### 3.2 Modified (delta specs)

- `jobs-aggregator-endpoint` (REQ-A-001..006): forwarding de
  `linkedin_geo_id` en la ruta `GET /jobs`.
- `jobs-aggregator-ranking` (REQ-AR-002..007): 4ª estrategia
  `keyword_match` al `Literal["posted_at", "priority", "none"]`.
- `infojobs-scraper` (REQ-J-001..006): filtro client-side que
  descarta cards sin token overlap con la query.
- `cache-ttl` (REQ-C-001..006): 6to campo
  `query_tokens: tuple[str, ...] = ()` en `JobSearchCacheKey`.

### 3.3 Sin cambios

- `domain` (Job, exceptions), `infrastructure/linkedin/scraper.py`,
  `infrastructure/indeed/scraper.py`, `infrastructure/location/`,
  `presentation/schemas.py`, `frontend/*`. El `Job` ya tiene
  `description: str | None` (obs #256); el frontend ya acepta
  `description: string | null` (frontend-scaffold design deviation
  #5).

## 4. Enfoque técnico

### 4.1 Mejora 1: Plumb `linkedin_geo_id` en `/jobs` route

En `presentation/routes/aggregator.py:148-153`, agregar
`linkedin_geo_id` resuelto vía `app.state.location_resolver`
(construido siempre en `app_factory.build_app()`, no solo cuando
`chat_enabled=True`). El agregador **ya acepta** el kwarg; solo
extendemos el forwarding del chat path al `/jobs` path. **Costo:
~3 líneas en el route + 1 línea en app_factory.**

### 4.2 Mejora 2: Strategy `keyword_match` + scorer puro

Extender `RankingStrategy = Literal["posted_at", "priority", "none",
"keyword_match"]`. Nuevo helper en `application/ranking.py`:

```python
def keyword_score(agg: AggregatedJob, q_tokens: set[str],
                  location_tokens: set[str]) -> float:
    """Score a job's relevance to the query in [0.0, 1.0].
    Tokenize title + company + description (lowercased),
    count overlap with q_tokens. Boost if location matches."""
```

**Default se queda en `"posted_at"`** para preservar v1
(ver §6 Open Question 1). Opt-in via env var
`AGGREGATOR_RANKING_STRATEGY=keyword_match`.

### 4.3 Mejora 3: Filtro client-side en InfoJobs

En `infrastructure/infojobs/scraper.py::_parse_cards`, agregar
3 líneas al inicio del loop que descartan cards cuyo
`title + company` comparte cero tokens con `q_tokens`
(capturado en el closure de `_make_fetch_one_page`). El
`remaining` cap se aplica **después** del filtro. **No usa
`description`** (queremos ser permisivos; el chat 2-stage + LLM
es el escape hatch para queries matizadas).

### 4.4 Mejora 4: `query_tokens` en `JobSearchCacheKey`

Agregar 6to campo `query_tokens: tuple[str, ...] = ()` al
`NamedTuple` en `application/ports.py:91`. En
`CachedJobSearchUseCase.search(...)` (línea 118-124), tokenizar
`keywords` con el mismo algoritmo del scorer y pasarlo al
constructor. NamedTuple con default es backward-compatible para
callers posicionales de 5 args.

## 5. Affected Areas

| Area | Impact |
|------|--------|
| `application/ranking.py` | Modified — 4th strategy + `keyword_score` + tokenize helper |
| `application/aggregator.py` | UNCHANGED — el dispatch es transparente |
| `application/ports.py` | Modified — 6to campo `query_tokens` |
| `application/usecases/_cached_search.py` | Modified — tokeniza `keywords` |
| `application/usecases/search_*.py` | UNCHANGED |
| `infrastructure/infojobs/scraper.py` | Modified — `_card_matches_query` en closure |
| `infrastructure/linkedin/scraper.py` | UNCHANGED (obs #302) |
| `infrastructure/indeed/scraper.py` | UNCHANGED |
| `infrastructure/location/` | UNCHANGED (`malaga → 104401670` ya verificado) |
| `presentation/routes/aggregator.py` | Modified — resolve `location` antes de search |
| `presentation/app_factory.py` | Modified — build resolver siempre + set `app.state` |
| `presentation/schemas.py` | UNCHANGED (HTTP shape preservada) |
| `domain/job.py` | UNCHANGED (`description` ya existe, obs #256) |
| `frontend/src/lib/types.ts` | UNCHANGED |
| `tests/unit/test_aggregator_ranking.py` | Modified — +6-8 scenarios |
| `tests/integration/test_aggregator_ranking.py` | Modified — +2-3 scenarios |
| `tests/integration/test_aggregator_api.py` | Modified — +1-2 scenarios |
| `tests/unit/test_infojobs_scraper.py` | Modified — +2-3 scenarios |
| `tests/unit/test_cached_job_search_use_case.py` | Modified — +2 scenarios |
| `tests/unit/test_hardcoded_location_resolver.py` | UNCHANGED |

## 6. Open Questions (decisiones del usuario)

1. **¿Default ranking flip de `posted_at` a `keyword_match`?**
   Recomiendo: **NO en v1** — opt-in via env var preserva v1
   contract. Confirmar con el usuario.
2. **¿Filtro client-side también a LinkedIn/Indeed?**
   Recomiendo: **solo InfoJobs en v1** (smallest correct change).
3. **¿Stemming (Porter) en `keyword_score`?** Recomiendo:
   **NO en v1** — 50 líneas de pure Python; follow-up trivial.

## 7. Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `keyword_score` heurístico imperfecto (falsos positivos en common words) | MEDIUM | Default en `posted_at`; opt-in via env var. Función pura, fácil de testear con 20+ pares sintéticos. Rollback = 1 env var change. |
| Tightening `geo_id` MIGHT romper locations desconocidas | LOW | Resolver retorna `None` + WARNING; scraper cae a `?location=<str>` (broken-but-doesn't-500). **No riesgo nuevo vs. status quo de `fix-linkedin-geoid`**. |
| Filtro InfoJobs descarta "Software Engineer" para query "react" (0 token overlap en title) | MEDIUM | Filtro usa `title + company` SOLO. Chat 2-stage + LLM es el escape hatch. Tests pin 5+ casos con descriptions que SÍ contienen "react" y verifican que NO se descartan. |
| `query_tokens` cache key es breaking change | LOW | NamedTuple con default value es backward-compatible. Cache in-memory se resetea en deploy (non-issue). |
| Tests existentes de `posted_at` se rompen | LOW | Strategy es aditivo; los 7 tests existentes siguen GREEN. |
| 2-stage chat filter se afecta | NONE | Chat path ya tiene su propio resolver wiring (obs #302). `keyword_match` es decisión del agregador; chat consume el resultado. |

## 8. Rollback Plan

Cada mejora es **independientemente revertible**:

- **Mejora 1**: revert el commit que modifica
  `presentation/routes/aggregator.py` y `app_factory.py`. 1 commit.
- **Mejora 2**: set `AGGREGATOR_RANKING_STRATEGY=posted_at` (o
  unset) — comportamiento default se restaura sin redeploy.
  0 commits; 1 env var change.
- **Mejora 3**: revert el commit que modifica
  `infrastructure/infojobs/scraper.py`. 1 commit.
- **Mejora 4**: revert el commit que modifica `application/ports.py`
  y `_cached_search.py`. 1 commit.

## 9. Dependencies

**No new external dependencies.** Todo en stdlib + código
existente. No new env vars. No new spec files en
`openspec/specs/` (los deltas cubren los 4 capabilities
modificados).

## 10. Success Criteria

- [ ] `GET /jobs?q=react&location=Málaga` ya NO devuelve las 8+
      ofertas de "DataAnimation" en "Washington" (verificable con
      LIVE test contra LinkedIn con `linkedin_geo_id=104401670`).
- [ ] Ya NO devuelve las 5 ofertas de InfoJobs (recepcionista,
      pintor, etc.) que no comparten tokens con "react" (LIVE test
      contra InfoJobs con el filtro client-side activo).
- [ ] Las ofertas de Indeed (Talan, Hero Gaming, Fuxiona, etc.)
      siguen en el top-N con `posted_at` (default) y con
      `keyword_match` (opt-in).
- [ ] Los 7 tests de `test_aggregator_ranking.py` + los 14 de
      `test_aggregator.py` siguen GREEN sin cambios.
- [ ] 4 quality gates GREEN: `pytest`, `mypy --strict`,
      `ruff check`, `ruff format --check`.
- [ ] ≥8 tests nuevos en `test_aggregator_ranking.py`,
      ≥2 en `test_aggregator_api.py`, ≥3 en
      `test_infojobs_scraper.py`, ≥2 en
      `test_cached_job_search_use_case.py`.
- [ ] `sdd-verify` PASS con 0 critical findings.
- [ ] Usuario confirma las 3 Open Questions antes de
      `sdd-apply`.

## 11. Workload Forecast & Suggested Tasks

**Total estimado**: ~200 LOC prod + ~330 tests + ~150 docstrings
= **~680 LOC netos** (~1000-1500 LOC con tax de strict TDD). Bien
por debajo del presupuesto de 5000 líneas. **No chained PR
needed** — single PR con 4 commits independientes (uno por mejora).

**Tareas (para `sdd-tasks`)**:

- **T-001**: `keyword_score(Job, q_tokens, location_tokens) -> float`
  + 8 unit tests (Mejora 2 scorer).
- **T-002**: Extender `RankingStrategy` Literal + branch en
  `rank_jobs(...)` + 6 unit tests (Mejora 2 dispatch).
- **T-003**: Plumb `linkedin_geo_id` en route + `app.state` +
  2 integration tests (Mejora 1).
- **T-004**: Filtro client-side en InfoJobs +
  3 unit tests (Mejora 3).
- **T-005**: `query_tokens` en `JobSearchCacheKey` + tokenización
  + 2 unit tests (Mejora 4).
- **T-006**: Integration test end-to-end: verifica que
  `GET /jobs?q=react&location=Málaga` con
  `AGGREGATOR_RANKING_STRATEGY=keyword_match` surfacea top-N
  por score.
- **T-007**: 1 LIVE test (gated `LLM_LIVE_TESTS=1`): ejecuta el
  path completo contra LinkedIn real con
  `linkedin_geo_id=104401670` y verifica que el top-5 NO incluye
  "DataAnnotation" en "Washington".
- **T-008**: Update `backend/README.md` secciones "Caching" y
  "Ranking" (~30 LOC doc).

**Review strategy**: single PR con 4 commits, uno por mejora.
Cada commit ~80-250 LOC, independientemente revertible.

## 12. Next Step

Listo para `sdd-spec`. El orchestrator debe:
1. Confirmar las 3 Open Questions (§6) con el usuario antes de
   `sdd-spec`.
2. Confirmar single PR vs. chained (recomiendo single).
3. Delegar a `sdd-spec` para escribir los 4 delta specs
   (`query-relevance-ranking` new + 3 modified).

**Skill resolution**: `paths-injected` — orchestrator pre-resolvió
`sdd-propose` + `_shared` + `sdd-apply` + `sdd-verify`.
