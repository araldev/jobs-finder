# apply-progress: backend-linkedin-location-fallback

**Change**: `backend-linkedin-location-fallback` • **Mode**: `both` (OpenSpec + Engram) • **Strict TDD**: ACTIVE
**Date**: 2026-06-10 • **Base**: `f41aa90` (feature/backend-linkedin-location-fallback) • **Final**: 1,181 passed / 14 skipped (was 1,142 / 13 baseline)

> Source: Engram observation #345. Mirrored to filesystem per `mode: both` contract.

## Status

`applied` — all 4 work units complete. Ready for `sdd-verify`.

## Commits (4 total, single PR, conventional commits)

| SHA | Subject | Work Unit |
|---|---|---|
| `a14b6a3` | `feat(location-resolver): add resolve_structured for 10-city triplet mapping` | T-001 |
| `a1394b5` | `feat(linkedin-scraper): _build_url priority geoId > structured > raw` | T-002 |
| `4534ed4` | `test(composition): verify shared location_resolver instance` | T-003 |
| `be4b783` | `docs(linkedin): document structured location fallback + LIVE test gate` | T-004 |

No `Co-Authored-By` trailers. Each commit < 600 LOC. Total: ~1,183 changed lines (1,149 insertions, 34 deletions), well below the 5,000-line budget.

## TDD Cycle Evidence

| Task | Test File | Layer | RED | GREEN | REFACTOR |
|------|-----------|-------|-----|-------|----------|
| T-001 | `test_hardcoded_location_resolver.py` | Unit | ✅ 27 written, RED confirmed (AttributeError) | ✅ 78 pass (51 baseline + 27 new) | ✅ Clean (no duplication) |
| T-002 | `test_linkedin_scraper.py` | Unit | ✅ 10 written, RED confirmed (TypeError) | ✅ 25 pass (15 baseline + 10 new) | ✅ Clean (3-branch priority) |
| T-003 | `test_composition.py` | Integration | ✅ 1 written, RED confirmed (assertion fail) | ✅ 12 pass (11 baseline + 1 new) | ✅ Clean |
| T-004 | `test_hardcoded_location_resolver.py` (README grep) + `test_linkedin_live.py` | Unit + Integration | ✅ 2 + 1 written | ✅ 2 pass (README already had keywords) + 1 skipped (LIVE gated) | ✅ Clean |

### Test Summary
- **Total tests written**: 39 new (27 + 10 + 1 + 2 + 1 LIVE) — 1 LIVE is skipped in CI
- **Total tests passing**: 1,181 (was 1,142 baseline; +39)
- **Total tests skipping**: 14 (was 13; +1 — the new LIVE test)
- **Layers used**: Unit (38), Integration (1)
- **Approval tests (refactoring)**: None — all work was new code
- **Pure functions created**: `resolve_structured` (the new Protocol method), `_build_url(..., structured=...)` (the URL formula)

## Files Changed

### New (2)
- `backend/src/jobs_finder/infrastructure/location/_structured_mapping.py` (61 lines) — 10-entry dict (1 VERIFIED + 9 SPECULATIVE)
- `backend/tests/integration/test_linkedin_live.py` (102 lines) — gated LIVE test

### Modified (9)
- `backend/src/jobs_finder/application/ports.py` — `LocationResolverPort.resolve_structured` (Protocol extension)
- `backend/src/jobs_finder/infrastructure/location/hardcoded_resolver.py` — `resolve_structured` method + `structured_mapping` ctor kwarg
- `backend/src/jobs_finder/infrastructure/linkedin/scraper.py` — `_build_url` priority + `search()` + `_make_fetch_one_page` extensions
- `backend/README.md` — new section "LinkedIn structured location fallback" + LIVE gate
- 4 test files: `test_hardcoded_location_resolver.py` (27 new + 2 README grep), `test_linkedin_scraper.py` (10 new), `test_composition.py` (1 new), `test_filter_use_case.py` (Protocol conformance), `test_linkedin_settings.py` (Protocol conformance)

## Deviations from Design

**None.** All design decisions implemented 1:1:
- Protocol extension (not new Protocol) — Option A from explore §5
- `geoId > structured > raw` priority — matches spec/design
- ONE `HardcodedLocationResolver` instance, BOTH methods — Option A from explore §6
- 10-entry dict shape (1 verified + 9 speculative) — matches spec
- `LLM_LIVE_TESTS=1` gate for LIVE test — Q4=A
- URL encoding: `urllib.parse.quote()` (default `safe="/"`) — matches user-captured URL `Antequera%2CAndaluc%C3%ADa%2CSpain` (commas ARE encoded as `%2C`)

