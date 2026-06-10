# Spec: `aggregator-relevance` — Per-source relevance filters at the aggregator

> **Promoted to source of truth on 2026-06-10** from
> `openspec/changes/backend-infojobs-provinces/specs/aggregator-relevance/spec.md`
> (archived in `openspec/changes/archive/2026-06-10-backend-infojobs-provinces/`).
>
> This was a MODIFIED delta — no prior
> `openspec/specs/aggregator-relevance/spec.md` existed. The delta
> documents the KEEP-and-document decision (the user's Q3 answer)
> on top of the pre-change `filter_infojobs_results` contract
> (defined in `infrastructure/aggregator_filters.py`, added in
> `backend-scraper-query-tuning` PR #4 merged 2026-06-10). The
> delta is promoted in full as the foundational spec for the
> capability. Source observation IDs for traceability:
> explore #330, proposal #331, spec #334, design #337, tasks #339,
> apply-progress #341, verify-report #342.

## Purpose

Document the new role of `filter_infojobs_results` after the
InfoJobs URL plumb in `infojobs-provinces` ships. The function
stays ALIVE in the codebase (no removal, no no-op refactor) as
a "belt and suspenders" safety net: once the URL includes
`provinceIds=<id>&countryIds=<id>`, the SERP returns a region-
scoped slice, so the filter is redundant for mapped locations.
But for unmapped locations (e.g. `"Berlin"`, future city
additions, or transient ID drift in the dict), the filter
removes the 0-token-overlap jobs that InfoJobs returns when the
region filter is missing. The cost of keeping the filter is
~100 LOC; the cost of removing it and re-deploying if we need
it again is greater.

## Requirements

### REQ-PROV-AGG-001-MOD — `filter_infojobs_results` stays alive (defense-in-depth)

(Previously: `filter_infojobs_results` was the PRIMARY defense against
InfoJobs returning all-Spain results for any `?l=<str>` query. It was
the only mitigation in `backend-scraper-query-tuning` PR #4. The docstring
said "primary relevance filter for InfoJobs results".)

The `filter_infojobs_results` function (in
`infrastructure/aggregator_filters.py`) MUST remain in the codebase
with UNCHANGED behavior. The function:

- Receives the InfoJobs result list + the query tokens
- Removes jobs with 0 token overlap with the query
- Returns the filtered list (byte-identical to the pre-change contract)

The aggregator (`application/aggregator.py`) MUST continue to call
the filter on InfoJobs results only (LinkedIn + Indeed are
unchanged).

The docstring MUST be UPDATED to reflect the new role: "defense-
in-depth safety net for unmapped locations + future province/
country ID drift. The primary relevance improvement comes from
the `provinceIds` + `countryIds` plumb in `InfoJobsPlaywrightScraper`."

#### Scenario: filter still applies to InfoJobs results

- **GIVEN** the aggregator is called with 5 InfoJobs jobs (2 with token overlap, 3 without)
- **WHEN** the filter runs
- **THEN** the filter returns the 2 jobs with token overlap (the 3 jobs without overlap are removed)
- **AND** the pre-change test `test_aggregator_filters.py::test_filter_infojobs_results` continues to pass (no behavioral change)
- **AND** the new test `test_aggregator_filters.py::test_filter_infojobs_results_docstring_updated` passes (asserts the docstring contains "defense-in-depth" or "safety net" wording)

#### Scenario: filter does NOT apply to LinkedIn or Indeed results

- **GIVEN** the aggregator receives LinkedIn and Indeed results alongside InfoJobs
- **WHEN** the filter runs
- **THEN** the filter applies to InfoJobs results ONLY (LinkedIn + Indeed pass through unchanged)
- **AND** the pre-change test `test_aggregator_filters.py::test_filter_does_not_apply_to_linkedin_indeed` continues to pass

#### Scenario: filter is still called even when the InfoJobs URL is correct (defense-in-depth)

- **GIVEN** the InfoJobs URL is `?q=react&l=malaga&page=1&provinceIds=34&countryIds=17` (the new URL formula with resolved province/country)
- **WHEN** the aggregator receives 20 jobs from the InfoJobs scraper
- **THEN** the filter is STILL called (the defense-in-depth role)
- **AND** if InfoJobs returns 0 jobs with 0 token overlap (the typical case with the URL plumb), the filter is a no-op (the 20 jobs all pass through)
- **AND** the test `test_aggregator_filters.py::test_filter_is_noop_when_results_have_token_overlap` passes (the "happy path" of the URL plumb — the filter does not over-filter)

#### Scenario: filter catches unrelated results when the URL plumb fails

- **GIVEN** the InfoJobs URL is `?q=react&l=Berlin&page=1` (unmapped location — the resolver returns `(None, None)`)
- **WHEN** the aggregator receives 20 jobs from InfoJobs (some from Madrid, some from Málaga, some from Berlin — the all-Spain fallback)
- **THEN** the filter removes the jobs with 0 token overlap with the user's query
- **AND** the test `test_aggregator_filters.py::test_filter_is_safety_net_for_unmapped_locations` passes (asserts the filter improves relevance for unmapped locations)

### REQ-PROV-AGG-002-MOD — `backend/README.md` documents the new role

(Previously: the README's "InfoJobs client-side filter" section
documented the filter as the primary mitigation for the all-
Spain problem. It did not mention the future URL plumb or the
defense-in-depth role.)

The `backend/README.md` "InfoJobs client-side filter" section
MUST be updated to document:

1. The `filter_infojobs_results` function is a defense-in-depth
   safety net for unmapped locations and future ID drift.
2. The PRIMARY relevance improvement comes from the URL plumb
   (`provinceIds=<id>&countryIds=<id>`) in
   `InfoJobsPlaywrightScraper._build_url()`.
3. A link to the new "InfoJobs province/country IDs" section
   that lists the known mapping entries and the LIVE test gate.

A new "InfoJobs province/country IDs" section MUST be added
that documents:

1. The 9-entry default mapping (with the user-confirmed Málaga=34, España=17; the 4 speculative IDs flagged for LIVE test validation).
2. The fallback behavior for unmapped locations (legacy `?l=<str>` URL).
3. The LIVE test gate (`LLM_LIVE_TESTS=1`) and its role in verifying speculative IDs.

#### Scenario: README documents the new role

- **GIVEN** the backend README is updated
- **WHEN** the "InfoJobs client-side filter" section is read
- **THEN** the section mentions "defense-in-depth" or "safety net" for the filter role
- **AND** the section links to (or mentions) the "InfoJobs province/country IDs" section
- **AND** the test `test_aggregator_filters.py::test_readme_documents_defense_in_depth` passes (asserts the README contains the updated wording — uses a grep-style assertion on the file content)

#### Scenario: README lists the 9-entry mapping

- **GIVEN** the backend README is updated
- **WHEN** the "InfoJobs province/country IDs" section is read
- **THEN** the section lists the 9 mapping entries (Málaga, Madrid, Barcelona, Valencia, Sevilla, España, Spain, Remote, Teletrabajo)
- **AND** the section flags the 4 speculative IDs (Madrid, Barcelona, Valencia, Sevilla) as "pending LIVE test validation"
- **AND** the test `test_aggregator_filters.py::test_readme_lists_infojobs_mapping` passes (asserts the README contains the 9 entry names)

## Out of scope

- Refactoring the filter to accept a different signature (the signature is byte-identical to the pre-change contract; the use case + aggregator call it the same way).
- Moving the filter to a different module (the file `aggregator_filters.py` is the right home — it groups the per-source filter functions).
- Removing the filter entirely (the user's Q3 answer is KEEP; the cost-benefit analysis is in the proposal §6 Q3).
- Adding new filter strategies (e.g. geographic distance, salary overlap — out of scope for this change).
- Adding new aggregator-level filters for LinkedIn or Indeed (out of scope — the URL plumb is per-source, and the filter is InfoJobs-specific).
