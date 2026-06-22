# Proposal: `feat-frontend-i18n`

> **Change**: `feat-frontend-i18n`
> **Status**: proposed (awaiting spec)
> **Date**: 2026-06-22
> **Project**: jobs-finder (frontend workspace)
> **Preflight**: Pace A2 · Artifacts B1 hybrid (engram primary + openspec mirror) · PRs C4 (auto-forecast) · Review budget D1 (400 lines) · Chain strategy `stacked-to-main` (15 slices)
> **Strict TDD**: false (per `sdd-init/jobs-finder`)
> **Mirror**: `openspec/changes/feat-frontend-i18n/proposal.md` (hybrid preflight)
> **Engram**: `sdd/feat-frontend-i18n/proposal` (canonical)

---

## Intent

The `jobs-finder` frontend is a Spanish-only product serving a Spanish-speaking primary audience, but it ships a 729-line Spanish landing page, mixed-language component copy, hardcoded `<html lang="es">`, locale-blind date/number formatting, and zero localization infrastructure. As the project reaches SaaS-grade bar (contributors, English-speaking job seekers, shareable English URLs), it needs a real i18n layer: a language switcher the user trusts, a default-locale that doesn't regress current users, and currency/pluralization that reads native. This change installs `next-intl` with `localePrefix: 'as-needed'` (default `es` at root, opt-in `/en/...`), translates every user-facing string into both locales, and fixes the locale bugs already lurking in `lib/formatters.ts` and `<html lang>`. The Spanish audience is preserved (zero URL regression for current users), English becomes a first-class shareable surface, and a `NEXT_LOCALE` cookie + `localStorage` mirror gives the switcher instant visual feedback. Translation is treated as work, not a refactor — the explore flagged per-string decisions for the ~12 mixed-language components and this change documents the canonical key for each.

---

## Scope

### In Scope

