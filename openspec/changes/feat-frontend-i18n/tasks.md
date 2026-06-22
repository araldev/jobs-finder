# Tasks: `feat-frontend-i18n`

> **Change**: `feat-frontend-i18n` • **Phase**: SDD tasks (post-design, pre-apply) • **Status**: ready
> **Date**: 2026-06-22 • **Mode**: hybrid (engram canonical + openspec file mirror)
> **Stack**: Next.js 15 App Router · next-intl 3.x · TS strict · vitest · framer-motion · Radix dropdown-menu
> **Spec reference**: `openspec/specs/frontend-i18n/spec.md` (19 REQs) + 3 capability deltas (28 total REQs, 39 SCNs)
> **Design reference**: `openspec/changes/feat-frontend-i18n/design.md` (15 decisions D1–D15)
> **Preflight**: Pace A2 · Artifacts B1 hybrid · PRs C4 · Review budget D1 (400 lines, MANDATORY chained PRs) · Chain strategy `stacked-to-main` (15 slices) · Strict TDD false

---

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Total LOC estimate | **~4,050** |
| Per-slice LOC | see per-task rows (each ≤ 700) |
| 400-line review budget | **EXCEEDED** (~10× over) |
| Chained PRs recommended | **YES** (mandatory per preflight D1) |
| Chain strategy | `stacked-to-main` |
| Decision needed before apply | **NO** (strategy already resolved: `stacked-to-main`) |
| Risk level | **HIGH** — cross-workspace architectural change, affects every component family |
| Slices approaching cap | slice 11 (700) and slice 8 (500) — both have explicit manual review gates |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Slice / LOC table (execution order = merge order)

| # | Slice title | LOC | Depends on |
|---|---|---:|---|
| 1 | install next-intl + middleware chain + messages skeleton | 250 | — |
| 2 | root layout dynamic `<html lang>` + NextIntlClientProvider | 80 | 1 |
| 3 | LanguageSwitcher widget + header slot + tests | 300 | 1, 2 |
| 4 | lib/formatters.ts locale-aware refactor | 120 | 1 |
| 5 | authCopy.ts → messages Auth + Validation namespaces | 250 | 1, 2 |
| 6 | layout chrome (Header, Sidebar, ThemeToggle, AppShell) | 200 | 3, 5 |
| 7 | dashboard + RightSidebar + JobSourceBreakdown + StatsCardsRow | 300 | 3, 4, 5 |
| 8 | jobs components | 500 | 3, 4, 5 |
| 9 | search + settings components + favorites page | 500 | 3, 4, 5 |
| 10 | chat components + useChat error i18n | 250 | 3, 4, 5 |
| 11 | landing page (`app/page.tsx`, 729 LOC) | 700 | 1, 2, 3 |
| 12 | auth pages (login, signup, forgot-password, reset-password) | 400 | 5, 8 |
| 13 | error/not-found + api error JSON | 80 | 1, 2 |
| 14 | privacidad decision (footer note + link) | 20 | 3 |
| 15 | remove deprecated authCopy.ts + final cleanup | 100 | 5, 6, 9 |
| **Total** | | **~4,050** | |

### Commit count per slice

| Slice | Commits | Rationale |
|---|---|---|
| 1 | 2 | code (install + middleware + messages) + tests/audit (audit-i18n.sh) |
| 2 | 1 | single layout change |
| 3 | 2 | code (LanguageSwitcher + Header) + tests (LanguageSwitcher.test.tsx + renderWithIntl) |
| 4 | 1 | formatters + tests ship together |
| 5 | 2 | code (messages + import sites) + tests (auth/validation bilingual) |
| 6 | 1 | layout chrome + Header.test.tsx bilingual |
| 7 | 1 | components + ICU plural tests ship together |
| 8 | 1 | components + tests ship together |
| 9 | 1 | components + tests ship together |
| 10 | 2 | code (components + hooks) + tests (chat bilingual + grep-audit integration) |
| 11 | 1 | single-file landing page refactor |
| 12 | 1 | auth pages + OAuth redirect test |
| 13 | 1 | error files + API route tests |
| 14 | 1 | footer + privacidad note |
| 15 | 1 | deletion + test cleanup |
| **Total** | **19 commits across 15 PRs** | |

### Dependency graph

```
S1 ──┬─► S2 ──┬─► S3 ──┬─► S6 ──┐
     │        │        ├─► S7   ├─► S15
     ├─► S4 ──┼────────┼─► S8   │
     │        │        ├─► S9   │
     │        │        ├─► S10  │
     │        │        └─► S14  │
     │        │                 │
     │        └─► S5 ───────────┼─► S12
     │                          │
     └─► S11                    │
     └─► S13                    │
```

### Execution order (the linear chain)

1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15

Slices 4, 11, 13 can in principle land in parallel with their dependency siblings, but `stacked-to-main` requires linear order for review focus.

### PR strategy reminder

`stacked-to-main`: each slice branches from `main` AFTER the previous slice has merged (or from the immediately previous slice branch for in-flight review). PR body MUST include a dependency diagram with `📍` on the current slice (per `chained-pr` skill). Slice 11 (700 LOC) and slice 8 (500 LOC) approach the cap and have explicit manual review gates in the proposal.

---

## Phase 0: Preconditions (apply once before slice 1)

- [ ] Confirm working tree is clean (`git status`)
- [ ] Create `feat-frontend-i18n/slice-1` branch off `main`
- [ ] Verify `frontend/package.json` pins no `^` (AGENTS.md rule 10)
- [ ] Confirm `pnpm` workspace is healthy: `cd frontend && pnpm install --frozen-lockfile`

---

### Task 1 — `chore(i18n): install next-intl + middleware chain + messages skeleton`

**Slice**: 1 / 15
**LOC estimate**: ~250
**Depends on**: none
**Closes**: REQ-I18N-001, REQ-I18N-002, REQ-I18N-003, REQ-I18N-004, REQ-I18N-012, REQ-I18N-015
**Closes AC**: AC-1, AC-2, AC-8, AC-12 (script only)

**Files touched**:
- **CREATE** `frontend/messages/en.json` (Common + Errors namespaces only — other namespaces added per slice)
- **CREATE** `frontend/messages/es.json` (Common + Errors namespaces only)
- **CREATE** `frontend/src/i18n/routing.ts` (`defineRouting({ locales:['es','en'], defaultLocale:'es', localePrefix:'as-needed', localeDetection:true })`)
- **CREATE** `frontend/src/i18n/request.ts` (`getRequestConfig` dynamic-imports `messages/${locale}.json`)
- **CREATE** `frontend/scripts/audit-i18n.sh` (ripgrep PCRE2 wrapper, PCRE2 pattern for hardcoded user-facing strings; excludes `messages/**`, `privacidad/**`, `*.test.{ts,tsx}`, `__tests__/**`, `test-utils.tsx`, `scripts/**`, JSDoc)
- **REWRITE** `frontend/src/middleware.ts` (chain `createIntlMiddleware(routing)(req)` → `updateSession(req)`; merge cookies; honor `NEXT_PUBLIC_I18N_ENABLED='false'` kill-switch)
- **UPDATE** `frontend/src/lib/supabase/middleware.ts` (add `stripLocalePrefix(path)` helper, apply before `publicPaths.some(...)`)
- **UPDATE** `frontend/next.config.ts` (wrap with `createNextIntlPlugin('./src/i18n/request.ts')`)
- **UPDATE** `frontend/package.json` (add `"next-intl": "3.<pinned-exact>"`; add scripts `lint:i18n: bash scripts/audit-i18n.sh`, `audit:i18n: bash scripts/audit-i18n.sh`)

**Preconditions**:
- Branch `feat-frontend-i18n/slice-1` is clean
- `main` is green (all 4 CI gates pass)
- `pnpm install --frozen-lockfile` succeeds; record the exact pinned version of `next-intl` (e.g., `3.26.5`) for the commit message

**Acceptance gate** (binary):
- [ ] `pnpm run typecheck` exits 0
- [ ] `pnpm run lint` exits 0
- [ ] `pnpm run test` exits 0
- [ ] `pnpm run build` exits 0
- [ ] `pnpm run lint:i18n` runs (may have matches in untranslated areas — expected)
- [ ] `curl -H "Accept-Language: es-ES,es;q=0.9,en;q=0.8" http://localhost:3000/dashboard` returns 200 (no redirect) — manual smoke
- [ ] `curl -H "Accept-Language: en-US,en;q=0.9,es;q=0.8" http://localhost:3000/dashboard` returns 307 with `Location: /en/dashboard` — manual smoke
- [ ] `NEXT_PUBLIC_I18N_ENABLED=false pnpm dev` still serves `/dashboard` (kill-switch works)

