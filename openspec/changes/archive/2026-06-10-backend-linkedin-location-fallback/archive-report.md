# Archive Report: `backend-linkedin-location-fallback`

## Status

**Closed** — implementación completa, verificación **`verified-pass`**
(0 CRITICAL, 0 WARNING, **3 SUGGESTION non-blocking** per obs #348
§9). El cambio cierra el gap residual del
`backend-scraper-query-tuning` (PR #4 merged 2026-06-10): el
`LinkedInPlaywrightScraper._build_url()` ahora emite la rama
intermedia `?location=City,Province,Country` (priority media) cuando
`LocationResolverPort.resolve_structured(location)` retorna una
tupla no-`None`. La cadena completa de prioridad es
`geoId > structured > raw` (3 ramas), preservando el geoId-path
para las 8 ciudades del `_CANONICAL_MAPPING` y el legacy
`?location=<raw>` para ciudades sin NINGÚN mapping (no regresión).

**Close date**: 2026-06-10 (ISO).

## Traceability — observation IDs de los artefactos del change

| Topic | Observation ID | Status |
|---|---|---|
| `sdd/backend-linkedin-location-fallback/explore` | #332 | explored |
| `sdd/backend-linkedin-location-fallback/proposal` | #333 | proposed |
| `sdd/backend-linkedin-location-fallback/spec` | #336 | specified (1 multi-domain delta spec, 3 domains) |
| `sdd/backend-linkedin-location-fallback/design` | #338 | designed (13 architecture decisions) |
| `sdd/backend-linkedin-location-fallback/tasks` | #340 | planned (4 work units) |
| `sdd/backend-linkedin-location-fallback/apply-progress` | #345 | applied (4 commits) |
| `sdd/backend-linkedin-location-fallback/discovery` | #346 | L607 shadowing bug discovery (RISK context) |
| `sdd/backend-linkedin-location-fallback/discovery` | #347 | Assertion quality audit (0 trivial assertions) |
| `sdd/backend-linkedin-location-fallback/verify-report` | #348 | verified (PASS, 0/0/3) |
| `sdd/backend-linkedin-location-fallback/archive-report` | (este report) | archived |

## Type

`feature` — el cambio introduce la capability
`linkedin-structured-location-fallback` (el dict complementario al
`_CANONICAL_MAPPING` con triplets `(city, province, country)` para
10 ciudades españolas) y extiende 2 capabilities preexistentes
(`location-resolver` con un tercer método `resolve_structured`, y
`linkedin-scraper` con la rama intermedia del URL builder).

## Capability name

`backend-linkedin-location-fallback` — la fix del "Antequera/Málaga
sin filtro de ubicación" bug. La mitigación previa (geoId path del
`backend-scraper-query-tuning`, PR #4 merged 2026-06-10) cubría
las 8 ciudades canónicas con `?geoId=<int>`. Este cambio agrega
el fallback intermedio `?location=City,Province,Country` para
ciudades con triplet conocido pero sin geoId (10 ciudades v1,
1 VERIFIED + 9 SPECULATIVE).

## Commits (4, branch `feature/backend-linkedin-location-fallback`)

| Hash | Subject | Work Unit | Lines |
|---|---|---|---|
| `a14b6a3` | `feat(location-resolver): add resolve_structured for 10-city triplet mapping` | T-001 (Resolver foundation: Protocol + 10-city dict + impl + 27 unit tests) | +400/-10 |
| `a1394b5` | `feat(linkedin-scraper): _build_url priority geoId > structured > raw` | T-002 (Scraper URL plumb: `_build_url` + `search()` + closure + 10 unit tests) | +437/-9 |
| `4534ed4` | `test(composition): verify shared location_resolver instance` | T-003 (Composition verify + 3 test doubles extended for Protocol conformance) | +28/-7 |
| `be4b783` | `docs(linkedin): document structured location fallback + LIVE test gate` | T-004 (README docs + 2 grep tests + 1 LIVE test gated) | +58/-2 |

> **Total diff vs `f41aa90`**:
> `git diff --stat f41aa90..be4b783 | tail -1`
> → `16 files changed, 2755 insertions(+), 34 deletions(-)` (~2,721 net LOC).
> Single PR, bien por debajo del review budget de 5,000 líneas.
> Ningún commit incluye `Co-Authored-By` trailer (regla AGENTS.md #6).
> Cada commit < 600 LOC.

## Verify verdict

`verified-pass` — 0 CRITICAL, 0 WARNING, **3 SUGGESTION non-blocking**
(per obs #348 §9 + orchestrator cache):

1. **[9 speculative city mappings pending LIVE validation]**
   Las entries de `fuengirola`, `marbella`, `toledo`, `salamanca`,
   `cadiz`, `granada`, `gijon`, `leon`, `vigo` son SPECULATIVE (su
   province/country fueron inferidos de la división administrativa
   de España; el LIVE test gate `LLM_LIVE_TESTS=1` valida 1 de 10,
   `antequera`; los otros 9 están diferidos). Follow-up opcional:
   change con 9 LIVE tests gated adicionales, uno por ciudad.
2. **[`test_chat_endpoint_2stage.py` extension no shipped]**
   La propuesta §4.5 mencionaba un end-to-end scenario
   `intent.location="Antequera"` → URL contains
   `location=Antequera%2CAndaluc%C3%ADa%2CSpain`. NO se shippeó
   (era "nice to have", no estaba en tasks.md T-001..T-004).
   Follow-up opcional: añadir 1 mock-friendly end-to-end test.
3. **[Historical `safe=","` mistake documented]** Inicialmente
   usé `quote(s, safe=",")` en la GREEN attempt de T-002, pero las
   assertions de los tests (y la URL real del user) mostraron que
   `%2C` es correcto. Removí el `safe=","` y usé el default.
   Documentado en apply-progress §"Deviations". Sin code action
   necesario.

**Spec compliance matrix**: 38/38 scenarios ✅ per obs #348 §"Spec
Compliance Matrix" (100%). Distribución:
- REQ-D1..D6 (location-resolver `resolve_structured`): 17 scenarios
- REQ-D7..D10 (linkedin-scraper URL priority + encoding): 12 scenarios
- REQ-D11..D15 (linkedin-structured-location-fallback): 9 scenarios

**Quality gates GREEN**:

- `bash scripts/check.sh` (ruff + mypy + pytest): **1,181 passed,
  14 skipped, 0 failed**.
- `uv run mypy --strict`: **Success: no issues found in 176 source files**.
- `uv run ruff format --check`: **177 files already formatted**.
- `git status` (pre-archive): clean.

**Test count delta**:

| Metric | Baseline (f41aa90) | Final (be4b783) | Delta |
|---|---|---|---|
| Passed | 1,142 | 1,181 | **+39** |
| Skipped | 13 | 14 | **+1** (LIVE test gated) |
| Failed | 0 | 0 | 0 |
| Regressions | 0 | 0 | 0 |

## OpenSpec sync (this archive)

Delta spec source:
`openspec/changes/archive/2026-06-10-backend-linkedin-location-fallback/specs/backend-linkedin-location-fallback/spec.md`
(Domain 1 + Domain 2 + Domain 3 in a single multi-domain delta file).

The archive split the multi-domain delta into 3 separate global
spec files, one per capability, and APPENDED/MERGED into the
existing source-of-truth tree at `openspec/specs/`. The sync is
**append-only** — the 2 pre-existing canonical specs
(`chat-streaming`, `frontend-scaffold`) remain intact.

| Target spec file | Action | Details |
|---|---|---|
| `openspec/specs/location-resolver/spec.md` | **CREATED (foundational, MERGED with sister change)** | New foundational spec combining: (a) the sister change's `resolve_infojobs` requirements (REQ-PROV-LOC-001, REQ-PROV-LOC-001-MOD, REQ-PROV-LOC-002, REQ-PROV-LOC-003) promoted from `openspec/changes/archive/2026-06-10-backend-infojobs-provinces/specs/location-resolver/spec.md`, AND (b) this change's `resolve_structured` requirements (REQ-LI-LOC-001..006) from Domain 1 of the delta. The resulting file documents the triple-method Protocol contract (`resolve` + `resolve_infojobs` + `resolve_structured`) on the SAME `LocationResolverPort`. 434 lines, 8 requirements, 24+ scenarios. The L607 shadowing bug is documented as known risk (see "Sister change coordination" below). |
| `openspec/specs/linkedin-scraper/spec.md` | **CREATED (foundational)** | New foundational spec promoted from Domain 2 of the delta. Covers the `_build_url` priority `geoId > structured > raw` (REQ-LI-SCR-001), URL encoding with NFC tildes + UTF-8 multibyte (REQ-LI-SCR-002), `search()` calls both resolvers exactly once with closure capture (REQ-LI-SCR-003), and backward compat with `location_resolver=None` and `resolve_structured=None` (REQ-LI-SCR-004). 190 lines, 4 requirements, 12 scenarios. |
| `openspec/specs/linkedin-structured-location-fallback/spec.md` | **CREATED (new capability)** | New capability spec promoted from Domain 3 of the delta. Covers the 10-city v1 mapping (REQ-LI-SFB-001), the VERIFIED/SPECULATIVE provenance (REQ-LI-SFB-002), country in English with Spanish alias (REQ-LI-SFB-003), province accent preservation (REQ-LI-SFB-004), and the LIVE test gate `LLM_LIVE_TESTS=1` (REQ-LI-SFB-005). 211 lines, 5 requirements, 11 scenarios. |
| `openspec/specs/chat-streaming/spec.md` | **UNCHANGED** (pre-existing) | Not affected by this change. |
| `openspec/specs/frontend-scaffold/spec.md` | **UNCHANGED** (pre-existing) | Not affected by this change. |

> **Sync discipline note**: The multi-domain delta spec (one file
> with 3 `## Domain N` blocks) was split into 3 separate global
> specs because the `openspec/specs/{domain}/spec.md` convention
> requires ONE spec file per capability, with the requirement
> names matching the `REQ-D1..D15` IDs from the spec. The
> `LocationResolverPort` extension is special: it grew the SAME
> Protocol with two new methods (`resolve_infojobs` from the
> sister change, `resolve_structured` from this change), and
> BOTH extensions are recorded in the SAME global
> `location-resolver` spec as a chronological addendum.

## Sister change coordination

This change and the sister change `backend-infojobs-provinces`
both extend `LocationResolverPort` with NEW methods (no name
collision — `resolve_infojobs()` returns
`tuple[int | None, int | None]`, `resolve_structured()` returns
`tuple[str, str, str] | None`). Both changes were developed in
parallel on separate branches (`feature/backend-linkedin-location-fallback`
and `feature/backend-infojobs-provinces`) and both have already
passed `sdd-verify` with verdict `verified-pass` (per
obs #348 and the sister change's obs #342).

**Key coordination facts**:

1. **L607 shadowing fix is on the SISTER branch only.** Per
   `apply-progress` §"Risks" (obs #345) and the explicit discovery
   in obs #346, the `app_factory.py:607` shadowing bug
   (`HardcodedLocationResolver()` constructor call that shadows
   the L185 instance for the chat-filter use case) is PRESENT on
   this branch and ALREADY FIXED on the sister branch (sister's
   T-003 commit `eec2526`). Per task instructions, this change
   did NOT fix L607 — it's the sister change's job. The merge
   at PR time will combine both branches' Protocol extensions
   and the L185/L522 sharing while applying the L607 fix.

2. **Both test doubles grew identically.** Both changes needed
   to add their respective second/third method to 2 test doubles
   (`FakeLocationResolver` in `test_filter_use_case.py` and
   `_FakeLocationResolver` in `test_linkedin_scraper.py`). The
   sister change added `resolve_infojobs`; this change added
   `resolve_structured` (and a third double, `_StubResolver` in
   `test_linkedin_settings.py`, was created in this change's
   T-001 commit to satisfy mypy --strict conformance for the
   extended Protocol). The merge at PR time will produce a
   triple-method `FakeLocationResolver` that satisfies the
   triple-method `LocationResolverPort`.

3. **Composition test added in T-003 is satisfied on this branch.**
   `test_resolver_shared_with_linkedin_scraper_settings` (in
   `test_composition.py`) PASSES on `f41aa90` because the L185
   instance is correctly shared with `app.state.location_resolver`
   and `LinkedInScraperSettings`. The L607 shadow only affects
   the chat-filter path, which is not exercised by this change's
   test. The merge at PR time must preserve this L185 sharing
   while also applying the sister's L607 removal.

4. **`location-resolver` global spec MERGES both branches' deltas.**
   The sister change's archive commit (`e786c42`) already promoted
   its `resolve_infojobs` delta to `openspec/specs/location-resolver/spec.md`
   on its OWN branch. Since this branch is based on `f41aa90`
   (pre-sister-merge), the global `location-resolver/spec.md` did
   NOT exist on this branch when this archive started. This
   archive therefore CREATES the global `location-resolver/spec.md`
   from scratch, embedding BOTH the sister's `resolve_infojobs`
   requirements AND this change's `resolve_structured` requirements
   in a single foundational spec. The result is the post-merge
   source of truth.

5. **Merge order recommendation** (per design obs #338 §10):
   merge **`backend-linkedin-location-fallback` (this) first** →
   `backend-infojobs-provinces` (sister) second. Rationale: this
   change has a smaller surface area (4 commits vs. 5) and a
   cleaner test (1 LIVE gated); the sister's L607 fix is a
   single-line removal that lands cleanly on top. The
   orchestrator will open 2 separate PRs (one per branch), and
   the merge conflict resolution at PR time (NOT this archive's
   job) will combine the L185/L522 sharing + L607 removal +
   3-method Protocol.

## Source of Truth Updated

The following specs now reflect the new behavior of the system:

- `openspec/specs/location-resolver/spec.md` — NEW foundational
  spec, 434 lines. Captures the triple-method
  `LocationResolverPort.resolve() / resolve_infojobs() / resolve_structured()`
  contract.
- `openspec/specs/linkedin-scraper/spec.md` — NEW foundational
  spec, 190 lines. Captures the 3-branch URL priority
  `geoId > structured > raw`.
- `openspec/specs/linkedin-structured-location-fallback/spec.md` —
  NEW capability spec, 211 lines. Captures the 10-city
  `_STRUCTURED_MAPPING` and the LIVE test gate.

The 2 pre-existing canonical specs (`chat-streaming`,
`frontend-scaffold`) remain intact (archive is APPEND-ONLY for
source of truth — the spec sync is additive, never destructive).

## SDD Cycle Complete

The change `backend-linkedin-location-fallback` has been fully
planned (5/8 phases), implemented (4 commits, all GREEN), verified
(`verified-pass` 0/0/3), and archived (this report). The branch
`feature/backend-linkedin-location-fallback` is ready for push +
PR. The sister change `backend-infojobs-provinces` follows the
same lifecycle on its own branch.

## Known follow-ups (from verify SUGGESTIONS)

1. LIVE test for the 9 SPECULATIVE cities (one per city, gated
   `LLM_LIVE_TESTS=1`).
2. End-to-end test in `test_chat_endpoint_2stage.py` for
   `intent.location="Antequera"` → URL contains
   `location=Antequera%2CAndaluc%C3%ADa%2CSpain`.
3. (None — historical `safe=","` mistake is documented, no
   code action needed.)

## Skill Resolution

`paths-injected` — orchestrator pre-resolved `_shared/SKILL.md`,
`sdd-archive/SKILL.md`, `_shared/openspec-convention.md`,
`_shared/persistence-contract.md`, `_shared/sdd-phase-common.md`.
All loaded at the start of the turn.

## Related observations

- **Explore**: #332
- **Proposal**: #333
- **Spec**: #336
- **Design**: #338
- **Tasks**: #340
- **Apply progress**: #345
- **Discoveries (RISK context)**: #346 (L607 shadowing),
  #347 (assertion quality audit)
- **Verify report**: #348
- **Archive report (this)**: engram topic
  `sdd/backend-linkedin-location-fallback/archive-report`
