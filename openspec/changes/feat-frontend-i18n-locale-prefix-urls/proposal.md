# Proposal: `feat-frontend-i18n-locale-prefix-urls`

> **Change**: `feat-frontend-i18n-locale-prefix-urls` • **Phase**: SDD propose (post-explore, pre-spec)
> **Status**: proposed (awaiting spec) • **Date**: 2026-06-22
> **Project**: jobs-finder (frontend workspace) • **Branch base**: `main`
> **Preflight**: Pace A2 (Automatic) · Artifacts hybrid (engram + openspec) · PRs C4 (auto-forecast) · Review D1 (400 lines) · Strict TDD: false
> **Mirror**: `openspec/changes/feat-frontend-i18n-locale-prefix-urls/proposal.md`
> **Engram**: `sdd/feat-frontend-i18n-locale-prefix-urls/proposal` (canonical)
> **Source**: v1 follow-up F9 (`openspec/changes/feat-frontend-i18n/archive-report.md`)

## Intent

Re-enable canonical shareable URLs (`/en/dashboard`, `/en/jobs/123`) by flipping `frontend/src/i18n/routing.ts` from `localePrefix: 'never'` → `'as-needed'`. v1 shipped without URL prefixes because the original 15-slice plan lacked the `[locale]/` route segment, which would have produced a 404 on every `/en/*` URL. Slice 16 fixed that by adding the segment + `baseResponse` middleware chain; v2 finishes the loop the user originally asked for, a "professional SaaS" experience with bookmark-able, share-with-colleagues, marketing-link-friendly EN URLs, while keeping the ES audience at root URLs with zero bookmark regression. The user is a SaaS professional who needs canonical URLs for share-with-colleagues, marketing links, and SEO. Cookie-only locale (v1) is invisible in URLs and unsuitable for SaaS-grade UX.

## Scope

### In Scope (8 files, ~185 LOC)

- `frontend/src/i18n/routing.ts` — flip flag (line 29) + JSDoc refresh.
- `frontend/src/components/layout/LanguageSwitcher.tsx` — re-add `usePathname()` + `stripLocalePrefix()` + `router.push(\`/${target}${stripped}\`)`.
- `frontend/src/lib/supabase/middleware.ts` — locale-aware redirect (`/en/dashboard` no-auth → `/en/login`; `/en/login` auth → `/en/dashboard`).
- `frontend/src/app/auth/callback/route.ts` — `localizePath(next, locale)` helper; read `NEXT_LOCALE` cookie; prefix `?next=` redirect target.
- `frontend/src/components/layout/LanguageSwitcher.test.tsx` — add `router.push` expectations.
- `frontend/src/app/auth/callback/__tests__/route.test.ts` — update locale-aware redirect block to v2 contract.
- `frontend/src/lib/supabase/__tests__/middleware.test.ts` — add 4 locale-prefix tests.

### Out of Scope

- No message changes (`messages/{en,es}.json` untouched).
- No new translations, no new components, no backend changes.
- No `[locale]/layout.tsx` changes (segment already in place).
- No `frontend/src/middleware.ts` changes (`baseResponse` chain already correct).
- No new dependencies (`next-intl@4.13.0` already installed).
- All v1 follow-ups F1–F7 (authCopy deletion, jobs components, useChat errors, landing EN, auth pages, footer scope, spec deltas) remain deferred.

## Capabilities

### Modified Capabilities

- `frontend-i18n`: REQ-I18N-002 ("Locale prefix policy"), REQ-I18N-016 ("OAuth callback locale-correct") become runtime-enforceable under v2. v1 satisfied them via cookie-only pathway; v2 satisfies by URL prefix (canonical). Delta spec narrows the gap from design-intent to runtime-evidence.

### New Capabilities

None.

## Approach

- **Routing config flip**: `localePrefix: 'never'` → `'as-needed'` in `i18n/routing.ts` line 29. JSDoc refreshes from "v1 pragmatic mode" → "canonical URLs per REQ-I18N-002".
- **LanguageSwitcher re-add**: import `usePathname`; call `stripLocalePrefix(pathname)`; build `nextPath = target === defaultLocale ? stripped : \`/${target}${stripped}\``; call `router.push(nextPath)` then `router.refresh()` (design.md §6, lines 287–294).
- **Supabase middleware re-add**: detect locale via `strippedPath.startsWith('/en/')`; build locale-aware redirect target. `stripLocalePrefix()` already at lines 20–26 — v2 makes it production-critical.
- **OAuth callback re-add**: `localizePath(next, locale)` helper. `locale` reads from `request.cookies.get('NEXT_LOCALE')?.value` (fallback: `Accept-Language` parsing → `'es'`). The `?next=` query is preserved as-is; only the prefix is added.
- **Middleware chain**: no change. `frontend/src/middleware.ts:57` already passes `intlResponse` as `baseResponse` to `updateSession(request, intlResponse)`; the `x-middleware-rewrite` header survives both REWRITE and REDIRECT cases.
- **Test updates**: 3 files migrate from v1 cookie-only contract to v2 URL-prefix contract.
- **Smoke tests**: curl matrix per explore §5; manual run only (not in CI per AGENTS.md rule 1).

## Acceptance Criteria