**Implementation steps** (ordered, concrete):
1. `cd frontend && pnpm add next-intl@latest` → record exact version → re-pin exact in `package.json` (no `^`)
2. Create `frontend/messages/en.json` with `Common` + `Errors` namespaces only (placeholder keys `Common.yes/no/loading/save/cancel/error/empty/retry`, `Errors.networkError/notFound/generic`)
3. Create `frontend/messages/es.json` matching structure with Spanish equivalents
4. Create `frontend/src/i18n/routing.ts` exporting `routing = defineRouting({ locales: ['es','en'] as const, defaultLocale: 'es', localePrefix: 'as-needed', localeDetection: true })` and `type Locale = 'es' | 'en'`
5. Create `frontend/src/i18n/request.ts` exporting `default getRequestConfig(async ({ requestLocale }) => { ... })` that resolves locale via `(routing.locales as readonly string[]).includes(...)` and dynamically imports `messages/${locale}.json`
6. Rewrite `frontend/src/middleware.ts` to chain `intlMiddleware(req)` first (assign result), then `await updateSession(request)`; merge `intlResponse.cookies.getAll()` onto `supabaseResponse`; honor kill-switch `process.env.NEXT_PUBLIC_I18N_ENABLED === 'false'`
7. Update `frontend/src/lib/supabase/middleware.ts`: add `stripLocalePrefix(path: string)` iterating over `routing.locales`, returning the first match stripped; apply before `publicPaths.some(p => stripped === p || stripped.startsWith(p + '/'))`
8. Update `frontend/next.config.ts`: wrap existing config with `createNextIntlPlugin('./src/i18n/request.ts')`
9. Create `frontend/scripts/audit-i18n.sh` (ripgrep PCRE2 against `frontend/src/**/*.{ts,tsx}` with documented excludes); chmod +x
10. Add `scripts.lint:i18n = "bash scripts/audit-i18n.sh"` to `frontend/package.json`
11. Update `frontend/.env.example` with `# NEXT_PUBLIC_I18N_ENABLED=true` (default true; uncomment + set `false` for kill-switch)
12. Update `frontend/README.md` "Caching" or new "i18n" section: document locale list, prefix policy, kill-switch, lint:i18n script

**Risks** (slice-specific):
- R1 (high): wrong middleware order breaks auth — mitigation: chain `intlMiddleware` BEFORE `updateSession`; cookies merged last; verify OAuth callback path (manual smoke)
- R-ext: `next-intl` peer-dep mismatch with `next@15.5.19` — mitigation: install latest stable 3.x; if version-pinned to 15.4.x specifically, fall back to next-intl `3.22.x`

**Rollback** (one-line):
- `git revert <merge-sha>` — removes dep + middleware; switcher/messages never wired (slice 3+); zero user-visible change

**Commit format**:
- Title: `chore(i18n): install next-intl <exact-version> + middleware chain + messages skeleton`
- Body: list files, document kill-switch env var, link REQ-I18N-001/002/003/004/015
- Second commit (audit + README only): `docs(i18n): add lint:i18n audit script + README i18n section`

---

### Task 2 — `feat(i18n): root layout dynamic <html lang> + NextIntlClientProvider`

**Slice**: 2 / 15
**LOC estimate**: ~80
**Depends on**: 1
**Closes**: REQ-I18N-005, REQ-I18N-018 (provider boundary)
**Closes AC**: AC-4

**Files touched**:
- **UPDATE** `frontend/src/app/layout.tsx` (convert to RSC: `setRequestLocale(locale)`, `await getLocale()`, `await getMessages()`, `<html lang={locale} suppressHydrationWarning>`, wrap children in `<NextIntlClientProvider locale={locale} messages={messages}>`)
- **CREATE** `frontend/tests/integration/layout-lang.test.tsx` (mounts layout, asserts `<html lang="es">` by default and `<html lang="en">` for `/en/*`)

**Preconditions**:
- Slice 1 merged to `main`
- Branch `feat-frontend-i18n/slice-2` off `main`

**Acceptance gate** (binary):
- [ ] `pnpm run typecheck` exits 0
- [ ] `pnpm run lint` exits 0
- [ ] `pnpm run test` exits 0
- [ ] `pnpm run build` exits 0
- [ ] `layout-lang.test.tsx` passes (mounts layout, asserts `<html lang>` flips ES↔EN)

**Implementation steps** (ordered, concrete):
1. Open `frontend/src/app/layout.tsx`; at the top, add `import { setRequestLocale, getLocale, getMessages } from 'next-intl/server'` and `import { NextIntlClientProvider } from 'next-intl'`
2. Add `export const dynamic = 'force-dynamic'` if not already RSC
3. In the default exported async function: `const locale = await getLocale(); const messages = await getMessages(); setRequestLocale(locale);`
4. Replace hardcoded `lang="es"` on `<html>` with `lang={locale}`; add `suppressHydrationWarning` (next-themes hydration noise)
5. Wrap `{children}` with `<NextIntlClientProvider locale={locale} messages={messages}>` (preserve existing `<Providers>` ordering — `Providers` inside `NextIntlClientProvider`)
6. Create `frontend/tests/integration/layout-lang.test.tsx` (or co-locate as `src/app/layout.test.tsx`) using vitest + `@testing-library/react`; assert default `lang="es"` and explicit `locale="en"` resolves `lang="en"`
7. Ensure all 8 `page.tsx` files remain `'use client'` per design D10 page audit (no RSC conversion in v1)

**Risks** (slice-specific):
- R2 (medium): RSC/client boundary leak — `NextIntlClientProvider` must wrap children but NOT be a client boundary for `getMessages` — mitigation: import `NextIntlClientProvider` from `next-intl` (server-safe), call `getMessages()` server-side
- R-ext (medium): static rendering warning — `setRequestLocale` MUST be called or next-intl warns "static rendering not enabled" — mitigation: call `setRequestLocale(locale)` before any child render

**Rollback** (one-line):
- `git revert <merge-sha>` — reverts layout to hardcoded `lang="es"`; provider tree gone; users see no change (no translations defined yet for them)

**Commit format**:
- Title: `feat(i18n): root layout dynamic <html lang> + NextIntlClientProvider`

---

### Task 3 — `feat(i18n): LanguageSwitcher widget + header slot + tests`

**Slice**: 3 / 15
**LOC estimate**: ~300
**Depends on**: 1, 2
**Closes**: REQ-I18N-006, REQ-I18N-007 (header slot), REQ-I18N-008, REQ-I18N-009, REQ-I18N-010, REQ-I18N-011, REQ-I18N-017
**Closes AC**: AC-3, AC-7 (partial — switcher + renderWithIntl)

**Files touched**:
- **CREATE** `frontend/src/components/layout/LanguageSwitcher.tsx` (Radix `DropdownMenu.Root` + `DropdownMenu.RadioGroup`; `lucide-react/Languages` icon; native-language labels "English"/"Español"; framer-motion spring w/ `useReducedMotion()` fallback; cookie + localStorage + `router.push()` + `router.refresh()`)
- **CREATE** `frontend/src/components/layout/LanguageSwitcher.test.tsx` (vitest: cookie set, localStorage set, URL change, re-render assertion; both locales)
- **UPDATE** `frontend/src/components/layout/Header.tsx` (mount `<LanguageSwitcher />` between `AuthStatus` and `ThemeToggle`; remove `ROUTE_META` EN literal — replace with `useTranslations('Navigation')`)
- **UPDATE** `frontend/src/components/layout/Footer.tsx` (mount `<LanguageSwitcher inFooter />` in footer; conditional render only on routes WITHOUT `AppShell` per D11)
- **UPDATE** `frontend/src/test-utils.tsx` (add `renderWithIntl(ui, { locale?: 'es'|'en', messages? })` wrapper composing `NextIntlClientProvider` + existing `QueryClient` + `ThemeProvider`; default `locale='es'`)
- **UPDATE** `frontend/messages/{en,es}.json` (add `Navigation` namespace: `dashboard/search/favorites/settings/jobDetail/signOut` keys)
- **UPDATE** `frontend/package.json` (no new deps — Radix dropdown-menu + framer-motion + lucide-react already in tree)

**Preconditions**:
- Slice 2 merged to `main`
- Branch `feat-frontend-i18n/slice-3` off `main`

**Acceptance gate** (binary):
- [ ] `pnpm run typecheck` exits 0
- [ ] `pnpm run lint` exits 0
- [ ] `pnpm run test` exits 0
- [ ] `pnpm run build` exits 0
- [ ] `LanguageSwitcher.test.tsx` passes for both locales
- [ ] Visual check: switcher trigger visible next to ThemeToggle in Header on `/dashboard`

