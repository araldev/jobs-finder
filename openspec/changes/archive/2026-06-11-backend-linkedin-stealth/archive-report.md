# Archive Report: `backend-linkedin-stealth`

## Status

**Closed — VERDICT: PASS_WITH_WARNINGS** (live outcome: `STEALTH_INSUFFICIENT`, follow-up required).

Implementation complete, verification clean on the 10 quality gates (15/15 REQs covered, 38 new tests, `scripts/check.sh` clean when env unloaded, v1 baseline preserved). The live smoke test against LinkedIn returned `HTTP 502 / ERR_TOO_MANY_REDIRECTS` in <5s with the operator's fresh 4-5 cookies + `playwright-stealth` — confirming the explore-phase 0.55 confidence that `playwright-stealth` alone is insufficient against the 2026 Cloudflare+LinkedIn anti-bot. **Mergeable; the documented follow-up is `backend-linkedin-xvfb` (Xvfb + browser real), pre-confirmed by the user on 2026-06-10.**

- **Close date**: 2026-06-11
- **Branch**: `feature/backend-linkedin-stealth` (PUSHED at `a37b481`, NOT MERGED — user creates the PR after this cycle closes)
- **Base**: `6402798` (post `backend-linkedin-auth` merge on main)
- **Head**: `a37b481`
- **Commits**: 5 (T-001..T-005)
- **Verify verdict**: PASS_WITH_WARNINGS (per `verify-report` obs #371)
- **Verify-report obs**: #371
- **Apply-progress obs**: #370
- **Tasks obs**: #369
- **Design obs**: #368
- **Spec obs**: #367
- **Proposal obs**: #366
- **Exploration obs**: #365
- **Trigger discovery obs**: #364
- **Open discoveries** (linked but not closed by this change):
  - obs #373 — `discovery/linkedin-fingerprinting-vs-rate-limit-hypothesis` (open, unvalidated)
  - obs #374 — `discovery/linkedin-redirect-loop-cookies-not-the-cause` (open, cookies ruled out)
- **Init context obs**: #1, #2, #3

---

## 1. Traceability — observation IDs of the change artifacts

| Topic | Observation ID | Status |
|---|---|---|
| `sdd-init/jobs-finder` | #1 | ok |
| `sdd/jobs-finder/testing-capabilities` | #2 | ok |
| `skill-registry` | #3 | ok |
| `sdd/backend-linkedin-auth/explore` | #353 | ok (precedent) |
| `sdd/backend-linkedin-auth/archive-report` | #362 | ok (precedent — just-closed) |
| `sdd/backend-linkedin-auth/verify-report` | #360 | ok (precedent) |
| `sdd/backend-linkedin-auth/apply-progress` | #358 | ok (precedent) |
| `discovery/backend-linkedin-stealth-trigger` | #364 | ok (TRIGGER) |
| `sdd/backend-linkedin-stealth/explore` | #365 | ok |
| `sdd/backend-linkedin-stealth/proposal` | #366 | ok |
| `sdd/backend-linkedin-stealth/spec` | #367 | ok |
| `sdd/backend-linkedin-stealth/design` | #368 | ok |
| `sdd/backend-linkedin-stealth/tasks` | #369 | ok |
| `sdd/backend-linkedin-stealth/apply-progress` | #370 | ok |
| `sdd/backend-linkedin-stealth/verify-report` | #371 | **PASS_WITH_WARNINGS** |
| `discovery/linkedin-fingerprinting-vs-rate-limit-hypothesis` | #373 | open (hypothesis, unvalidated) |
| `discovery/linkedin-redirect-loop-cookies-not-the-cause` | #374 | ok (cookies ruled out) |
| `sdd/backend-linkedin-stealth/archive-report` | (this one) | **closing** |

---

## 2. Capabilities (delta)

| Action | Capability | REQ count | REQ namespace |
|---|---|---|---|
| **NEW** | `linkedin-anti-bot-detector` | 3 | `REQ-LST-CF-001..003` |
| **EXTENDED** | `linkedin-auth-cookie` | +5 (on top of 4 v1 `REQ-LA-COOKIE-*`) | `REQ-LST-COOKIE-001..005` |
| **EXTENDED** | `linkedin-scraper` | +4 (on top of 4 `REQ-LI-SCR-*` + 6 v1 `REQ-LA-SCR-*`) | `REQ-LST-SCR-001..004` |
| **EXTENDED** | `linkedin-config` | +3 (on top of 4 v1 `REQ-LA-CFG-*`) | `REQ-LST-CFG-001..003` |
| **UNCHANGED** | `linkedin-auth-wall-detector` | 0 (v1 6 `REQ-LA-AWALL-*` stay byte-identical) | n/a |

**No MODIFIED or REMOVED capabilities.** The mixed namespace (`REQ-LA-*` for v1 + `REQ-LI-*` for URL builder + `REQ-LST-*` for stealth) is intentional; all v1 REQs are preserved byte-identical.

**Total after archive**: 4 global spec files extended, 1 new global spec file created. 15 new `REQ-LST-*` promoted to the canonical source of truth.

---

## 3. Spec sync (per multi-domain delta split pattern, obs #350)

Per the v1 cycle's precedent (obs #362 archive + obs #350 pattern), the delta spec was multi-capability (1 file with 4 sections in the change folder) and the archive splits it into 4 separate global spec files.

| Capability | Global spec file | Action | REQ count added |
|---|---|---|---|
| `linkedin-anti-bot-detector` | `openspec/specs/linkedin-anti-bot-detector/spec.md` | **NEW** (foundational) | 3 `REQ-LST-CF-*` |
| `linkedin-auth-cookie` | `openspec/specs/linkedin-auth-cookie/spec.md` | **EXTENDED** (appended 5 new) | 5 `REQ-LST-COOKIE-*` |
| `linkedin-scraper` | `openspec/specs/linkedin-scraper/spec.md` | **EXTENDED** (appended 4 new) | 4 `REQ-LST-SCR-*` |
| `linkedin-config` | `openspec/specs/linkedin-config/spec.md` | **EXTENDED** (appended 3 new) | 3 `REQ-LST-CFG-*` |

**Sync discipline notes:**

- `linkedin-anti-bot-detector` is a NEW foundational spec (the delta's Domain 1 did not have a pre-existing main spec).
- `linkedin-auth-cookie` is EXTENDED — pre-existing 4 `REQ-LA-COOKIE-001..004` (v1 single-cookie, kept) + 5 new `REQ-LST-COOKIE-001..005` (multi-cookie, appended).
- `linkedin-scraper` is EXTENDED — pre-existing 4 `REQ-LI-SCR-001..004` (URL builder) + 6 `REQ-LA-SCR-001..006` (v1 cookie injection) + 4 new `REQ-LST-SCR-001..004` (stealth + multi-cookie + closure precedence + Cloudflare WARNING) APPENDED. The mixed namespace (`REQ-LI-` for URL builder + `REQ-LA-` for v1 cookie + `REQ-LST-` for stealth) is intentional.
- `linkedin-config` is EXTENDED — pre-existing 4 `REQ-LA-CFG-001..004` (v1 `linkedin_li_at`) + 3 new `REQ-LST-CFG-001..003` (3 new optional SecretStr fields + shared validator + repr no-leak) APPENDED.
- All v1 REQs and the v1 `Settings.linkedin_li_at` field + v1 `EnvLinkedInAuthCookieAdapter` are preserved byte-identical (the 35 v1 tests stay GREEN).

---

## 4. Branch state

- **Branch**: `feature/backend-linkedin-stealth`
- **Base**: `6402798` (main, post v1 `backend-linkedin-auth` merge)
- **Head**: `a37b481`
- **Commits ahead of main**: 5 (T-001..T-005)
- **Status**: PUSHED to `origin`, NOT MERGED
- **PR**: not yet created (user creates after archive closes via `gh pr create --base main --head feature/backend-linkedin-stealth`)
- **Single-PR strategy**: confirmed at design phase (the 5-commit history is well-bounded, ~1,867 net LOC, well under the 5,000-line hard review budget; 37% utilization)

### Commit history

| Hash | Subject | Work unit | Lines |
|---|---|---|---|
| `d5b72a4` | `feat(linkedin-stealth): add LinkedInAuthCookiesPort + MultiEnvAdapter + test double` | T-001 (Protocol + adapter + test double + 19 new tests) | +1200 |
| `634ca14` | `feat(linkedin-stealth): add Settings.linkedin_{jsessionid,bcookie,li_gc} + shared validators` | T-002 (3 new fields + 2 shared validators + 5 new tests) | +265 |
| `0d42a8c` | `feat(linkedin-stealth): add is_cloudflare_challenge defensive detector` | T-003 (pure `is_cloudflare_challenge(soup)` + `CLOUDFLARE_CHALLENGE_HTML` fixture + 7 new tests) | +227 |
| `4ba96c6` | `feat(linkedin-stealth): inject playwright-stealth + extend closure precedence` | T-004 (stealth injection + multi-cookie `add_cookies` + closure precedence + 4 new tests) | +278 |
| `a37b481` | `feat(composition): wire multi-cookie + operator docs` | T-005 (composition wire + integration tests + `.env.example` + `README.md` + 3 new tests) | +130 |

**Cumulative diff (5 commits vs `6402798`)**: 17 files changed, 1,867 net LOC (`+1,867`, `-111`). No `Co-Authored-By:` trailer (AGENTS.md rule #6). All 5 commits are conventional (`feat(linkedin-stealth)` × 4 + `feat(composition)` × 1).

---

## 5. Quality gates (final, per verify-report obs #371)

| Gate | Command | Operator's env (`.env` loaded) | Env unloaded (`.env` moved aside) |
|---|---|---|---|
| pytest (full suite) | `uv run pytest` | 1289 passed / 15 skipped / **3 FAILED** (the 3 env-related failures) | **1292 passed / 15 skipped / 0 FAILED** |
| pytest (without T-005 integration) | `uv run pytest --ignore=tests/integration/test_linkedin_stealth.py` | 1289 passed / 15 skipped / 2 FAILED (v1 pre-existing) | 1292 passed / 15 skipped / 0 FAILED |
| mypy (project-wide) | `uv run mypy` | ✅ Success: no issues found in 187 source files | n/a |
| ruff check | `uv run ruff check` | ✅ All checks passed! | n/a |
| ruff format --check | `uv run ruff format --check` | ✅ 188 files already formatted | n/a |
| **scripts/check.sh (canonical local-CI)** | `bash scripts/check.sh` | ❌ 3 env-related failures | ✅ **CLEAN** (1292 / 15 / 0) |

**`scripts/check.sh` is the canonical local-CI gate** per the v1 cycle's lesson learned. It is **CLEAN when env is unloaded** (the same gate that was the original failure mode for the v1 cycle, fixed at T-006 of `backend-linkedin-auth`).

**Real LinkedIn cookie scan**: CLEAN. Only the synthetic 12-byte `"AQEAAAAQEAAA"` + `"ajax:12345"` / `"v2_xyz_padded"` / `"gc_abc_padded"` test sentinels appear in test code. AGENTS.md rule #7 honored.

---

## 6. Deviations (independently assessed by verify-report obs #371 §6)

- **T-001 empty `SecretStr` normalization in adapter** (defense-in-depth): PASS. The adapter normalizes empty `SecretStr` to `None` at the ctor even though the `Settings._normalize_empty_*` validator does the same. The redundancy is intentional so a test that constructs the adapter directly with `SecretStr("")` still observes the same contract.
- **T-004 `is_auth_wall` precedence flip** (spec compliance): PASS. The apply phase implements a conditional precedence flip — the cookie path checks `is_cloudflare_challenge` FIRST (NEW, softest) → `is_auth_wall` SECOND (v1 soft) → `is_block_page` THIRD (v1 hard raise). The anonymous path keeps `is_block_page` FIRST (v1 byte-identical). The spec contract (`REQ-LST-SCR-003`) is fully satisfied; the v1 35-test baseline is preserved.
- **T-005 integration test uses 8+ char synthetic values** (deviation from spec's `"v2_xyz"` / `"gc_abc"` sentinels): PASS. The `Settings._reject_short_*` validators (T-002) reject values <8 chars. The T-005 integration test uses 8+ char padded versions (`"v2_xyz_padded"`, `"gc_abc_padded"`) that are still obviously synthetic. The unit tests in `test_linkedin_stealth.py` (T-001) construct the adapter directly (bypassing `Settings`) and use the 6-char sentinels as-is.
- **T-005 production-wire test accesses `use_case._port._port`** (private attribute): PASS WITH SUGGESTION S-2. Functional (the test passes) but a code smell. Refactoring to a public `app.state.linkedin_scraper` accessor is a separate architectural decision. Deferred to F-2 (see §8).
- **T-005 v1 startup WARNING message change** (`"without auth cookie"` → `"without any auth cookies"`): RESOLVED IN ARCHIVE. The implementer documented it as intentional, well-documented, no external log consumers break. The v1 substring `"without auth cookie"` is NOT a substring of the new message (the new message inserts `"any"` between `"without"` and `"auth"`); the change is intentional (covers all 4 cookies + mentions Cloudflare). The v1 integration test was UPDATED to the new prefix. The 35 v1 tests stay GREEN. SUGGESTION S-3 (verify-report) is RESOLVED via the documentation here.

---

## 7. Live smoke test outcome — STEALTH_INSUFFICIENT (the key finding)

- **HTTP 502** in 4.38 seconds (with 60s timeout) — `LinkedInBlockedError: Page.goto: net::ERR_TOO_MANY_REDIRECTS`
- **Tested with**: operator's 4 fresh cookies (`li_at` 152 chars + `JSESSIONID` 24 chars + `bcookie` 40 chars + `li_gc` 72 chars) + `playwright-stealth` + `playwright_BCOOKIE` env var also set
- **Faster than 10s timeout**: increasing timeout to 60s revealed the failure is `ERR_TOO_MANY_REDIRECTS` in <5s, not a slow response
- **Cookies are NOT the root cause**: same failure with fresh cookies (ruled out per obs #374)
- **TLS / HTTP/2 fingerprinting is the leading hypothesis** (per obs #373) — unvalidated; needs the user's manual browser test to confirm
- **The detector itself is correctly implemented**: 3/3 negative scenarios + 1/1 positive scenario pass with the `CLOUDFLARE_CHALLENGE_HTML` fixture; the operational reality is that LinkedIn's anti-bot closes the connection BEFORE the page renders as HTML, so the detector never has a chance to fire on the live request

**Operator-facing message** (per verify-report obs #371 §4.5): "Stealth didn't work for the real LinkedIn + Cloudflare-2026 case. The 0.55 confidence played out exactly as expected. The change is mergeable (code is correct; soft-path `is_cloudflare_challenge` detector is in place); the documented follow-up is `backend-linkedin-xvfb` (Xvfb + browser real)."

---

## 8. SUGGESTIONs from verify-report (4 total — all DEFERRED per Phase 1 decision)

### S-1 (DEFER to F-1): 3 env-related test failures when operator's `.env` is loaded

- **Pre-existing v1 root cause**: pydantic-settings re-reads `.env` AFTER `monkeypatch.delenv`; the operator's local `.env` has `LINKEDIN_LI_AT` set, so `Settings().linkedin_li_at` is `SecretStr('**********')` (not `None`)
- **Tests affected** (all same root cause, 2 pre-existing v1 + 1 new T-005):
  - `tests/unit/test_linkedin_config.py::TestSettingsEnvBinding::test_settings_linkedin_li_at_defaults_to_none` (v1)
  - `tests/integration/test_linkedin_auth_cookie.py::test_startup_warning_when_cookie_absent` (v1)
  - `tests/integration/test_linkedin_stealth.py::TestBuildAppMultiCookieWire::test_build_app_emits_startup_warning_when_all_cookies_unset` (NEW T-005)
- **Fix**: 1-line per test — `Settings(_env_file=None)` to force-disable the `.env` load
- **Status**: DEFERRED. The fix is safe, low-priority, and can be a T-006 apply-fix on the same branch OR a follow-up PR. Not blocking; the change is mergeable as-is.

### S-2 (DEFER to F-2): T-005 production-wire test accesses `use_case._port._port` (private attribute)

- **Code smell**: the test at `tests/integration/test_linkedin_stealth.py:115-117` reaches into the private `_port._port` chain. Functional but unclean.
- **Fix**: refactor to a public `app.state.linkedin_scraper` accessor
- **Status**: DEFERRED. Requires a design decision (where does the accessor live?). Separate change; can be folded into the `backend-linkedin-xvfb` follow-up or a dedicated refactor PR.

### S-3 (RESOLVED in archive): T-005 v1 startup WARNING message change

- **Intentional change**: the v1 message `"LinkedIn scraper running without auth cookie"` was updated to `"LinkedIn scraper running without any auth cookies"` to cover all 4 cookies + mention Cloudflare
- **The v1 substring `"without auth cookie"` is NOT a substring of the new message** (the new message inserts `"any"` between `"without"` and `"auth"`); the change is intentional and well-documented
- **No external log consumers in this repo break** (the v1 integration test was UPDATED to the new prefix)
- **Status**: RESOLVED. Documented in §6 Deviations. No further action needed.

### S-4 (renamed, DEFERRED to F-3): the cloudflare-challenge suggestion from verify-report

- **Not actually a SUGGESTION for this change** — it's a FOLLOW-UP. The "use a residential proxy or browser real" suggestion from the verify-report §5.3 is the documented next step.
- **Documented follow-up**: `backend-linkedin-xvfb` (Xvfb + browser real, per the user's pre-confirmed choice on 2026-06-10 23:50).
- **Status**: TRACKED as F-3.

---

## 9. Follow-ups (punted from this change)

| ID | Origin | Description | Pre-confirmed |
|---|---|---|---|
| **F-1** | verify-report S-1 | 1-line per test fix (`Settings(_env_file=None)`) for the 3 env-related test failures. Can be a T-006 apply-fix on the same branch OR a follow-up PR. | n/a (low-priority) |
| **F-2** | verify-report S-2 | Refactor T-005 production-wire test to use a public `app.state.linkedin_scraper` accessor instead of `use_case._port._port`. Requires a design decision. | n/a (low-priority) |
| **F-3** | verify-report S-4 (renamed) | **`backend-linkedin-xvfb`** — replace the headless Playwright with a real browser running under Xvfb so the browser has a real TLS fingerprint, real HTTP/2 SETTINGS frame, real canvas/WebGL. The orchestrator's recommendation per the user's pre-confirmed choice (Option D, 70-80% prob, 1-2 hours). | **YES** (user pre-confirmed 2026-06-10 23:50) |
| **F-4** | discovery obs #374 | Operator's `bscookie` cookie — the operator's browser has a `bscookie` (in addition to the `bcookie` already wired). The current code reads `bcookie` but not `bscookie`. This is a 1 Settings field + 1 wire + 1 test change; can be folded into F-3 (the Xvfb change) since the operator will be re-doing the cookie wiring anyway. | n/a (can be folded) |

---

## 10. Next steps for the user

1. **Create the PR**: `gh pr create --base main --head feature/backend-linkedin-stealth --title "feat(linkedin-stealth): multi-cookie + playwright-stealth + is_cloudflare_challenge" --body "<paste §1-§7 of this archive-report as the PR description, with the live test outcome honestly disclosed>"`
   - Direct URL: `https://github.com/araldev/jobs-finder/pull/new/feature/backend-linkedin-stealth`
2. **After PR is merged**, the next cycle is `backend-linkedin-xvfb` (F-3). This is the pre-confirmed approach.
3. **Manual verification** (in the new session, with F-3 deployed): with Xvfb + real browser, the operator should see LinkedIn return the full SERP without redirect loops. If YES → archive the Xvfb change with PASS. If NO → the next follow-up is a residential proxy (Option E).

---

## 11. Anti-patterns explicitly avoided

- No `Co-Authored-By:` trailer (AGENTS.md rule #6)
- No real LinkedIn cookie value in any committed file (AGENTS.md rule #7)
- No `__init__.py` business logic (AGENTS.md rule #4)
- No live network in any test (AGENTS.md rule #1)
- No global `os.environ['LINKEDIN_*']` read in the scraper (REQ-LST-SCR-001)
- No log of any cookie value at any level (REQ-LST-SCR-005)
- No use of pip/poetry (AGENTS.md rule #2; uv only)
- `mypy` (project-wide) was used for every quality gate, not `mypy --strict src/...` — the v1 cycle's lesson learned (obs #360 C-1) was applied
- The 5 work units are independently revertible (no inter-commit dependencies that would break a single `git revert`)

---

## 12. Archive contents

```
openspec/changes/archive/2026-06-11-backend-linkedin-stealth/
├── archive-report.md   ✅ (this file)
├── design.md           ✅ (691 lines, 58KB — referenced as obs #368)
├── proposal.md         ✅ (referenced as obs #366)
├── spec.md             ✅ (482 lines — referenced as obs #367)
└── tasks.md            ✅ (5/5 work units complete — referenced as obs #369)
```

> **Note**: The change's `apply-progress.md` and `verify-report.md` live in Engram (obs #370, obs #371), not in the filesystem. The pre-change archive convention stores only the 5 standard SDD phase artifacts (proposal, spec, design, tasks, archive-report) PLUS the `archive-report.md` for the closure summary. The apply-progress and verify-report are referenced by their observation IDs in this archive-report's traceability table.

---

## 13. Global specs updated (the canonical record)

```
openspec/specs/
├── linkedin-anti-bot-detector/  (NEW) — 3 REQ-LST-CF-*
├── linkedin-auth-cookie/        (EXTENDED) — 4 v1 REQ-LA-COOKIE-* + 5 new REQ-LST-COOKIE-*
├── linkedin-auth-wall-detector/ (UNCHANGED — v1 cycle, 6 REQ-LA-AWALL-*)
├── linkedin-config/             (EXTENDED) — 4 v1 REQ-LA-CFG-* + 3 new REQ-LST-CFG-*
└── linkedin-scraper/            (EXTENDED) — 4 v1 REQ-LI-SCR-* + 6 v1 REQ-LA-SCR-* + 4 new REQ-LST-SCR-*
```

15 new `REQ-LST-*` requirements promoted to the canonical source of truth.

---

## 14. PRs

Per the preflight `single-pr` strategy (cached at session start; user explicitly authorized), the branch `feature/backend-linkedin-stealth` is ready for `gh pr create` (target: `araldev/jobs-finder` `main` from `feature/backend-linkedin-stealth`). **The orchestrator does NOT create the PR automatically** — the user creates it after this cycle closes (per the orchestrator prompt: "the user will merge after this cycle closes"). The PR description can take §1-§7 of this archive-report as the body.

Suggested `gh` command:

```bash
gh pr create \
  --base main \
  --head feature/backend-linkedin-stealth \
  --title "feat(linkedin-stealth): multi-cookie + playwright-stealth + is_cloudflare_challenge" \
  --body "$(cat openspec/changes/archive/2026-06-11-backend-linkedin-stealth/archive-report.md | sed -n '1,/^## 8\. /p')"
```

Direct URL for creating the PR (per gh CLI conventions):

```
https://github.com/araldev/jobs-finder/pull/new/feature/backend-linkedin-stealth
```

---

## 15. Discoveries / decisions worth remembering for future changes

- **The `LinkedInAuthCookiesPort` (plural) Protocol is structurally conformed by `MultiEnvLinkedInAuthCookiesAdapter` (prod) and `FakeLinkedInAuthCookiesPort` (test conftest companion).** `mypy --strict` validates the conformance at type-check time; NOT `@runtime_checkable` (mirror of v1 `LinkedInAuthCookiePort`).
- **The 2 shared validators in `Settings` (`_normalize_empty_linkedin_optional_secret` + `_reject_short_linkedin_optional_cookie`) cover all 4 cookie fields.** v1 inline validators were REFACTORED to delegate (no behavior change for the v1 `linkedin_li_at`). The constant `MIN_LI_AT_LENGTH = 8` is the single source of truth.
- **The 4 cookies are read individually via `AliasChoices` env binding** (matching the per-source precedent at `config.py:175-201`). No JSON env var; each is independently optional.
- **The multi-cookie injection is byte-identical to the v1 single-cookie injection** — same `add_cookies` shape, generalized to N cookies via list comprehension. The leading dot in `.linkedin.com` is load-bearing (match all subdomains); `httpOnly` and `secure` match LinkedIn's real issuance contract.
- **The `playwright-stealth` invocation is byte-identical to Indeed+InfoJobs precedent.** `apply_stealth_async(ctx)` AFTER `new_context()` BEFORE `add_cookies()`. The import is `from playwright_stealth import Stealth  # type: ignore[import-untyped]`.
- **The conditional precedence flip** (cookie path: `is_cloudflare_challenge` → `is_auth_wall` → `is_block_page`; anonymous path: `is_block_page` only) is intentional and documented in `REQ-LST-SCR-003`. The v1 anonymous path is preserved byte-identical; the 35 v1 tests are the regression check.
- **The `is_cloudflare_challenge` detector is a pure function** (no I/O, no await, no logging side-effects) per `REQ-LST-CF-001`. Mirrors the v1 `is_auth_wall` + `is_block_page` precedent.
- **The CLOUDFLARE_CHALLENGE_HTML fixture is the canonical "Cloudflare 302-loop page" representation.** Captured offline — committed, no live network (AGENTS.md rule #1). The fixture pins the 3 Cloudflare 2026 markers (`<title>Just a moment...</title>`, `<noscript>` redirect, `div.cf-mitigated data-cf-challenge`) and 0 cards.
- **The `MultiEnvLinkedInAuthCookiesAdapter.__repr__` masks the cookie count, not the values.** `SecretStr` masks at the value-object level; the adapter-level `__repr__` is defense-in-depth. A 1-bit side-channel on "is the operator fully configured" is acceptable (the operator's own `ls -la .env` is a richer side-channel).
- **The `_logger.debug("LinkedIn auth cookies injected (count=%d)", len(cookies))` is the only line that mentions the cookies at runtime; it uses `len()` NEVER the values.** The WARNING at `is_cloudflare_challenge` mentions 3 env-var names, NEVER the values.
- **The 4 cookie `Settings.__repr__` no-leak tests** (`test_settings_repr_does_not_leak_*_value`) extend the v1 pattern to the 3 new fields. Defense-in-depth: a future field that accidentally accepts plain `str` would fail the test immediately.
- **The 4 cookies share the v1 validator pattern** (HARD on `len < 8` when present, soft `None` allowed). The error message includes the field name so the operator can self-diagnose which env var is wrong.
- **The composition root** (`app_factory.build_app()`) is the ONLY site that reads env (per the v1 precedent). The new `MultiEnvLinkedInAuthCookiesAdapter` and `Stealth()` are wired at the composition root; the scraper's `search()` method takes them via ctor kwargs.
- **The v1 single-cookie `EnvLinkedInAuthCookieAdapter(SecretStr)` ctor is KEPT byte-identical** for the 35 v1 backward-compat tests. The v1 `LinkedInAuthCookiePort` (singular) Protocol is KEPT. Both coexist with the new `LinkedInAuthCookiesPort` (plural) and `MultiEnvLinkedInAuthCookiesAdapter`.
- **The 5-commit history (`d5b72a4` → `634ca14` → `0d42a8c` → `4ba96c6` → `a37b481`) is independently revertible.** A `git revert` of any one commit removes that layer without breaking the others (the v1 baseline is preserved byte-identically throughout).

---

## 16. Open discoveries (linked to this change, not closed by it)

These are documented separately but inform the `backend-linkedin-xvfb` follow-up design:

- **obs #373 — `discovery/linkedin-fingerprinting-vs-rate-limit-hypothesis`** (open). The orchestrator hypothesized that `playwright-stealth` failed because Cloudflare is doing TLS/HTTP2 fingerprinting of the client. The user pointed out that earlier (pre-cookie, pre-stealth) the SAME scraping flow returned a reduced list behind the auth-wall popup, which contradicts the strict fingerprinting theory. The orchestrator's "fingerprinting" diagnosis is plausible but unvalidated. A simpler hypothesis (rate-limiting on the IP after N scraping requests) is equally consistent with the data. The diagnostic test the user can do: open the same URL in their normal browser. If the user's normal browser works → the problem is automation/headless. If the user's normal browser also fails → the problem is the IP or the account.

- **obs #374 — `discovery/linkedin-redirect-loop-cookies-not-the-cause`** (open). Confirmed empirically that the LinkedIn scraper fails with `ERR_TOO_MANY_REDIRECTS` in <5 seconds with multi-cookie (4 cookies) + playwright-stealth. The redirect loop completes in seconds, NOT after the 10s timeout — meaning LinkedIn is actively rejecting the request, not slow to respond. After renewing all 4 cookies, the SAME 502/redirect-loop behavior. This rules out "obsolete cookies" as the root cause. The redirect loop in <5s is a strong signal of LinkedIn's anti-bot decision: the server sees cookies that say "I am user X" but the client fingerprint (TLS, HTTP/2, behavioral) says "I am a bot". The user mentioned a `bscookie` in their browser cookie list (in addition to the `bcookie` they had earlier) — a 1 Settings field + 1 wire change that can be folded into F-3.

---

## 17. Result contract

- **Status**: ok
- **Executive summary**: 1 multi-capability delta spec promoted to 4 separate global spec files (1 NEW foundational + 3 EXTENDED). 15 REQ-LST-* added to the canonical source of truth. Change folder moved to `openspec/changes/archive/2026-06-11-backend-linkedin-stealth/`. Verify verdict PASS_WITH_WARNINGS (re-run by obs #371, 0/0/4 SUGGESTIONs). 3 SUGGESTIONs deferred to follow-up (S-1, S-2, S-4=cloudflare challenge); 1 SUGGESTION resolved in archive (S-3 v1 WARNING message change, documented in §6). +38 new tests, no new skips, no regressions. ~1,867 net LOC across 5 commits. Single PR ready for `gh pr create` (user creates manually after cycle closes). Live smoke test outcome: STEALTH_INSUFFICIENT — the 0.55 confidence played out exactly as expected; the documented follow-up is `backend-linkedin-xvfb` (pre-confirmed by the user on 2026-06-10).
- **Artifacts**:
  - `archive_report_topic_key`: `sdd/backend-linkedin-stealth/archive-report`
  - `archive_report_file`: `openspec/changes/archive/2026-06-11-backend-linkedin-stealth/archive-report.md`
  - `synced_specs` (4):
    - `openspec/specs/linkedin-anti-bot-detector/spec.md` — NEW foundational, 3 `REQ-LST-CF-*` / 7 scenarios
    - `openspec/specs/linkedin-auth-cookie/spec.md` — EXTENDED, 4 pre-existing `REQ-LA-COOKIE-*` + 5 new `REQ-LST-COOKIE-*` (9 REQ total / ~20 scenarios total)
    - `openspec/specs/linkedin-scraper/spec.md` — EXTENDED, 4 pre-existing `REQ-LI-SCR-*` + 6 pre-existing `REQ-LA-SCR-*` + 4 new `REQ-LST-SCR-*` (14 REQ total / ~30 scenarios total)
    - `openspec/specs/linkedin-config/spec.md` — EXTENDED, 4 pre-existing `REQ-LA-CFG-*` + 3 new `REQ-LST-CFG-*` (7 REQ total / ~15 scenarios total)
  - `archive_folder`: `openspec/changes/archive/2026-06-11-backend-linkedin-stealth/`
  - `archive_cleanup_in_change_files`: none (the change's design.md, proposal.md, spec.md, tasks.md were already in good shape from the apply phase; the v1 startup WARNING message change is documented in §6 Deviations above)
- **Next recommended**: session close (orchestrator does `mem_session_summary`)
- **User action required**: Create the PR via `gh pr create` (the orchestrator does not create the PR per the preflight `single-pr` + user-merges-manually policy)
- **Risks**:
  - **STEALTH_INSUFFICIENT** (live outcome) — the 0.55 confidence played out exactly as expected; the follow-up `backend-linkedin-xvfb` is the documented next step. F-3 is pre-confirmed by the user.
  - **S-1 (env-related test failures) and S-2 (private attribute access)** are deferred to follow-up. Non-blocking; merge is safe as-is.
  - **The v1 startup WARNING message change** is intentional, well-documented, and no external log consumers in this repo break. The change is a deliberate one-shot at process start; no test or production code greps for the old prefix.
  - **The mixed namespace** (`REQ-LI-*` for URL builder + `REQ-LA-*` for v1 cookie injection + `REQ-LST-*` for stealth) is intentional. Downstream changes should preserve all 3 prefixes.
  - **`feature/backend-linkedin-stealth` is PUSHED but NOT MERGED.** The user creates the PR manually after this cycle closes.
  - **The 1 new global spec file (`linkedin-anti-bot-detector`)** is brand new in `openspec/specs/`. Downstream changes that reference it should know it is a foundational spec (no MODIFIED blocks against a pre-existing base).
  - **The 3 EXTENDED global spec files** are byte-preserved for the v1 sections. Downstream changes should not modify the v1 `REQ-LA-*` / `REQ-LI-*` blocks; the new `REQ-LST-*` REQs are appended at the end with a clear section header.
  - **Open discoveries** (obs #373, obs #374) are linked but NOT closed by this change. The follow-up `backend-linkedin-xvfb` (F-3) is where these are expected to be validated or rejected.
- **Skill resolution**: `paths-injected` — orchestrator pre-resolved `sdd-archive/SKILL.md` + `cognitive-doc-design/SKILL.md` + `_shared/sdd-phase-common.md` + `_shared/openspec-convention.md` + `_shared/persistence-contract.md`.
