# Tasks: `feat-frontend-i18n-locale-prefix-urls`

> **Change**: `feat-frontend-i18n-locale-prefix-urls`
> **Status**: ready (post-design, pre-apply)
> **Preflight**: A2 (Automatic) · hybrid artifacts · C4 (auto-forecast, 1 PR) · D1 (well under 400) · Strict TDD: false
> **PR strategy**: single PR on `feat-frontend-i18n-locale-prefix-urls` → `main`
> **Total LOC estimate**: ~185 across 8 files
> **Total task count**: 5
> **Total commit count**: 2 (per `work-unit-commits`: config flip first, logic re-add second)
> **Execution order**: linear, sequential (1 → 2 → 3 → 4 → 5)

## Review Workload Forecast

- **Total LOC estimate**: ~185
- **Per-task LOC**: see table above (each ≤ 75)
- **400-line review budget**: well under (46% of budget)
- **Chained PRs recommended**: No (single PR is sufficient)
- **Decision needed before apply**: No
- **Risk level**: Medium (revert of v1 trade-off; 3 test files change)
- **Plain-text guard lines** (downstream match contract):
  - `Decision needed before apply: No`
  - `Chained PRs recommended: No`
  - `Chain strategy: pending`
  - `400-line budget risk: Low`

## Commit Map (per `work-unit-commits`)

| Commit | Tasks | Conventional subject |
|---|---|---|
| **C1** | Task 1 | `chore(i18n): flip localePrefix to 'as-needed' + routing JSDoc refresh` |
| **C2** | Tasks 2 + 3 + 4 + 5 | `feat(i18n): re-enable locale-prefix URLs (switcher, callback, supabase, tests, docs)` |

C1 is independently verifiable (4 CI gates pass on routing flip alone — `middleware.ts` chain and `[locale]/` segment already handle the new mode from slice 16). C2 is the logic re-add; rollback can stop at C1 without touching the 4 logic paths.

---

### Task 1 — `chore(i18n): flip localePrefix to 'as-needed' + routing JSDoc refresh`

**Slice**: 1 / 5
**LOC estimate**: ~5
**Depends on**: none
**Closes**: REQ-I18N-002, SCN-I18N-002, SCN-I18N-015

**Files touched**:
- UPDATE `frontend/src/i18n/routing.ts` (line 29: `'never'` → `'as-needed'`; JSDoc lines 6-22 rewrite to drop "v1 pragmatic mode" framing)

**Preconditions**:
- Branch `feat-frontend-i18n-locale-prefix-urls` exists from `main`
- Working tree clean

**Acceptance gate** (binary, must pass):
- [ ] `pnpm run typecheck` exits 0
- [ ] `pnpm run lint` exits 0
- [ ] `pnpm run test` exits 0 (existing tests still pass — v1 cookie-only assertions are the regression floor)
- [ ] `pnpm run build` exits 0

**Implementation steps** (ordered, concrete):
1. Edit `frontend/src/i18n/routing.ts` line 29: change `localePrefix: "never"` → `localePrefix: "as-needed"`.
2. Rewrite JSDoc lines 6-22: replace "v1 pragmatic mode" framing with "v2: URL-prefix mode (`localePrefix: 'as-needed'`) — default locale `es` URLs stay unprefixed; non-default `en` URLs are prefixed. Closes REQ-I18N-002. See `feat-frontend-i18n-locale-prefix-urls` for rationale."
3. Run all 4 CI gates from `frontend/` to confirm `[locale]/` segment + `baseResponse` chain still work standalone.

**Risks** (slice-specific):
- Flag flip alone, with no logic re-add, may surface bare `/en/*` URLs with stale locale in LanguageSwitcher and Supabase redirects → **expected**: C2 closes those. The 4 gates pass at C1 because no test asserts URL prefix yet.

**Rollback** (one-line):
- `git revert <merge-sha>` (single line change inside `routing.ts`)

**Commit format**:
- `<type>(<scope>): <subject>` per AGENTS.md convention
- NO `Co-Authored-By:` or AI attribution trailer

---

### Task 2 — `feat(i18n): re-introduce locale-prefix logic in middleware + OAuth callback`

**Slice**: 2 / 5
**LOC estimate**: ~55
**Depends on**: Task 1
**Closes**: REQ-I18N-016, REQ-I18N-020, SCN-I18N-014

**Files touched**:
- UPDATE `frontend/src/lib/supabase/middleware.ts` (~25 LOC: add `detectLocalePrefix` helper, locale-aware `/login` + `/dashboard` redirects, JSDoc refresh)
- UPDATE `frontend/src/app/auth/callback/route.ts` (~30 LOC: add `readLocalePrefix` + `localizePath` helpers, apply to `?next=` + error path)

**Preconditions**:
- Task 1 merged into branch (commit C1 present)
- Working tree clean