**Implementation steps** (ordered, concrete):
1. Extend `frontend/messages/en.json` + `es.json` with `Navigation` namespace keys (5 nav items × 2 locales)
2. Create `frontend/src/components/layout/LanguageSwitcher.tsx`:
   - `'use client'`; props `{ inFooter?: boolean }`
   - Use `useLocale()` + `useRouter()` + `usePathname()` from `next-intl`/`next/navigation`
   - DropdownMenu items: array `[{value:'es', label:'Español'}, {value:'en', label:'English'}]`
   - Switch action: set `document.cookie="NEXT_LOCALE=<v>; path=/; max-age=31536000; SameSite=Lax"` + `localStorage.setItem('NEXT_LOCALE', v)` + `router.push(localizedPath)` + `router.refresh()`
   - Header variant: `h-9 w-9` icon-only; Footer variant: text + icon
   - Animation: `motion.div` with spring `{type:'spring', bounce:0.1, duration:0.15}`; `useReducedMotion()` strips spring → opacity-only
3. Create `frontend/src/components/layout/LanguageSwitcher.test.tsx`:
   - Test 1: click "English" → `document.cookie` contains `NEXT_LOCALE=en`; `localStorage['NEXT_LOCALE']==='en'`; mock router asserted called with `/en/...`
   - Test 2: keyboard nav — Tab focuses trigger, Enter opens, ArrowDown × 2 + Enter selects
   - Test 3: `prefers-reduced-motion: reduce` → framer-motion `transition.duration` is `0.15` (no spring)
4. Update `frontend/src/components/layout/Header.tsx`:
   - Add `'use client'` if not present; import `useTranslations('Navigation')`
   - Replace hardcoded nav labels with `t('dashboard')` etc.
   - Mount `<LanguageSwitcher />` in the right-side slot between `AuthStatus` and `ThemeToggle`
5. Update `frontend/src/components/layout/Footer.tsx`:
   - Mount `<LanguageSwitcher inFooter />` conditionally on public routes (`/`, `/login`, `/signup`, `/privacidad`) — use `usePathname()` guard
6. Update `frontend/src/test-utils.tsx`:
   - Add `renderWithIntl(ui, { locale = 'es', messages } = {})` that imports messages dynamically and wraps with `NextIntlClientProvider`
   - Re-export existing `render` from `@testing-library/react` aliased as `render` (default)
7. Add translation keys to `Footer` namespace: `Footer.privacy`, `Footer.copyright`, `Footer.languageSwitcher`

**Risks** (slice-specific):
- R3 (medium): switcher breaks Header layout if mounted in wrong slot — mitigation: visual regression via Storybook or manual screenshot; header height MUST stay `h-14` per REQ-I18N-007
- R-ext (medium): Radix keyboard model breaks if `DropdownMenu.RadioGroup` `value` not controlled — mitigation: use `value={currentLocale}` + `onValueChange={handleSelect}`

**Rollback** (one-line):
- `git revert <merge-sha>` — switcher removed; Header labels revert to EN literal; Footer loses footer-variant switcher; users see no functional change

**Commit format**:
- Title (commit 1): `feat(i18n): LanguageSwitcher widget + Header/Footer slot`
- Title (commit 2): `test(i18n): LanguageSwitcher bilingual tests + renderWithIntl wrapper`

---

### Task 4 — `feat(i18n): lib/formatters.ts locale-aware refactor`

**Slice**: 4 / 15
**LOC estimate**: ~120
**Depends on**: 1
**Closes**: REQ-I18N-014
**Closes AC**: AC-5

**Files touched**:
- **UPDATE** `frontend/src/lib/formatters.ts` (add `locale?: Locale` param to `formatDistanceToNow`, `formatNumber`, `formatDate`; import `es` + `enUS` from `date-fns/locale`; default `locale='es'` per D14 safety net)
- **CREATE** `frontend/src/lib/__tests__/formatters.test.ts` (vitest: `formatDistanceToNow` with both locales; `formatNumber` with both locales; default `locale='es'` preserved)
- **UPDATE** `frontend/src/types/i18n.ts` (re-export `Locale` type from `@/i18n/routing` if not already; optional — may inline)

**Preconditions**:
- Slice 1 merged to `main`
- Branch `feat-frontend-i18n/slice-4` off `main`

**Acceptance gate** (binary):
- [ ] `pnpm run typecheck` exits 0
- [ ] `pnpm run lint` exits 0
- [ ] `pnpm run test` exits 0
- [ ] `pnpm run build` exits 0
- [ ] `formatters.test.ts` passes for both locales
- [ ] `grep -rn '"en-US"\|"es-ES"' frontend/src --include='*.ts' --include='*.tsx'` returns ZERO matches outside `lib/formatters.ts` and `privacidad/page.tsx`

**Implementation steps** (ordered, concrete):
1. Open `frontend/src/lib/formatters.ts`:
   - Add `import { es, enUS } from 'date-fns/locale'`
   - Add `import type { Locale } from '@/i18n/routing'`
   - Update `formatDistanceToNow(dateStr, locale: Locale = 'es')` to pass `{ locale: locale === 'es' ? es : enUS }` as 3rd arg
   - Add `formatNumber(value: number, locale: Locale = 'es')` wrapping `new Intl.NumberFormat(locale).format(value)`
   - Update `formatDate(dateStr, locale: Locale = 'es')` similarly
   - `getPlatformColorClass` unchanged
2. Create `frontend/src/lib/__tests__/formatters.test.ts`:
   - Test: `formatDistanceToNow(threeHoursAgo, 'es')` contains "hace"
   - Test: `formatDistanceToNow(threeHoursAgo, 'en')` contains "ago" or "hours"
   - Test: `formatNumber(1234.5, 'es')` returns Spanish thousands separator
   - Test: `formatNumber(1234.5, 'en')` returns English thousands separator
   - Test: default `formatDistanceToNow(threeHoursAgo)` (no arg) returns ES (default)
3. Do NOT migrate callers yet — they still pass no `locale`; default arg keeps behavior stable

**Risks** (slice-specific):
- R4 (medium): default arg `'es'` hides missing callers — mitigation: TODO comments on each unmigrated callsite; explicit migration in slices 7, 8, 9, 10
- R-ext (low): `date-fns/locale` import paths change between versions — mitigation: pin via existing `date-fns@4.1.0` already installed

**Rollback** (one-line):
- `git revert <merge-sha>` — formatters revert to English default; callers unchanged; tests removed

**Commit format**:
- Title: `feat(i18n): lib/formatters.ts locale-aware refactor + bilingual tests`

---

### Task 5 — `feat(i18n): authCopy.ts → messages/{en,es}.json Auth + Validation namespaces`

**Slice**: 5 / 15
**LOC estimate**: ~250
**Depends on**: 1, 2
**Closes**: REQ-I18N-012 (Validation namespace), auth-deprecation step 1
**Closes AC**: AC-7 (partial — auth form tests bilingual)

**Files touched**:
- **UPDATE** `frontend/messages/en.json` (add `Auth` namespace ~30 keys + `Validation` namespace ~10 keys)
- **UPDATE** `frontend/messages/es.json` (matching keys)
- **UPDATE** `frontend/src/components/auth/{ForgotPasswordForm,MagicLinkForm,ResetPasswordForm,EmailVerificationBanner}.tsx` (replace `import { authCopy } from '@/lib/authCopy'` with `useTranslations('Auth')` + `useTranslations('Validation')`)
- **UPDATE** `frontend/src/components/settings/{ChangePasswordForm,DeleteAccountDialog,GlobalSignoutButton}.tsx` (same import replacement)
- **UPDATE** `frontend/src/lib/validation/authSchemas.ts` (replace `authCopy.validation.*` with `t('Validation.*')` via `getTranslations` at module load — OR move messages to static lookup keyed by schema)
- **UPDATE** `frontend/src/lib/api-client.ts` (error messages via `useTranslations('Errors')`; for client-side fetch wrappers, accept a `t` function arg or pass error keys)
- **KEEP** `frontend/src/lib/authCopy.ts` (deprecated but unused — DELETE in slice 15)
- **UPDATE** `frontend/src/lib/__tests__/authCopy.test.ts` (mark `@deprecated`; keep green until slice 15)
- **UPDATE** `frontend/src/app/(auth)/{forgot-password,reset-password}/__tests__/*.test.tsx` (replace `authCopy.*` lookups with `screen.getByText(t('Auth.*'))`)
- **UPDATE** `frontend/src/app/login/__tests__/page.test.tsx` (same)

**Preconditions**:
- Slice 2 merged to `main` (provider boundary exists)
- Branch `feat-frontend-i18n/slice-5` off `main`

**Acceptance gate** (binary):
- [ ] `pnpm run typecheck` exits 0
- [ ] `pnpm run lint` exits 0
- [ ] `pnpm run test` exits 0
- [ ] `pnpm run build` exits 0
- [ ] Auth form tests pass for both `locale='es'` AND `locale='en'`
- [ ] `git grep authCopy frontend/src` shows ONLY `lib/authCopy.ts` (file) and `lib/__tests__/authCopy.test.ts` (test) — all import sites migrated

