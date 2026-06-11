# Proposal: `backend-linkedin-stealth`

> **Change**: `backend-linkedin-stealth` • **Mode**: `both` (OpenSpec files + Engram copy) • **Strict TDD**: ACTIVE
> **Date**: 2026-06-10 • **Base**: `6402798` (post `backend-linkedin-auth` merge on main; working tree clean)
> **Status**: `proposed` (ready for `sdd-spec`)
> **Upstream**: obs #365 (explore — the 0.55 confidence + precedent shapes) + obs #364 (trigger — the 152-char `li_at` + 50-redirect loop) + obs #362 (`backend-linkedin-auth` archive — the `REQ-LA-*` namespace we are NOT polluting) + obs #83 (the `playwright-stealth` Indeed precedent we are mirroring)
> **Precedent cycle**: `backend-linkedin-auth` (5 WU, 1,303 net LOC, PASS at `6402798`) — this change is a smaller, surgical follow-up.

## Why

The just-merged `backend-linkedin-auth` works at the code level (the cookie loads, the adapter returns the value, the wiring is correct — confirmed by obs #364's live test) but LinkedIn/Cloudflare blocks all requests with `ERR_TOO_MANY_REDIRECTS` (50 redirects → 302 loop) on both Playwright and direct curl. The Cloudflare Bot Management decision happens at the TLS/canvas/behavioral layer BEFORE checking `li_at`, and `is_auth_wall` from the v1 cycle does NOT fire because the browser never reaches a soup parseable.

**This change is the first-intent mitigation**: add `playwright-stealth` (already a project dep, used by Indeed + InfoJobs) + extend the cookie port to support **multiple LinkedIn cookies** (`li_at` + `JSESSIONID` + `bcookie` + `li_gc`) + add a Cloudflare-challenge detector that surfaces the 302 loop gracefully (soft path: WARNING + return `[]`, no raise). **Confidence that stealth bypasses the LinkedIn + Cloudflare-2026-302-loop case: 0.55** (per explore obs #365 §4.4 — the upstream `playwright-stealth` README self-describes as "proof-of-concept starting point"; the Indeed precedent succeeded against the Cloudflare variant Indeed serves, but the LinkedIn 302-loop case is a 2024+ escalation). If this does not work, the follow-up is `backend-linkedin-residential-proxy` (out of scope; documented in §Out of scope).

## What changes

- **EXTENDED** capability `linkedin-auth-cookie` — the v1 `LinkedInAuthCookiePort.cookie() -> SecretStr | None` Protocol is **REPLACED** with `cookies() -> list[tuple[str, SecretStr]] | None` (multi-cookie shape, per Q1). The v1 `EnvLinkedInAuthCookieAdapter(SecretStr | None)` is **KEPT** as a backward-compat shim (a single-cookie constructor auto-wraps to a 1-element list); a new `MultiEnvLinkedInAuthCookiesAdapter` aggregates the 4 cookies (`li_at` + `JSESSIONID` + `bcookie` + `li_gc`) and is wired in `app_factory`. Each cookie is independently optional. The 35 v1 tests stay green.
- **EXTENDED** capability `linkedin-scraper` — `LinkedInPlaywrightScraper` constructor gets a new `stealth: Stealth | None = None` kwarg; `search()` calls `await self._stealth.apply_stealth_async(ctx)` between `new_context()` and `add_cookies()` (mirroring the Indeed precedent at `indeed/scraper.py:246-247` and the InfoJobs precedent at `infojobs/scraper.py:326-327`). The `_make_fetch_one_page` closure gains a third check `is_cloudflare_challenge(soup)` BEFORE the existing `is_auth_wall(soup)` (when `auth_cookie is not None`); the v1 `is_block_page` hard-raise remains the anonymous-path fallback (per Q4 soft path, per Q5 new function).
- **NEW** capability `linkedin-anti-bot-detector` — a pure `is_cloudflare_challenge(soup: BeautifulSoup) -> bool` function in `infrastructure/linkedin/parsers.py` (next to the v1 `is_block_page` + `is_auth_wall`). Returns `True` when the page contains Cloudflare's "Checking your browser before accessing..." challenge markers (specific 2026 selector set, pinned in the test via a new `CLOUDFLARE_CHALLENGE_HTML` fixture).
- **EXTENDED** capability `linkedin-config` — 3 new optional `SecretStr | None` fields in `Settings`: `linkedin_jsessionid`, `linkedin_bcookie`, `linkedin_li_gc`, each with the v1 validator pattern (HARD on `<8` chars when present, soft `None` is allowed). The v1 `linkedin_li_at` field stays unchanged.
- **NEW** `CLOUDFLARE_CHALLENGE_HTML` fixture in `tests/fixtures/linkedin_search.py`, mirroring the v1 `BLOCKED_PAGE_HTML` precedent in `tests/fixtures/indeed_search.py` (per obs #365 §2.9 + the Indeed `is_indeed_blocked` precedent that was proved against the live Cloudflare variant per obs #74). Captured offline — committed, no live network.
- **EXTENDED** `backend/README.md` "Manual verification" section with a new `### LinkedIn anti-bot stealth (multi-cookie + playwright-stealth)` subsection (mirrors the v1 `### LinkedIn auth cookie (optional)` structure).
- **EXTENDED** `backend/.env.example` with the 3 new placeholder lines + a note that they're optional (per Q2 — individual env vars matching the per-source `AliasChoices` precedent at `config.py:175-201`).
- **NEW** test surface: `tests/unit/test_linkedin_stealth.py` (stealth wiring + multi-cookie composition), `tests/unit/test_linkedin_cloudflare_challenge.py` (the new detector — mirror of `test_linkedin_auth_wall.py`), `tests/integration/test_linkedin_stealth.py` (end-to-end offline via `build_app(use_case=...)` with `FakeLinkedInAuthCookiesPort`).

## Out of scope (explicit)

- **Residential proxy integration** — the documented fallback path is `backend-linkedin-residential-proxy` if stealth fails (per explore obs #365 §4.6). NOT shipped in this change.
- **Browser real (non-headless) mode** — headless is the test default; real mode is a follow-up if Cloudflare-2026 escalates further.
- **Automated cookie refresh** — the operator rotates manually; `is_cloudflare_challenge` WARNING is the signal.
- **Retry/backoff with exponential backoff** — the existing `paginated_search` helper handles timeouts; per-page retry would couple to source-specific concerns.
- **Circuit breaker for LinkedIn** — would require process-state that we deliberately do not add.
- **Detectors for other anti-bot vendors** (DataDome, PerimeterX, Akamai) — out of scope; each new source/vendor is its own follow-up.
- **Modifying the other 2 scrapers (Indeed, InfoJobs)** — they already use stealth; no LinkedIn-specific work applies to them.
- **Live-network test against real LinkedIn** — AGENTS.md rule #1 forbids live scraping in tests; the live smoke test is documented in the README and run by the operator manually, not by CI.

## Affected capabilities (the contract with `sdd-spec`)

| Capability | Action | Notes |
|---|---|---|
| `linkedin-anti-bot-detector` | **NEW** | `is_cloudflare_challenge(soup)` pure function + `CLOUDFLARE_CHALLENGE_HTML` fixture + `TestCloudflareChallengeDetector` test class. REQ namespace `REQ-LST-CF-001..003` (~3 REQs). |
| `linkedin-auth-cookie` | **EXTENDED** | `LinkedInAuthCookiePort.cookie() -> SecretStr \| None` REPLACED with `LinkedInAuthCookiesPort.cookies() -> list[tuple[str, SecretStr]] \| None`. The v1 `EnvLinkedInAuthCookieAdapter` kept as backward-compat shim; new `MultiEnvLinkedInAuthCookiesAdapter` aggregates 4 cookies. REQ namespace `REQ-LST-COOKIE-001..005` (extends, NOT replaces, the v1 4 REQ-LA-COOKIE-*). |
| `linkedin-scraper` | **EXTENDED** | New `stealth: Stealth \| None = None` ctor kwarg + per-context `apply_stealth_async(ctx)` call; new `is_cloudflare_challenge` check in the closure (BEFORE the v1 `is_auth_wall`, AFTER the v1 `is_block_page` only on the anonymous path). REQ namespace `REQ-LST-SCR-001..004` (~4 new REQs; the v1 6 REQ-LA-SCR-* stay byte-identical). |
| `linkedin-config` | **EXTENDED** | 3 new optional `SecretStr \| None` fields (`linkedin_jsessionid`, `linkedin_bcookie`, `linkedin_li_gc`) with the v1 validator pattern (HARD on `<8` chars when present, soft `None` is allowed). REQ namespace `REQ-LST-CFG-001..003` (3 new REQs; the v1 4 REQ-LA-CFG-* stay unchanged). |
| `composition-root` (in `app_factory.build_app()`) | **EXTENDED** | Wire `MultiEnvLinkedInAuthCookiesAdapter(...)` with the 4 `Settings.linkedin_*` fields; pass `stealth=Stealth()` to the `LinkedInPlaywrightScraper` ctor (mirrors the Indeed wire at `app_factory.py:323-339` and the InfoJobs wire below it). NO new exception types, NO new WARNING log messages (the v1 "LinkedIn scraper running without auth cookie" WARNING still fires when ALL 4 cookies are absent). |

**No MODIFIED or REMOVED capabilities.** **No new spec files** beyond what the archive sync will create: 1 NEW spec (`linkedin-anti-bot-detector`) + 3 EXTENDED specs (the v1 `linkedin-auth-cookie`, `linkedin-scraper`, `linkedin-config`).

## Acceptance

- All 4 new/extended capabilities have a `proposal.md` (this doc) + (after spec) `spec.md` + (after design) `design.md` + (after tasks) `tasks.md`.
- The v1 single-cookie `EnvLinkedInAuthCookieAdapter(SecretStr("AQE..."))` ctor still works (backward compat, per Q1).
- The new `MultiEnvLinkedInAuthCookiesAdapter(None, None, None, None).cookies() is None` (soft mode preserved — no cookies configured = anonymous path).
- The new `is_cloudflare_challenge(BeautifulSoup(CLOUDFLARE_CHALLENGE_HTML))` returns `True`; on the v1 `SEARCH_PAGE_HTML` returns `False` (no false positive).
- The `_make_fetch_one_page` closure precedence is: **`is_cloudflare_challenge` → `is_auth_wall` → `is_block_page`** when `auth_cookie is not None` (newest first — the soft path wins), and **`is_block_page` → `is_auth_wall` (skipped) → `is_cloudflare_challenge` (skipped)** when `auth_cookie is None` (anonymous path — the v1 hard-raise behavior is preserved byte-identical).
- `ruff check`, `ruff format --check`, `mypy` (project-wide, the correct invocation per the v1 verify-report), and `pytest` are all green.
- The 35 v1 `backend-linkedin-auth` tests stay green (the v1 anonymous-path behavior is preserved; the v1 `test_search_raises_blocked_on_auth_wall` is preserved unchanged).
- New test count delta: **+20 to +30** tests (the change is smaller than the v1 cycle — ~6 production files, ~5 test files).
- **Live verification** (out of CI): a manual smoke test with a real `li_at` cookie is expected to pass (LinkedIn returns real job data, not the auth-walled reduced list). This is documented in the README; the CI suite does NOT run live verification (AGENTS.md rule #1).
- **Real `li_at` leak scan**: CLEAN — only the synthetic 12-byte `"AQEAAAAQEAAA"` placeholder + field/env-var names appear in test code (AGENTS.md rule #7).
- **`Co-Authored-By:` trailers**: NONE (AGENTS.md rule #6).
- **Conventional commits**: ALL commits follow `<type>(<scope>): <subject>` (scope: `linkedin-stealth` for T-001..T-005, `linkedin-anti-bot` for the detector, `composition` for the wire, `docs` for README/.env).

## Risks

| # | Risk | Likelihood | Mitigation |
|---|------|------------|------------|
| 1 | **`playwright-stealth` may NOT bypass the LinkedIn + Cloudflare-2026-302-loop** (per explore obs #365 §4.4 — the upstream README self-describes as "proof-of-concept starting point"; the Indeed precedent succeeded, the LinkedIn 302 case is a 2024+ escalation; **confidence 0.55**) | **HIGH** | The change is reversible (a `git revert` removes it; the v1 anonymous path is preserved). The follow-up `backend-linkedin-residential-proxy` is the documented fallback path (in §Out of scope). The CI suite does NOT depend on stealth working at runtime (all tests are offline with fixtures), so a stealth failure does not block CI. |
| 2 | **Multi-cookie partial injection** — the 4 minimum cookies (`li_at` + `JSESSIONID` + `bcookie` + `li_gc`) may be insufficient against a fingerprinting gate that expects 19+ cookies (the operator's full cookie set per obs #364) | **HIGH** | The soft-path `is_cloudflare_challenge` detector surfaces this clearly (WARNING + return `[]`, no raise). The `LinkedInAuthCookiesPort.cookies()` Protocol returns an arbitrary-length list — a future change can add more cookies to `app_factory` without code changes. |
| 3 | **The Cloudflare challenge page evolves**; the detector needs maintenance (the 2026 selector set may be replaced by 2027 selectors) | **MED** | The test fixture is pinned to a 2026-06 capture. A future Cloudflare change requires a re-capture (procedure documented in the README); the detector is a single function in `parsers.py` — 1 function + 1 fixture update path. |
| 4 | **Backward compat with the v1 single-cookie `EnvLinkedInAuthCookieAdapter(SecretStr)` ctor** — 35 v1 tests construct it directly bypassing `Settings` | **MED** | The v1 adapter is kept as a single-cookie shim (auto-wraps to a 1-element list); the new adapter is a different class. The 35 v1 tests stay green (the v1 `is_auth_wall` behavior is preserved). |
| 5 | **`playwright-stealth` Python port maintenance status** (single maintainer, ~1 release per 4-8 months) | **LOW** | The dep is `playwright-stealth>=2.0,<3.0` (already pinned in `pyproject.toml:25`); the 2.x API is stable. The fallback path (residential proxy) does NOT depend on `playwright-stealth`. |
| 6 | **Future LinkedIn-cookie-set growth** (LinkedIn adds new cookies; Cloudflare adds new ones) | **LOW** | The Protocol accepts an arbitrary `list[tuple[str, SecretStr]]`. A future change adds 1 `Settings` field + 1 adapter line; the Protocol + scraper are unchanged. |
| 7 | **The new `MultiEnvLinkedInAuthCookiesAdapter.__repr__` could leak the cookie COUNT** in a way that reveals WHICH cookies the operator has (a 1-bit side-channel) | **LOW** | The repr shows the count only, not the names. A count-of-4 vs count-of-2 is a 1-bit side-channel; the operator's own `ls -la .env` is already a richer side-channel. Acceptable. |
| 8 | **The 3 new env vars leak via process listings** (`/proc/<pid>/environ`) | **LOW** | Same risk as `LINKEDIN_LI_AT` (the v1 precedent, AGENTS.md rule #7). Mitigated by `direnv` (the documented operator pattern from the v1 README). Not in scope for this change. |
| 9 | **`is_cloudflare_challenge` fires a false positive on a healthy SERP** (e.g. if LinkedIn reuses the "Just a moment..." title for a legitimate rate-limit page) | **LOW** | The detector checks BOTH the title AND the absence of job cards (the same "cards win" rule as `is_block_page` + `is_auth_wall`). A healthy SERP with cards never matches. A false positive is impossible by construction. |
| 10 | **The v1 verify-report's lessons are not applied** (e.g. adding a `__init__.py` re-export hub by accident, or shipping a real cookie value) | **LOW** | The apply phase is RED-first; the v1 `apply-progress.md` (obs #358) and `verify-report.md` (obs #360) are referenced as the discipline template. `__init__.py` files stay docstring-only; only the synthetic 12-byte `"AQEAAAAQEAAA"` is in test code. |

## Open questions

**None — all 5 open questions from explore obs #365 §6 are auto-resolved by the orchestrator** (Q1=`list[tuple[str, SecretStr]]`, Q2=individual env vars matching the `AliasChoices` precedent, Q3=BrowserContext level, Q4=soft path mirrors `is_auth_wall`, Q5=new function `is_cloudflare_challenge` parallel to `is_auth_wall`).

## Rollback plan

3 logical commits, each independently revertible:

- **Commit 1 (stealth wiring + multi-cookie Protocol)**: revert removes the `stealth: Stealth | None = None` ctor kwarg + the `apply_stealth_async(ctx)` call + the `LinkedInAuthCookiesPort` Protocol + the `MultiEnvLinkedInAuthCookiesAdapter`. The v1 single-cookie `EnvLinkedInAuthCookieAdapter` is preserved; the scraper reverts to v1 behavior (single cookie, no stealth). The 35 v1 tests stay green.
- **Commit 2 (Cloudflare detector)**: revert removes the `is_cloudflare_challenge` function + the `CLOUDFLARE_CHALLENGE_HTML` fixture + the closure integration. The v1 `is_auth_wall` + `is_block_page` are preserved; the scraper reverts to the v1 auth-wall detection surface.
- **Commit 3 (3 new Settings fields + docs)**: revert removes the 3 new `Settings.linkedin_*` fields + the 2 new env vars in `.env.example` + the new README subsection. The v1 `linkedin_li_at` field stays. Zero runtime impact.

**Zero-downtime rollback**: a deploy with the new Protocol added but the scraper NOT updated is safe (the new `cookies()` method has no callers yet; the v1 `cookie()` method is preserved on the v1 adapter for any code that constructs it directly). **Runtime kill switch**: leaving all 4 `LINKEDIN_*` env vars empty in `.env` runs the scraper anonymously (v1 behavior) without re-deploy.

## Dependencies

- **No new external dependencies.** `playwright-stealth>=2.0,<3.0` is **already pinned** in `pyproject.toml:25` (Indeed + InfoJobs use it; this change just adds a 3rd caller). All other deps are stdlib or already-imported (`pydantic.SecretStr`, `pydantic.field_validator`, `pydantic.AliasChoices`, `playwright_stealth.Stealth`, `bs4.BeautifulSoup.select_one`).
- **No new spec files** beyond what the archive sync will create. The 4 spec files (1 NEW + 3 EXTENDED) live in `openspec/changes/backend-linkedin-stealth/specs/{capability}/spec.md` and sync to `openspec/specs/` on archive (per the v1 multi-capability-delta pattern in obs #362).
- **No new env vars** beyond the 3 new `LINKEDIN_*` fields added in `Settings` (the 4 total are: `LINKEDIN_LI_AT` (v1) + `LINKEDIN_JSESSIONID` (NEW) + `LINKEDIN_BCOOKIE` (NEW) + `LINKEDIN_LI_GC` (NEW)).

## Workload forecast (for `sdd-tasks`)

| Field | Value |
|-------|-------|
| Estimated changed lines | ~440 (range 380–500, per design §3 + TDD tax) |
| 400-line budget risk | **Low** (~88 LOC/commit avg, 5 commits) |
| Chained PRs recommended | **No** |
| Suggested split | single PR (5 conventional commits) |
| Delivery strategy | ask-on-risk → resolved as `single-pr` (per preflight C2) |
| Decision needed before apply | No (single PR approved at design) |

**5 work units** (mirrors the v1 cycle's T-001..T-005 + T-006 pattern):

- **T-001** (stealth wiring + `LinkedInAuthCookiesPort` Protocol + `MultiEnvLinkedInAuthCookiesAdapter`): ~80 LOC, mirrors the Indeed T-001 + the v1 T-001.
- **T-002** (3 new `Settings.linkedin_*` fields + reusable validator helper extracted from v1 `_normalize_empty_li_at`): ~95 LOC, mirrors the v1 T-002.
- **T-003** (`is_cloudflare_challenge(soup)` + `CLOUDFLARE_CHALLENGE_HTML` fixture): ~95 LOC, mirrors the v1 T-003 (`is_auth_wall` + `BLOCK_PAGE_HTML`).
- **T-004** (scraper changes: stealth injection + closure `is_cloudflare_challenge` integration with conditional precedence): ~110 LOC, mirrors the v1 T-004 (cookie injection + closure `is_auth_wall` integration).
- **T-005** (composition root wire + `app_factory` updates + integration test + `README.md` + `.env.example`): ~60 LOC, mirrors the v1 T-005.

**Total**: ~440 LOC across 5 commits (~88 LOC/commit avg). Well under the 400-line per-PR sub-budget and the 5,000-line hard review budget. Single PR is sufficient — no chained PRs needed.

## Next step

Ready for `sdd-spec`. The orchestrator should:

1. Confirm the 5 auto-resolved decisions (Q1-Q5) are still locked-in — they are, per the launch prompt.
2. Verify the parallel cycles (`backend-linkedin-auth` at `6402798`) are merged — they are.
3. Delegate to `sdd-spec` with inputs: this proposal (Engram observation to be created), explore obs #365, trigger obs #364, the 4 affected capabilities (1 NEW + 3 EXTENDED), and the v1 cycle's `apply-progress.md` (obs #358) + `verify-report.md` (obs #360) as the discipline template.
4. Expect ~14-18 new REQs across the 4 capabilities (3 `REQ-LST-CF-*` + 5 `REQ-LST-COOKIE-*` + 4 `REQ-LST-SCR-*` + 3 `REQ-LST-CFG-*`).

**Skill resolution**: `paths-injected` — orchestrator pre-resolved `sdd-propose/SKILL.md` + `test-driven-development/SKILL.md` + `_shared/sdd-phase-common.md` + `_shared/openspec-convention.md`.
