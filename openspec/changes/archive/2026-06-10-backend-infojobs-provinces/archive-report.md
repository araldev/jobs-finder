# Archive Report: `backend-infojobs-provinces`

## Status

**Closed** — implementación completa, verificación **`verified-pass`**
(0 CRITICAL, 0 WARNING, **3 SUGGESTION non-blocking**). El cambio
introduce 4 capabilities nuevas/promovidas: `infojobs-provinces` (new),
`infojobs-scraper` (foundational), `location-resolver` (foundational),
y `aggregator-relevance` (foundational). El fix real de la "all-Spain
InfoJobs results" bug: el `InfoJobsPlaywrightScraper._build_url()`
ahora emite `provinceIds=<id>&countryIds=<id>` cuando el
`HardcodedLocationResolver.resolve_infojobs(location)` retorna una
tupla no-`None`. El filtro client-side `filter_infojobs_results` se
mantiene como defense-in-depth safety net (decisión Q3=KEEP).

**Close date**: 2026-06-10 (ISO).

## Traceability — observation IDs de los artefactos del change

| Topic | Observation ID | Status |
|---|---|---|
| `sdd/backend-infojobs-provinces/explore` | #330 | explored |
| `sdd/backend-infojobs-provinces/proposal` | #331 | proposed |
| `sdd/backend-infojobs-provinces/spec` | #334 | specified (4 delta specs) |
| `sdd/backend-infojobs-provinces/design` | #337 | designed |
| `sdd/backend-infojobs-provinces/tasks` | #339 | planned (5 work units) |
| `sdd/backend-infojobs-provinces/apply-progress` | #341 | applied (5 commits) |
| `sdd/backend-infojobs-provinces/verify-report` | #342 | verified (PASS, 0/0/3) |
| `sdd/backend-infojobs-provinces/archive-report` | (este report) | archived |

> **Note**: el verify-report obs #342 tiene una inconsistencia menor:
> §1 dice "0 CRITICAL, 0 WARNING, 1 SUGGESTION" pero §9 lista 3
> SUGGESTIONs. El conteo del orchestrator's prompt ("3 SUGGESTION")
> concuerda con §9 — es el conteo canónico. La inconsistencia es
> puramente cosmética (un typo en §1) y no afecta el verdict PASS.

## Type

`feature` — el cambio introduce la capability `infojobs-provinces` (la
resolución de `location` → `(province_id, country_id)` para el scraper
de InfoJobs) y extiende 3 capabilities preexistentes: `infojobs-scraper`,
`location-resolver`, y `aggregator-relevance`.

## Capability name

`backend-infojobs-provinces` — la fix real del "all-Spain InfoJobs
results" bug. La mitigación previa (`filter_infojobs_results`,
PR #4 merged 2026-06-10) queda como defense-in-depth; el cambio
presente corrige la CAUSA (URL sin `provinceIds`/`countryIds`).

## Commits (5, branch `feature/backend-infojobs-provinces`)

| Hash | Subject | Work Unit | Lines |
|---|---|---|---|
| `82e3fce` | `feat(location-resolver): add resolve_infojobs for province/country mapping` | T-001 | +380/-10 |
| `effe979` | `feat(infojobs-scraper): plumb province/country IDs via resolve_infojobs` | T-002 | +584/-9 |
| `eec2526` | `fix(app_factory): share location_resolver instance + remove L607 shadow` | T-003 | +113/-7 |
| `2167245` | `docs(backend): document InfoJobs province/country resolution + defense-in-depth filter` | T-004 | +203/-2 |
| `2d9114d` | `test(infojobs): add gated LIVE test for Malaga province/country resolution` | T-005 | +167/-0 |