**Implementation steps** (ordered, concrete):
1. Read `frontend/src/lib/authCopy.ts`; catalog all keys (expect ~50 strings across `auth`, `change`, `delete`, `forgot`, `reset`, `magicLink`, `globalSignOut`, `banner`, `validation`)
2. Add `Auth` namespace to `frontend/messages/en.json` + `es.json` (split keys by feature: `Auth.forgotPassword.*`, `Auth.resetPassword.*`, `Auth.changePassword.*`, `Auth.deleteAccount.*`, `Auth.globalSignOut.*`, `Auth.emailVerification.*`, `Auth.magicLink.*`)
3. Add `Validation` namespace (10 keys: `emailRequired`, `emailInvalid`, `passwordRequired`, `passwordMinLength`, `passwordsMismatch`, `confirmRequired`, `magicLinkEmailInvalid`, `forgotEmailRequired`, `resetTokenRequired`, `deleteConfirmRequired`)
4. For each of the 8 import sites: replace `import { authCopy } from '@/lib/authCopy'` with `const t = useTranslations('Auth');` (or `useTranslations('Validation')`) inside the component body; replace each `authCopy.section.key` with `t('section.key')`
5. For `validation/authSchemas.ts` (module-level Zod schemas): change error messages to Zod `message` callbacks that accept `{ t }` arg at form-render time, OR refactor schemas to return error KEYS that the form component resolves via `t()`
6. Add JSDoc `@deprecated` to `authCopy.ts` exports
7. Update `authCopy.test.ts` to assert only the deprecation notice (test still passes until slice 15)
8. Run `pnpm run test -- --run frontend/src/components/auth frontend/src/components/settings frontend/src/lib frontend/src/app/login frontend/src/app/(auth)`; verify bilingual pass

**Risks** (slice-specific):
- R5 (medium): Zod schema `message` callback can't call `useTranslations` (module scope) — mitigation: pass error KEY as message, resolve at form via `t(errorKey)`; document in slice 12 (auth pages) for the form-level rendering
- R-ext (low): ESLint `no-unused-vars` may flag `authCopy` after migration — mitigation: JSDoc `@deprecated` + skip ESLint rule via comment; final cleanup in slice 15

**Rollback** (one-line):
- `git revert <merge-sha>` — import sites revert to `authCopy`; messages added but unused (no harm); file still present

**Commit format**:
- Title (commit 1): `feat(i18n): migrate authCopy → messages Auth + Validation namespaces`
- Title (commit 2): `test(i18n): auth + validation form bilingual tests`

---

### Task 6 — `feat(i18n): layout chrome (Header, Sidebar, ThemeToggle, AppShell)`

**Slice**: 6 / 15
**LOC estimate**: ~200
**Depends on**: 3, 5
**Closes**: REQ-I18N-007 (Navigation in Sidebar)
**Closes AC**: AC-7 (Header.test.tsx bilingual)

**Files touched**:
- **UPDATE** `frontend/src/components/layout/Header.tsx` (replace remaining `ROUTE_META` English literals with `useTranslations('Navigation')`; ensure `LanguageSwitcher` already mounted in slice 3; descriptions via `t('Navigation.<route>.description')`)
- **UPDATE** `frontend/src/components/layout/Sidebar.tsx` (`navItems` `label` keys → `t('Navigation.<key>')`; sr-only via `t('Navigation.<key>ScreenReader')`)
- **UPDATE** `frontend/src/components/layout/ThemeToggle.tsx` (`sr-only` text → `useTranslations('Common.toggleTheme')` or new `Theme.toggleTheme` key)
- **UPDATE** `frontend/src/components/layout/AppShell.tsx` (any hardcoded EN strings → `useTranslations`)
- **UPDATE** `frontend/messages/{en,es}.json` (extend `Navigation` namespace with route descriptions + sr-only variants + active-state announcements; add `Theme.toggleTheme` to `Common`)
- **UPDATE** `frontend/src/components/layout/__tests__/Header.test.tsx` (assert bilingual: `screen.getByText('Panel')` for ES, `screen.getByText('Dashboard')` for EN)

**Preconditions**:
- Slices 3 + 5 merged to `main`
- Branch `feat-frontend-i18n/slice-6` off `main`

**Acceptance gate** (binary):
- [ ] `pnpm run typecheck` exits 0
- [ ] `pnpm run lint` exits 0
- [ ] `pnpm run test` exits 0
- [ ] `pnpm run build` exits 0
- [ ] `Header.test.tsx` passes for both locales (asserts Spanish `Panel` + English `Dashboard`)
- [ ] Sidebar active-state still functions (manual visual check)

**Implementation steps** (ordered, concrete):
1. Extend `frontend/messages/en.json` + `es.json`:
   - `Navigation.<route>.description` for dashboard/search/favorites/settings/jobDetail (5 keys × 2 locales)
   - `Navigation.<route>.screenReader` for active-state announcements
   - `Common.toggleTheme` (2 locales)
2. Update `Header.tsx`: replace `ROUTE_META[r].label` with `t(\`Navigation.${r}.label\`)`, `ROUTE_META[r].description` with `t(\`Navigation.${r}.description\`)`
3. Update `Sidebar.tsx`:
   - `navItems` array — convert label keys to `useTranslations` calls (use `useTranslations` hook at top of component, then `navItems` array literal references `t('key')`)
   - sr-only text via `t('Navigation.<key>ScreenReader')`
4. Update `ThemeToggle.tsx`: `<span className="sr-only">{t('Common.toggleTheme')}</span>`
5. Update `AppShell.tsx`: any hardcoded EN strings → `useTranslations` (likely 0–2 strings)
6. Update `Header.test.tsx`: replace `screen.getByText('Dashboard')` with bilingual assertion — render with `renderWithIntl(ui, { locale: 'es' })` and assert `'Panel'`; render again with `locale: 'en'` and assert `'Dashboard'`

**Risks** (slice-specific):
- R6 (medium): Sidebar active-state broken if `useTranslations` called inside `.map()` — mitigation: hoist `const t = useTranslations(...)` to component top; pass to map closure

**Rollback** (one-line):
- `git revert <merge-sha>` — Header/Sidebar/ThemeToggle revert to EN literals; bilingual test reverts to single-locale

**Commit format**:
- Title: `feat(i18n): layout chrome Header/Sidebar/ThemeToggle/AppShell bilingual`

---

### Task 7 — `feat(i18n): dashboard + RightSidebar + JobSourceBreakdown + StatsCardsRow`

**Slice**: 7 / 15
**LOC estimate**: ~300
**Depends on**: 3, 4, 5
**Closes**: REQ-DASH-I18N-001, REQ-DASH-I18N-002, REQ-DASH-I18N-003 (RightSidebar nav), REQ-I18N-013 (ICU plurals for dashboard counts)
**Closes AC**: AC-9 (ICU plurals)

**Files touched**:
- **UPDATE** `frontend/src/components/dashboard/{StatCard,StatsCardsRow,PlatformDistribution,JobSourceBreakdown}.tsx` (replace literals with `useTranslations('Dashboard')`; ICU plurals for counts via `t('Dashboard.stats.totalJobs', { count: n })`)
- **UPDATE** `frontend/src/components/dashboard/RightSidebar.tsx` (`useTranslations('Dashboard')` for Latest Jobs, View all jobs, Summary, Sources, Last sync, No jobs yet; sr-only via `t('Dashboard.<key>ScreenReader')`)
- **UPDATE** `frontend/src/app/(app)/dashboard/page.tsx` (`useTranslations('Dashboard')` for any page-level strings)
- **UPDATE** `frontend/messages/{en,es}.json` (add `Dashboard` namespace: `stats.*` (4 cards + plural variants), `rightSidebar.*`, `jobs.totalJobs` ICU plural, `sources.*`, `noJobsYet`)
- **UPDATE** `frontend/src/components/shared/EmptyState.tsx` (`title` + `description` props now accept translation keys OR pre-resolved strings; favorites usage will use translation-key variant in slice 9)
- **CREATE** `frontend/src/components/dashboard/__tests__/StatsCardsRow.test.tsx` (ICU plural snapshot for both locales)

**Preconditions**:
- Slices 3 + 4 + 5 merged
- Branch `feat-frontend-i18n/slice-7` off `main`

**Acceptance gate** (binary):
- [ ] `pnpm run typecheck` exits 0
- [ ] `pnpm run lint` exits 0
- [ ] `pnpm run test` exits 0
- [ ] `pnpm run build` exits 0
- [ ] `StatsCardsRow.test.tsx` ICU plural snapshots pass (count 0/1/2/5 for both locales)
- [ ] `grep -rn '"[0-9] trabajos"\|"[0-9] jobs"' frontend/src/components/dashboard` returns ZERO matches (ICU keys only)

