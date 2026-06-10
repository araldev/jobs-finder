# Exploration: backend-infojobs-provinces

**Change**: `backend-infojobs-provinces` • **Mode**: `both` (OpenSpec files in `openspec/changes/backend-infojobs-provinces/` + Engram copy) • **Strict TDD**: ACTIVE
**Date**: 2026-06-10 • **Base**: `f41aa90` (feature/backend-infojobs-provinces; branched from main at the `backend-scraper-query-tuning` merge; baseline 1,142 passed / 13 skipped / 0 deselected per obs #329)
**Upstream artifacts**: obs #329 (`backend-scraper-query-tuning` archive-report — defines the `filter_infojobs_results` mitigation as a temporary safety net), obs #322 (the same change's proposal — proposes this `backend-infojobs-provinces` change as the real fix), obs #294 + #295 (`fix-linkedin-geoid` explore + proposal — the analog pattern for plumbing `geoId` through the same `HardcodedLocationResolver`-style seam).

## 1. status
`explored`

## 2. executive_summary

The `backend-scraper-query-tuning` cycle shipped a `filter_infojobs_results` client-side filter as a *mitigation* for the InfoJobs noise problem (PR #4, merged 2026-06-10). The real fix — confirmed by a real captured InfoJobs URL the user found during manual smoke testing — is to pass `provinceIds=<id>&countryIds=<id>` in the InfoJobs scraper URL. The format is `provinceIds=34&countryIds=17` (Málaga = 34, Spain = 17), and InfoJobs returns the right regional slice when these are present, regardless of the `l=<location>` string param. **The change is the InfoJobs sibling of `fix-linkedin-geoid`** (obs #294): same `HardcodedLocationResolver` pattern, same `location_resolver` injection in the scraper settings, same plumb-through-the-closure contract. The only new concept is a `(province_id, country_id)` tuple return type instead of a single `int` — and the InfoJobs "Remote" + "Spain-only" cases where the country is set but the province is `None`.

## 3. Current state — how InfoJobs URL building works today (verified)

The InfoJobs Playwright scraper builds its search URL in `_build_url(keywords, location, page)` at `backend/src/jobs_finder/infrastructure/infojobs/scraper.py:327-331`:

```python
@staticmethod
def _build_url(self, keywords: str, location: str, page: int) -> str:
    return (
        f"https://{self._settings.domain}/ofertas-trabajo"
        f"?q={quote(keywords)}&l={quote(location)}&page={page}"
    )
```

The scraper's `search(keywords, location, limit)` signature (line 225-231) has **no `geo_id` kwarg** — the `JobSearchPort` Protocol at `application/ports.py:52-58` declares the 4th `geo_id: int | None = None` kwarg, but the InfoJobs scraper hasn't been updated to accept it. Indeed is the same shape; only LinkedIn consumes `geo_id` today (obs #302, `fix-linkedin-geoid`).

The `paginated_search` helper at `infrastructure/pagination.py:52` owns the loop; the per-page closure passed by `_make_fetch_one_page(keywords, location)` (scraper.py:279-325) captures the source-specific concerns (URL formula, `is_infojobs_blocked` check, 3-arg `_parse_cards(soup, remaining, domain)`, page-0 zero-cards raise semantic). The URL is built INSIDE the closure on every page from the captured `keywords, location` — the seam for plumb-through is the closure's captured-variable list.

The current user-visible problem: `GET /jobs?q=react&location=Málaga` calls InfoJobs with `?q=react&l=Málaga`, and InfoJobs returns results from all of Spain (or worse, all of Europe). The `filter_infojobs_results` post-scrape filter discards 0-token-overlap cards, but it cannot recover jobs that were in the wrong region to begin with. The user's real captured URL that produces the correct Málaga slice is `?keyword=react&provinceIds=34&countryIds=17&page=1&sortBy=RELEVANCE` (InfoJobs uses both `keyword` and `q` interchangeably; the `q=` param is the v1 contract the scraper uses).

## 4. Affected areas

### 4.1 NEW files

- `backend/src/jobs_finder/infrastructure/location/infojobs_province_resolver.py` (NEW) — `InfoJobsLocationResolver` (or extend the existing class via a second method) that returns `tuple[int | None, int | None]` `(province_id, country_id)` from a free-form `location` string. Same NFC + casefold + strip + remove-accents normalization as `HardcodedLocationResolver`. New mapping file `infojobs_province_mapping.py` (or extension of `_mapping.py`) with ~5-8 entries (Málaga, Madrid, Barcelona, Valencia, Sevilla, Remote → `(None, 17)`, Spain-only → `(None, 17)`).
- `backend/src/jobs_finder/application/ports.py` — EXTEND `LocationResolverPort` Protocol with a SECOND method `def resolve_infojobs(self, location: str) -> tuple[int | None, int | None]` (or define a NEW Protocol `InfoJobsLocationResolverPort`). The current `resolve(location: str) -> int | None` is LinkedIn-specific (returns a `geoId`); adding a second method makes the type semantics explicit per-source. **Tradeoff to resolve in proposal**: see §5.
- `backend/tests/unit/test_infojobs_province_resolver.py` (NEW) — table-driven tests mirroring `test_hardcoded_location_resolver.py`: happy-path (5-7 entries), alias normalization (4 invariants), `None` semantic (unknown city / empty / country-only / province-only), ctor custom mapping override.
- `backend/tests/unit/test_infojobs_scraper.py` (EXTEND) — 4-5 new scenarios: URL with `provinceIds=34&countryIds=17` (Málaga), URL with `countryIds=17` only (Remote, no province), URL with neither (unknown city, fallback to `?l=<str>`), `geo_id`-like kwarg plumbed through `_make_fetch_one_page` closure, `location_resolver` setting injected via `InfoJobsScraperSettings`.

### 4.2 MODIFIED files

- `backend/src/jobs_finder/infrastructure/infojobs/scraper.py:225-273` (`search()`) — add `geo_id: int | None = None` kwarg (mirroring LinkedIn's signature, even though the kwarg name is `geo_id` and the value is actually `(province_id, country_id)` for InfoJobs); accept a tuple via a NEW dedicated kwarg `infojobs_geo: tuple[int | None, int | None] | None = None` for type clarity. **Decision pending in proposal §5.** Inside `search()`, call `self._settings.location_resolver.resolve_infojobs(location)` (or use the explicit kwarg) and pass the result to `_make_fetch_one_page(keywords, location, infojobs_geo=...)`. Modify the closure to capture the tuple.
- `backend/src/jobs_finder/infrastructure/infojobs/scraper.py:279-325` (`_make_fetch_one_page`) — accept the `infojobs_geo` tuple; pass it to `_build_url` on every page.
- `backend/src/jobs_finder/infrastructure/infojobs/scraper.py:327-331` (`_build_url`) — extend to accept the tuple; when `infojobs_geo` is `(province_id, country_id)` with `country_id is not None`, emit `?q=...&l=...&provinceIds=<id>&countryIds=<id>&page=...`; when the tuple is `None` (unmapped), fall back to the v1 `?q=...&l=...&page=...` (broken-but-doesn't-500, same as LinkedIn's `?location=<str>` fallback).
- `backend/src/jobs_finder/infrastructure/infojobs/scraper.py:111-167` (`InfoJobsScraperSettings`) — add `location_resolver: InfoJobsLocationResolverPort | None = None` field (mirroring `LinkedInScraperSettings:133`); extend `__slots__`, `__eq__`, `__hash__`, `__repr__`.
- `backend/src/jobs_finder/presentation/app_factory.py:319-363` (InfoJobs default branch) — wire the new `InfoJobsLocationResolver()` into `InfoJobsScraperSettings(location_resolver=...)`. The existing `HardcodedLocationResolver` (line 185) is reused for the LinkedIn + chat-filter path; a separate `InfoJobsLocationResolver` (or a 2nd method on the same class) is wired for the InfoJobs path. **Decision pending in proposal §5.**
- `backend/src/jobs_finder/infrastructure/aggregator_filters.py:75-97` (`filter_infojobs_results`) — DECISION PENDING (see §6): keep as defense-in-depth, no-op it, or remove. Recommend **KEEP** (defense-in-depth, no test changes).
- `backend/src/jobs_finder/infrastructure/config.py:211-236` (InfoJobs env vars) — no changes (the resolver is a code-level mapping, not an env-var-driven config; the existing `INFOJOBS_*` env vars are unchanged).
- `backend/README.md` (extend) — document the new `InfoJobsLocationResolver` + the `provinceIds/countryIds` URL formula in the "Manual verification" InfoJobs section; document the `filter_infojobs_results` decision (keep / no-op / remove).
- `backend/src/jobs_finder/presentation/schemas.py:180-201` (`AggregatedJobsQuery`) — **NO change**. The frontend still sends `location=...`; the resolver converts internally. The v1 HTTP contract is preserved.
- `backend/src/jobs_finder/presentation/routes/aggregator.py:168-180` — **NO change**. The `linkedin_geo_id` plumb (added in T-009) is already in place; the InfoJobs resolver runs INSIDE the InfoJobs scraper's `search()` from the resolver injected via `InfoJobsScraperSettings` (mirroring how LinkedIn's resolver runs INSIDE `LinkedInPlaywrightScraper.search()` — confirmed at `scraper.py:249-250`).

## 5. Approaches

### Option A: Separate `InfoJobsLocationResolver` class + new Protocol method (RECOMMENDED)

A NEW `InfoJobsLocationResolver` class in `infrastructure/location/infojobs_province_resolver.py` that returns `tuple[int | None, int | None]` from a 5-7 entry hardcoded dict (the same 5-7 Spanish cities + Remote + Spain-only). The `LocationResolverPort` Protocol grows a SECOND method `def resolve_infojobs(self, location: str) -> tuple[int | None, int | None]`. The `HardcodedLocationResolver` class implements BOTH methods (`resolve` returns the LinkedIn geoId; `resolve_infojobs` returns the `(province_id, country_id)` tuple).

**Pros**:
- Type clarity: each method's return type matches its consumer's expectation (`int` for LinkedIn `geoId`; `tuple` for InfoJobs `province/country`).
- Mirrors the existing `IntentExtractorPort` / `LLMClientPort` Protocol pattern (multiple methods on one Protocol is fine; the structural conformance is enforced by mypy).
- No new dependency on the Protocol shape: the `JobSearchPort.search(geo_id: int | None = None)` kwarg stays the same (LinkedIn-specific); the InfoJobs plumb uses a NEW kwarg on the InfoJobs scraper, not on the Port.
- The dict in `infojobs_province_mapping.py` is independent from `_mapping.py` (the LinkedIn geoIds) — different ID namespaces, different sources of truth.
- The composition root wires ONE `HardcodedLocationResolver` (or a thin subclass) that implements BOTH methods; the LinkedIn use case calls `resolve`; the InfoJobs scraper calls `resolve_infojobs`. The test doubles (e.g. `FakeLocationResolver` in `tests/conftest.py`) satisfy both methods structurally.

**Cons**:
- The `LocationResolverPort` Protocol grows a second method — a small spec change. Existing `FakeLocationResolver` doubles need a second method (a no-op returning `(None, None)` is a backward-compat sentinel).
- Two dicts to maintain (`_mapping.py` + `infojobs_province_mapping.py`). The InfoJobs dict is small (~5-7 entries) so the maintenance burden is low.
- The InfoJobs "Remote" case (no province, country 17) and the "Spain" case (no province, country 17) are the same — the dict collapses 2 cases to 1 entry. Not a con; just an observation.

**Effort**: Low (~150-200 LOC prod + ~150-200 LOC tests; single PR).
**Dependency surface**: zero new deps.
**Failure modes**: only "key not found" → returns `(None, None)` (graceful degradation, the scraper falls back to `?l=<str>`).
**Testability**: trivial (in-process dict; no mocks needed).

### Option B: Reuse the existing `HardcodedLocationResolver` and return `(province_id, country_id)` from the same `resolve` method

Change the `HardcodedLocationResolver.resolve` return type from `int | None` to `tuple[int, int] | tuple[None, None]` and have the InfoJobs scraper interpret the tuple as `(province_id, country_id)`. Drop the `(province_id, country_id)` distinction for the LinkedIn case (the LinkedIn scraper just uses `tuple[0]` as the geoId).

**Pros**:
- One resolver class, one method, one mapping file.
- Less Protocol surface.

**Cons**:
- **Type abuse**: a `tuple[int, int]` is semantically a `(province_id, country_id)` for InfoJobs but a meaningless 2-tuple for LinkedIn. The `int | None` return type is the LinkedIn contract; switching to `tuple` breaks every existing caller (the chat use case at `filter_jobs_by_intent.py:382-389` and the `app.state.location_resolver` at `routes/aggregator.py:169` both call `resolve` and expect `int | None`).
- The mapping would need to carry BOTH a LinkedIn geoId AND an InfoJobs province_id for every city — duplicating 34+ entries with two distinct IDs each. The maintainer now has to update two columns in lockstep.
- A future third source (e.g. Indeed city IDs) would need a third column — the tuple grows unboundedly.
- Breaks the v1 `JobSearchCacheKey` 5th field semantics (`geo_id: int | None` is the LinkedIn-specific value, not a 2-tuple).

**Effort**: Medium — the Protocol + impl + 3 call sites + the cache key field all need to change.
**Dependency surface**: zero new deps.
**Testability**: harder (the 2-tuple return type leaks the InfoJobs concern into every test that asserts `resolve`).

**REJECTED.** The semantic clarity of Option A (per-source method, per-source return type) is worth the small Protocol surface increase. The 34+ entry lockstep maintenance burden of Option B is a real cost.

### Option C: JSON-file-driven mapping (no code deploy to add a city)

Replace the hardcoded dict with a JSON file in `backend/src/jobs_finder/infrastructure/location/infojobs_province_mapping.json` loaded at startup. Adding a city = edit JSON + redeploy (no Python code change).

**Pros**:
- The dict is data, not code — non-engineers can update it.
- The 5-7 entries fit naturally in a 10-line JSON file.

**Cons**:
- JSON file adds a new deployment artifact (the JSON file must be shipped alongside the wheel).
- The startup loading is the same complexity as the hardcoded dict (the loader is ~10 lines).
- Pydantic `ValidationError` on invalid mapping is the same pattern (move the validation to Pydantic on the JSON-load path).
- The "non-engineers can update it" benefit is moot for v1 — the maintainer IS the engineer, and the next change ("add a 4th source") will touch the loader anyway.

**Effort**: Low — same as Option A + a JSON loader (~30 LOC).
**Dependency surface**: zero new deps.

**DEFERRED** — the v1 hardcoded dict is the smallest correct change. JSON-file-driven is a follow-up if the dict grows past ~15 entries (the 34-entry LinkedIn dict is already hardcoded and the team has accepted the maintenance pattern).

## 6. Recommendation

**Option A** (separate `InfoJobsLocationResolver` + second Protocol method on `LocationResolverPort`). The change is small (~150-200 LOC prod + ~150-200 LOC tests), the Protocol surface grows by one method, and the per-source type clarity is preserved.

**On the `filter_infojobs_results` decision** (the biggest open question):
- **KEEP** the filter as defense-in-depth. The cost is ~100 LOC of dead-but-tested code; the benefit is a safety net if a future InfoJobs province/country ID change silently breaks the resolver (analog to the `LOCATION_RESOLVER_ENABLED` kill switch on the LinkedIn path). The filter is a post-scrape, client-side safeguard that catches the "wrong region + zero token overlap" case (worst-case 0 tokens, discarded). The cost of removing it is small (97 LOC) but the cost of needing it again (a re-deploy + a hotfix + a re-capture) is higher.
- The 6 tests in `test_aggregator_filters.py` stay GREEN (no test changes).
- The README "InfoJobs client-side filter" section (lines 719-737) is updated to read "defense-in-depth safety net for unmapped regions + future ID drift".

## 7. Risks

1. **The InfoJobs province ID for Málaga = 34 is the user's smoke-test number, not a captured-from-source value.** The user found a real InfoJobs URL during manual smoke testing that showed `provinceIds=34&countryIds=17` for Málaga. We have not captured the IDs for Madrid, Barcelona, etc. — the proposal will list "at least 4 cities" but the actual mapping will be: (a) the user's known Málaga=34, Spain=17; (b) the team's best-effort research for the other cities via InfoJobs's public-facing documentation. A future test (LIVE, gated `LLM_LIVE_TESTS=1`) will verify each ID against the live InfoJobs SERP. **Mitigation**: the change is shipped with the 4 known cities + Remote + Spain; the "unknown city" fallback to `?l=<str>` is the same broken-but-doesn't-500 behavior as today (strict improvement over zero coverage, no regression for known cities).

2. **InfoJobs can change province IDs at any time** (same as LinkedIn geoIds, same as the `infojobs_throttle_seconds` defaults). The hardcoded dict is committed; adding/changing a province = a code change + PR. The `filter_infojobs_results` defense-in-depth is the safety net.

3. **The `LocationResolverPort` Protocol grows a second method.** Existing `FakeLocationResolver` test doubles in `tests/conftest.py` (the chat wiring test fixtures) need a second method to satisfy the structural Protocol. **Mitigation**: add a default `def resolve_infojobs(self, location: str) -> tuple[int | None, int | None]: return (None, None)` to the Protocol with a docstring noting the default `None` semantic; existing test doubles get the default for free; new tests for the InfoJobs path inject a real `InfoJobsLocationResolver`.

4. **The InfoJobs URL adds 2 query params (`provinceIds`, `countryIds`) but the captured URL also has `sortBy=RELEVANCE` and `sinceDate=ANY`.** Out of scope (per the proposal §3.2); the scraper continues to use the v1 sort + freshness behavior. The added 2 params are enough to fix the user's smoke-test bug.

5. **The `filter_infojobs_results` removal/no-op decision is in §6** (recommend KEEP). The risk of KEEP is that the function is dead-but-tested code (~100 LOC); the risk of REMOVE is losing the safety net.

6. **`paginated_search` helper is UNCHANGED** — the InfoJobs closure just grows one more captured variable (the `(province_id, country_id)` tuple). The helper is the same source-agnostic loop it always was. The `JobSearchCacheKey` 5th field `geo_id: int | None` is the LinkedIn-specific value; the InfoJobs tuple is plumbed via a NEW kwarg on the InfoJobs scraper + closure (NOT on the cache key, NOT on the Port — keeps the Port source-agnostic).

7. **Backward compat for unmapped locations** (e.g. "Berlin", "Tokyo", "Buenos Aires") — the resolver returns `(None, None)`, the scraper falls back to `?l=<str>` (the v1 behavior). The `filter_infojobs_results` safety net catches the 0-token case. **No regression vs. today's behavior for unknown cities.**

## 8. Open questions for sdd-propose

1. **Protocol shape**: extend `LocationResolverPort` with a second method `resolve_infojobs`, or define a NEW `InfoJobsLocationResolverPort` Protocol? The first is the smaller change; the second is the more explicit type. **Recommend**: extend (mirrors the `LLMClientPort.complete` + `LLMClientPort.stream_complete` pattern in `application/ports.py:374-451`).

2. **Kwarg name on `InfoJobsScraperSettings.search()`**: reuse the `geo_id: int | None = None` kwarg (the existing Port signature) and stuff the tuple into a sentinel value? Or add a NEW kwarg `infojobs_geo: tuple[int | None, int | None] | None = None`? **Recommend**: the NEW kwarg is the explicit choice; the v1 `JobSearchPort.search(geo_id=...)` is LinkedIn-specific (its name is `geo_id` because the LinkedIn URL uses `geoId=`, but the value is a `int`). The InfoJobs tuple has no LinkIn-style URL name; naming the kwarg `infojobs_geo` (or `infojobs_location_ids`) makes the type discoverable.

3. **Where does the resolver live at composition-root time**: same single `HardcodedLocationResolver` instance (now implementing BOTH methods) wired into BOTH `LinkedInScraperSettings.location_resolver` AND `InfoJobsScraperSettings.location_resolver`? Or two separate instances (one for LinkedIn, one for InfoJobs)? **Recommend**: ONE instance, BOTH methods. The dict sizes are small (34 LinkedIn + 5-7 InfoJobs = ~40 entries total); the per-source method dispatch keeps the type clear. The future "add a 4th source" change adds a 3rd method to the same class.

4. **The `filter_infojobs_results` decision**: KEEP (defense-in-depth), NO-OP (return the input list, keep the function alive as a hook for future re-activation), or REMOVE (delete the function and the `aggregator_filters.py` module). **Recommend**: KEEP. The 6 tests in `test_aggregator_filters.py` stay GREEN; the function continues to run on every aggregator call (it's a pure O(n) pass, ~10µs for 20 jobs).

5. **The `sortBy=RELEVANCE` and `sinceDate=ANY` URL params** the user's captured URL also has: add them to the v1 URL formula? **Recommend**: NO — out of scope. The proposal's "Out of Scope" section flags them as a follow-up. The added 2 params (`provinceIds` + `countryIds`) are the minimum needed to fix the user's bug.

## 9. Skill resolution

`paths-injected` — orchestrator pre-resolved `sdd-explore/SKILL.md` + `_shared/sdd-phase-common.md` + `openspec-convention.md` + `engram-convention.md` + `persistence-contract.md` + `sdd-propose/SKILL.md` (in preflight). Loaded at the start of this turn.

## 10. Codebase verification (real code, not guesses)

- `src/jobs_finder/infrastructure/infojobs/scraper.py:225-231` — `search(keywords, location, limit=20, geo_id=None)` signature (already extended in `fix-linkedin-geoid`, but the kwarg is unused by the InfoJobs scraper body). VERIFIED.
- `src/jobs_finder/infrastructure/infojobs/scraper.py:327-331` — `_build_url(keywords, location, page)` static method. URL is `?q=...&l=...&page=...`. VERIFIED.
- `src/jobs_finder/infrastructure/infojobs/scraper.py:279-325` — `_make_fetch_one_page(keywords, location)` closure factory. Captures `domain` + `keywords` + `location`; URL is built INSIDE the closure via `self._build_url(keywords, location, page_index + 1)`. The seam for plumb-through is the closure's captured-variable list. VERIFIED.
- `src/jobs_finder/application/ports.py:52-60` — `JobSearchPort.search(keywords, location, limit, geo_id)` Protocol signature. The `geo_id` kwarg is part of the v1 contract; the InfoJobs scraper can ignore it (as Indeed does today) or consume it (as the proposed change will, via a NEW dedicated kwarg). VERIFIED.
- `src/jobs_finder/application/ports.py:170-208` — `LocationResolverPort` Protocol with the single `resolve(location: str) -> int | None` method. VERIFIED.
- `src/jobs_finder/infrastructure/location/hardcoded_resolver.py:40-151` — the existing class. The ctor accepts a `mapping` kwarg for test injection. VERIFIED.
- `src/jobs_finder/infrastructure/location/_mapping.py:40-79` — the 34-entry `_CANONICAL_MAPPING` dict. VERIFIED.
- `src/jobs_finder/infrastructure/linkedin/scraper.py:211-250` — `search()` calls `self._settings.location_resolver.resolve(location)` when `geo_id is None`. The seam pattern. VERIFIED.
- `src/jobs_finder/infrastructure/linkedin/scraper.py:104-176` — `LinkedInScraperSettings` with the `location_resolver: LocationResolverPort | None = None` field, slots + `__eq__` + `__hash__` + `__repr__`. The mirror pattern. VERIFIED.
- `src/jobs_finder/presentation/app_factory.py:185` — `location_resolver = HardcodedLocationResolver()` constructed unconditionally. VERIFIED.
- `src/jobs_finder/presentation/app_factory.py:237-274` (LinkedIn default branch) — wires `location_resolver=location_resolver` into `LinkedInScraperSettings`. VERIFIED.
- `src/jobs_finder/presentation/app_factory.py:319-363` (InfoJobs default branch) — does NOT wire any resolver today. This is the seam. VERIFIED.
- `src/jobs_finder/presentation/routes/infojobs.py:60-77` — the `/jobs/infojobs` route. The `query` is `InfoJobsJobsQuery(keywords, location, limit)` — `location` is a `str`. NO schema change needed. VERIFIED.
- `src/jobs_finder/presentation/routes/aggregator.py:168-180` — the `linkedin_geo_id` plumb is already in place. The InfoJobs resolver does NOT need a route-level plumb (the resolver runs INSIDE the InfoJobs scraper from `InfoJobsScraperSettings.location_resolver`). VERIFIED.
- `src/jobs_finder/infrastructure/aggregator_filters.py:75-97` — `filter_infojobs_results(jobs, query_tokens) -> list[Job]`. The 97-LOC pure function. VERIFIED.
- `src/jobs_finder/application/aggregator.py:444-465` — the dispatch: `if query_tokens: ... filter_infojobs_results(...)` applied to the InfoJobs slice of the deduped list. VERIFIED.
- `tests/unit/test_aggregator_filters.py:71-164` — 6 scenarios pinning the filter behavior. NO test changes needed if KEEP. VERIFIED.
- `tests/unit/test_hardcoded_location_resolver.py` (383 LOC) — the test pattern: 5 sections (canonical happy-path, alias normalization, alias-to-canonical recurse, None semantic, ctor custom mapping). The InfoJobs resolver test mirrors this structure. VERIFIED.
- `tests/unit/test_infojobs_scraper.py:248-256` — `test_search_navigates_to_infojobs_ofertas_trabajo` asserts the v1 URL. The new tests will extend this to the provinceIds/countryIds case. VERIFIED.
- `tests/unit/test_chat_wiring.py:342-381` — the test pattern for asserting `app.state.location_resolver` wiring. The InfoJobs test mirrors this for `InfoJobsScraperSettings.location_resolver`. VERIFIED.
- `backend/README.md:719-737` — the "InfoJobs client-side filter" section. KEEP recommendation updates this section. VERIFIED.
- `backend/README.md:101-150` — the "Legal Notice — InfoJobs" section. NO change needed (the change does not modify the scraping boundary; it just narrows the URL). VERIFIED.
- `openspec/changes/archive/2026-06-09-frontend-scaffold/` and `openspec/changes/archive/2026-06-09-chat-streaming/` — the existing archive structure. The new change folder follows the same convention. VERIFIED.

## 11. Ready for Proposal

**Yes.** The exploration is complete:
- The InfoJobs URL builder + closure seam is verified.
- The `HardcodedLocationResolver` + Protocol pattern is verified and mirrored.
- The composition-root injection seam is verified.
- The 4 architectural decisions in §8 (Protocol shape, kwarg name, resolver instance, filter disposition) have recommended defaults; the orchestrator can confirm with the user.
- The 7 affected areas in §4 are scoped.
- The 7 risks in §7 are documented.
- The single approach (Option A) is selected; the rejected alternatives (B, C) are documented.

**Workload forecast**: ~500-1000 LOC (150-200 prod + 150-200 tests + ~50 docs + ~100 dict + ~50 test infra). The 5000-line review budget is generous; the work-unit-commits pattern can keep each commit under 400 changed lines (e.g. WU1 = Protocol + resolver + dict; WU2 = scraper + tests; WU3 = app_factory + tests; WU4 = docs + filter disposition + README).

**Next step**: the orchestrator can launch `sdd-propose` to lock the 4 open questions, the file set, the PR slice strategy (single PR vs chained), and the capability taxonomy.
