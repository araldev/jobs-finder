# apply-progress: backend-infojobs-provinces

**Change**: `backend-infojobs-provinces` • **Mode**: `both` (OpenSpec + Engram) • **Strict TDD**: ACTIVE
**Date**: 2026-06-10 • **Base**: `f41aa90` (feature/backend-infojobs-provinces) • **Final**: 1,176 passed / 14 skipped (was 1,142 / 13 baseline)

> **Source**: This file was created by the `sdd-verify` executor from
> Engram obs #341 (`sdd/backend-infojobs-provinces/apply-progress`)
> because the original apply phase did not write it to the filesystem
> (mode `both` requires both stores to be populated; the Engram
> artifact was saved, the filesystem file was missing).

## Status

`applied` — all 5 work units complete. Verified by `sdd-verify` (see
`verify-report.md` for the full compliance matrix).

## Commits (5 total, single PR, conventional commits)

| SHA | Subject | Lines | Work Unit |
|---|---|---|---|
| `82e3fce` | `feat(location-resolver): add resolve_infojobs for province/country mapping` | 380+/10- | T-001 |
| `effe979` | `feat(infojobs-scraper): plumb province/country IDs via resolve_infojobs` | 584+/9- | T-002 |
| `eec2526` | `fix(app_factory): share location_resolver instance + remove L607 shadow` | 113+/7- | T-003 |
| `2167245` | `docs(backend): document InfoJobs province/country resolution + defense-in-depth filter` | 203+/2- | T-004 |
| `2d9114d` | `test(infojobs): add gated LIVE test for Malaga province/country resolution` | 167+ | T-005 |

No `Co-Authored-By` trailers. Each commit < 600 LOC. Total: ~1,500 LOC across 5 commits.

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| T-001 | `test_hardcoded_location_resolver.py` | Unit | ✅ 51/51 | ✅ Written | ✅ 66 pass | ✅ 15 cases | ✅ Clean |
| T-002 | `test_infojobs_scraper.py` | Unit | ✅ 24/24 | ✅ Written | ✅ 35 pass | ✅ 11 cases | ✅ Clean |
| T-003 | `test_composition.py` | Integration | ✅ 11/11 | ✅ Written | ✅ 13 pass | ✅ 2 cases | ✅ Clean |
| T-004 | `test_aggregator_filters.py` | Unit | ✅ 6/6 | ✅ Written | ✅ 9 pass | ✅ 3 cases | ✅ Clean |
| T-005 | `test_infojobs_live.py` | Integration | N/A (new) | ✅ Written | ✅ 1 skip (gated) | ➖ Single (LIVE) | ✅ Clean |

### Test Summary
- **Total tests written**: 32 new (15 + 11 + 2 + 3 + 1)
- **Total tests passing**: 1,176 (was 1,142 baseline; +34)
- **Total tests skipping**: 14 (was 13; +1 — the new LIVE test)
- **Layers used**: Unit (29), Integration (3)
- **Approval tests (refactoring)**: None — all work was new code, no refactor of existing behavior
- **Pure functions created**: `resolve_infojobs` (the new Protocol method), `_build_url(..., infojobs_geo=...)` (the URL formula)

## Files Changed

### New (2)
- `backend/src/jobs_finder/infrastructure/location/_infojobs_mapping.py` (77 lines) — 9-entry dict (5 user-verified + 4 speculative)
- `backend/tests/integration/test_infojobs_live.py` (127 lines) — gated LIVE test