**Implementation steps** (ordered, concrete):
1. Extend `frontend/messages/{en,es}.json` with `Dashboard` namespace:
   - `Dashboard.stats.{totalJobs,newJobs,activePlatforms,averageSalary}.label` + `.plural` ICU keys
   - `Dashboard.rightSidebar.{latestJobs,viewAllJobs,summary,sources,lastSync,noJobsYet,srOnly.*}`
   - `Dashboard.platforms.{linkedin,indeed,infojobs}` (display names)
   - ICU example: `es.json` → `"stats.totalJobs": "{count, plural, =0 {Sin trabajos} one {# trabajo} other {# trabajos}}"`; `en.json` → `"stats.totalJobs": "{count, plural, =0 {No jobs} one {# job} other {# jobs}}"`
2. Update `StatCard.tsx`: `label` prop becomes translation key; component calls `t(label)` internally OR accepts pre-resolved string (prefer translation key approach)
3. Update `StatsCardsRow.tsx`: replace 4 hardcoded labels with `useTranslations('Dashboard')` keys; counts via `t('Dashboard.stats.totalJobs', { count: totalJobs })`
4. Update `PlatformDistribution.tsx`: `t('Dashboard.platforms.<name>')` for platform display names
5. Update `JobSourceBreakdown.tsx`: `t('Dashboard.platforms.<name>')` + ICU `t('Dashboard.activePlatforms', { count })`
6. Update `RightSidebar.tsx`: `useTranslations('Dashboard')` for all chrome strings; `sr-only` text via `t('Dashboard.rightSidebar.srOnly.<key>')`
7. Update `dashboard/page.tsx`: any page-level chrome strings via `useTranslations('Dashboard')`
8. Update `EmptyState.tsx`: extend props `{ titleKey?: string, title?: string, descriptionKey?: string, description?: string }` — favor key variant; deprecated string variant kept for backward compat until slice 9
9. Create `StatsCardsRow.test.tsx`: 4 sub-tests × 3 counts (0, 1, 5) × 2 locales = 24 assertions via `renderWithIntl`

**Risks** (slice-specific):
- R7 (medium): mixed-language files produce wrong translations if existing literals are partially ES/EN — mitigation: catalog each literal per proposal §"Per-string canonicalization"; pick the canonical key once
- R-ext (medium): ICU `=0` variant requires explicit selector in BOTH locales — mitigation: write `=0 {…}` in both `es.json` and `en.json` (Spanish distinguishes "Sin" from "0")

**Rollback** (one-line):
- `git revert <merge-sha>` — dashboard components revert to current ES/EN literals; ICU test reverts

**Commit format**:
- Title: `feat(i18n): dashboard + RightSidebar + ICU plurals + StatsCardsRow bilingual tests`

---

### Task 8 — `feat(i18n): jobs components (JobCard, CompactJobCard, JobDetailContent, JobDetailAside, JobList, GenerateCVModal, FavoriteButton)`

**Slice**: 8 / 15
**LOC estimate**: ~500
**Depends on**: 3, 4, 5
**Closes**: REQ-I18N-013 (Jobs ICU plurals), REQ-I18N-016 (OAuth callback locale-aware redirectTo via job page)
**Closes AC**: AC-9 (jobs ICU), AC-8 (OAuth redirect)

**Files touched**:
- **UPDATE** `frontend/src/components/jobs/{JobCard,CompactJobCard,JobDetailContent,JobDetailAside,JobList,GenerateCVModal,FavoriteButton,PlatformBadge,SalaryBadge}.tsx` (replace all literals with `useTranslations('Jobs')`; ICU plurals for `jobs.count` and `jobs.applicants`; mixed-language files canonicalized)
- **UPDATE** `frontend/src/app/jobs/[id]/page.tsx` (`useTranslations('Jobs')` for page chrome; OAuth `redirectTo` becomes `${origin}/auth/callback?next=${dashboardPath}` where `dashboardPath` derived from `useLocale()`)
- **UPDATE** `frontend/src/app/jobs/page.tsx` (`useTranslations('Jobs')`)
- **UPDATE** `frontend/messages/{en,es}.json` (add `Jobs` namespace: `card.{title,apply,view,posted,location,source}`, `count` ICU plural, `detail.{description,requirements,benefits,applyNow}`, `modal.{title,consent,generate,downloading}`, `favorite.{add,remove}`, `source.{linkedin,indeed,infojobs}`, `applicants` ICU plural, `noJobs`)
- **UPDATE** `frontend/src/components/jobs/__tests__/{JobCard,JobDetailContent,GenerateCVModal}.test.tsx` (bilingual assertions; ICU plural count test for `applicants`)

**Preconditions**:
- Slices 3 + 4 + 5 merged
- Branch `feat-frontend-i18n/slice-8` off `main`

**Acceptance gate** (binary):
- [ ] `pnpm run typecheck` exits 0
- [ ] `pnpm run lint` exits 0
- [ ] `pnpm run test` exits 0
- [ ] `pnpm run build` exits 0
- [ ] All `jobs/__tests__/*.test.tsx` pass for both locales
- [ ] ICU `jobs.count` renders "1 trabajo" / "2 trabajos" / "0 trabajos" (ES) and "1 job" / "2 jobs" / "0 jobs" (EN)
- [ ] Manual smoke: OAuth login with `NEXT_LOCALE=en` lands on `/en/dashboard`

**Implementation steps** (ordered, concrete):
1. Extend `messages/{en,es}.json` with `Jobs` namespace (~50 keys × 2 locales)
2. Update `JobCard.tsx`: `useTranslations('Jobs')` for all literals; ICU plural for `applicants`
3. Update `CompactJobCard.tsx`: same pattern
4. Update `JobDetailContent.tsx`: `t('Jobs.detail.<key>')` for description/requirements/benefits/applyNow
5. Update `JobDetailAside.tsx`: per-string canonicalization for mixed ES/EN literals (audit each line per proposal §"Per-string canonicalization")
6. Update `JobList.tsx`: `t('Jobs.count', { count })` for result count; empty state via `t('Jobs.noJobs')`
7. Update `GenerateCVModal.tsx`: `t('Jobs.modal.<key>')`; consent text bilingual
8. Update `FavoriteButton.tsx`: `t('Jobs.favorite.add' / 'remove')` for `aria-label` and toast text
9. Update `PlatformBadge.tsx` + `SalaryBadge.tsx`: `t('Jobs.source.<name>')` for platform display
10. Update `jobs/[id]/page.tsx`: OAuth `redirectTo` logic — read `useLocale()`; build `dashboardPath = locale === 'es' ? '/dashboard' : '/en/dashboard'`; pass to `signInWithOAuth({ options: { redirectTo: \`${origin}/auth/callback?next=${dashboardPath}\` } })`
11. Update `jobs/page.tsx`: page-level chrome via `useTranslations('Jobs')`
12. Update tests: `renderWithIntl(ui, { locale: 'es' })` + `locale: 'en'` variants; ICU plural snapshots for `count` and `applicants`

**Risks** (slice-specific):
- R8 (medium): mixed-language `JobDetailAside` produces wrong translations if any literal is missed — mitigation: full file re-read line-by-line; mark TODO with `@i18n-audit` JSDoc for any post-merge misses
- R-ext (medium): OAuth `redirectTo` mismatch if `useLocale()` returns wrong locale during SSR — mitigation: hardcode `dashboardPath` from URL segment via `useParams()` if `useLocale()` is unreliable in server components; verify via manual E2E before merge

**Rollback** (one-line):
- `git revert <merge-sha>` — jobs components revert to current ES/EN literals; OAuth redirect logic reverts (acceptable: existing behavior)

**Commit format**:
- Title: `feat(i18n): jobs components bilingual + OAuth callback locale-aware redirectTo`

---

### Task 9 — `feat(i18n): search + settings components + favorites page`

**Slice**: 9 / 15
**LOC estimate**: ~500
**Depends on**: 3, 4, 5
**Closes**: REQ-I18N-013 (Search/Favorites ICU), REQ-FAV-I18N-001, REQ-FAV-I18N-002, REQ-FAV-I18N-003
**Closes AC**: AC-9 (favorites count plural), AC-6 (FavoriteButton toast)

