# Verify Report: backend-scraper-query-tuning

## Status
**PASS WITH WARNINGS**

## Summary
- **Change**: `backend-scraper-query-tuning`
- **Branch**: `feature/backend-scraper-query-tuning`
- **Commits**: 19 backend commits (T-001 → T-010 each as RED-then-GREEN, plus 1 REFACTOR)
- **Diff size (backend only)**: 2,317 lines added / 55 deleted across 24 files (forecast ~1,340 — actual ~2,317, see findings)
- **Tests added**: 45 new (49 added - 4 renamed for the new 502 / 6-field contract)
- **Test count**: 1,097 (forecast baseline per spec) → 1,142 (+45 net, +3 from existing 502-rename adjustments)
- **Coverage**: 7/7 REQ covered (REQ-LOC-001, REQ-LOC-002, REQ-FILTER-001, REQ-SCORE-001, REQ-CACHE-001, REQ-DEFENSIVE-001, REQ-TEST-001)
- **Quality gates**: pytest PASS (1,142 passed, 13 skipped); ruff check PASS; ruff format check PASS (175 files); mypy PASS (no issues in 174 source files)

## Quality gates

| Gate | Result | Details |
|---|---|---|
| `uv run pytest` | PASS | 1,142 passed, 13 skipped in 12.71s (skips are LLM live + Redis live, gated by env vars per AGENTS.md rule #1) |
| `uv run mypy` | PASS | Success: no issues found in 174 source files |
| `uv run ruff check` | PASS | All checks passed! |
| `uv run ruff format --check` | PASS | 175 files already formatted |
| Forbidden patterns | PASS | No `Co-Authored-By` trailers; no `^` floating versions in `pyproject.toml`; no TODO/FIXME/XXX/HACK markers in `src/jobs_finder/` |
| Pre-existing tests | PASS | All 1,097 baseline tests remain GREEN (verified by running the full suite) |
| New tests | PASS | 45 new tests across 12 test files (3 new files + 9 extended), all GREEN |
| Backwards compat | PARTIAL | 3 pre-existing tests were renamed to assert the new 502 contract (intentional, documented in `apply.risks` and per-spec REQ-DEFENSIVE-001 scenario 2) |

## Spec coverage matrix

| REQ | Implemented in | Tested by | Status |
|---|---|---|---|
| REQ-LOC-001 | `backend/src/jobs_finder/infrastructure/linkedin/scraper.py:249-250` (resolver call) + `:261` (`geo_id=geo_id` kwarg forwarded to `_make_fetch_one_page`) + `:306` (`_build_url(..., geo_id=geo_id)`) | `tests/unit/test_linkedin_scraper.py::test_search_uses_geo_id_when_resolver_returns_int`, `test_search_uses_location_when_resolver_returns_none`, `test_search_uses_location_when_resolver_is_none`, `test_resolver_called_once_per_search_not_per_page` | PASS |
| REQ-LOC-002 | `backend/src/jobs_finder/presentation/app_factory.py` (resolver instantiated unconditionally + passed to `LinkedInScraperSettings(location_resolver=...)`) | `tests/integration/test_composition.py::test_linkedin_scraper_has_resolver`, `test_resolver_built_when_chat_disabled` | PASS |
| REQ-FILTER-001 | `backend/src/jobs_finder/infrastructure/aggregator_filters.py` (`tokenize` + `filter_infojobs_results`) + `backend/src/jobs_finder/application/aggregator.py:444-465` (filter applied only to InfoJobs slice) | `tests/unit/test_aggregator_filters.py` (6 tests) + `tests/unit/test_aggregator.py::test_aggregator_applies_infojobs_filter`, `test_aggregator_does_not_filter_linkedin_or_indeed`, `test_aggregator_default_query_tokens_does_not_filter` | PASS |
| REQ-SCORE-001 | `backend/src/jobs_finder/infrastructure/keyword_score.py` (`keyword_score` pura) + `backend/src/jobs_finder/application/aggregator.py:487-496` (sort dispatch) + `backend/src/jobs_finder/infrastructure/config.py` (`enable_keyword_scoring` env var) | `tests/unit/test_keyword_score.py` (8 tests) + `tests/unit/test_aggregator.py::test_aggregator_sorts_by_keyword_score_when_enabled`, `test_aggregator_sorts_by_posted_at_when_disabled` + `tests/unit/test_aggregator_settings.py` (2 env var tests) | PASS |
| REQ-CACHE-001 | `backend/src/jobs_finder/application/ports.py:133` (`query_tokens: tuple[str, ...] = ()` 6th field) + `backend/src/jobs_finder/application/usecases/_cached_search.py:100,137` (kwarg + normalized tuple) | `tests/unit/test_cached_job_search_use_case.py::test_cache_key_default_query_tokens_is_empty`, `test_cache_key_includes_normalized_tokens`, `test_cache_key_distinguishes_queries`, `test_cache_separates_entries_by_query_tokens`, `test_job_search_cache_key_has_six_fields` | PASS |
| REQ-DEFENSIVE-001 | `backend/src/jobs_finder/application/aggregator.py:347-377` (per-source try/except + WARNING log) + `:417-419` (raise `AllSourcesFailedError` when `success_count == 0`) + `backend/src/jobs_finder/domain/exceptions.py:25-37` (`AllSourcesFailedError` subclass of `JobSearchError`) | `tests/integration/test_aggregator_defensive.py` (4 tests) + `tests/unit/test_exceptions.py` (3 tests) | PASS |
| REQ-TEST-001 | (meta-requirement) 45+ new tests pass; 7/7 spec scenarios covered | Full suite: 1,142 passed | PASS |

## Task completion matrix

| Task | Description | Commit(s) | Status |
|---|---|---|---|
| T-001 | Fix pre-existing `geo_id` kwarg bug + inject `location_resolver` in `LinkedInScraperSettings` | `63a94a8` (RED) + `ea60d61` (GREEN) | PASS |
| T-002 | `keyword_score` pure function + 8 tests | `2d9dbf6` (GREEN) | PASS |
| T-003 | `filter_infojobs_results` + `tokenize` helper + 6 tests | `c86fe67` (RED) + `7a0ad42` (GREEN) | PASS |
| T-003.1 | REFACTOR: reuse `tokenize` from `aggregator_filters` in `keyword_score` | `bf39885` | PASS |
| T-004 | Aggregator integrates filter + opt-in sort | `9009b98` (RED) + `c721d05` (GREEN) | PASS |
| T-005 | Aggregator defensive partial-results + `AllSourcesFailedError` + WARNING logs | `6796cc1` (RED) + `eebd7cc` (GREEN) | PASS |
| T-006 | Cache key includes `query_tokens` (6th field) | `1233d11` (RED) + `3910b58` (GREEN) | PASS |
| T-007 | `app_factory` wires `HardcodedLocationResolver` unconditionally | `bb3ed79` (RED) + `7dc0da3` (GREEN) | PASS |
| T-008 | `ENABLE_KEYWORD_SCORING` env var | `e08fc5f` (RED) + `6c15596` (GREEN) | PASS |
| T-009 | Route forwards `query_tokens` + `enable_keyword_scoring` + `linkedin_geo_id` | `ca9b696` (RED) + `881f0ea` (GREEN) | PASS |
| T-010 | README + `.env.example` docs | `5569efb` | PASS |

## Pre-existing bug fix verified (T-001)

**Real bug, real fix.** The `fix-linkedin-geoid` change added `geo_id` to the
`_make_fetch_one_page` signature, but the call at
`backend/src/jobs_finder/infrastructure/linkedin/scraper.py:231` was missing
the `geo_id=...` kwarg — the parameter existed in the closure but was
permanently `None`. The `geoId=<int>` URL parameter added in the prior change
**never reached production**.

T-001 closes this gap:

- `scraper.py:249-250` — `if geo_id is None and self._settings.location_resolver is not None: geo_id = self._settings.location_resolver.resolve(location)`. Called ONCE per `search()`, not per page (verified by `test_resolver_called_once_per_search_not_per_page`).
- `scraper.py:261` — `fetch_one_page=self._make_fetch_one_page(keywords, location, geo_id=geo_id)` (the actual fix — `geo_id` is now forwarded to the closure).
- `scraper.py:306` — `url = self._build_url(keywords, location, page_index * 25, geo_id=geo_id)` (the closure uses the captured `geo_id`).

`HardcodedLocationResolver` returns `104401670` for "malaga" /
"Málaga" / "MALAGA" (accent- and case-insensitive per the
existing resolver tests). With the fix, `GET /jobs?q=react&location=malaga`
now navigates to `https://www.linkedin.com/jobs/search?keywords=react&geoId=104401670&start=0`
instead of `&location=malaga&start=0` — the same `geoId` value the
test fixture expected from the original `fix-linkedin-geoid` change.

## Defensive aggregator verified (REQ-DEFENSIVE-001)

Read of `backend/src/jobs_finder/application/aggregator.py`:

- **Try/except per source** (lines 347-377): each `_call_one(source)` call is wrapped in `try/except JobSearchError`; non-`JobSearchError` exceptions re-raise to preserve the 500 path for programming bugs.
- **WARNING log** (lines 365-371): `logger.warning("aggregator source failed", extra={"source": source, "error_type": type(exc).__name__})`. The `request_id` is auto-injected into every `LogRecord` by `_install_request_id_factory()` in `presentation/logging_config.py:89-116` (which wraps `logging.getRequestId()` from the same `ContextVar` set by `RequestIdMiddleware` in `presentation/middleware.py:49`). The dependency rule is preserved because the aggregator does NOT import from `presentation/`; the request_id propagates through the existing log-factory pipeline.
- **Single log per source failure** (verified by `test_failed_source_logged_once`): the WARNING appears once per source call, not once per job the source would have returned.
- **All-fail → 502** (lines 417-419): `if success_count == 0: raise AllSourcesFailedError("all sources failed")`. The `AllSourcesFailedError` (in `domain/exceptions.py:25-37`) subclasses `JobSearchError`, which the registered handler in `presentation/exception_handlers.py:36` maps to HTTP 502.
- **Partial results → 200**: when 1 or 2 sources succeed, `success_count > 0`, no exception is raised, the result has the partial `list[AggregatedJob]` and the v1 200 contract is preserved.

## Cache key verified (REQ-CACHE-001)

Read of `backend/src/jobs_finder/application/ports.py:128-133`:

```python
class JobSearchCacheKey(NamedTuple):
    source: str
    keywords: str
    location: str
    limit: int
    geo_id: int | None = None
    query_tokens: tuple[str, ...] = ()
```

`tuple[str, ...] = ()` (not `frozenset`) per the design's deviation #9 and the spec's REQ-CACHE-001 statement. The verify report template mentioned `frozenset` in one bullet — that was a template wording issue, not an implementation deviation. The spec, design, and code all agree on `tuple[str, ...]`.

Read of `backend/src/jobs_finder/application/usecases/_cached_search.py:94-138`: the wrapper accepts `query_tokens: tuple[str, ...] = ()` and normalizes via `tuple(sorted(query_tokens))` so a `set` (or any iterable) from the caller becomes a canonical sorted tuple. The kwarg is NOT forwarded to the port (cache-only concern per REQ-CACHE-001).

## Backwards-compat verification

- **3 pre-existing tests were renamed** to assert the new 502 contract, per `apply.risks` and REQ-DEFENSIVE-001 scenario 2:
  1. `test_aggregator_with_all_sources_failing_returns_200_and_empty_jobs` → `test_aggregator_with_all_sources_failing_returns_502` (in `test_aggregator_api.py`)
  2. `test_aggregator_headers_all_sources_fail_lists_all_three_in_errors` → `test_aggregator_headers_all_sources_fail_returns_502` (in `test_aggregator_headers.py`)
  3. `test_all_3_sources_fail_returns_empty_jobs_with_all_errors` → `test_all_3_sources_fail_raises_all_sources_failed_error` (in `test_aggregator.py`)
- **1 pre-existing test was renamed** for the 6-field cache key:
  4. `test_job_search_cache_key_has_five_fields` → `test_job_search_cache_key_has_six_fields` (in `test_cache_port.py`)
- **The v1 200 + partial-results contract is preserved** for 1-of-3 and 2-of-3 source failures (no exception raised, the route returns 200 with the partial job list + `X-Aggregator-Errors: <failed_source>` header).
- **The `ENABLE_KEYWORD_SCORING=false` default** preserves the v1 `posted_at desc` ranking; the `keyword_score` opt-in is gated by the env var and the `app_factory` wires `enable_keyword_scoring=settings.enable_keyword_scoring` into the use case constructor.
- **`HardcodedLocationResolver` resolves "malaga" / "Málaga" / "MALAGA" to `104401670`** (the value added in `fix-linkedin-geoid`), making the T-001 fix finally observably correct end-to-end.

## Findings

### CRITICAL
(none)

### WARNING

1. **Diff size grew 73% over design forecast.** The design forecast ~1,340 LOC; the actual backend diff is 2,317 added + 55 deleted = 2,372 total LOC. The growth is concentrated in tests (1,685 lines added across 12 test files), which is consistent with Strict TDD's "tests first, then implementation" discipline. Production code grew only ~570 lines (12 production files). The 5000-line review budget is still respected (47% of budget); `delivery_strategy=ask-always → single-pr` remains the correct call. Not blocking.

2. **`test_in_memory_ttl_cache.py` has no `query_tokens`-specific tests.** The 3 REQ-CACHE-001 scenarios for the cache layer are implemented and exercised via `test_cached_job_search_use_case.py` (the wrapper that builds the `JobSearchCacheKey`). The TTL cache itself is hash-agnostic (it stores by `Hashable` key), so the `query_tokens` behavior IS transitively covered by the wrapper tests. The spec's REQ-CACHE-001 scenario 4 ("el cache in-memory usa el nuevo key format") is satisfied by `test_cache_separates_entries_by_query_tokens` in the wrapper test file. Not blocking — equivalent coverage in a different test file.

3. **WARNING log does not explicitly pass `request_id` via `extra={}`.** The `request_id` reaches the rendered JSON log line through the `LogRecordFactory` in `presentation/logging_config.py:89-116` (which auto-injects from the `ContextVar` set by `RequestIdMiddleware`). The dependency rule is preserved (aggregator does NOT import from `presentation/`), so this is a deliberate architectural choice, not a bug. The verify prompt and spec REQ-DEFENSIVE-001 scenario 1 both state the WARNING must include `request_id` — the requirement IS met in the rendered output, just via a different mechanism than a literal `extra={"request_id": ...}` kwarg. Worth a docstring note in `_call_one` for future readers.

4. **Verify report template wording inconsistency.** The template said `query_tokens: frozenset[str] = frozenset()` for the cache key; the spec, design, and code all use `tuple[str, ...] = ()`. Template was inconsistent with the source artifacts. Resolved in this report in favor of the spec wording.

### SUGGESTION

1. **`sdd-archive` follow-up note (1)**: `backend-infojobs-provinces` — use `provinceIds=<id>` and `countryIds=<id>` in the InfoJobs scraper URL. The user found Málaga = province 34, Spain = country 17 in InfoJobs. The current `filter_infojobs_results` is a mitigation; the real fix is to pass province/country IDs the way LinkedIn uses `geoId=`.

2. **`sdd-archive` follow-up note (2)**: `backend-linkedin-location-fallback` — when the `HardcodedLocationResolver` doesn't have a `geoId` for the user's location, fall back to the format `location=<city>,<province>,<country>` (e.g. `location=Antequera,Andalucía,Spain`) instead of the current `location=<raw_string>`. This would give LinkedIn's location fuzzy-matching a better chance for unmapped cities.

3. **Docstring note in `_call_one`**: explicitly mention the `LogRecordFactory` auto-injects `request_id` so the warning is not mistaken for missing the `request_id` field.

## Follow-ups to track (not in this change)

- `backend-infojobs-provinces`: use `provinceIds=<id>` and `countryIds=<id>` in the InfoJobs scraper URL. The user found that Málaga = province 34, Spain = country 17 in InfoJobs. This is the real fix for InfoJobs relevance; the current `filter_infojobs_results` is a mitigation.
- `backend-linkedin-location-fallback`: when the `HardcodedLocationResolver` doesn't have a geoId for the user's location, fall back to the format `location=<city>,<province>,<country>` (e.g. `location=Antequera,Andalucía,Spain`) instead of the current `location=<raw_string>`.

## Sign-off

**Ready for archive: yes.**

All 7 REQ scenarios are covered with passing tests. All 4 quality gates are clean. The pre-existing `geo_id` bug from `fix-linkedin-geoid` is genuinely fixed. The 3 pre-existing test renames to the 502 contract are intentional and documented. v1 backwards-compat is preserved for partial-failure paths. Two follow-up changes (`backend-infojobs-provinces`, `backend-linkedin-location-fallback`) are queued for the next iteration; they are NOT blockers for archiving this change.
