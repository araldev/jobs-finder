# Exploration: backend-scraper-query-tuning

**Change**: `backend-scraper-query-tuning`
**Date**: 2026-06-09
**Project**: jobs-finder
**Mode**: `both` (OpenSpec files in `openspec/changes/backend-scraper-query-tuning/` + Engram copy)

## 1. status
`explored`

## 2. executive_summary

The user reported that `GET /jobs?q=react&location=Málaga` returns 8+ LinkedIn
offers from "DataAnnotation" titled "Frontend Developer - AI Trainer" in
"Washington, United States", plus 5 InfoJobs offers completely unrelated to
"react" (recepcionista, pintor, ordenanza, técnico farmacia). The relevant
results (Indeed offers in Málaga from Talan, Hero Gaming, etc.) confirm the
underlying parser data is correct — the issue is upstream of the frontend.

Investigation identified **5 independent root causes**, ordered by
highest-to-lowest expected impact:

1. **LinkedIn's `location=` string param is silently ignored** by the
   public search endpoint (the `fix-linkedin-geoid` change already added
   the resolver + the `geo_id` plumbing, but **only the 2-stage chat
   path forwards it** — the `GET /jobs` aggregator route does NOT
   resolve `location` before calling the LinkedIn use case).
2. **InfoJobs has weak server-side filtering** — its search
   `?q=<keyword>&l=<location>` ranks by the keyword but does NOT
   exclude results that don't share any word with the query. The 5
   noise offers are in the SERP even when the keyword is "react".
3. **The aggregator has no client-side relevance filter** — even if
   the sources return noisy results, the aggregator does not score
   `(title, company, description)` against the query and surface top-N.
4. **The current ranking is `posted_at` DESC** (REQ-AR-002) — a job
   posted 5 minutes ago wins over a 2-week-old job that's a perfect
   keyword match. The user's query "react + Málaga" expects RELEVANCE,
   not freshness, as the primary sort.
5. **The cache key is `(source, keywords, location, limit, geo_id)`** —
   this is fine for the per-source cache, but the aggregator's
   per-source cache hit rate on a query like "react + Málaga" is
   actually 0% because the user always passes different `q` values;
   this is a non-issue for the relevance problem, flagged for
   awareness only.