**Files touched**:
- **UPDATE** `frontend/src/components/search/{SearchBar,LocationBar,FilterPanel,SalaryRangeSlider}.tsx` (`useTranslations('Search')` for placeholders, filters, results count; ICU plural for `results`)
- **UPDATE** `frontend/src/components/settings/{UserCVCard,AccountSection,NotificationSettings,PlatformConfigCard,ChangePasswordForm,DeleteAccountDialog,GlobalSignoutButton}.tsx` (`useTranslations('Settings')` + `useTranslations('Auth')` for forms)
- **UPDATE** `frontend/src/app/(app)/search/page.tsx` (page-level chrome via `useTranslations('Search')`)
- **UPDATE** `frontend/src/app/(app)/favorites/page.tsx` (`useTranslations('Favorites')` for heading, count ICU plural, filter placeholder)
- **UPDATE** `frontend/src/app/(app)/settings/page.tsx` (`useTranslations('Settings')`)
- **UPDATE** `frontend/messages/{en,es}.json` (add `Search` namespace: `placeholder`, `locationPlaceholder`, `filters.{salary,date,platform,remote,contractType}`, `results` ICU plural, `noResults`; `Favorites` namespace: `heading`, `filter.placeholder`, `emptyState.{title,description}`, `count` ICU plural; `Settings` namespace: `notifications.{email,push,weekly}`, `platform.{linkedin,indeed,infojobs}.{enabled,interval}`, `account.{title,changePassword,deleteAccount,signOut}`)
- **UPDATE** `frontend/src/components/settings/__tests__/{NotificationSettings,PlatformConfigCard}.test.tsx` (bilingual assertions)
- **UPDATE** `frontend/src/app/(app)/favorites/__tests__/page.test.tsx` (ICU plural for `count`)

**Preconditions**:
- Slices 3 + 4 + 5 merged
- Branch `feat-frontend-i18n/slice-9` off `main`

**Acceptance gate** (binary):
- [ ] `pnpm run typecheck` exits 0
- [ ] `pnpm run lint` exits 0
- [ ] `pnpm run test` exits 0
- [ ] `pnpm run build` exits 0
- [ ] Search + favorites + settings tests pass for both locales
- [ ] `favorites.count` ICU renders "1 favorito guardado" / "5 favoritos guardados" (ES) and "1 saved favorite" / "5 saved favorites" (EN)
- [ ] FavoriteButton toast text resolves to active locale

**Implementation steps** (ordered, concrete):
1. Extend `messages/{en,es}.json` with `Search`, `Favorites`, `Settings` namespaces (~60 keys × 2 locales)
2. Update `SearchBar.tsx`: placeholder via `t('Search.placeholder')`; results count via `t('Search.results', { count })`
3. Update `LocationBar.tsx`: placeholder via `t('Search.locationPlaceholder')`
4. Update `FilterPanel.tsx`: filter labels via `t('Search.filters.<key>')`
5. Update `search/page.tsx`: page chrome via `t('Search.<key>')`
6. Update `favorites/page.tsx`:
   - Heading via `t('Favorites.heading')`
   - Count via `t('Favorites.count', { count: favorites.length })` ICU
   - Filter input placeholder via `t('Favorites.filter.placeholder')`
   - Empty state: `EmptyState titleKey="Favorites.emptyState.title" descriptionKey="Favorites.emptyState.description"`
7. Update `settings/page.tsx`: page chrome via `t('Settings.<key>')`
8. Update `NotificationSettings.tsx`: `t('Settings.notifications.<key>')` for labels + descriptions
9. Update `PlatformConfigCard.tsx`: `t('Settings.platform.<name>.<key>')`
10. Update `AccountSection.tsx`: `t('Settings.account.<key>')`
11. Update `ChangePasswordForm.tsx` + `DeleteAccountDialog.tsx` + `GlobalSignoutButton.tsx`: use `useTranslations('Auth')` (slice 5 already added the keys)
12. Update tests: bilingual assertions for each component

**Risks** (slice-specific):
- R9 (medium): settings Zod schema i18n timing — schema defined at module scope, errors rendered at form time — mitigation: pass error KEYS via `message` callback; resolve in component via `t()` (same pattern as slice 5)
- R-ext (medium): favorites `EmptyState` translation-key variant not yet wired (slice 7 added prop, slice 9 uses it) — mitigation: verify `EmptyState` accepts both `titleKey` and `title`; fallback to string variant if key variant broken

**Rollback** (one-line):
- `git revert <merge-sha>` — search + settings + favorites revert to current literals

**Commit format**:
- Title: `feat(i18n): search + settings + favorites components + ICU plurals`

---

### Task 10 — `feat(i18n): chat components + useChat error i18n`

**Slice**: 10 / 15
**LOC estimate**: ~250
**Depends on**: 3, 4, 5
**Closes**: REQ-CHAT-I18N-001, REQ-CHAT-I18N-002, REQ-CHAT-I18N-003
**Closes AC**: AC-6 (toasts localized)

**Files touched**:
- **UPDATE** `frontend/src/components/chat/{ChatDialog,ChatPanel,ChatMessages,AssistantMessage,ChatInput}.tsx` (`useTranslations('Chat')` for FAB label, dialog title, chat header, "Looking for:", "Matching jobs", "Done" badge, input placeholder, send button aria-label)
- **UPDATE** `frontend/src/hooks/useChat.ts` (replace 4 hardcoded English error strings with `useTranslations('Chat.errors')` keys; callsite must be inside component tree wrapped by `NextIntlClientProvider`)
- **UPDATE** `frontend/src/hooks/{useStats,useJobs,useJobsInfinite,useJobDetail}.ts` (replace hardcoded English error strings with `useTranslations('Jobs.errors')` / `useTranslations('Common.errors')` keys)
- **UPDATE** `frontend/src/lib/api-client.ts` (error messages accept translation KEY arg, caller resolves via `t(key)`)
- **UPDATE** `frontend/src/app/api/{jobs/[id],cv/generate,jobs/chat/stream,stats}/route.ts` (error JSON responses use `getTranslations` from `next-intl/server`; return `{ error: { key, locale } }` shape)
- **UPDATE** `frontend/messages/{en,es}.json` (add `Chat` namespace: `fab.label`, `dialog.title`, `panel.header`, `messages.{lookingFor,matchingJobs,done}`, `input.{placeholder,sendAriaLabel}`, `errors.{streamFailed,connectionFailed,generic}`; extend `Jobs.errors` namespace)
- **UPDATE** `frontend/src/components/chat/__tests__/{ChatDialog,ChatMessages}.test.tsx` (bilingual assertions; toast text resolution)
- **CREATE** `frontend/src/hooks/__tests__/useChat.test.ts` (mock `useTranslations`; assert error toasts use ICU keys)

**Preconditions**:
- Slices 3 + 4 + 5 merged
- Branch `feat-frontend-i18n/slice-10` off `main`

**Acceptance gate** (binary):
- [ ] `pnpm run typecheck` exits 0
- [ ] `pnpm run lint` exits 0
- [ ] `pnpm run test` exits 0
- [ ] `pnpm run build` exits 0
- [ ] Chat tests pass for both locales
- [ ] `grep -rn '"Something went wrong"\|"Connection failed"' frontend/src --include='*.ts' --include='*.tsx'` returns ZERO matches outside `messages/*.json`
- [ ] Manual smoke: chat error toast shows in active locale

