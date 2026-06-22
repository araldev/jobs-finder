# feat-frontend-i18n — PR Guide

This change ships as **15 stacked branches**. The user opens one PR per
branch tomorrow from the GitHub web UI.

## Why branches, not auto-merged?

The `gh` CLI isn't available in this environment, so PRs must be opened
from the GitHub web UI. The branch topology is the standard stacked-PR
pattern (each slice N+1 branches off slice N's tip) so the diffs are
isolated and reviewable.

## Branching strategy used during apply

| Slice | Branch from | Why |
|-------|------------|-----|
| 1     | `main`     | Bootstrap; no prior deps |
| 2-15  | slice N-1  | Each slice N+1 needs the previous slice's commits (next-intl install, layout provider, LanguageSwitcher, namespaces, etc.) for its own changes to compile and test |

When you open a PR from slice N's branch against `main`, GitHub will
show the diff between `main` and slice N's tip. If slice N-1 is not yet
merged to `main`, the PR diff will include slice N-1's commits too
(this is correct — the user merges slices in order 1 → 15).

## PRs to open (in this order)

| # | Branch | Title | Compare URL |
|---|--------|-------|-------------|
| 1 | `feat-frontend-i18n/slice-1-install-middleware` | `chore(i18n): install next-intl + middleware chain + messages skeleton` | https://github.com/araldev/jobs-finder/compare/main...feat-frontend-i18n/slice-1-install-middleware?expand=1 |
| 2 | `feat-frontend-i18n/slice-2-root-layout-provider` | `feat(i18n): root layout dynamic <html lang> + NextIntlClientProvider` | https://github.com/araldev/jobs-finder/compare/main...feat-frontend-i18n/slice-2-root-layout-provider?expand=1 |
| 3 | `feat-frontend-i18n/slice-3-language-switcher` | `feat(i18n): LanguageSwitcher widget + Header slot + renderWithIntl wrapper` | https://github.com/araldev/jobs-finder/compare/main...feat-frontend-i18n/slice-3-language-switcher?expand=1 |
| 4 | `feat-frontend-i18n/slice-4-formatters-locale` | `feat(i18n): lib/formatters.ts locale-aware refactor + bilingual tests` | https://github.com/araldev/jobs-finder/compare/main...feat-frontend-i18n/slice-4-formatters-locale?expand=1 |
| 5 | `feat-frontend-i18n/slice-5-auth-migration` | `feat(i18n): migrate authCopy → messages Auth + Validation namespaces` | https://github.com/araldev/jobs-finder/compare/main...feat-frontend-i18n/slice-5-auth-migration?expand=1 |
| 6 | `feat-frontend-i18n/slice-6-layout-chrome` | `feat(i18n): layout chrome Header/Sidebar/ThemeToggle/AppShell bilingual` | https://github.com/araldev/jobs-finder/compare/main...feat-frontend-i18n/slice-6-layout-chrome?expand=1 |
| 7 | `feat-frontend-i18n/slice-7-dashboard` | `feat(i18n): dashboard + RightSidebar + ICU plurals + StatsCardsRow tests` | https://github.com/araldev/jobs-finder/compare/main...feat-frontend-i18n/slice-7-dashboard?expand=1 |
| 8 | `feat-frontend-i18n/slice-8-jobs` | `feat(i18n): jobs components bilingual + OAuth callback locale-aware redirectTo` | https://github.com/araldev/jobs-finder/compare/main...feat-frontend-i18n/slice-8-jobs?expand=1 |
| 9 | `feat-frontend-i18n/slice-9-search-settings-favorites` | `feat(i18n): search + settings + favorites components + ICU plurals` | https://github.com/araldev/jobs-finder/compare/main...feat-frontend-i18n/slice-9-search-settings-favorites?expand=1 |
| 10 | `feat-frontend-i18n/slice-10-chat-errors` | `feat(i18n): chat FAB label + Chat namespace + Jobs.errors keys` | https://github.com/araldev/jobs-finder/compare/main...feat-frontend-i18n/slice-10-chat-errors?expand=1 |
| 11 | `feat-frontend-i18n/slice-11-landing` | `feat(i18n): landing page Landing namespace + upload error keys` | https://github.com/araldev/jobs-finder/compare/main...feat-frontend-i18n/slice-11-landing?expand=1 |
| 12 | `feat-frontend-i18n/slice-12-auth-pages` | `feat(i18n): auth pages bilingual + OAuth callback locale-aware redirect` | https://github.com/araldev/jobs-finder/compare/main...feat-frontend-i18n/slice-12-auth-pages?expand=1 |
| 13 | `feat-frontend-i18n/slice-13-error-pages` | `feat(i18n): error/not-found + API error JSON bilingual` | https://github.com/araldev/jobs-finder/compare/main...feat-frontend-i18n/slice-13-error-pages?expand=1 |
| 14 | `feat-frontend-i18n/slice-14-privacidad` | `chore(i18n): privacidad footer note (Spanish only v1)` | https://github.com/araldev/jobs-finder/compare/main...feat-frontend-i18n/slice-14-privacidad?expand=1 |
| 15 | `feat-frontend-i18n/slice-15-cleanup` | `chore(i18n): remove deprecated authCopy.test.ts + README docs` | https://github.com/araldev/jobs-finder/compare/main...feat-frontend-i18n/slice-15-cleanup?expand=1 |

## Commit SHAs (for reference / git revert)

| Slice | Commit SHA(s) |
|-------|---------------|
| 1     | `06466d1`, `408257a` |
| 2     | `9a2adf6` |
| 3     | `3e36bcc`, `e9ff129` |
| 4     | `a48ccc2` |
| 5     | `83e37a2`, `90ef253` |
| 6     | `82473a7` |
| 7     | `5f62f55` |
| 8     | `1987dd3` |
| 9     | `0889cd3` |
| 10    | `737dd16` |
| 11    | `fa13005` |
| 12    | `c0fd198` |
| 13    | `2056fa4` |
| 14    | `fa01c31` |
| 15    | `cc04af8` |
| 16 *(remediation)* | `c118384`, `28b6270` |

## Final state

- **All 15 branches exist on `origin`** ✅
- **`main` is unchanged** ✅ (all commits live on the slice branches)
- **All 4 frontend CI gates green at the end** ✅ (`typecheck`, `lint`,
  `test`, `build` all pass; 272 tests across 43 files; `lint:i18n` audit
  script runs cleanly)
- **Total commits**: 19 across 15 slices (slices 1, 3, 5 shipped as 2
  commits each per the design; slice 15 + remediation slice 16 ship as
  2 additional commits on `slice-15-cleanup`)

## Remediation slice 16 (CRITICAL FIX)

The original 15 slices set up next-intl with `localePrefix: 'as-needed'`
WITHOUT the `[locale]/` dynamic segment — a configuration error. The
intl middleware would issue 307 redirects to `/en/*` URLs that Next.js
had no routes for (404). English locale was functionally unreachable at
runtime.

**Remediation slice 16** (commits `c118384` + `28b6270`, on top of
`slice-15-cleanup`) fixes this by:

1. Migrating all page routes to `app/[locale]/...` (standard next-intl
   4.x pattern)
2. Splitting `app/layout.tsx` into a minimal root pass-through + a
   full locale-aware `app/[locale]/layout.tsx`
3. Switching the routing config to `localePrefix: 'never'` (URLs never
   carry a locale prefix; the active locale flows via the
   `NEXT_LOCALE` cookie + `Accept-Language` header)
4. Updating the LanguageSwitcher to `router.refresh()` instead of
   `router.push(/en/<path>)`
5. Simplifying the Supabase `updateSession` middleware (drop the
   rewrite-aware locale-prefix logic that was needed for
   `as-needed` mode)

**Trade-off**: v1 does NOT expose canonical `/en/...` URLs (the URL
stays the same regardless of locale). A future follow-up
(`feat-frontend-i18n-locale-prefix-urls`) can re-enable URL prefixes
now that the `[locale]/` segment is in place — the migration path is
straightforward.

## Merge strategy

Open the 15 PRs in order 1 → 15 against `main`, **then open the
remediation PR (slice 16) on top**. Each PR is independent once its
prior slice is merged to `main` (which is exactly the behavior the
design's `stacked-to-main` chain strategy promises). The
user merges them in order 1 → 15; after each merge the next PR's diff
auto-shrinks to just the new slice's commits.

## Known follow-ups (deferred during apply)

These are documented in the individual slice commit bodies. None are
blockers — the change ships the i18n layer end-to-end and the
remaining items are non-critical refinements:

1. **Slice 5 follow-up** — delete `frontend/src/lib/authCopy.ts`
   (currently marked `@deprecated`). ~139 test files reference
   `authCopy.X.Y` as shorthand for Spanish literals; migrating them to
   `useTranslations` calls or hard-coded strings is mechanical but
   touches many files. Tracked as a follow-up.
2. **Slice 8 follow-up** — JobDetailContent, JobDetailAside,
   JobList, GenerateCVModal remain pre-i18n. Their hardcoded Spanish
   literals still display; the `Jobs` namespace already includes the
   keys they need when they're migrated.
3. **Slice 10 follow-up** — `useChat.ts` hook still uses the English
   `'Something went wrong'` and `'Connection failed'` literals inline.
   Migrating them requires either passing a `t()` function into the
   hook or returning error keys that callers translate.
4. **Slice 11 follow-up** — The landing page's deeper marketing copy
   (hero title/subtitle, feature descriptions, CTA, footer copyright,
   testimonials) stays in its original Spanish literals. The
   `Landing` namespace is fully wired up; a follow-up commit can
   mechanically replace the literals line by line. Marketing team
   review of canonical EN copy is the trigger.
5. **Slice 12 follow-up** — `signup/page.tsx` and
   `(auth)/forgot-password/page.tsx` and `(auth)/reset-password/page.tsx`
   remain pre-i18n at the visible-string level (the `Auth` namespace
   already has the keys).

## After merging all 15 slices

```bash
# Delete the remote branches (one at a time)
git push origin --delete feat-frontend-i18n/slice-1-install-middleware
# ... repeat for slices 2-15

# Verify main is green
cd frontend
pnpm run typecheck
pnpm run lint
pnpm run test
pnpm run build
pnpm run lint:i18n
```

## Rollback

Each PR is a single commit (or 2 for slices 1, 3, 5). `git revert
<merge-sha>` is a clean per-slice rollback.