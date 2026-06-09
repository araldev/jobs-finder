# Archive Report: backend-scraper-query-tuning

## Status
**Closed** — implementation complete, verification **PASS WITH WARNINGS**
(0 CRITICAL, 4 WARNING non-blocking, 3 SUGGESTION non-blocking). The
change fixes a pre-existing bug in `fix-linkedin-geoid` (the `geo_id`
kwarg was never forwarded from `search()` to `_make_fetch_one_page`),
adds an opt-in `keyword_score` relevance ranking, an InfoJobs
client-side 0-token-title filter, defensive partial-results handling,
a `query_tokens` cache key field, the `ENABLE_KEYWORD_SCORING` env
var, and routes the 3 new kwargs through `GET /jobs`.

## Type
`feature` + `bugfix` — extends the aggregator with
relevance/filtering/defensive capabilities AND fixes a pre-existing
bug from `fix-linkedin-geoid`.

## Capability name
`aggregator-relevance` — the aggregator's relevance ranking, source
filtering, and defensive partial-results behavior. **New canonical
capability** (no `openspec/specs/aggregator-relevance/` existed
before).

## Traceability — observation IDs of the change artifacts

| Topic | Observation ID | Status |
|---|---|---|
| `sdd/backend-scraper-query-tuning/explore` | #321 | explored |
| `sdd/backend-scraper-query-tuning/proposal` | #322 | proposed → `status: archived` after this report |
| `sdd/backend-scraper-query-tuning/spec` | #323 | specified |
| `sdd/backend-scraper-query-tuning/design` | #324 | designed |
| `sdd/backend-scraper-query-tuning/tasks` | #325 | planned |
| `sdd/backend-scraper-query-tuning/apply-progress` | #326 | applied |
| `sdd/backend-scraper-query-tuning/verify-report` | #327 | verified (PASS WITH WARNINGS) |
| `sdd/backend-scraper-query-tuning/archive-report` | #328 (this report) | archived |

## Commits (19, on `feature/backend-scraper-query-tuning`)

Strict TDD pattern (RED → GREEN) per work unit. Listed
chronologically (oldest → newest):

| # | Hash | Subject | Work unit |
|---|---|---|---|
| 1  | `63a94a8` | `test(linkedin): add geoId plumb failing tests (RED)`           | T-001 RED   |
| 2  | `ea60d61` | `fix(linkedin): forward geo_id through pagination loop and inject location_resolver` | T-001 GREEN |
| 3  | `2d9dbf6` | `feat(aggregator): add keyword_score pure function for opt-in relevance ranking` | T-002       |
| 4  | `c86fe67` | `test(aggregator): add filter_infojobs_results and tokenize failing tests (RED)` | T-003 RED   |
| 5  | `7a0ad42` | `feat(aggregator): add filter_infojobs_results and tokenize helpers` | T-003 GREEN |
| 6  | `bf39885` | `refactor(keyword_score): reuse canonical tokenize from aggregator_filters` | T-003.1     |
| 7  | `9009b98` | `test(aggregator): add infojobs filter and keyword_score sort failing tests (RED)` | T-004 RED   |
| 8  | `c721d05` | `feat(aggregator): integrate infojobs filter and opt-in keyword_score sort` | T-004 GREEN |
| 9  | `6796cc1` | `test(aggregator): add defensive partial-results and AllSourcesFailedError failing tests (RED)` | T-005 RED   |
| 10 | `eebd7cc` | `feat(aggregator): add defensive partial-results handling with AllSourcesFailedError` | T-005 GREEN |
| 11 | `1233d11` | `test(cache): add query_tokens cache key failing tests (RED)`   | T-006 RED   |
| 12 | `3910b58` | `feat(cache): include query_tokens in JobSearchCacheKey for better hit rate` | T-006 GREEN |
| 13 | `bb3ed79` | `test(app_factory): add HardcodedLocationResolver injection failing tests (RED)` | T-007 RED   |
| 14 | `7dc0da3` | `feat(app_factory): inject HardcodedLocationResolver into LinkedInScraperSettings` | T-007 GREEN |
| 15 | `e08fc5f` | `test(config): add ENABLE_KEYWORD_SCORING env var failing tests (RED)` | T-008 RED   |
| 16 | `6c15596` | `feat(config): add ENABLE_KEYWORD_SCORING env var for opt-in relevance ranking` | T-008 GREEN |
| 17 | `ca9b696` | `test(aggregator_route): add query_tokens, enable_keyword_scoring, linkedin_geo_id forwarding failing tests (RED)` | T-009 RED   |
| 18 | `881f0ea` | `feat(aggregator_route): forward query_tokens, enable_keyword_scoring, and linkedin_geo_id to use case` | T-009 GREEN |
| 19 | `5569efb` | `docs(backend): document ENABLE_KEYWORD_SCORING, geoId plumb, InfoJobs filter, defensive partial results` | T-010       |

## PRs
(Per preflight `ask-always` strategy, the orchestrator decides on PR
creation. The branch `feature/backend-scraper-query-tuning` is **NOT
yet pushed**. The orchestrator will prompt the user to push + open
PR after archive closes.)

## Delta specs synced to

