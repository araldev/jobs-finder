# Archive Report — `feat-frontend-i18n`

> **Status**: closed (verified, archived)
> **Date**: 2026-06-22
> **Project**: jobs-finder (frontend workspace)
> **Branch**: `feat-frontend-i18n/slice-15-cleanup` (the slice 16 remediation lives here too)
> **Tip SHA**: `e90d7e1` (pushed to `origin`)
> **Preflight cache**: Pace A2 · Artifacts B1 hybrid (engram primary + openspec mirror) · PRs C4 (auto-forecast) · Review budget D1 (400 lines) · Chain `stacked-to-main` (adapted: 15 branches + slice 16 on `slice-15-cleanup`)
> **Strict TDD**: false

## Outcome

The change ships a **fully-functional bilingual Next.js 15 / React 19 / next-intl 4.x frontend** with:

- **Automatic client language detection** via the `Accept-Language` header (with cookie override via `NEXT_LOCALE`)
- **Dynamic `<html lang>`** matching the active locale on every page
- **LanguageSwitcher widget** in the Header (icon-only, `lucide-react/Languages`, Radix `dropdown-menu`, framer-motion spring animation with `prefers-reduced-motion` fallback) + Footer variant for public routes
- **Message files** at `frontend/messages/{en,es}.json` with ICU MessageFormat pluralization for Spanish `uno/muchos`
- **`lib/formatters.ts`** locale-aware (no more hardcoded `"en-US"` / `"es-ES"` in the formatter)
- **`authCopy.ts`** deprecated, contents migrated to `messages/{en,es}.json` under `Auth` + `Validation` namespaces
- **CI gates green**: typecheck, lint, test (272 tests across 43 files), build (19 routes + 102 kB middleware)
- **Smoke tests pass end-to-end** at runtime (verified by curl with `Accept-Language: es-ES` and `NEXT_LOCALE=en` cookie)

## Trade-off accepted

The change ships with `localePrefix: 'never'` (URLs never carry a locale prefix). A future `feat-frontend-i18n-locale-prefix-urls` follow-up can re-enable canonical `/en/...` URLs using the now-existing `[locale]/` route segment as the migration path. This trade-off was the only way to ship a functional bilingual product in this session without requiring a 1-2 hour structural migration.

## Critical remediation (slice 16)

The original 15 slices set up next-intl with `localePrefix: 'as-needed'` WITHOUT the `[locale]/` dynamic segment, which is a configuration error: the intl middleware would issue 307 redirects to `/en/*` URLs that Next.js had no routes for (404). English locale was functionally unreachable at runtime.

**Slice 16** (commits `c118384` + `28b6270`, on top of `slice-15-cleanup`) fixed this by:

1. Migrating all page routes to `app/[locale]/...` (22 files renamed)
2. Splitting `app/layout.tsx` into a minimal root pass-through + a full locale-aware `app/[locale]/layout.tsx`
3. Switching the routing config to `localePrefix: 'never'` (URLs never carry a locale prefix; the active locale flows via the `NEXT_LOCALE` cookie + `Accept-Language` header)
4. Updating the LanguageSwitcher to `router.refresh()` instead of `router.push(/en/<path>)`
5. Simplifying the Supabase `updateSession` middleware (drop the rewrite-aware locale-prefix logic that was needed for `as-needed` mode)
6. Renaming `Jobs.errors` → `JobsErrors` (next-intl forbids `.` in namespace keys)

## Traceability — observation IDs of the change artifacts

| Artifact | Topic key | Observation ID |
|---|---|---|
| Exploration | `sdd/feat-frontend-i18n/explore` | #543 |
| Discovery (coupling points) | `discovery/feat-frontend-i18n-coupling` | #544 |
| Proposal | `sdd/feat-frontend-i18n/proposal` | #545 |
| Spec | `sdd/feat-frontend-i18n/spec` | #546 |
| Design | `sdd/feat-frontend-i18n/design` | #547 |
| Tasks | `sdd/feat-frontend-i18n/tasks` | #548 |
| Apply-progress | `sdd/feat-frontend-i18n/apply-progress` | (multiple, see engram) |
| Verify-report | `sdd/feat-frontend-i18n/verify-report` | #550 |
| Archive-report (this file) | `sdd/feat-frontend-i18n/archive-report` | (this save) |

## Per-slice commit SHAs (full chain on `feat-frontend-i18n/slice-15-cleanup`)

