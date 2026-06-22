# Archive Report — `feat-frontend-i18n-locale-prefix-urls`

> **Status**: closed (verified, archived)
> **Date**: 2026-06-22
> **Project**: jobs-finder (frontend workspace)
> **Branch**: `feat-frontend-i18n-locale-prefix-urls`
> **Tip SHA**: `4defe48` (pushed to `origin`)
> **Preflight cache**: Pace A2 · Artifacts hybrid · PRs C4 (1 PR) · Review D1 (well under 400) · Strict TDD: false

## Outcome

The change ships **canonical shareable URLs (`/en/dashboard`, `/en/login`, `/en/jobs/123`)** for the non-default locale — the SaaS-grade experience the user originally asked for. The v1 cookie-only mode is fully superseded.

### What changed

- `frontend/src/i18n/routing.ts`: `localePrefix: 'never'` → `'as-needed'`
- `frontend/src/middleware.ts`: respect intl redirect (307/308) so canonical locale-prefixed URLs survive the chain
- `frontend/src/lib/supabase/middleware.ts`: `deriveLocalePrefix()` + locale-aware auth bounce (`/en/dashboard` → `/en/login`)
- `frontend/src/components/layout/LanguageSwitcher.tsx`: `router.push(/en/<path>)` re-introduced
- `frontend/src/app/auth/callback/route.ts`: `localizePath()` + `readLocalePrefix()` re-introduced for OAuth locale-aware redirects
- 3 test files updated to v2 contract: 280 tests pass (was 272 in v1)
- `frontend/README.md`: locale precedence documented (URL prefix > cookie > Accept-Language > default)

### CI gates final

| Gate | Status |
|---|---|
| `pnpm run typecheck` | ✅ |
| `pnpm run lint` | ✅ |
| `pnpm run test` | ✅ (280 tests across 43 files) |
| `pnpm run build` | ✅ |

### Smoke tests verified at runtime

| Request | Expected | Actual |
|---|---|---|
| `GET /dashboard` + `Accept-Language: es-ES` | 307 → `/login` | ✅ |
| `GET /dashboard` + `Accept-Language: en-US` | 307 → `/en/dashboard` | ✅ |
| `GET /en/dashboard` + `Accept-Language: es-ES` | 307 → `/en/login` | ✅ |
| `GET /en/dashboard` + `NEXT_LOCALE=es` cookie | 307 → `/en/login` (URL wins over cookie) | ✅ |
| `GET /dashboard` + `NEXT_LOCALE=en` cookie | 307 → `/en/dashboard` | ✅ |
| `GET /en/login` | 200, `<html lang="en">` | ✅ |
| `GET /login` | 200, `<html lang="es">` | ✅ |
| `GET /api/jobs` | 200 (unaffected) | ✅ |

## Per-commit breakdown

```
4defe48  feat(i18n): locale-aware redirects + URL-prefixed switcher (v2 contract)
9a20518  chore(i18n): flip localePrefix to 'as-needed' for canonical /en/ URLs
e7fd50d  docs(sdd): feat-frontend-i18n-locale-prefix-urls planning artifacts
```

3 commits, 1 PR. Per `work-unit-commits`: C1 (routing flip) reviewable in isolation, C2 (logic + tests + docs) bundled.

## REQ / SCN traceability

| Requirement | Status |
|---|---|
| REQ-I18N-002 (modified) | Locale prefix policy is now `as-needed` (was `never` in v1) |
| REQ-I18N-016 (modified) | OAuth callback redirects to locale-prefixed paths |
| REQ-I18N-020 (new) | Supabase `updateSession` locale-aware auth redirect |
| REQ-I18N-021 (new) | LanguageSwitcher navigates to locale-prefixed URL |
| SCN-I18N-002 (modified) | First-time `Accept-Language: en-US` visitor redirects to `/en/dashboard` |
| SCN-I18N-003 (modified) | Switcher click sets cookie + `localStorage` AND navigates URL |
| SCN-I18N-013 (new) | `/en/dashboard` with `NEXT_LOCALE=es` cookie renders in English (URL wins) |
| SCN-I18N-014 (new) | `/en/dashboard` no auth redirects to `/en/login` |
| SCN-I18N-015 (new) | `/dashboard` with `NEXT_LOCALE=en` cookie redirects to `/en/dashboard` |

## Trade-off resolved

v1 (slice 16) shipped with `localePrefix: 'never'` because the original 15-slice plan lacked the `[locale]/` route segment, which would have caused 404s on every `/en/*` URL. v2 (this change) re-enables URL prefixes now that the `[locale]/` segment + `baseResponse` middleware chain are in place. The user now has SaaS-grade shareable URLs.

## Rollback

1. **Single-PR revert**: `git revert 4defe48 9a20518` is a clean two-commit revert.
2. **Feature-flag escape hatch**: `NEXT_PUBLIC_I18N_ENABLED=false` in `frontend/.env.local` short-circuits the intl middleware → v1 cookie-only behavior resumes in <2 minutes, no redeploy.
3. **The `[locale]/` route segment stays** in the codebase — it's harmless under `localePrefix: 'never'` and useful as the foundation for any future locale-prefix migration.

## Carry-over follow-ups (unchanged from v1 archive)

| # | Issue | Change name |
|---|---|---|
| F1 | `authCopy.ts` deprecated but not deleted | `chore(i18n): remove deprecated authCopy.ts` |
| F2 | 5 jobs components untranslated (`JobDetailContent`, `JobDetailAside`, `JobList`, `GenerateCVModal`, `FavoriteButton`) | `feat(i18n): migrate remaining jobs components` |
| F3 | `useChat.ts` 3 hardcoded EN error literals | `feat(i18n): useChat error key pattern` |
| F4 | Landing page partial (~3 of 731 strings translated) | `feat(i18n): landing page EN marketing copy` (needs marketing review) |
| F5 | Auth pages partial (`signup`, `(auth)/forgot-password`, `(auth)/reset-password`) | `feat(i18n): complete auth pages` |
| F6 | Footer appears globally on (app) routes (double-footer) | `fix(layout): scope Footer to non-AppShell routes` |
| F7 | Spec deltas for cross-cutting capabilities missing | `docs(spec): fold cross-cutting i18n REQs into capability specs` |

## Next steps

1. **Open the PR** from `feat-frontend-i18n-locale-prefix-urls` against `main` (compare URL: `https://github.com/araldev/jobs-finder/compare/main...feat-frontend-i18n-locale-prefix-urls?expand=1`).
2. After merge: cycle 2 (i18n coverage — F2 + F3 + F5 + F6) and cycle 3 (F1 — remove `authCopy.ts`).