- **Created**: `openspec/specs/aggregator-relevance/spec.md` (canonical
  new capability, copied from the change's delta spec).
- The change's delta spec lived at
  `openspec/changes/.../specs/backend-scraper-query-tuning/spec.md`
  and was promoted (not merged into an existing capability) because
  `aggregator-relevance` did not exist as a canonical capability
  before this change.
- **7 REQ-*** promoted: `REQ-LOC-001`, `REQ-LOC-002`, `REQ-FILTER-001`,
  `REQ-SCORE-001`, `REQ-CACHE-001`, `REQ-DEFENSIVE-001`, `REQ-TEST-001`.

## Archive contents

- `explore.md` ✅
- `proposal.md` ✅
- `specs/backend-scraper-query-tuning/spec.md` ✅
- `design.md` ✅
- `tasks.md` ✅ (10/10 tasks complete: T-001 → T-010)
- `verify-report.md` ✅ (PASS WITH WARNINGS, 0 CRITICAL)

## Spec → code coverage (from verify-report)

| REQ | Status |
|---|---|
| REQ-LOC-001 (LinkedIn `geoId` plumb)        | PASS |
| REQ-LOC-002 (`app_factory` wires resolver)  | PASS |
| REQ-FILTER-001 (InfoJobs 0-token filter)   | PASS |
| REQ-SCORE-001 (`keyword_score` opt-in)      | PASS |
| REQ-CACHE-001 (`query_tokens` in cache key) | PASS |
| REQ-DEFENSIVE-001 (partial + 502)           | PASS |
| REQ-TEST-001 (coverage matrix)              | PASS |

## Pre-conditions for the next change
1. `feature/backend-scraper-query-tuning` is ready to push and open
   a PR (NOT pushed yet — orchestrator prompts user).
2. The 4 WARNINGs from the verify report are non-blocking but should
   be addressed in a follow-up if the user wants full coverage
   (largest: diff size grew 73% over design forecast; tests account
   for most of that growth).
3. The 3 SUGGESTIONs are non-blocking (mostly documentation nits).

## Next recommended

1. **`feature/backend-scraper-query-tuning` → `git push` + open PR**
   (orchestrator prompts user; `ask-always` delivery strategy).
2. **`backend-infojobs-provinces`** (SDD change) — use
   `provinceIds=<id>` and `countryIds=<id>` in the InfoJobs scraper
   URL. The user found Málaga = province 34, Spain = country 17 in
   InfoJobs. The current `filter_infojobs_results` is a mitigation;
   the real fix is to plumb province/country IDs (analogous to how
   this change plumbed `geoId` for LinkedIn). Forecast: 500–1000
   LOC (mapping + URL builder + tests + Settings field).
3. **`backend-linkedin-location-fallback`** (SDD change) — when
   `HardcodedLocationResolver` doesn't have a `geoId` for the user's
   location, fall back to the format
   `location=<city>,<province>,<country>` (e.g.
   `location=Antequera,Andalucía,Spain`) instead of the current
   `location=<raw_string>`. Forecast: 200–400 LOC (formatter +
   tests).
4. **`backend-aggregator-ranking-strategy`** (optional, future) —
   replace the heuristic `keyword_score` with an LLM-based relevance
   ranking (similar to the chat filter) when
   `ENABLE_KEYWORD_SCORING=true`. Not in v1 scope; this is a future
   enhancement if the heuristic proves insufficient.

## Discovery / decisions worth remembering for future changes

- The `HardcodedLocationResolver` pattern is reusable for InfoJobs
  provinces/countries. The same construction (Pydantic
  `ValidationError` on startup for invalid mapping, no-op on
  unmapped values) can be copied.
- The `paginated_search` helper at
  `infrastructure/pagination.py` accepts the `geo_id` kwarg; the bug
  fixed by T-001 was in the **caller**, not the helper. A future
  audit of `fix-linkedin-geoid` should look for similar "kwarg
  added to closure factory but never passed" patterns.
- The `keyword_score` heuristic is intentionally simple: tokenize
  `title + company + description` (lowercased, punctuation-stripped,
  Unicode-safe), count overlap with query tokens, boost title
  matches. The LLM chat filter is the escape hatch for nuanced
  relevance; the heuristic exists to drop the most egregious
  zero-overlap results client-side.
- The `AllSourcesFailedError` → 502 contract is a **breaking change**
  from the v1 silent 200+empty-list behavior. Document for any
  downstream clients. The `X-Aggregator-Errors: <failed_source>`
  header is preserved for partial-failure paths.
- The `WARNING` log emitted by `_call_one` does **not** pass
  `request_id` via `extra={...}`; the `request_id` reaches the
  rendered JSON log line through the `LogRecordFactory` in
  `presentation/logging_config.py:89-116` (which auto-injects from
  the `ContextVar` set by `RequestIdMiddleware`). The dependency
  rule is preserved (aggregator does NOT import from
  `presentation/`). Worth a docstring note in `_call_one` so the
  next reader doesn't think `request_id` is missing.

## Skill resolution
`paths-injected` — orchestrator pre-resolved
`sdd-archive/SKILL.md` + `_shared/sdd-phase-common.md` +
`openspec-convention.md`.