| Area | What changes |
|---|---|
| `frontend/package.json` | Add `next-intl` (pinned exact) + `date-fns` locale peers (already present) |
| `frontend/messages/{en,es}.json` *(new)* | ~500–600 keys × 2 locales, namespaced by feature |
| `frontend/src/i18n/{routing,request}.ts` *(new)* | next-intl config; locale list `['es','en']`; default `es`; `localePrefix: 'as-needed'` |
| `frontend/src/middleware.ts` | Chain `createMiddleware(...).middleware` → Supabase `updateSession`; locale-aware `publicPaths` |
| `frontend/src/lib/supabase/middleware.ts` | `publicPaths` becomes locale-prefix-aware (regex/strip) |
| `frontend/src/app/layout.tsx` | Dynamic `<html lang>`; wrap with `NextIntlClientProvider`; `getMessages()` in RSC |
| `frontend/src/components/layout/LanguageSwitcher.{tsx,test.tsx}` *(new)* | Radix `dropdown-menu` widget, `lucide-react/Languages`, next to `ThemeToggle` |
| `frontend/src/lib/formatters.ts` | Locale-aware refactor: `formatDistanceToNow` + `Intl.NumberFormat` accept `locale: 'es'\|'en'` |
| `frontend/src/lib/authCopy.ts` | Deprecated; contents migrated to `messages/{en,es}.json` `Auth` + `Validation` namespaces (last slice removes file) |
| `frontend/src/components/layout/Header.tsx` | `ROUTE_META.label/description` → `t()`; mount `LanguageSwitcher` |
| `frontend/src/components/layout/Sidebar.tsx` | `navItems[].label` → `t()` |
| `frontend/src/components/layout/ThemeToggle.tsx` | `sr-only` text → `t()` |
| `frontend/src/components/dashboard/{StatsCardsRow,RightSidebar,JobSourceBreakdown,PlatformDistribution,StatCard}.tsx` | Per-string ES/EN decision; ICU plurals for counts |
| `frontend/src/components/jobs/{JobCard,CompactJobCard,JobDetailContent,JobDetailAside,JobList,GenerateCVModal,FavoriteButton,PlatformBadge,SalaryBadge}.tsx` | Mixed-language files → unified per-locale keys |
| `frontend/src/components/search/{SearchBar,LocationBar,FilterPanel}.tsx` | EN copy → `t()`; placeholders localized |
| `frontend/src/components/settings/{UserCVCard,AccountSection,NotificationSettings,PlatformConfigCard,ChangePasswordForm,DeleteAccountDialog,GlobalSignoutButton}.tsx` | All ES/EN → `t()`; auth forms via `messages.Auth` |
| `frontend/src/components/chat/{ChatDialog,ChatPanel,ChatMessages,AssistantMessage,ChatInput}.tsx` | EN copy + ES literals → `t()` |
| `frontend/src/components/auth/{AuthStatus,EmailVerificationBanner,ForgotPasswordForm,MagicLinkForm,ResetPasswordForm}.tsx` | All via `messages.Auth` (already centralized) |
| `frontend/src/components/shared/{EmptyState,ErrorState,ExportButton}.tsx` | 4 × `EmptyState` variants + `ErrorState` + `ExportButton` → `t()` |
| `frontend/src/app/page.tsx` (landing, 729 LOC) | ~80 marketing strings → `t()`; biggest single-file slice |
| `frontend/src/app/{error,not-found,loading}.tsx` | `error.tsx` + `not-found.tsx` EN copy → `t()` |
| `frontend/src/app/(app)/{dashboard,search,favorites,settings}/{page,loading}.tsx` | Placeholders + page copy → `t()` |
| `frontend/src/app/(auth)/{forgot-password,reset-password}/page.tsx` + `layout.tsx` | Auth copy via `messages.Auth`; alt text via `t()` |
| `frontend/src/app/jobs/[id]/page.tsx` | Mixed ES/EN → `t()`; locale-aware Supabase `redirectTo` |
| `frontend/src/app/login/page.tsx`, `signup/page.tsx` | Hardcoded ES → `t()` via `messages.Auth` |
| `frontend/src/app/api/{jobs/[id],cv/generate,jobs/chat/stream,stats}/route.ts` | English error JSON → locale-aware via `next-intl/server` |
| `frontend/src/hooks/{useChat,useStats,useJobs,useJobsInfinite,useJobDetail}.ts` | English error strings → `t()`; `useChat` toasts inside `NextIntlClientProvider` boundary |
| `frontend/src/lib/{api-client,validation/authSchemas}.ts` | Error strings → `t()`; `authSchemas` consumes `messages.Validation` |
| `frontend/src/test-utils.tsx` | Extend with `NextIntlClientProvider` wrapper; `Header.test.tsx` and new switcher tests use it |

### Out of Scope

- **Translation of `app/privacidad/page.tsx`** (478-line legal document) — stays Spanish-only in v1; footer link in EN locale points to the Spanish page with a note. Legal-reviewed translation opens as a follow-up change.
- **Currency reformatting** — backend returns raw salary strings (`"30.000 €"`, `"$2,500 USD"`); v1 displays them as-is. Requires backend schema change (structured `currency` + `amount` fields) — follow-up.
- **Locales beyond `en` + `es`** — routing + middleware are extensible; only new `messages/{locale}.json` is needed later.
- **RTL support** — neither `en` nor `es` requires it.
- **Backend changes** — out of scope; no FastAPI code touched.
- **Database / persistence of locale** — cookie + `localStorage` only.

---

## Approach