> **Total diff vs `f41aa90`**: `git diff --stat f41aa90..2d9114d | tail -1`
> → `23 files changed, 3278 insertions(+), 28 deletions(-)` (≈3,278 net LOC).
> Ningún commit incluye `Co-Authored-By` trailer (regla AGENTS.md #6).
> Single PR, bien por debajo del review budget de 5,000 líneas.

## Verify verdict

`verified-pass` — 0 CRITICAL, 0 WARNING, **3 SUGGESTION non-blocking**
(per obs #342 §9 + orchestrator cache; obs #342 §1 dice "1 SUGGESTION"
pero §9 lista las 3):

1. **[test file naming]** Spec nombró `tests/unit/test_infojobs_province_resolver.py` (NEW); la implementación extendió `tests/unit/test_hardcoded_location_resolver.py` en su lugar. Coverage es completa (12/12 REQ-PROV-001). Follow-up opcional.
2. **[fail-fast on invalid mapping — soft requirement]** REQ-PROV-LOC-003 scenario 2 fue documentado en el spec como soft requirement con `xfail` opt-out. La implementación no tiene ctor validation ni `xfail` test. Documentado como follow-up.
3. **[LIVE test covers 1 of 5 IDs]** T-005 cubre solo el caso user-verified Málaga=34; los 4 speculative IDs (Madrid, Barcelona, Valencia, Sevilla) están diferidos a un follow-up per obs #341.

**Spec compliance matrix**: 38/38 scenarios ✅ (12 + 7 + 3 + 2 + 3 + 2 + 4 + 2 + 3 = 38)
per obs #342 §4.

**Quality gates GREEN**:

| Gate | Result |
|---|---|
| `cd backend && bash scripts/check.sh` | ✅ passed (ruff + mypy + pytest) |
| `cd backend && uv run mypy --strict` | ✅ no issues found in 176 source files |
| `cd backend && uv run ruff format --check` | ✅ 177 files already formatted |
| `cd backend && uv run ruff check` | ✅ clean |
| pytest (full) | ✅ 1,176 passed, 14 skipped, 0 failed (was 1,142/13 baseline) |
| Test count delta | +34 new tests (15 + 11 + 2 + 3 + 3) |
| Skip count delta | +1 LIVE-gated skip (T-005) |

## OpenSpec syncs (specs promovidos al source of truth)

4 delta specs promovidos a `openspec/specs/` (todos foundational — no
existía main spec previo para ninguno de los 4 capabilities). El
archive es APPEND-ONLY — ninguna capability canónica existente fue
modificada (las 2 preexistentes `chat-streaming` y `frontend-scaffold`
siguen intactas).

### `infojobs-provinces/spec.md` (NEW → foundational, promoted to canonical)

El delta spec del change
(`openspec/changes/backend-infojobs-provinces/specs/infojobs-provinces/spec.md`)
era **fundacional** (no existía main spec previo). Se promovió completo a:

```
openspec/changes/backend-infojobs-provinces/specs/infojobs-provinces/spec.md
  → openspec/specs/infojobs-provinces/spec.md
```

Contiene 1 REQ-* (REQ-PROV-001) con 12 scenarios cubriendo: lookup
canonical (Málaga=34, España=17), alias normalization (NFC +
casefold + strip + accent-strip), 4 speculative INE codes (Madrid,
Barcelona, Valencia, Sevilla), country-only (Remote, España),
unmapped + WARNING (Berlin), empty short-circuit, custom mapping
via ctor, y 9-entry default count lock.

### `infojobs-scraper/spec.md` (MODIFIED → foundational, promoted to canonical)

El delta spec era **MODIFIED** pero sin base spec preexistente. Se
promovió completo a:

```
openspec/changes/backend-infojobs-provinces/specs/infojobs-scraper/spec.md
  → openspec/specs/infojobs-scraper/spec.md
```

Contiene 3 REQ-* (REQ-PROV-002 URL plumb con 7 scenarios,
REQ-PROV-002-MOD `search()` resolution con 3 scenarios,
REQ-PROV-003 settings con 3 scenarios) = **13 scenarios** cubriendo
URL formula con province/country, country-only, unmapped fallback,
empty short-circuit, resolver called once per search, legacy wiring
+ DeprecationWarning, explicit `infojobs_geo` kwarg bypass, tuple
forwarding al closure a través de páginas, y settings hashability
+ equality.

### `location-resolver/spec.md` (MODIFIED → foundational, promoted to canonical)

El delta spec era **MODIFIED** sobre la v1 LinkedIn-only contract.
Se promovió completo a:

```
openspec/changes/backend-infojobs-provinces/specs/location-resolver/spec.md
  → openspec/specs/location-resolver/spec.md
```

Contiene 3 REQ-* (REQ-PROV-LOC-001 Protocol extension con 2
scenarios, REQ-PROV-LOC-001-MOD pre-change call-site preservation
con 1 scenario, REQ-PROV-LOC-002 test doubles growth con 3 scenarios,
REQ-PROV-LOC-003 composition root con 2 scenarios) = **8 scenarios**
cubriendo Protocol extension (mirroring `LLMClientPort.complete` +
`stream_complete`), `HardcodedLocationResolver` structural
conformance a mypy --strict, 2 test doubles crecen `resolve_infojobs`
con default `(None, None)`, pre-change call sites sin cambios, y
composition root que comparte la MISMA instancia entre LinkedIn +
InfoJobs (`is`, no `==`).

### `aggregator-relevance/spec.md` (MODIFIED → foundational, promoted to canonical)

El delta spec era **MODIFIED** sobre el pre-change
`filter_infojobs_results` contract (PR #4, merged 2026-06-10). Se
promovió completo a:

```
openspec/changes/backend-infojobs-provinces/specs/aggregator-relevance/spec.md
  → openspec/specs/aggregator-relevance/spec.md
```

Contiene 2 REQ-* (REQ-PROV-AGG-001-MOD filter kept con 4 scenarios,
REQ-PROV-AGG-002-MOD README docs con 2 scenarios) = **6 scenarios**
cubriendo filter still applies a InfoJobs results, filter does NOT
apply a LinkedIn/Indeed, filter is no-op cuando URL plumb funciona,
filter es safety net para unmapped locations, README documenta el
nuevo rol "defense-in-depth", y README lista las 9-entry mapping
con 4 speculative flagged.

**Cero MODIFIED blocks a otras capabilities**: ningún main spec
preexistente fue tocado. El archive es puramente additive para
`openspec/specs/`.

## Pre-condiciones para el próximo change

1. `feature/backend-infojobs-provinces` está lista para `git push` + open
   PR (NO pusheada aún — orchestrator decide per preflight `ask-always`).
2. Los 3 SUGGESTIONs del verify report son non-blocking; pueden abordarse
   en un follow-up `backend-infojobs-provinces-followups` (test file
   rename + ctor validation + 4 speculative ID LIVE tests) si el equipo
   lo desea.
3. **`backend-linkedin-location-fallback` está ahora en curso** (ver
   `openspec/changes/backend-linkedin-location-fallback/`). Ambos cambios
   extienden `LocationResolverPort` con métodos nuevos (sin colisión de
   nombres: `resolve_infojobs` vs `resolve_structured`); el merge PR
   resolverá cualquier conflict en la Protocol class manualmente.

## Archive contents

```
openspec/changes/archive/2026-06-10-backend-infojobs-provinces/
├── explore.md         ✅
├── proposal.md        ✅
├── design.md          ✅
├── tasks.md           ✅ (5/5 work units complete)
├── verify-report.md   ✅ (verified-pass, 0/0/3)
├── apply-progress.md  ✅ (5 commits, 32 new tests, 1,176/14 PASS)
└── specs/
    ├── aggregator-relevance/
    │   └── spec.md    ✅ (foundational, 2 REQ-* / 6 scenarios)
    ├── infojobs-provinces/
    │   └── spec.md    ✅ (foundational, 1 REQ-* / 12 scenarios)
    ├── infojobs-scraper/
    │   └── spec.md    ✅ (foundational, 3 REQ-* / 13 scenarios)
    └── location-resolver/
        └── spec.md    ✅ (foundational, 3 REQ-* / 8 scenarios)
```

## Source of truth actualizado

4 nuevos canonical specs en `openspec/specs/` (todos foundational, todos
promovidos del delta). Los 2 canonical specs preexistentes (`chat-streaming`,
`frontend-scaffold`) están intactos.

```
openspec/specs/
├── aggregator-relevance/    (NEW)  136 lines — promoted from delta
├── chat-streaming/          (unchanged — pre-existing canonical)
├── frontend-scaffold/       (unchanged — pre-existing canonical)
├── infojobs-provinces/      (NEW)  157 lines — promoted from delta
├── infojobs-scraper/        (NEW)  194 lines — promoted from delta
└── location-resolver/       (NEW)  156 lines — promoted from delta
```

## PRs

Per la preflight `ask-always`, el orchestrator decidirá. La rama
`feature/backend-infojobs-provinces` está lista para `git push` + open
PR (target: `araldev/jobs-finder` `main` from `feature/backend-infojobs-provinces`,
PR #5 per orchestrator's plan). El orchestrator deberá promptar al user.

## Próximos recomendados

- `feature/backend-infojobs-provinces` → `git push` + open PR (orchestrator
  prompta al user per preflight `ask-always`)
- Follow-up opcional `backend-infojobs-provinces-followups` — cerrar los
  3 SUGGESTIONs (test file rename, ctor validation, 4 speculative LIVE tests)
- Siguiente change: `backend-linkedin-location-fallback` (ya en curso per
  `openspec/changes/backend-linkedin-location-fallback/`)

## Discoveries / decisions worth remembering for future changes

- **El bug pre-existente L607 shadowing de `app_factory.py` (que
  reconstruía `location_resolver = HardcodedLocationResolver()` dentro
  del branch `chat_enabled`, shadowing la L185 instance) fue arreglado
  como bonus de T-003**. Sin este fix, el test
  `test_resolver_shared_between_linkedin_and_infojobs` (que asserta
  `is`, no `==`) hubiera fallado cuando `chat_enabled=True`. El fix
  garantiza que EXACTAMENTE una `HardcodedLocationResolver()` se
  construye en `app_factory.py` (L185) y se comparte entre LinkedIn +
  InfoJobs + chat filter + `app.state`.
- **El kwarg `infojobs_geo` es scraper-internal y NO está en
  `JobSearchPort` ni en `JobSearchCacheKey`**. La tupla
  `(province_id, country_id)` viaja por el closure
  `_make_fetch_one_page(keywords, location, infojobs_geo=...)` —
  desacoplando el Port de las concerns de InfoJobs. El
  `JobSearchCacheKey` 5to campo `geo_id: int | None` queda
  LinkedIn-specific (correcto).
- **El `LocationResolverPort` creció un segundo método siguiendo el
  patrón canónico `LLMClientPort.complete` + `stream_complete`**
  (`application/ports.py:374-451`). 1 Protocol, 2 métodos, 1
  implementación. Si un futuro 4to source necesita un 3er shape de
  ID, agregar otro método (no romper el contrato).
- **El resolver se llama UNA SOLA VEZ por `search()` (no por página)**,
  y la tupla se captura en el closure `_make_fetch_one_page`. Esto
  evita N llamadas inútiles y mantiene `paginated_search` helper
  source-agnostic. El helper sigue siendo el mismo loop canónico que
  para LinkedIn e Indeed — solo agregamos 1 kwarg al closure.
- **`filter_infojobs_results` se mantiene como defense-in-depth** (decisión
  Q3=KEEP). Costo: ~100 LOC + ~10µs por call. Beneficio: safety net
  para unmapped locations + future province/country ID drift + casos
  donde el URL plumb no captura el resultado esperado. 6 tests pre-cambio
  siguen GREEN sin cambios.
- **El `DeprecationWarning` se loggea una vez por `search()` cuando
  el scraper se construye sin resolver** (legacy wiring, pre-cambio).
  NO se raise — el path legacy sigue siendo válido (v1 byte-identical
  URL), solo es subóptimo. Es un nudge para que ops inyecten el resolver.
- **4 IDs son speculative** (Madrid=28, Barcelona=8, Valencia=46,
  Sevilla=41 — basados en códigos INE oficiales; InfoJobs puede usar
  IDs internos diferentes). La mitigación es:
  (1) el LIVE test gated `LLM_LIVE_TESTS=1` (T-005) verifica cada ID;
  (2) si un ID es incorrecto, se elimina del dict (1-line change, 0
  LOC) y cae al fallback `(None, None)` (graceful degradation, no 500);
  (3) el `filter_infojobs_results` defense-in-depth provee una red de
  seguridad secundaria.
- **El método `resolve_infojobs` retorna `tuple[int | None, int | None]`
  con 4 casos semánticos**: `(int, int)` ambos conocidos, `(None, int)`
  country-only (Remote/España), `(int, None)` province-only (futuro),
  `(None, None)` unmapped/empty (legacy fallback). El sentinel
  `(None, None)` es la clave del graceful degradation.
- **El test file naming diff (SUGGESTION #1) es menor**: el spec
  propuso `tests/unit/test_infojobs_province_resolver.py` (NEW file)
  pero la implementación extendió `tests/unit/test_hardcoded_location_resolver.py`
  (mirroring el patrón LinkedIn: no hay un `test_linkedin_location_resolver.py`
  separado — el resolver test vive junto al resolver). La cobertura
  es completa (12/12 REQ-PROV-001) y la organización es más coherente
  con el patrón existente.
- **El `LinkedInScraperSettings.location_resolver` field ya existía**
  (introducido en `fix-linkedin-geoid`, obs #302). El presente change
  replicó el patrón exacto para `InfoJobsScraperSettings` — un
  field `LocationResolverPort | None = None` con `__slots__` +
  `__eq__` + `__hash__` + `__repr__`. El mirror pattern facilita
  razonar sobre los 2 scrapers en paralelo.
- **3 test doubles crecieron `resolve_infojobs` con default
  `(None, None)`** para backward-compat: `FakeLocationResolver` en
  `test_filter_use_case.py:955`, `_FakeLocationResolver` en
  `test_linkedin_scraper.py:277`, y un tercer test double (per
  design §9 bonus fix) en `test_linkedin_settings.py`. El default
  `(None, None)` hace que los tests que no exercen el path InfoJobs
  sigan pasando sin tocar el resolver.

## Skill resolution

`paths-injected` (orchestrator pre-resolvió `sdd-archive/SKILL.md` +
`_shared/SKILL.md` + `sdd-phase-common.md` + `openspec-convention.md`
+ `persistence-contract.md` + `result-contract.md` [en
`skills/_shared/`]).

## Result contract

- `status`: `archived`
- `executive_summary`: 4 delta specs promoted a canonical source of
  truth (1 NEW + 3 MODIFIED → todos foundational porque no existía
  main spec previo). Change folder movido a
  `openspec/changes/archive/2026-06-10-backend-infojobs-provinces/`.
  Verify verdict PASS (0/0/3). +34 tests (1,142→1,176), +1 LIVE-gated
  skip. +3,278 net LOC across 5 commits. Single PR ready for push.
- `artifacts`:
  - `archive_report_topic_key`: `sdd/backend-infojobs-provinces/archive-report`
  - `archive_report_file`: `openspec/changes/archive/2026-06-10-backend-infojobs-provinces/archive-report.md`
  - `synced_specs` (4):
    - `openspec/specs/infojobs-provinces/spec.md` — NEW foundational, 1 REQ / 12 scenarios
    - `openspec/specs/infojobs-scraper/spec.md` — foundational, 3 REQ / 13 scenarios
    - `openspec/specs/location-resolver/spec.md` — foundational, 3 REQ / 8 scenarios
    - `openspec/specs/aggregator-relevance/spec.md` — foundational, 2 REQ / 6 scenarios
  - `archive_folder`: `openspec/changes/archive/2026-06-10-backend-infojobs-provinces/`
- `next_recommended`: `sdd-apply backend-linkedin-location-fallback`
  (orchestrator will switch branches and launch the next change)
- `risks`:
  - Verify-report obs #342 §1 dice "1 SUGGESTION" pero §9 lista 3
    SUGGESTIONs — el orchestrator's prompt confirma "3 SUGGESTIONs"
    canónicos. La inconsistencia es cosmética (typo en §1) y no
    afecta el verdict PASS.
  - 4 speculative province IDs (Madrid=28, Barcelona=8, Valencia=46,
    Sevilla=41) están pending LIVE test validation. T-005 cubre solo
    Málaga=34. SUGGESTION #3.
  - `infojobs-provinces` y los otros 3 specs son brand new en
    `openspec/specs/`. Downstream changes que los referencien deben
    saber que son foundational specs (no MODIFIED blocks contra un
    base preexistente).
  - `backend-linkedin-location-fallback` también extiende
    `LocationResolverPort` — el merge PR resolverá cualquier conflict
    en la Protocol class manualmente (no name collision: `resolve_infojobs`
    vs `resolve_structured`).
- `skill_resolution`: `paths-injected`