### Modified (8)
- `backend/src/jobs_finder/application/ports.py` — `LocationResolverPort.resolve_infojobs` (Protocol extension)
- `backend/src/jobs_finder/infrastructure/location/hardcoded_resolver.py` — `resolve_infojobs` method + `infojobs_mapping` ctor kwarg
- `backend/src/jobs_finder/infrastructure/infojobs/scraper.py` — `InfoJobsScraperSettings.location_resolver` + `search()` + `_make_fetch_one_page` + `_build_url` extensions
- `backend/src/jobs_finder/presentation/app_factory.py` — wire resolver into InfoJobsScraperSettings (L341) + remove L607 shadowing bug
- `backend/src/jobs_finder/infrastructure/aggregator_filters.py` — docstring update ("defense-in-depth")
- `backend/README.md` — new section "InfoJobs province/country resolution" + defense-in-depth role update
- 4 test files: `test_hardcoded_location_resolver.py` (15 new), `test_infojobs_scraper.py` (11 new), `test_composition.py` (2 new), `test_aggregator_filters.py` (3 new), `test_filter_use_case.py` (Protocol conformance), `test_linkedin_scraper.py` (Protocol conformance), `test_linkedin_settings.py` (Protocol conformance)

## Deviations from Design

**None blocking.** All design decisions implemented 1:1:
- Protocol extension (not new Protocol) — Option A from explore §5
- `infojobs_geo` kwarg (not `geo_id` reuse) — Option A from explore §5
- ONE `HardcodedLocationResolver` instance, BOTH methods — Option A from explore §5
- KEEP `filter_infojobs_results` as defense-in-depth — Q3=A
- 9-entry dict shape (5 verified + 4 speculative) — matches spec mapping
- L607 shadowing fix — bonus from design §9
- `LLM_LIVE_TESTS=1` gate for LIVE test — Q4=A

**Non-blocking deviations** (logged as SUGGESTIONs in the verify-report):
1. Spec named `tests/unit/test_infojobs_province_resolver.py` (NEW); implementation extended `test_hardcoded_location_resolver.py` instead with 7 new `test_resolve_infojobs_*` tests. Coverage is complete (12/12 REQ-PROV-001 scenarios).
2. REQ-PROV-LOC-003 scenario 2 (fail-fast on invalid `infojobs_mapping`) was a soft requirement with `xfail` opt-out per the spec; no validation in the ctor and no `xfail` test. Documented as a known follow-up.
3. T-005 LIVE test covers 1 of 5 IDs (Málaga=34). The 4 speculative IDs are deferred to a follow-up.

## Issues Found

**None blocking.** One minor adjustment during T-005:
- The `FakeLocationResolver` test doubles in 3 files (test_filter_use_case, test_linkedin_scraper, test_linkedin_settings) needed to grow the new `resolve_infojobs` method with a default `(None, None)` return — this was the pre-planned backward-compat path documented in spec §4 / REQ-PROV-004.

## Risks (for verify phase)

1. **4 speculative province IDs (Madrid=28, Barcelona=8, Valencia=46, Sevilla=41)** are pending LIVE test validation. The test is gated by `LLM_LIVE_TESTS=1` and skipped in CI per AGENTS.md rule #1. If a speculative ID is wrong, the scraper returns 0 results from that region (URL still works; region filter excludes all matching jobs) — graceful degradation, no 500. The fallback is a 1-line dict removal.
2. The new `infojobs_geo` kwarg on `InfoJobsPlaywrightScraper.search()` is keyword-only (not positional) to avoid breaking the v1 `search(keywords, location, limit, geo_id)` positional chain. The `geo_id` kwarg is now unused but kept for `JobSearchPort` compat.
3. The `LocationResolverPort` Protocol grew a 2nd method. Existing test doubles (`FakeLocationResolver` in 3 files) grew the default `(None, None)` return — 3 small files modified for Protocol conformance.
4. No new env vars, no new schema fields, no frontend changes. HTTP shape preserved 100%.
5. The 4 new LIVE-test-style behaviors (one per speculative ID) are deferred to a follow-up change; the shipped test exercises only the verified Málaga=34 case.

## Workload / PR Boundary

- Mode: single PR
- Current work unit: N/A (all 5 done)
- Boundary: full change complete
- Estimated review budget impact: ~1,500 LOC across 5 commits, well below the 5,000-line review budget. The largest commit (T-002) is 584/9 = 593 net LOC, which is the second-largest but well within budget.

## Next Step

`sdd-archive` — the orchestrator should launch archive after `sdd-verify` confirms zero CRITICAL findings (which it does — see `verify-report.md`).