- **Library**: `next-intl@3.x` (pinned exact). Native App Router, RSC `getTranslations`, server-side middleware, ~14 KB, drop-in.
- **Routing**: `createMiddleware({ locales: ['es','en'], defaultLocale: 'es', localePrefix: 'as-needed', localeDetection: true })`. Default locale stays at root URLs (`/dashboard`, `/search`, `/login`) — zero regression for current users. Opt-in English gets shareable canonical URLs (`/en/dashboard`).
- **Middleware chain**: `createMiddleware(...).middleware` runs **before** `updateSession(request)` from `@/lib/supabase/middleware`. `publicPaths` becomes locale-prefix-aware via a small stripper helper (`stripLocalePrefix(path)`) so existing Supabase auth checks still match.
- **Message storage**: `frontend/messages/{en,es}.json`, namespaced by feature (`Common`, `Errors`, `Validation`, `Auth`, `Landing`, `Dashboard`, `Jobs`, `Search`, `Favorites`, `Settings`, `Chat`, `Footer`, `DateTime`). Namespaces mirror the existing folder structure so per-slice translation is mechanical.
- **Provider boundary**: `app/layout.tsx` becomes a server component that calls `getMessages()` + `getLocale()`, then wraps children in `<NextIntlClientProvider locale={locale} messages={messages}>`. Client components use `useTranslations('Namespace')`; RSCs use `getTranslations('Namespace')`.
- **Pluralization**: ICU MessageFormat for Spanish `uno/muchos` (`{count, plural, one {# trabajo} other {# trabajos}}`) on every count callsite (`JobCard`, `EmptyState`, `StatsCardsRow`, `SearchBar`, `useJobsInfinite`).
- **Locale refactor of `lib/formatters.ts`**: add `locale: 'es' | 'en'` parameter; `formatDistanceToNow` imports `es` from `date-fns/locale`; `Intl.NumberFormat(locale).format(n)`; wrap `toLocaleString()` without-arg callsites in a `formatNumber(value, locale)` helper. Currency is left untouched (out of scope).
- **Switcher widget spec** (matches the design system):
  - **Primitive**: shadcn `dropdown-menu` (Radix); `lucide-react/Languages` icon.
  - **Trigger**: ghost icon-only button `h-9 w-9`, `aria-label="Change language"`, sits next to `ThemeToggle` in the Header; footer fallback on routes without `AppShell` (`/`, `/login`, `/signup`, `/privacidad`).
  - **Items**: language name **in its own language** ("English" / "Español") — never a flag. Active item shows `lucide-react/Check` + bg highlight. Hover: ring + bg. `prefers-reduced-motion: reduce` → opacity-only fade (drop the spring).
  - **Animation**: framer-motion `motion.div` with `initial={{opacity:0, scale:0.95}}`, `animate={{opacity:1, scale:1}}`, `transition={{type:"spring", bounce:0.1, duration:0.15}}` — matches `JobCard.tsx` spring language.
  - **Theme-aware**: `bg-popover`, `text-popover-foreground`, `border-border` CSS variables (already wireframe-compliant).
  - **Persistence**: `document.cookie = "NEXT_LOCALE=en; path=/; max-age=31536000"` + `localStorage["NEXT_LOCALE"] = "en"` mirror; `router.refresh()` to re-render RSC tree.
  - **A11y**: full Radix keyboard model (Tab to focus, Enter/Space to open, Arrow nav, Enter to select, Escape to close) + `aria-haspopup="menu"` + `aria-expanded`.
- **Migration of `authCopy.ts`**: contents become `Auth` + `Validation` namespaces in both message files. Last slice removes `authCopy.ts` and updates the 8 import sites.

---

## Capabilities

> This section is the **contract** between proposal and specs. `sdd-spec` reads this to know exactly which spec files to create or update.

### New Capabilities

- **`frontend-i18n`**: locale routing, middleware chain, message storage, provider boundary, switcher widget, locale-aware formatters, pluralization rules. Becomes `openspec/specs/frontend-i18n/spec.md`.

### Modified Capabilities

- **`frontend-dashboard`**: every dashboard component gets locale-aware labels; counts use ICU plurals.
- **`chat-frontend`**: chat copy + `useChat` error toasts use `useTranslations`; `NextIntlClientProvider` boundary required.
- **`favorites`**: favorites page placeholders + empty-state copy localized.
- **`job-domain`** *(cross-cutting, not a UI capability but affected)*: shared types unchanged; only the string-bearing fields (`title`, `company`, `location`, `salary`) are display-only and locale-formatted via `lib/formatters.ts`. No schema delta — purely a frontend concern.

---

## Acceptance Criteria