`Job` already has a `description: str | None` field (added in
`linkedin-description-capture`, per Engram obs #256) and the 3 scrapers
populate it. The frontend already accepts `description: string | null`
(per the `frontend-scaffold` design deviation #5, archived
`2026-06-09-frontend-scaffold/design.md:544-549`). A `keyword_match`
scorer that uses `title + company + description` is therefore
backward-compatible end-to-end.

The `HardcodedLocationResolver` already maps `Málaga` → `104401670`
(verified at `backend/src/jobs_finder/infrastructure/location/_mapping.py:47`
and pinned by 9 unit tests in `test_hardcoded_location_resolver.py:81,146,148,200-203`).
The fallback (unknown location → `None` → `?location=<str>`) is preserved
by the existing `geo_id` plumbing.

## 3. current_state_evidence

### 3.1 Aggregator (`backend/src/jobs_finder/application/aggregator.py`)

- **Parallel orchestration**: `asyncio.gather(*(_call_one(s) for s in ordered_sources))`
  at `aggregator.py:309`. Sources are ordered by `SOURCE_PRIORITY` so the
  dedup picks the first occurrence in LinkedIn > Indeed > InfoJobs order.
- **Dedup**: `(title, company, location)` lowercased+stripped at
  `aggregator.py:321-325`. First occurrence wins; `sources` list
  accumulates all source names.
- **Per-source error isolation**: `JobSearchError` is caught and recorded
  in `per_source` (`aggregator.py:270-281`); non-`JobSearchError`
  re-raises. A failing source does NOT take down the request.
- **No relevance scoring**: `rank_jobs` only sorts by `posted_at` DESC
  (default), `priority` map, or input order. No `keyword_match`
  scoring at all.
- **`linkedin_geo_id` forwarding**: `aggregator.search(..., linkedin_geo_id=None)`
  at `aggregator.py:267` forwards the kwarg ONLY to the LinkedIn
  use case. Indeed + InfoJobs receive the 3-arg call. The default
  `None` keeps backward compat.
- **CRITICAL GAP**: the `GET /jobs` aggregator route
  (`backend/src/jobs_finder/presentation/routes/aggregator.py:148-153`)
  calls `use_case.search(keywords=..., location=..., limit=..., sources=...)`
  WITHOUT `linkedin_geo_id`. The resolver is only invoked in the
  2-stage chat path (`FilterJobsByIntentUseCase._execute_2stage`).
  This means: even though the infrastructure is wired, the public
  `GET /jobs?q=react&location=Málaga` STILL sends
  `?keywords=react&location=Málaga` to LinkedIn (the broken path).

### 3.2 Per-source scrapers

| Source | URL formula | Has `geoId`? | Parser populates `description`? | Page-0 zero-cards |
|---|---|---|---|---|
| LinkedIn | `?keywords=...&location=<str>&start=<n>` (or `?geoId=<n>&...` when `geo_id` is set) | **YES** (via `geo_id` kwarg, wired in WU2 of `fix-linkedin-geoid`) | **YES** (added in `linkedin-description-capture`, obs #256) | Silent break (returns `[]`) |
| Indeed | `?q=<keyword>&l=<location>&start=<n>` | NO (Indeed uses `l=` string) | **YES** (existing parser) | Raise `IndeedParseError("zero_cards_on_first_page")` |
| InfoJobs | `?q=<keyword>&l=<location>&page=<n>` (1-indexed) | NO (InfoJobs uses `l=` string) | **YES** (existing parser) | Raise `InfoJobsParseError("zero_cards_on_first_page")` |

All 3 scrapers pass a `geo_id` kwarg through to `paginated_search` via
the `_make_fetch_one_page` closure, but Indeed/InfoJobs ignore it. The
LinkedIn scraper is the ONLY one that benefits from `geo_id`.

### 3.3 The `Job` value object (`backend/src/jobs_finder/domain/job.py`)

- Fields: `id, title, company, location, url, posted_at, description`.
- `description: str | None = None` is already populated by the 3 scrapers
  (verified by reading the 3 `_parse_cards` functions).
- The frontend's `Job` interface (`frontend/src/lib/types.ts:36-45`)
  already has `description: string | null`. **No frontend change needed.**

### 3.4 Location resolver

- `HardcodedLocationResolver.resolve(location)` is a pure dict lookup
  with a 4-step normalization chain (NFC + casefold + strip + NFD-drop-accents).
- 34 canonical entries (8 ES cities + 16 ES autonomous communities +
  9 LATAM cities + 1 Remote) + 5 aliases (mad/bcn/cdmx/caba/df).
- **`malaga → 104401670`** is verified at
  `infrastructure/location/_mapping.py:47` and pinned by 9 unit tests.
- The fallback (`resolve("anything else")` → `None` + WARNING log) is
  preserved by the existing `geo_id` plumbing.

### 3.5 Tests surface (Strict TDD anchor)

- `test_aggregator.py` (615 lines): dedup, error isolation, source
  priority, `linkedin_geo_id` forwarding (4 tests), cache-key isolation.
  **Tests that will need to update for this change**:
  - `test_one_source_fails_with_job_search_error_returns_others` (line 270)
    pins the current 2-succeed-1-fail behavior; this is unchanged.
  - `test_3_sources_all_succeed_returns_3_jobs_with_source_lists`
    (line 151) pins the default `posted_at` ranking order; the new
    `keyword_match` scorer will need to coexist with this (e.g. by
    introducing a new strategy `"keyword_match"` rather than changing
    the default).
- `test_aggregator_ranking.py` (316 lines): 7 tests pin the
  `posted_at`/`priority`/`none` strategies. The new `keyword_match`
  strategy will need ~6-8 new tests.
- `test_aggregator_settings.py`: does not pin ranking behavior.
- `test_linkedin_scraper.py` (258 lines), `test_indeed_scraper.py`
  (648 lines), `test_infojobs_scraper.py` (712 lines): pin URL formulas
  and page-0 zero-cards semantics. No changes needed for these (the
  per-source URL formulas are correct; the aggregator's `geo_id`
  forwarding is the seam).
- `test_aggregator_api.py` (367 lines, integration): pins end-to-end
  FastAPI response shape. NO shape change in this proposal — the
  `AggregatedJobsResponse` stays the same; only the order + content
  of `jobs` improves.

### 3.6 Engram context

- obs #234 (`ai-chat-filter` explore): confirmed that `description`
  IS available from Indeed (`data-testid="belowJobSnippet"`) and
  InfoJobs (`p.ij-OfferCardContent-description-description`).
  LinkedIn description extraction was the original gap, closed
  by `linkedin-description-capture` (obs #256, #267).
- obs #289 (`chat-filter-2stage` archive): the `Intent` Pydantic
  model + the `LocationResolverPort` Protocol were introduced here;
  `fix-linkedin-geoid` (obs #302) extended the resolver wiring.
- obs #302 (`fix-linkedin-geoid` archive): the `geoId` plumbing is
  fully wired from the 2-stage chat filter all the way to the
  LinkedIn scraper URL formula. The aggregator's `search()` already
  accepts `linkedin_geo_id: int | None = None` and forwards it ONLY
  to LinkedIn. The ONLY missing piece is the `GET /jobs` aggregator
  route not calling the resolver.

## 4. affected_areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/src/jobs_finder/application/aggregator.py` | Modified | Add a new `"keyword_match"` `RankingStrategy` + a `keyword_score(Job, q)` scorer; sort the deduped list by the score before ranking |
| `backend/src/jobs_finder/application/ranking.py` | Modified | Add a 4th strategy `"keyword_match"` (primary: score DESC; tie-breaker: existing `posted_at` DESC → priority → id). Add a `keyword_score(Job, q, location)` pure function. Update `Literal` type. |
| `backend/src/jobs_finder/application/ports.py` | Modified | Add `query_tokens: tuple[str, ...]` to `JobSearchCacheKey` (the cache key includes the tokenized query, not just `keywords`); pin via type |
| `backend/src/jobs_finder/application/usecases/_cached_search.py` | Modified | Tokenize `keywords` and pass `query_tokens=` to `JobSearchCacheKey` |
| `backend/src/jobs_finder/presentation/routes/aggregator.py` | Modified | Resolve `location` → `linkedin_geo_id` via the `HardcodedLocationResolver` before calling `use_case.search(...)`. Inject the resolver via `app.state`. |
| `backend/src/jobs_finder/presentation/app_factory.py` | Modified | Build a `HardcodedLocationResolver` (always, not just when `chat_enabled`) and set it on `app.state.location_resolver`. Pass it to the aggregator route. |
| `backend/src/jobs_finder/infrastructure/infojobs/scraper.py` | Modified | Add a client-side `keyword_filter` that drops cards whose `title + company` share NO token with the query tokens. This is a defensive belt for InfoJobs's weak server-side filter. |
| `backend/tests/unit/test_aggregator_ranking.py` | Modified | Add 6-8 new scenarios for the `"keyword_match"` strategy + the `keyword_score` function |
| `backend/tests/integration/test_aggregator_ranking.py` | Modified | Add 2-3 end-to-end scenarios pinning the `keyword_match` strategy on the FastAPI stack |
| `backend/tests/integration/test_aggregator_api.py` | Modified | Add 1-2 scenarios for the new `linkedin_geo_id` forwarding in the `/jobs` route |
| `backend/tests/unit/test_hardcoded_location_resolver.py` | UNCHANGED | The resolver is already tested; no new tests needed. |
| `backend/tests/unit/test_infojobs_scraper.py` | Modified | Add 2-3 scenarios for the client-side `keyword_filter` |

## 5. approaches

| Approach | Pros | Cons | Effort |
|---|---|---|---|
| **A. All-in-one change**: `geo_id` in the route + `keyword_match` strategy + InfoJobs filter + `query_tokens` in cache | Each improvement is small (~50-100 LOC); the change is reviewable in a single PR; solves all 5 root causes | Larger PR (~800-1200 LOC including tests). One reviewer, one decision. | Medium-High |
| **B. Chained PRs**: (1) `keyword_match` strategy + tests; (2) `geo_id` plumb through `/jobs` route; (3) InfoJobs client-side filter; (4) `query_tokens` cache key | Each PR is ~200-400 LOC; the chain is reviewable; each PR is independently revertable; matches the project's `chat-filter-2stage` chain style | 4 PRs = 4× review cycles. The `query_tokens` cache key is technically a breaking change to existing per-source cache keys (a v1 cache hit on `(source, keywords, location, limit, geo_id)` becomes a miss on `(source, query_tokens, location, limit, geo_id)`); the v1 cache is in-memory, so a deploy restarts the cache — non-issue in practice. | Medium |
| **C. Minimal: just the `geo_id` plumb + `keyword_match` strategy**, defer InfoJobs filter + `query_tokens` cache key | Smallest possible PR (~400-600 LOC); addresses root causes #1, #3, #4; InfoJobs noise remains a follow-up | The user's report SPECIFICALLY mentions 5 InfoJobs offers with NO relation to "react" (recepcionista, pintor, etc.); if we don't fix the InfoJobs filter, the user will be unhappy. **NOT RECOMMENDED** for the user's stated complaint. | Low |
| **D. ML-based relevance** (e.g. a small embedding model, cosine similarity) | Theoretically the "right" answer | 10x the scope, requires a model download, adds a dependency, latency, and a per-query cost. Out of scope per the orchestrator's launch prompt. | Very High |

## 6. recommendation

**Approach A (single PR, ~1000-1500 LOC)**, but with a clear separation of
concerns in the code so each improvement is independently testable:

1. **`geo_id` plumb through `/jobs` route** (~50 LOC + 30 LOC tests):
   resolve `location` → `linkedin_geo_id` in the route and forward to
   `use_case.search(..., linkedin_geo_id=...)`. **One-line change in
   the route; the aggregator already accepts the kwarg.**
2. **`keyword_match` ranking strategy** (~100 LOC prod + 200 LOC tests):
   add a 4th strategy to `RankingStrategy` Literal; implement a
   `keyword_score(Job, q, location)` pure function (the scorer); the
   function returns a float in `[0.0, 1.0]` based on token overlap
   between `(title, company, description)` and the query tokens
   (after stop-word + stemming). **The default strategy stays
   `posted_at`** to preserve the v1 contract; `AGGREGATOR_RANKING_STRATEGY=keyword_match`
   is the new opt-in via env var.
3. **InfoJobs client-side `keyword_filter`** (~30 LOC prod + 60 LOC tests):
   in the InfoJobs `_parse_cards`, drop cards whose normalized
   `title + company` share zero tokens with the query tokens.
   This is a per-card filter that runs BEFORE the `Job` is built (so
   we don't waste effort on a card we'll discard). The card is
   silently dropped (the dedup is unaffected; the per-page count
   decreases; the helper's zero-cards break handles end-of-results).
4. **`query_tokens` in `JobSearchCacheKey`** (~20 LOC prod + 40 LOC tests):
   extend the NamedTuple with `query_tokens: tuple[str, ...] = ()`.
   The per-source cache key is now
   `(source, query_tokens, location, limit, geo_id)` — two queries
   with the same `keywords="react"` and `keywords="React Backend"`
   are now distinct cache entries (they tokenize to different sets).
   This is technically a cache invalidation on deploy (the in-memory
   cache is empty on startup), but the hit rate will be HIGHER for
   similar queries going forward (e.g. "react" and "react developer"
   share tokens, so a future query for "react developer" can reuse
   some of the "react" cache if we want to — but the v1 design
   doesn't support partial-token sharing, so they remain distinct
   entries; the value is in disambiguating "react" from "redux").

**Review budget forecast**: ~1000-1500 LOC. The orchestrator's review
budget is 5000 lines; we're well under. **No chained PR needed.**
**Strict TDD**: every new module ships tests-first; no implementation
code without a failing test pin.

## 7. risks

1. **The `keyword_score` heuristic is imperfect** (MEDIUM): simple
   token overlap + stemming will false-positive on common words
   ("react" matches "reaction", "manager" matches "manage"). The
   `keyword_match` strategy is a STRICT IMPROVEMENT over today's
   `posted_at`-only sort, but it's not a substitute for the LLM
   filter (which is opt-in via the chat endpoint). Mitigation: the
   default strategy stays `posted_at`; `keyword_match` is opt-in
   via `AGGREGATOR_RANKING_STRATEGY=keyword_match`. Roll back via
   env var. The scorer is a pure function; tests pin the behavior
   on 20+ synthetic (title, query) pairs.

2. **Tightening LinkedIn `geoId` MIGHT break queries for unknown
   locations** (LOW): the resolver returns `None` for unknown
   inputs and logs a WARNING; the LinkedIn scraper falls back to
   `?location=<str>` (the broken-but-doesn't-500 path). The
   fallback IS already pinned by `test_linkedin_geo_id_none_is_forwarded_to_linkedin_port`
   (line 473). **No new risk vs. the `fix-linkedin-geoid` status
   quo**; we're just extending the forwarding from the chat path to
   the `/jobs` path.

3. **The InfoJobs client-side `keyword_filter` MIGHT drop
   legitimately relevant results** (MEDIUM): a job titled
   "Software Engineer" for the query "react" has zero token overlap
   with "react" — but the job might describe "React, TypeScript,
   Node.js" in the description. Mitigation: the filter uses
   `title + company` ONLY (not `description`), so the job IS
   dropped. The chat path (2-stage + LLM filter) is the escape
   hatch for nuanced queries. The filter is a per-CARD filter
   (not a per-RESULT filter), so the dedup + ranking is unaffected
   for cards that pass.

4. **The `query_tokens` cache key is a breaking change to the
   per-source cache key shape** (LOW): the in-memory cache is empty
   on startup, so deploys are non-issues. The v1 `JobSearchCacheKey`
   has 5 fields; adding a 6th `query_tokens: tuple[str, ...] = ()`
   field with a default value is backward-compatible for callers
   that construct the NamedTuple positionally. The aggregator's
   `search()` is the only constructor; it computes the tokens
   from `keywords`.

5. **The default ranking stays `posted_at` for backward compat**
   (LOW): the new `keyword_match` strategy is opt-in. The user's
   `GET /jobs` call will NOT see the new behavior unless
   `AGGREGATOR_RANKING_STRATEGY=keyword_match` is set. This is the
   right call for backward compat, but the user might expect the
   default to change. **Mitigation: flag this as an open question
   in the proposal; ask the user to confirm whether the default
   should flip to `keyword_match` or stay `posted_at`.**

6. **The 4 unit tests in `test_aggregator_ranking.py` that pin
   the `posted_at` default behavior will stay GREEN** (LOW): the
   new strategy is additive. The 7 existing tests pass unchanged.

7. **The 2-stage chat filter path is unchanged** (LOW): the
   resolver is already plumbed in `_execute_2stage`. The
   `keyword_match` strategy is the AGGREGATOR's choice; the chat
   filter reuses the aggregator's output. **No chat-path regression.**

## 8. open_questions

1. **Should the default ranking strategy flip from `posted_at` to
   `keyword_match`?** The user's complaint is about relevance, not
   freshness. A flip would make every `GET /jobs` call use the new
   scorer. The conservative default is "stay `posted_at`, opt-in
   via env var" — but that means the user has to set the env var
   to see the improvement. **Recommend: ask the user.** This is a
   one-line config flip in `app_factory.build_app()`.

2. **Should the InfoJobs client-side `keyword_filter` apply to
   LinkedIn + Indeed too?** The user's report specifically mentions
   LinkedIn "DataAnnotation" offers — those have the word "AI" and
   "Frontend" which DO share tokens with "react" (well, "react" is
   not in any of those, but "developer" is). A more aggressive
   filter (across all 3 sources) would catch them, but it would
   also drop legit offers that don't mention the keyword in the
   card preview. **Recommend: apply ONLY to InfoJobs for v1; the
   LLM filter is the escape hatch for LinkedIn/Indeed nuanced
   queries.** This is the smallest correct change.

3. **Should the `keyword_score` use stemming (e.g. `react` matches
   `reactive`)?** Stemming reduces false negatives but increases
   false positives. The v1 scorer uses plain token overlap +
   lowercasing; a `porter-stemmer` library is a future enhancement.
   **Recommend: NO for v1 — keep it as 50 lines of pure Python.**

## 9. ready_for_proposal

Yes. The 4 work items (geo_id, keyword_match, InfoJobs filter,
query_tokens) are well-scoped, each is ~50-300 LOC, and the Strict TDD
discipline is straightforward (RED test → GREEN impl). The proposal
artifact will follow the OpenSpec template (in Spanish per the
orchestrator's request, with code/path identifiers in English).

## 10. skill_resolution

`paths-injected` — received exact skill paths from orchestrator
(`sdd-explore` + `sdd-propose` + `_shared` + `sdd-apply` + `sdd-verify`).