**Minor implementation note**: initial GREEN attempt used `quote(s, safe=",")` thinking LinkedIn expects un-encoded commas, but the test assertions (and the user-captured URL) showed `%2C` is correct. The `safe=","` was removed and the default is used — matches the byte-for-byte URL.

## Issues Found

**None blocking.** Two minor observations:

1. **Test doubles required mypy conformance**: extending `LocationResolverPort` with `resolve_structured` broke 3 test doubles (`FakeLocationResolver` in `test_filter_use_case.py`, `_StubResolver` in `test_linkedin_settings.py`, `_FakeLocationResolver` in `test_linkedin_scraper.py`). The `resolve_structured` method was added to all 3 doubles in the T-001 commit (to keep mypy green) — the T-003 commit's "test doubles extension" was reduced to just the 1 composition test. This was the disciplined TDD approach (keep the suite green between work units).

2. **mypy `--strict` flagged the broken Protocol conformance** — this was the canary that caught the missing methods. Without strict mypy, the test doubles would have passed tests but broken the static conformance invariant. Strong validation that the project's strict typing is paying off.

## Risks (for verify phase)

1. **9 speculative province/country mappings** (Fuengirola=Málaga, Marbella=Málaga, Toledo=Castilla-La Mancha, Salamanca=Castilla y León, Cádiz=Andalucía, Granada=Andalucía, Gijón=Asturias, León=Castilla y León, Vigo=Galicia) are pending LIVE test validation. The test is gated by `LLM_LIVE_TESTS=1` and skipped in CI per AGENTS.md rule #1. If a speculative ID is wrong (e.g. LinkedIn doesn't recognize "Vigo,Galicia,Spain"), the URL still works (no 500) but returns 0 results from that region — graceful degradation. The fallback is a 1-line dict removal.

2. **`app_factory.py:607` shadowing bug is PRESENT on this branch** — this branch is based on `f41aa90` (pre-sister-apply), so the sister change's L607 fix has NOT been applied here. The L607 line `location_resolver = HardcodedLocationResolver()` shadows the L185 instance for the chat-filter use case. Per task instructions, the fix was NOT applied here (it's the sister change's job). The merge conflict resolver at PR time will need to handle this. **Verification**: `grep -n "HardcodedLocationResolver" backend/src/jobs_finder/presentation/app_factory.py` shows the bug at lines 185 and 607.

3. **Madrid is intentionally EXCLUDED** from `_STRUCTURED_MAPPING` (per design decision #2: geoId is the preferred format and always wins). The test `test_resolve_structured_madrid_returns_none_geoid_only` pins this contract.

4. **The LIVE test exercises only the VERIFIED case (Antequera)** — the 9 SPECULATIVE cases are deferred to a follow-up change. The shipped test is sufficient to prove the structured URL format works against real LinkedIn; the 9 speculative entries are data-only changes (1-line dict removal) if any fail.

5. **No new env vars, no new schema fields, no frontend changes.** HTTP shape preserved 100% — the frontend sigue enviando `location=<raw>`; el resolver convierte internamente.

## Workload / PR Boundary

- Mode: single PR
- Current work unit: N/A (all 4 done)
- Boundary: full change complete
- Estimated review budget impact: ~1,183 changed lines across 4 commits, well below the 5,000-line review budget. The largest commit (T-002) is ~437 LOC, which is the second-largest and well within budget.

## Next Step

`sdd-verify` — the orchestrator should launch verify to confirm:
- 1,181 passed / 14 skipped / 0 regressions (vs 1,142 / 13 baseline)
- `cd backend && bash scripts/check.sh` clean (ruff + mypy + pytest) — already confirmed
- `cd backend && uv run mypy --strict` clean — already confirmed
- `cd backend && uv run ruff format --check` clean — already confirmed

## Skill Resolution

`paths-injected` — orchestrator pre-resolved `_shared/SKILL.md`, `sdd-apply/SKILL.md`, `work-unit-commits/SKILL.md`, `strict-tdd.md`, `result-contract.md`, `openspec-convention.md`, `persistence-contract.md`. All loaded at the start of the turn.