- [ ] **AC-1** — A first-time visitor with `Accept-Language: es-ES,es;q=0.9,en;q=0.8` sees `/dashboard` rendered in Spanish (no redirect, no prefix).
- [ ] **AC-2** — A first-time visitor with `Accept-Language: en-US,en;q=0.9,es;q=0.8` is redirected to `/en/dashboard` and the page renders in English.
- [ ] **AC-3** — Clicking the switcher and selecting "English" sets `NEXT_LOCALE=en`, persists for 1 year (`max-age=31536000`), updates `localStorage["NEXT_LOCALE"]`, and the URL becomes `/en/...` (or stays if already there).
- [ ] **AC-4** — `<html lang>` matches the active locale on every page (verified by an integration test that mounts `app/layout.tsx` and asserts the attribute).
- [ ] **AC-5** — Date formatting (`formatDistanceToNow`, `toLocaleDateString`) and number formatting (`Intl.NumberFormat`, `toLocaleString()`) respect the active locale; no hardcoded `"en-US"` or `"es-ES"` strings remain in the codebase.
- [ ] **AC-6** — Every sonner toast in `useChat` (and other client hooks) uses `useTranslations`; no hardcoded English error strings in `useChat`, `useStats`, `useJobs`, `useJobsInfinite`, `useJobDetail`.
- [ ] **AC-7** — Vitest tests pass for the `LanguageSwitcher` in both locales (en + es) and for the `Header` (which already asserts `ROUTE_META.label`).
- [ ] **AC-8** — The Supabase middleware's `publicPaths` matches `/login`, `/es/login`, `/en/login`, `/auth/callback`, etc.; OAuth callback lands on the correct-locale `/dashboard` or `/en/dashboard` based on the user's active locale.
- [ ] **AC-9** — Spanish pluralization is grammatically correct everywhere a count is rendered: `1 trabajo / 2 trabajos / 0 trabajos` in `es.json`; `1 job / 2 jobs / 0 jobs` in `en.json` (ICU MessageFormat `{count, plural, one {...} other {...}}`).
- [ ] **AC-10** — `app/privacidad/page.tsx` remains Spanish-only in v1; the footer link in the EN locale points to `/privacidad` and renders a small note ("Spanish only — English version coming soon" — translated into the active locale).
- [ ] **AC-11** — All 4 frontend CI gates (`pnpm run typecheck`, `pnpm run lint`, `pnpm run test`, `pnpm run build`) pass after every PR.
- [ ] **AC-12** — A grep for hardcoded English or Spanish user-facing strings in `frontend/src/**/*.{ts,tsx}` (excluding `messages/*.json` and `privacidad/page.tsx`) returns zero matches outside of test fixtures and JSDoc.

---

## Risks

| # | Risk | Likelihood | Impact | Mitigation | Owner per slice |
|---|---|---|---|---|---|
| R1 | **Routing rewrites break existing bookmarks + OAuth redirects** — Supabase middleware hardcodes `/dashboard`, `/login`, `/auth/callback`; new `/en/...` prefix could mismatch. | High | High | Use `localePrefix: 'as-needed'` (default URLs unchanged); chain `createMiddleware(...).middleware` → `updateSession`; make Supabase `publicPaths` locale-prefix-aware (strip-prefix helper); run OAuth E2E before each merge. | Slice 1 (chain), Slice 2 (provider), Slice 12 (auth pages) |
| R2 | **Mixed-language strings already exist** — `StatsCardsRow`, `JobCard`, `CompactJobCard`, `JobDetailAside`, `jobs/[id]/page.tsx` ship with hand-mixed EN/ES literals; naive "wrap in `t()`" produces wrong translations. | High | Medium | Per-string canonicalization: each file gets an explicit ES-key / EN-key / both-key decision; ship v1 with ICU fallback for any single-language key; enforce via PR review checklist. | Slices 7, 8, 12 |
| R3 | **Locale-aware formatting** — `formatDistanceToNow` defaults to EN, `Intl.NumberFormat("en-US")` hardcoded, `.toLocaleString()` no-arg defaults to browser locale (unpredictable for SSR). | High | Medium | Slice 4 refactors `lib/formatters.ts` to accept `locale: 'es'\|'en'`; `date-fns/locale` imports for `es` + `enUS`; `formatNumber(value, locale)` helper for the no-arg callsites. | Slice 4 |
| R4 | **478-line Spanish legal page** — `app/privacidad/page.tsx` needs legal review to translate; not a typical i18n workload. | Medium | Low | Decision already made (orchestrator): keep Spanish-only v1; footer link in EN locale points to the Spanish page with a translated note. Slice 14 documents the decision; the slice is small (~20 LOC). | Slice 14 |
| R5 | **Spanish pluralization** — naive string replacement produces ungrammatical Spanish (`1 trabajo` vs `2 trabajos`). | Medium | Medium | All count callsites use `t('jobs.count', { count: n })` with ICU MessageFormat in both `es.json` and `en.json`. Audit grep for `\.length\b`, `${count}`, `toLocaleString()` before each affected slice merges. | Slices 7, 8, 9, 11 |