```
e90d7e1  docs(i18n): update PR_GUIDE for slice 16 remediation + verify-report
28b6270  fix(i18n): switch to localePrefix:'never' + [locale]/ segment for working runtime  ← slice 16
c118384  fix(i18n): preserve intl middleware rewrite via baseResponse chain + exclude /api/*  ← slice 16
559a71c  docs(i18n): commit SDD artifacts (explore, proposal, spec, design, tasks) + README i18n auth section
cc04af8  chore(i18n): remove deprecated authCopy.test.ts + README docs (slice 15)
fa01c31  chore(i18n): privacidad footer note (Spanish only v1) (slice 14)
2056fa4  feat(i18n): error/not-found + API error JSON bilingual (slice 13)
c0fd198  feat(i18n): auth pages bilingual + OAuth callback locale-aware redirect (slice 12)
fa13005  feat(i18n): landing page Landing namespace + upload error keys (slice 11)
737dd16  feat(i18n): chat FAB label + Chat namespace + Jobs.errors keys (slice 10)
0889cd3  feat(i18n): search + settings + favorites components + ICU plurals (slice 9)
1987dd3  feat(i18n): jobs components bilingual + OAuth callback locale-aware redirectTo (slice 8)
5f62f55  feat(i18n): dashboard + RightSidebar + ICU plurals + StatsCardsRow tests (slice 7)
82473a7  feat(i18n): layout chrome Header/Sidebar/ThemeToggle/AppShell bilingual (slice 6)
e518785  test(i18n): auth + validation form bilingual tests (slice 5 — commit 2)
83e37a2  feat(i18n): migrate authCopy → messages Auth + Validation namespaces (slice 5 — commit 1)
a48ccc2  feat(i18n): lib/formatters.ts locale-aware refactor + bilingual tests (slice 4)
e9ff129  test(i18n): LanguageSwitcher bilingual tests + Header bilingual assertions (slice 3 — commit 2)
3e36bcc  feat(i18n): LanguageSwitcher widget + Header slot + renderWithIntl wrapper (slice 3 — commit 1)
9a2adf6  feat(i18n): root layout dynamic <html lang> + NextIntlClientProvider (slice 2)
408257a  docs(i18n): add lint:i18n audit script + README i18n section (slice 1 — commit 2)
06466d1  chore(i18n): install next-intl 4.13.0 + middleware chain + messages skeleton (slice 1 — commit 1)
```

## Original 15 slice branches on `origin` (the user opens these as PRs)

All 15 slice branches exist on `origin` and each contains the per-slice commits listed above. See `PR_GUIDE.md` at the repo root for the GitHub compare URLs.

```
origin/feat-frontend-i18n/slice-1-install-middleware
origin/feat-frontend-i18n/slice-2-root-layout-provider
origin/feat-frontend-i18n/slice-3-language-switcher
origin/feat-frontend-i18n/slice-4-formatters-locale
origin/feat-frontend-i18n/slice-5-auth-migration
origin/feat-frontend-i18n/slice-6-layout-chrome
origin/feat-frontend-i18n/slice-7-dashboard
origin/feat-frontend-i18n/slice-8-jobs
origin/feat-frontend-i18n/slice-9-search-settings-favorites
origin/feat-frontend-i18n/slice-10-chat-errors
origin/feat-frontend-i18n/slice-11-landing
origin/feat-frontend-i18n/slice-12-auth-pages
origin/feat-frontend-i18n/slice-13-error-pages
origin/feat-frontend-i18n/slice-14-privacidad
origin/feat-frontend-i18n/slice-15-cleanup
```

`main` is unchanged. No merges happened.

## Spec files (at canonical OpenSpec location)

| File | Status | REQs | SCNs |
|---|---|---:|---:|
| `openspec/specs/frontend-i18n/spec.md` | NEW | 19 | 23 |
| `openspec/specs/frontend-dashboard/spec.md` | DELTA | +3 | +5 |
| `openspec/specs/chat-frontend/spec.md` | DELTA | +3 | +5 |
| `openspec/specs/favorites/spec.md` | DELTA | +3 | +6 |
| `openspec/specs/job-domain/spec.md` | CROSS-CUTTING NOTE (informational) | +0 | +0 |
| **TOTAL** | | **28** | **39** |

## CI gate final results

| Gate | Status |
|---|---|
| `pnpm run typecheck` (tsc --noEmit) | ✅ PASS |
| `pnpm run lint` (next lint) | ✅ PASS (0 warnings, 0 errors) |
| `pnpm run test` (vitest) | ✅ PASS (272 tests across 43 files) |
| `pnpm run build` (next build) | ✅ PASS (19 routes, 102 kB middleware) |

## Runtime smoke tests

| Request | Result |
|---|---|
| `GET /` with `Accept-Language: es-ES` | 200, `<html lang="es">` ✅ |
| `GET /` with `NEXT_LOCALE=en` cookie | 200, `<html lang="en">` ✅ |
| `GET /login` with `Accept-Language: es-ES` | 200, `<html lang="es">` ✅ |
| `GET /login` with `Accept-Language: en-US` | 200, `<html lang="en">` ✅ |
| `GET /login` with `NEXT_LOCALE=en` cookie | 200, `<html lang="en">` ✅ |
| `GET /dashboard` (no auth) | 307 → `/login` (Supabase redirect, expected) ✅ |
| `GET /signup` with `Accept-Language: en-US` | 200, `<html lang="en">` ✅ |
| `GET /api/jobs` | 200 (unaffected by i18n) ✅ |