**Acceptance gate** (binary, must pass):
- [ ] `pnpm run typecheck` exits 0
- [ ] `pnpm run lint` exits 0
- [ ] `pnpm run test` exits 0 (existing tests still pass; new tests not yet written — that's Task 4)
- [ ] `pnpm run build` exits 0

**Implementation steps** (ordered, concrete):
1. In `supabase/middleware.ts`: add `detectLocalePrefix(originalPathname)` helper (~10 LOC) that returns `""` or `/${locale}` based on `routing.locales`.
2. Add `const localePrefix = detectLocalePrefix(request.nextUrl.pathname);` near line 80 (uses ORIGINAL `request.nextUrl`, not rewritten — D3 in design).
3. Line 94: `url.pathname = "/login"` → `url.pathname = \`${localePrefix}/login\``.
4. Line 104: `url.pathname = "/dashboard"` → `url.pathname = \`${localePrefix}/dashboard\``.
5. Drop "defensive no-op" framing in JSDoc lines 5-19 and 67-71.
6. In `auth/callback/route.ts`: add `readLocalePrefix(request)` (reads `NEXT_LOCALE` cookie, validates against `routing.locales`) and `localizePath(path, localePrefix)` (idempotent per D5).
7. Apply `localizePath(next, localePrefix)` to both the success redirect (line 38) and the error fallback (`/login?error=...` line 33).
8. Rewrite JSDoc lines 1-22 to describe v2 contract.

**Risks** (slice-specific):
- Using `request.nextUrl.pathname` (rewritten) instead of original → wrong locale detection. Mitigation: pass original via closure; verify with smoke test row #9 (`/en/dashboard` no-auth → `/en/login`).
- `localizePath` double-prefix if `next` already contains `/en/`. Mitigation: D5 idempotency check inside `localizePath`.

**Rollback** (one-line):
- `git revert <commit-sha>` (single C2 revert undoes both files atomically)

**Commit format**:
- `<type>(<scope>): <subject>` per AGENTS.md convention
- NO `Co-Authored-By:` or AI attribution trailer

---

### Task 3 — `feat(i18n): LanguageSwitcher re-introduce usePathname + router.push`

**Slice**: 3 / 5
**LOC estimate**: ~20
**Depends on**: Task 2
**Closes**: REQ-I18N-021, SCN-I18N-003

**Files touched**:
- UPDATE `frontend/src/components/layout/LanguageSwitcher.tsx` (re-add `usePathname` import, `stripLocalePrefix` helper, build `nextPath`, call `router.push(nextPath)` before `router.refresh()`; JSDoc refresh)

**Preconditions**:
- Tasks 1 + 2 merged into branch
- Working tree clean

**Acceptance gate** (binary, must pass):
- [ ] `pnpm run typecheck` exits 0
- [ ] `pnpm run lint` exits 0
- [ ] `pnpm run test` exits 0 (existing LanguageSwitcher test still passes — but asserts only `refresh`, not `push`; Task 4 closes that gap)
- [ ] `pnpm run build` exits 0

**Implementation steps** (ordered, concrete):
1. Line 4: add `usePathname` to the `next/navigation` import.
2. Add local `stripLocalePrefix(path: string): string` helper (lines 16-23 area, mirrors the one in `supabase/middleware.ts` per design §Interfaces).
3. In `switchTo()`: after cookie + localStorage writes, call `const stripped = stripLocalePrefix(pathname);` and `const nextPath = target === routing.defaultLocale ? stripped : \`/${target}${stripped}\`;`.
4. Call `router.push(nextPath);` BEFORE `router.refresh();` (soft navigation + RSC re-render).
5. Update JSDoc lines 16-30 to describe v2 navigation pattern (URL + locale atomic switch).

**Risks** (slice-specific):
- `router.push` triggers hard reload → React state loss. Mitigation: Next.js `router.push` is soft navigation; RSC streams new payload; `router.refresh()` is the canonical RSC re-render pattern (design D9, risk R3).

**Rollback** (one-line):
- `git revert <commit-sha>` (single file revert restores v1 cookie-only switcher)

**Commit format**:
- `<type>(<scope>): <subject>` per AGENTS.md convention
- NO `Co-Authored-By:` or AI attribution trailer

---

### Task 4 — `test(i18n): update 3 test files to v2 contract`

**Slice**: 4 / 5
**LOC estimate**: ~75
**Depends on**: Task 3
**Closes**: SCN-I18N-013, SCN-I18N-014, SCN-I18N-015 (test coverage); D6 mock contract

**Files touched**:
- UPDATE `frontend/src/components/layout/LanguageSwitcher.test.tsx` (~15 LOC: add `push: vi.fn()` to `useRouter()` mock; rebindable `usePathname`; assert `routerPushMock.toHaveBeenCalledWith(...)` in 3 tests)
- UPDATE `frontend/src/app/auth/callback/__tests__/route.test.ts` (~50 LOC: rename describe block to "v2 contract"; migrate 6 locale tests to expect `/en/...` prefixes; add 1 `localizePath` idempotency test for D5)
- UPDATE `frontend/src/lib/supabase/__tests__/middleware.test.ts` (~40 LOC: add 4 tests — `/en/dashboard` no-auth → 307 `/en/login`; `/en/login` auth → 307 `/en/dashboard`; `/en/forgot-password` no-auth → 200; regression guard `/dashboard` auth-no-cookie → 307 `/login`)

**Preconditions**:
- Tasks 1 + 2 + 3 merged into branch
- Working tree clean

**Acceptance gate** (binary, must pass):
- [ ] `pnpm run typecheck` exits 0
- [ ] `pnpm run lint` exits 0
- [ ] `pnpm run test` exits 0 (net +10 tests: 3 switcher + 4 supabase + 1 callback idempotency + 2 callback migrations; 0 deletions)
- [ ] `pnpm run build` exits 0

**Implementation steps** (ordered, concrete):
1. In `LanguageSwitcher.test.tsx`: add `routerPushMock = vi.fn()`; mock `useRouter: () => ({ refresh, push: routerPushMock })`; convert `usePathname` to `let pathnameMock = "/dashboard"` rebindable per test.
2. `beforeEach`: `routerPushMock.mockClear(); pathnameMock = "/dashboard";`.
3. Assert `routerPushMock` in 3 existing test cases (English on `/dashboard` → `/en/dashboard`; Spanish on `/en/dashboard` → `/dashboard`; keyboard nav).
4. In `route.test.ts` line 126: rename `describe("...v1 contract")` → `...v2 contract`; update 6 expected URLs to `/en/...` prefixes when cookie=en.
5. Add 1 idempotency test: `?next=/en/dashboard` no cookie → `/en/dashboard` (D5 guard).
6. In `middleware.test.ts`: add 4 tests per design §Testing Strategy row 3; reuse existing `runMiddleware` helper.

**Risks** (slice-specific):
- Mock missing `push` → assertion silently passes (R7 in explore). Mitigation: explicit `routerPushMock` reference per test.
- Idempotency test wrong (`localizePath` strips when path already prefixed) → false positive. Mitigation: write test against `localizePath` directly with both `/dashboard` and `/en/dashboard` inputs.

**Rollback** (one-line):
- `git revert <commit-sha>` (3 test files revert in one step; C2 logic remains)

**Commit format**:
- `<type>(<scope>): <subject>` per AGENTS.md convention
- NO `Co-Authored-By:` or AI attribution trailer

---

### Task 5 — `docs(i18n): update README + PR merge note`

**Slice**: 5 / 5
**LOC estimate**: ~10
**Depends on**: Task 4
**Closes**: docs-only (no REQ/SCN — runtime contract already proven by Tasks 1-4)

**Files touched**:
- UPDATE `frontend/README.md` (i18n section: document URL-prefix mode is now active; list `/en/dashboard`, `/en/login` as canonical EN URLs; mention `localePrefix: 'as-needed'` and the precedence URL > cookie > Accept-Language > default)

**Preconditions**:
- Tasks 1-4 merged into branch
- All 4 CI gates green
- Working tree clean

**Acceptance gate** (binary, must pass):
- [ ] `pnpm run typecheck` exits 0
- [ ] `pnpm run lint` exits 0
- [ ] `pnpm run test` exits 0
- [ ] `pnpm run build` exits 0

**Implementation steps** (ordered, concrete):
1. Locate the i18n section in `frontend/README.md` (search for `Locale prefix` or `i18n` heading).
2. Replace the "v1 cookie-only mode" paragraph with: "URL-prefix mode is active (`localePrefix: 'as-needed'` in `src/i18n/routing.ts`). Default locale `es` URLs stay unprefixed (`/dashboard`, `/login`); non-default `en` URLs are prefixed (`/en/dashboard`, `/en/login`). Precedence: URL prefix > `NEXT_LOCALE` cookie > `Accept-Language` > `defaultLocale`."
3. Add a one-line PR merge note (comment in the README) referencing `feat-frontend-i18n-locale-prefix-urls` so future readers find the design rationale.

**Risks** (slice-specific):
- Doc drifts from runtime if `routing.ts` flips back → doc + code out of sync. Mitigation: keep the doc concise; reference the file path so future contributors cross-check.

**Rollback** (one-line):
- `git revert <commit-sha>` (README-only revert; no runtime impact)

**Commit format**:
- `<type>(<scope>): <subject>` per AGENTS.md convention
- NO `Co-Authored-By:` or AI attribution trailer

---

## Open Questions

**None.** All design decisions settled by v1 design (`openspec/changes/feat-frontend-i18n/design.md` §3, §4, §6, §10), v1 archive-report F9 follow-up, explore §1.1 (verified `next-intl@4.x` `resolveLocale.tsx` Prio 1), and design.md §Open Questions (lines 262-269). The brief correction on smoke-test row #4 (URL prefix wins over cookie) is folded into REQ-I18N-002, SCN-I18N-013, AC-4, and the design §Data Flow.