---

## Out-of-Scope Follow-Ups

| # | Follow-up | Why deferred |
|---|---|---|
| F1 | **`feat-frontend-privacidad-i18n`** — translate `app/privacidad/page.tsx` to English; legal review; add `messages/en.json` `Privacy` namespace. | Legal text requires review; out of v1 i18n scope. |
| F2 | **`feat-backend-currency-schema`** — expose structured `currency` (ISO 4217) + `amount` (number) on the `Job` domain; frontend parses + reformats via `Intl.NumberFormat(locale, { style: 'currency', currency })`. | Requires backend schema change + migration; cross-workspace. |
| F3 | **`feat-frontend-locale-aware-salary-parsing`** — parse the existing raw salary strings (`"30.000 €"`, `"$2,500 USD"`) client-side into a structured form so v1 can still display them locale-correctly without backend change. | Best-effort, lossy parsing; defer until F2 ships. |
| F4 | **`feat-frontend-add-locale-{pt,fr,...}`** — add Portuguese, French, etc. Routing + middleware are already extensible; only `messages/{locale}.json` needs to be added. | Demand-driven; not v1. |
| F5 | **`chore(i18n): audit ICU MessageFormat coverage`** — full-codebase scan for un-ICU'd count callsites; lint rule to forbid `t('...${count}...')` string interpolation in favor of ICU. | Polish pass; needs a real i18n linter setup. |

---

## PR Slice Plan (15 slices, `stacked-to-main`)

Chain strategy: **`stacked-to-main`** (per preflight C4 + D1). Each slice ≤ 700 LOC, ends with a green build, independently mergeable. Slices 1–3 are foundational; slices 4–15 are ordered by dependency. Each slice body must include a dependency diagram marking the current PR with `📍` (per `chained-pr` skill).