| # | Test | Expected |
|---|---|---|
| AC-1 | `GET /dashboard` + `Accept-Language: es-ES` | 200, `<html lang="es">`, URL stays `/dashboard` |
| AC-2 | `GET /dashboard` + `Accept-Language: en-US` | 307 → `/en/dashboard` |
| AC-3 | `GET /en/dashboard` + `Accept-Language: es-ES` | 200, `<html lang="en">` (URL wins over Accept-Language) |
| AC-4 | `GET /en/dashboard` + `NEXT_LOCALE=es` cookie | 200, `<html lang="en">` (URL wins over cookie) |
| AC-5 | `GET /dashboard` + `NEXT_LOCALE=en` cookie | 307 → `/en/dashboard` |
| AC-6 | `GET /en/login` | 200, `<html lang="en">` |
| AC-7 | `GET /login` | 200, `<html lang="es">` (default) |
| AC-8 | `GET /api/jobs` | 200, unaffected (matcher excludes `/api/*`) |
| AC-9 | `GET /en/dashboard` (no auth) | 307 → `/en/login` (locale-aware bounce) |
| AC-10 | All 4 CI gates green | typecheck, lint, test, build pass; 3 test files pass v2 contract |

**Brief correction (AC-4)**: Verified in `next-intl/src/middleware/resolveLocale.tsx` Prio 1 — URL prefix WINS over cookie. `/en/dashboard` + cookie=es → locale=en, no redirect, browser stays on `/en/dashboard`. Matches GitHub/Vercel behavior.

## Risks

| # | Risk | Likelihood | Mitigation |
|---|---|---|---|
| R1 | `updateSession` locale-aware redirect breaks auth | Med | `stripLocalePrefix()` already in place. Add `startsWith('/en/')` branch; build locale-aware URL. |
| R2 | OAuth callback regression — `en` user lands on `/login` | Med | `localizePath(next, locale)` reads `NEXT_LOCALE` cookie. All 6 v1 locale-aware tests migrate. |
| R3 | LanguageSwitcher `router.push` triggers hard reload, loses React state | Low | Next.js soft navigation; no hard reload. `router.refresh()` is canonical RSC re-render pattern. |
| R4 | `stripLocalePrefix` "defensive no-op" → critical | Low | Helper already correct (strips when prefix exists, returns unchanged when not). Only JSDoc changes. |
| R5 | Supabase `NextResponse.redirect()` overrides intl rewrite header | Med | `updateSession` mutates `baseResponse` (carries rewrite). Redirect cases build locale-aware URLs so bounce lands correctly. |
| R6 | Kill-switch (`NEXT_PUBLIC_I18N_ENABLED=false`) regression | Low | Kill-switch bypasses intl; identical to v1 behavior. No change needed. |
| R7 | `useRouter()` mock in test missing `push` | Med | Mock must add `push: vi.fn()`; assertions check it. |

## Out-of-Scope Follow-Ups (carry-over from v1)

| # | Issue | Change name | Effort |
|---|---|---|---|
| F1 | `authCopy.ts` deprecated but not deleted | `chore(i18n): remove deprecated authCopy.ts` | 1–2h |
| F2 | 5 jobs components untranslated (`JobDetailContent`, `JobDetailAside`, `JobList`, `GenerateCVModal`, `FavoriteButton`) | `feat(i18n): migrate remaining jobs components` | 1–2h |
| F3 | `useChat.ts` 3 hardcoded EN error literals | `feat(i18n): useChat error key pattern` | 30min |
| F4 | Landing page partial (~3 of 731 strings translated) | `feat(i18n): landing page EN marketing copy` (needs marketing review) | 2h |
| F5 | Auth pages partial (`signup`, `(auth)/forgot-password`, `(auth)/reset-password`) | `feat(i18n): complete auth pages` | 1h |
| F6 | Footer appears globally on (app) routes (double-footer) | `fix(layout): scope Footer to non-AppShell routes` | 15min |
| F7 | Spec deltas for cross-cutting capabilities missing | `docs(spec): fold cross-cutting i18n REQs into capability specs` | 30min |

## PR Plan

**1 PR**, ~185 LOC across 8 files — well under the 400-line D1 review budget. Branch `feat-frontend-i18n-locale-prefix-urls` → `main`. Per `work-unit-commits`: 1–2 commits (config flip first, then logic re-add). Pre-commit gates: `cd frontend && pnpm run typecheck && pnpm run lint && pnpm run test && pnpm run build`.

## Dependencies

- `next-intl@4.13.0` (already installed; no dep change).
- v1's `[locale]/` route segment (slice 16, in `main`).
- v1's `baseResponse` middleware chain (`frontend/src/middleware.ts:50–57`).

## Rollback Plan

1. **Code**: `git revert <merge-sha>` — single PR, single revert, clean.
2. **Feature-flag escape hatch**: `NEXT_PUBLIC_I18N_ENABLED=false` in `frontend/.env.local` short-circuits intl middleware → v1 cookie-only behavior resumes in <2 minutes, no redeploy.
3. **Cookie wipe**: deleting `NEXT_LOCALE` cookie + clearing `localStorage` falls back to `Accept-Language` → root URLs.
4. **Safe rollback path**: v1's state (URLs without prefix, cookie-only locale) is recoverable in <2 minutes via the kill-switch without redeploying.

## Open Questions

**None.** All design decisions settled by v1's design (design.md §3, §4, §6, §10) and v1's archive-report (F9 follow-up). The orchestrator's brief correction on AC-4 (URL prefix wins over cookie) is incorporated in the explore analysis and the AC table above.