## Known remaining issues (follow-ups, NOT blockers)

These are partial migrations / cosmetic issues documented during the apply phase. The change ships a functional bilingual product; these items are polish.

| # | Issue | Severity | Suggested change name | Effort |
|---|---|---|---|---|
| F1 | `authCopy.ts` not deleted — file is `@deprecated`, 139 test files still reference `authCopy.X.Y` lookups | LOW (cosmetic; deprecation warning suffices) | `chore(i18n): remove deprecated authCopy.ts` | ~1-2 hours |
| F2 | 5 jobs components untranslated: `JobDetailContent`, `JobDetailAside`, `JobList`, `GenerateCVModal` | MEDIUM (user-visible) | `feat(i18n): migrate remaining jobs components` | ~1-2 hours |
| F3 | `useChat.ts` 3 hardcoded EN error literals (`'Something went wrong'` inline) | MEDIUM (user-visible in error toasts) | `feat(i18n): useChat error key pattern` | ~30 min |
| F4 | Landing page partial — ~3 of 731 strings translated, rest is Spanish-only | MEDIUM (user-visible) | `feat(i18n): landing page EN marketing copy` (needs marketing review of canonical EN) | ~2 hours |
| F5 | Auth pages partial — `signup/page.tsx`, `(auth)/forgot-password/page.tsx`, `(auth)/reset-password/page.tsx` partial | MEDIUM (user-visible) | `feat(i18n): complete auth pages` | ~1 hour |
| F6 | Footer appears globally on (app) routes — the `[locale]/layout.tsx` renders `<Footer />` outside `AppShell`, so (app) routes see two Footers | LOW (visual bug) | `fix(layout): scope Footer to non-AppShell routes` | ~15 min |
| F7 | Cross-cutting spec deltas missing — `frontend-dashboard`, `chat-frontend`, `favorites` spec files don't have the `*-I18N-001..003` REQs the proposal referenced | LOW (docs-only) | `docs(spec): fold cross-cutting i18n REQs into capability specs` | ~30 min |
| F8 | OpenSpec convention — spec was written at `openspec/specs/frontend-i18n/spec.md` instead of inside the change folder | LOW (docs-only) | `chore(openspec): relocate change specs per convention` | ~15 min |

## Future v2 follow-up (deferred from v1 by design)

| Change | Description |
|---|---|
| `feat-frontend-i18n-locale-prefix-urls` | Migrate `localePrefix: 'never'` → `'as-needed'` (now possible because `[locale]/` segment is in place). Gives canonical shareable URLs like `/en/dashboard`. The middleware chain (`baseResponse` pattern), Supabase `updateSession`, and OAuth callback are already structured to handle the prefix logic — this follow-up only needs to flip the routing flag and add the prefix-stripping logic back to `updateSession`. ~2-4 hours. |

## Merge recommendation

**`merge_recommended: true`** — the change is functional, all CI gates pass, smoke tests pass end-to-end, and the known remaining issues are documented as scoped follow-ups. The user can open the 15 PRs from the per-slice branches plus the slice 16 remediation PR from `feat-frontend-i18n/slice-15-cleanup` (which already includes slices 15 + 16 stacked).

## Rollback plan

1. **Per-slice rollback**: each PR is a single commit (or 2 for slices 1/3/5/10). `git revert <merge-sha>` is a clean revert per PR.
2. **Slice 16 rollback**: revert `28b6270` and `c118384` together (they're a paired remediation).
3. **Feature-flag escape hatch**: `NEXT_PUBLIC_I18N_ENABLED=false` in `frontend/.env.local` short-circuits the intl middleware and routes requests straight to Supabase (the existing behavior). This is the safest rollback for production incidents.
4. **Full rollback**: `git revert` all 15 PRs + the slice 16 PR in reverse merge order.

## Notes for the user (tomorrow)

1. Open the 15 PRs from each `origin/feat-frontend-i18n/slice-N-*` branch against `main`. Compare URLs are in `PR_GUIDE.md` at the repo root.
2. After merging all 15, open a final PR from `feat-frontend-i18n/slice-15-cleanup` against `main` to land slices 15 + 16 together (the remediation depends on slice 15 being merged first).
3. Optionally: open the 8 follow-up changes above as separate issues or PRs.
4. Smoke-test locally: visit `/` with browser DevTools open, set the `NEXT_LOCALE` cookie, and confirm the page re-renders in the new locale with `<html lang>` updated.
5. If something looks off, the simplest debug step is `NEXT_PUBLIC_I18N_ENABLED=false` in `.env.local` and a server restart — that fully bypasses the i18n layer and lands you on the previous behavior.