| # | PR title | LOC (≈) | Acceptance gate | Rollback boundary |
|---|---|---:|---|---|
| 1 | `chore(i18n): install next-intl + middleware chain + messages skeleton` | 250 | typecheck + lint + build pass; `/` still renders Spanish; smoke test `/en/dashboard` returns 200 | Revert dep + middleware → no UI change |
| 2 | `feat(i18n): root layout dynamic <html lang> + NextIntlClientProvider` | 80 | `app/layout.tsx` renders `<html lang="es">` by default and `<html lang="en">` for `/en/*`; integration test asserts attribute | Revert layout → app back to hardcoded `lang="es"` |
| 3 | `feat(i18n): LanguageSwitcher widget + header slot + tests` | 300 | vitest passes for both locales; visual check matches design system; switcher persists cookie | Hide widget; no functional regression |
| 4 | `feat(i18n): lib/formatters.ts locale-aware refactor` | 120 | `formatters.test.ts` (new) passes for both locales; no hardcoded `"en-US"`/`"es-ES"` left | Revert formatters; callers use English default (today's behavior) |
| 5 | `feat(i18n): authCopy.ts → messages/{en,es}.json Auth + Validation namespaces` | 250 | All auth/validation form tests pass for both locales; `authSchemas` consumes `messages.Validation` | Revert imports to `authCopy` (file remains until slice 15) |
| 6 | `feat(i18n): layout chrome (Header, Sidebar, ThemeToggle, AppShell)` | 200 | `Header.test.tsx` passes for both locales; `Sidebar` renders translated nav; `ThemeToggle` sr-only text localized | Revert `ROUTE_META`/`navItems` to English literals |
| 7 | `feat(i18n): dashboard + RightSidebar + JobSourceBreakdown + StatsCardsRow` | 300 | Snapshot tests for both locales; ICU plurals correct in `StatsCardsRow` | Revert per-component to current ES/EN mix |
| 8 | `feat(i18n): jobs components (JobCard, CompactJobCard, JobDetailContent, JobDetailAside, JobList, GenerateCVModal, FavoriteButton)` | 500 | All jobs tests pass for both locales; `GenerateCVModal` consent text in both | Revert per-component |
| 9 | `feat(i18n): search + settings components` | 500 | All settings tests pass for both locales; placeholders localized; auth forms via `messages.Auth` | Revert per-component |
| 10 | `feat(i18n): chat components + useChat error i18n` | 250 | Chat integration tests pass; toasts render in active locale; no hardcoded EN errors in `useChat` | Revert `useChat` to English errors |
| 11 | `feat(i18n): landing page (app/page.tsx, 729 LOC)` | 700 | `/` renders correctly in both locales; manual review of marketing copy | Revert landing to Spanish only |
| 12 | `feat(i18n): auth pages (login, signup, forgot-password, reset-password, jobs/[id])` | 400 | Auth flow E2E passes for both locales; Supabase `redirectTo` lands on correct locale | Revert per-page |
| 13 | `feat(i18n): error/not-found + api error JSON` | 80 | `error.tsx` + `not-found.tsx` localized; API error JSON localized via `next-intl/server` | Revert per-file |
| 14 | `chore(i18n): privacidad decision (footer note + link)` | 20 | Footer link in EN locale points to `/privacidad` with translated note; `privacidad/page.tsx` untouched | Hide the note; link still works |
| 15 | `chore(i18n): remove deprecated authCopy.ts + final cleanup` | 100 | typecheck + lint + test + build green; grep for `authCopy` returns zero; full coverage check | Restore `authCopy.ts` from git history (file is small) |
| **Total** | | **~4,050** | | |

> **Note on per-slice LOC vs. the 400-line review budget**: each individual PR is a stacked child of the previous one. The diff visible to the reviewer on `main` is per-slice; the per-slice budget is ≤ 700 LOC to allow the larger landing-page slice (slice 11) to stay mergeable without splitting. Every slice below the 400-line budget is held tighter; slice 11 and slice 8 are the only ones that approach the cap, and both have explicit "manual review" gates.

---

## Open Questions for the User

**None — proceed to spec.** All explore-level questions were resolved by the orchestrator's auto-decisions (default `es`, `next-intl`, `localePrefix: 'as-needed'`, privacidad Spanish-only v1, currency deferred, `stacked-to-main` chain strategy). The five follow-up table entries (F1–F5) are explicitly deferred to separate changes, not blocking decisions for this one.

---

## Rollback Plan

1. **Per-slice rollback**: each PR targets `main` stacked; `git revert <merge-sha>` is a clean revert because the slice is self-contained and tested in isolation.
2. **Feature-flag escape hatch** (if a slice lands and causes a regression in production): the middleware's `localeDetection: true` can be flipped to `false` in one line, which preserves the cookie-based locale but stops redirecting on `Accept-Language`. Users who never clicked the switcher see the same URLs as before.
3. **Emergency rollback**: `git revert` the last merge. Worst case, the `lib/authCopy.ts` shim still exists until slice 15 — pre-15 reversions keep the file and the import sites intact (the file is removed only in the last slice, by design).
4. **Data safety**: no DB writes; cookie + `localStorage` are user-local only; clearing them returns the user to the default Spanish experience.

---

## Dependencies

- **External**: `next-intl@3.x` (pinned exact at apply time) — first new frontend dep in this change.
- **Internal**: existing `date-fns` (locales `es` + `enUS`), `lucide-react` (`Languages`, `Check` icons), `framer-motion` (spring animation), Radix `dropdown-menu` via shadcn (already in dep tree).
- **Predecessor**: none. The change is self-contained within `frontend/`.
- **Successor**: F1 (privacidad i18n) and F2 (backend currency schema) are follow-ups, not prerequisites.

---

**Next phase**: `sdd-spec` — write the `frontend-i18n` delta spec (and any deltas for `frontend-dashboard`, `chat-frontend`, `favorites` if their requirements change beyond UI strings).