**Implementation steps** (ordered, concrete):
1. Extend `messages/{en,es}.json` with `Chat` namespace (~15 keys × 2 locales)
2. Update each chat component: replace literals with `t('Chat.<key>')`; ensure `'use client'` directive present (they already are)
3. Update `useChat.ts`:
   - Move `const t = useTranslations('Chat.errors')` to hook top (hooks can call `useTranslations` if they're called inside a client component, which `useChat` is)
   - Replace 4 hardcoded strings: `toast.error(t('streamFailed'))`, `toast.error(t('connectionFailed'))`, etc.
4. Update `useStats.ts` + `useJobs.ts` + `useJobsInfinite.ts` + `useJobDetail.ts`: same pattern — `const t = useTranslations('Jobs.errors')` at hook top; replace literal error messages
5. Update `api-client.ts`: error responses pass back `error.key` instead of `error.message`; client hook callsites resolve via `t(key)`
6. Update API route handlers (`jobs/[id]`, `cv/generate`, `jobs/chat/stream`, `stats`): use `getTranslations` from `next-intl/server`; return `{ error: { key: 'Jobs.errors.notFound', locale } }`
7. Update `ChatDialog.test.tsx` + `ChatMessages.test.tsx`: render with `renderWithIntl`; assert Spanish + English labels
8. Create `useChat.test.ts`: mock `useTranslations`; assert toast calls receive ICU keys
9. Wire `pnpm run lint:i18n` failure in CI for any new hardcoded English errors

**Risks** (slice-specific):
- R10 (high): toast fires BEFORE `NextIntlClientProvider` mounts (RSC boundary violation) — mitigation: hooks ARE inside the provider boundary (called from client components); verify by manual smoke; if toast appears blank, move `toast` call into a child component
- R-ext (high): API route `getTranslations` requires `requestLocale` to be set — mitigation: call `unstable_setRequestLocale(locale)` at the top of each route handler (next-intl 3.x pattern); fallback to default `'es'` if header parsing fails

**Rollback** (one-line):
- `git revert <merge-sha>` — useChat + hooks revert to English errors; chat components revert to current literals

**Commit format**:
- Title (commit 1): `feat(i18n): chat components + useChat/useStats/useJobs error i18n`
- Title (commit 2): `test(i18n): chat bilingual + useChat toast key assertions + grep-audit wired`

---

### Task 11 — `feat(i18n): landing page (app/page.tsx, 729 LOC)`

**Slice**: 11 / 15
**LOC estimate**: ~700
**Depends on**: 1, 2, 3
**Closes**: REQ-I18N-012 (Landing namespace)
**Closes AC**: AC-7 (landing renders both locales)

**Files touched**:
- **UPDATE** `frontend/src/app/page.tsx` (replace ~80 marketing strings with `useTranslations('Landing')`; ICU plurals for any counts; per-string canonicalization for ES/EN marketing copy)
- **EXTRACT** (optional, if duplication emerges) `frontend/src/components/landing/{Hero,Features,CTA,Testimonials,FooterNote}.tsx` from `app/page.tsx` — each consumes `useTranslations('Landing.<section>')`
- **UPDATE** `frontend/messages/{en,es}.json` (add `Landing` namespace: `hero.{title,subtitle,ctaPrimary,ctaSecondary}`, `features.{search,matches,save,apply,privacy,offline}.{title,description}`, `cta.{title,subtitle,button}`, `testimonials.{quote,author}`, `footerNote`)
- **UPDATE** `frontend/src/app/page.test.tsx` if exists (bilingual render assertions)

**Preconditions**:
- Slices 1 + 2 + 3 merged
- Branch `feat-frontend-i18n/slice-11` off `main`
- Marketing team has reviewed the canonical EN copy (per proposal §"Out-of-Scope Follow-Ups" — auto-decision: use existing EN literal as canonical)

**Acceptance gate** (binary):
- [ ] `pnpm run typecheck` exits 0
- [ ] `pnpm run lint` exits 0
- [ ] `pnpm run test` exits 0
- [ ] `pnpm run build` exits 0
- [ ] `/` renders correctly in both locales (manual screenshot review)
- [ ] Marketing copy review: EN matches team-approved canonical
- [ ] `git diff main -- frontend/src/app/page.tsx` ≤ 700 LOC

**Implementation steps** (ordered, concrete):
1. Read `frontend/src/app/page.tsx` end-to-end; identify all user-facing literals (~80 strings)
2. Extend `messages/{en,es}.json` with `Landing` namespace (~80 keys × 2 locales = 160 keys); group by section (`hero.*`, `features.*`, `cta.*`, `testimonials.*`, `footerNote.*`)
3. Decide whether to extract sub-components OR keep single-file with hook calls — recommended: extract if file becomes unwieldy after migration; otherwise keep single-file with `'use client'` + `const t = useTranslations('Landing')` at top
4. Replace each literal: `t('Landing.hero.title')`, `t('Landing.features.search.description')`, etc.
5. ICU plurals for any count callsites (e.g., `t('Landing.features.matches.count', { count: 100 })`)
6. Manual review by maintainer: walk through `/` in both locales, screenshot, verify marketing copy reads native
7. If components extracted: create `frontend/src/components/landing/__tests__/Hero.test.tsx` with bilingual assertions

**Risks** (slice-specific):
- R11 (high): 729-LOC file with `useTranslations` calls scattered — risk of missing one literal — mitigation: enable `pnpm run lint:i18n` as REQUIRED check on this slice (not just informational); pre-merge manual grep audit of the diff
- R-ext (medium): marketing copy rewording — mitigation: ES copy is CANONICAL from current file; EN copy is faithful translation; defer creative rewording to marketing follow-up

**Rollback** (one-line):
- `git revert <merge-sha>` — landing reverts to Spanish-only; EN visitors see Spanish page (acceptable — landing was Spanish-only pre-change)

**Commit format**:
- Title: `feat(i18n): landing page bilingual (app/page.tsx, 729 LOC)`

---

### Task 12 — `feat(i18n): auth pages (login, signup, forgot-password, reset-password, jobs/[id])`

**Slice**: 12 / 15
**LOC estimate**: ~400
**Depends on**: 5, 8 (8 for OAuth callback via jobs/[id])
**Closes**: REQ-I18N-016 (OAuth callback locale-correct)
**Closes AC**: AC-8 (OAuth callback)

**Files touched**:
- **UPDATE** `frontend/src/app/login/page.tsx` (`useTranslations('Auth.login')` for all literals; OAuth `redirectTo` locale-aware)
- **UPDATE** `frontend/src/app/signup/page.tsx` (`useTranslations('Auth.signup')`)
- **UPDATE** `frontend/src/app/(auth)/forgot-password/page.tsx` (`useTranslations('Auth.forgotPassword')`)
- **UPDATE** `frontend/src/app/(auth)/reset-password/page.tsx` (`useTranslations('Auth.resetPassword')`)
- **UPDATE** `frontend/src/app/auth/callback/route.ts` (OAuth callback handler reads `NEXT_LOCALE` cookie or `Accept-Language`; redirects to locale-correct `/dashboard`)
- **UPDATE** `frontend/messages/{en,es}.json` (extend `Auth` namespace with `login.*`, `signup.*` keys; alt text via `t('Common.altText.<key>')`)
- **UPDATE** `frontend/src/app/login/__tests__/page.test.tsx` (bilingual assertions; OAuth `redirectTo` assertion)
- **UPDATE** `frontend/src/app/signup/__tests__/page.test.tsx` (bilingual assertions)
- **UPDATE** `frontend/src/app/(auth)/forgot-password/__tests__/page.test.tsx` (bilingual assertions)

**Preconditions**:
- Slices 5 + 8 merged
- Branch `feat-frontend-i18n/slice-12` off `main`

**Acceptance gate** (binary):
- [ ] `pnpm run typecheck` exits 0
- [ ] `pnpm run lint` exits 0
- [ ] `pnpm run test` exits 0
- [ ] `pnpm run build` exits 0
- [ ] Auth tests pass for both locales
- [ ] Manual smoke: OAuth login with `NEXT_LOCALE=en` → callback → `/en/dashboard`
- [ ] Manual smoke: OAuth login with `NEXT_LOCALE=es` → callback → `/dashboard`

**Implementation steps** (ordered, concrete):
1. Extend `messages/{en,es}.json` with `Auth.login.*` (10 keys), `Auth.signup.*` (8 keys), alt text keys
2. Update `login/page.tsx`:
   - `'use client'` (already is); `const t = useTranslations('Auth.login')`
   - Replace all literals
   - OAuth `signInWithOAuth({ options: { redirectTo: \`${origin}/auth/callback?next=${locale === 'es' ? '/dashboard' : '/en/dashboard'}\` } })`
3. Update `signup/page.tsx`: same pattern, no OAuth redirect (email/password signup)
4. Update `forgot-password/page.tsx` + `reset-password/page.tsx`: `useTranslations('Auth.forgotPassword' / 'resetPassword')`
5. Update `auth/callback/route.ts`:
   - Read `request.cookies.get('NEXT_LOCALE')?.value`
   - Fallback: parse `Accept-Language` header → 'es' or 'en'
   - Read `next` query param (default `/dashboard`)
   - Prepend locale prefix if `next === '/dashboard'` and locale is 'en'
   - Redirect
6. Update tests: bilingual assertions for each page; OAuth callback redirect test mock with `NEXT_LOCALE=en` cookie → expect `/en/dashboard` redirect

**Risks** (slice-specific):
- R12 (high): OAuth callback path mismatch if locale detection wrong — mitigation: explicit cookie read + Accept-Language fallback; manual E2E before merge; verify both cookie set and not-set paths
- R-ext (medium): Supabase `redirectTo` URL must be in allowed list — mitigation: `${origin}` derived from `request.nextUrl.origin` (trusted source)

**Rollback** (one-line):
- `git revert <merge-sha>` — auth pages revert to current Spanish literals; OAuth callback reverts to single-locale redirect

**Commit format**:
- Title: `feat(i18n): auth pages bilingual + OAuth callback locale-aware redirect`

---

### Task 13 — `feat(i18n): error/not-found + api error JSON`

**Slice**: 13 / 15
**LOC estimate**: ~80
**Depends on**: 1, 2
**Closes**: REQ-I18N-012 (Errors in error boundaries)
**Closes AC**: AC-7 (error/not-found bilingual)

**Files touched**:
- **UPDATE** `frontend/src/app/error.tsx` (`'use client'`; `useTranslations('Errors')` for title/description/cta)
- **UPDATE** `frontend/src/app/not-found.tsx` (RSC; `getTranslations('Errors')` for title/description/cta)
- **UPDATE** `frontend/src/app/api/{jobs/[id],cv/generate,jobs/chat/stream,stats}/route.ts` (error JSON via `getTranslations` from `next-intl/server`; call `unstable_setRequestLocale(locale)` first)
- **UPDATE** `frontend/messages/{en,es}.json` (extend `Errors` namespace: `boundary.{title,description,retry}`, `notFound.{title,description,home}`)

**Preconditions**:
- Slices 1 + 2 merged (slice 10 may have already touched API routes — coordinate; merge order ensures slice 13 runs after slice 10 OR refactor slice 10 to leave the locale-setup for slice 13)

**Acceptance gate** (binary):
- [ ] `pnpm run typecheck` exits 0
- [ ] `pnpm run lint` exits 0
- [ ] `pnpm run test` exits 0
- [ ] `pnpm run build` exits 0
- [ ] Manual smoke: visit `/this-route-does-not-exist` → 404 page renders in active locale
- [ ] Manual smoke: trigger runtime error → `error.tsx` renders in active locale

**Implementation steps** (ordered, concrete):
1. Extend `messages/{en,es}.json` with `Errors.boundary.*` + `Errors.notFound.*`
2. Update `error.tsx`:
   - Add `'use client'` directive (required for hooks)
   - `const t = useTranslations('Errors.boundary')`
   - Render `<h1>{t('title')}</h1>` etc.
3. Update `not-found.tsx`:
   - Make RSC: add `import { getTranslations } from 'next-intl/server'`
   - `export default async function NotFound() { const t = await getTranslations('Errors.notFound'); ... }`
4. Update API routes: at top of each handler, `const locale = await getRequestLocale(); await unstable_setRequestLocale(locale); const t = await getTranslations('Errors');` → return `{ error: t('generic') }`
5. If slice 10 already modified API routes, verify locale-setup is consistent; coordinate via PR description

**Risks** (slice-specific):
- R13 (low): `error.tsx` is client component — hook usage safe — mitigation: standard next-intl pattern
- R-ext (medium): API route `unstable_setRequestLocale` API may change in next-intl 3.x patch versions — mitigation: pin exact version; if API differs in installed version, use `getLocale()` + manual message load

**Rollback** (one-line):
- `git revert <merge-sha>` — error/not-found revert to EN literals; API errors revert to English

**Commit format**:
- Title: `feat(i18n): error/not-found + API error JSON bilingual`

---

### Task 14 — `chore(i18n): privacidad decision (footer note + link)`

**Slice**: 14 / 15
**LOC estimate**: ~20
**Depends on**: 3
**Closes**: REQ-I18N-019
**Closes AC**: AC-10

**Files touched**:
- **UPDATE** `frontend/src/components/layout/Footer.tsx` (add translated note via `useTranslations('Footer.privacyNote')`; link `/privacidad` unchanged)
- **UPDATE** `frontend/messages/{en,es}.json` (add `Footer.privacyNote` ICU for the "Spanish only" note — or two static keys: `Footer.privacyNoteSpanishOnlyEs`, `Footer.privacyNoteSpanishOnlyEn`)

**Preconditions**:
- Slice 3 merged (LanguageSwitcher mounted in Footer)
- Branch `feat-frontend-i18n/slice-14` off `main`

**Acceptance gate** (binary):
- [ ] `pnpm run typecheck` exits 0
- [ ] `pnpm run lint` exits 0
- [ ] `pnpm run test` exits 0
- [ ] `pnpm run build` exits 0
- [ ] Manual smoke: on `/en/`, footer note shows EN translation; click `/privacidad` → renders Spanish

**Implementation steps** (ordered, concrete):
1. Add to `messages/en.json`: `"Footer": { "privacyNote": "Spanish only — English version coming soon", ... }`
2. Add to `messages/es.json`: `"Footer": { "privacyNote": "Solo en español — versión en inglés próximamente", ... }`
3. Update `Footer.tsx`:
   - `const t = useTranslations('Footer')`
   - Below `/privacidad` link, render `<p className="text-xs text-muted-foreground">{t('privacyNote')}</p>`
4. No changes to `app/privacidad/page.tsx` (stays Spanish-only per D13)

**Risks**: None (small slice)

**Rollback** (one-line):
- `git revert <merge-sha>` — note removed; `/privacidad` link unchanged

**Commit format**:
- Title: `chore(i18n): privacidad footer note (Spanish only v1)`

---

### Task 15 — `chore(i18n): remove deprecated authCopy.ts + final cleanup`

**Slice**: 15 / 15
**LOC estimate**: ~100
**Depends on**: 5, 6, 9
**Closes**: auth-deprecation step 2 (file removal)
**Closes AC**: AC-12 (grep audit clean)

**Files touched**:
- **DELETE** `frontend/src/lib/authCopy.ts`
- **DELETE** `frontend/src/lib/__tests__/authCopy.test.ts`
- **UPDATE** `frontend/src/app/login/__tests__/page.test.tsx` (replace any `authCopy.*` references with `t()` calls)
- **UPDATE** `frontend/src/app/(auth)/forgot-password/__tests__/page.test.tsx` (same)
- **UPDATE** `frontend/src/app/(auth)/reset-password/__tests__/page.test.tsx` (same)
- **UPDATE** `frontend/src/components/settings/__tests__/{ChangePasswordForm,DeleteAccountDialog,GlobalSignoutButton}.test.tsx` (same)
- **UPDATE** `frontend/src/components/auth/__tests__/{ForgotPasswordForm,MagicLinkForm,ResetPasswordForm,EmailVerificationBanner}.test.tsx` (same)
- **UPDATE** `frontend/README.md` (document `authCopy.ts` removal; link to `messages/{en,es}.json` `Auth` namespace)

**Preconditions**:
- Slices 5 + 6 + 9 merged (all import sites migrated)
- Branch `feat-frontend-i18n/slice-15` off `main`

**Acceptance gate** (binary):
- [ ] `pnpm run typecheck` exits 0
- [ ] `pnpm run lint` exits 0
- [ ] `pnpm run test` exits 0
- [ ] `pnpm run build` exits 0
- [ ] `git grep authCopy frontend/` returns ZERO matches outside `CHANGELOG.md` / git history
- [ ] `pnpm run lint:i18n` passes (zero hardcoded user-facing strings)

**Implementation steps** (ordered, concrete):
1. Run `git grep -n authCopy frontend/src`; verify ONLY `authCopy.ts` (file) + `authCopy.test.ts` (test) + possibly CHANGELOG references
2. Delete `frontend/src/lib/authCopy.ts` via `git rm`
3. Delete `frontend/src/lib/__tests__/authCopy.test.ts` via `git rm`
4. For each test file with `authCopy.*` reference: replace with `screen.getByText(t('Auth.<key>'))` patterns; ensure `renderWithIntl` wrapper is in use
5. Update `frontend/README.md` "Architecture" section: remove any reference to `authCopy.ts`; add link to `messages/{en,es}.json` `Auth` namespace as source of truth
6. Final grep audit: `git grep -n 'authCopy\|"Something went wrong"\|"Connection failed"\|"en-US"\|"es-ES"' frontend/src --include='*.ts' --include='*.tsx' | grep -v messages/ | grep -v privacidad/page.tsx` returns ZERO matches
7. Run `pnpm run lint:i18n`; should report ZERO matches in source

**Risks** (slice-specific):
- R15 (low): stale test references — mitigation: explicit per-file grep + test run before commit

**Rollback** (one-line):
- `git restore frontend/src/lib/authCopy.ts frontend/src/lib/__tests__/authCopy.test.ts` (file is small; can be restored from history without full revert)

**Commit format**:
- Title: `chore(i18n): remove deprecated authCopy.ts + final cleanup`

---

## Open Questions

**None — proceed to `sdd-apply`.** All architectural decisions resolved in design (D1–D15). The five explicit follow-ups (F1 privacidad translation, F2 backend currency schema, F3 client-side salary parsing, F4 additional locales, F5 ICU lint rule) are deferred per proposal §"Out-of-Scope Follow-Ups" — not blockers.

---

## Total summary

- **Tasks**: 15
- **Commits**: 19 (slices 1, 3, 5, 10 = 2 commits each; slices 2, 4, 6, 7, 8, 9, 11, 12, 13, 14, 15 = 1 commit each)
- **Total LOC**: ~4,050 across frontend workspace
- **PRs (stacked-to-main)**: 15
- **Files touched (cumulative)**: ~95 files
- **CI gates enforced per slice**: `typecheck`, `lint`, `test`, `build`, `lint:i18n` (from slice 6 onward)
- **PR strategy**: `stacked-to-main`; each PR body includes dependency diagram with `📍` on current slice per `chained-pr` skill

---

## Next recommended phase

`sdd-apply` — start from Task 1 (slice 1: install next-intl + middleware chain + messages skeleton). Each task above is self-contained and executable in one session by an `sdd-apply` sub-agent. The `sdd-apply` orchestrator MUST honor the `stacked-to-main` chain strategy and the per-slice LOC caps (slice 11 and slice 8 approach 700 LOC; both have explicit manual review gates).
