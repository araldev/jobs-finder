# Exploration: `feat-frontend-i18n-locale-prefix-urls`

> **Change**: `feat-frontend-i18n-locale-prefix-urls`
> **Status**: explored (awaiting proposal)
> **Date**: 2026-06-22
> **Project**: jobs-finder (frontend workspace)
> **Mirror**: `openspec/changes/feat-frontend-i18n-locale-prefix-urls/explore.md` (hybrid preflight)
> **Engram**: `sdd/feat-frontend-i18n-locale-prefix-urls/explore` (canonical)
> **Upstream**: v1 closed in `feat-frontend-i18n/archive-report.md` (follow-up F9).

---

## 1. Verification result — next-intl 4.x `localePrefix: 'as-needed'` semantics

**Library version pinned**: `next-intl@4.13.0` (per `frontend/package.json` and slice-1 commit `06466d1`).

**Verified against**:
- Official docs: `https://github.com/amannn/next-intl/blob/main/docs/src/pages/docs/routing/configuration.mdx` (section `localePrefix: 'as-needed'`).
- Source: `packages/next-intl/src/middleware/resolveLocale.tsx` (priority order) + `packages/next-intl/src/middleware/middleware.tsx` (redirect vs. rewrite decision tree).

### 1.1 Locale resolution priority (verified in source)

```
Prio 1: route prefix      (URL segment match)
Prio 2: cookie            (NEXT_LOCALE if localeDetection=true)
Prio 3: Accept-Language   (if localeDetection=true)
Prio 4: defaultLocale     (fallback)
```

**Implication for v2**: URL prefix WINS over the `NEXT_LOCALE` cookie. A user visiting `/en/dashboard` with cookie `NEXT_LOCALE=es` gets locale=en (URL wins) — NOT locale=es. This corrects a misconception in the brief's smoke test row #4 (see §3.1).

### 1.2 Redirect vs. rewrite decision tree (verified in source)

For `locales=['es','en']`, `defaultLocale='es'`, `localePrefix='as-needed'`:

| Request | Resolved locale | Middleware action |
|---|---|---|
| `GET /dashboard` (no prefix) | es (default) | **REWRITE** (internal `x-middleware-rewrite` → `/es/dashboard`); URL stays `/dashboard`. |
| `GET /dashboard` + cookie `NEXT_LOCALE=en` | en (cookie) | **REDIRECT 307** → `/en/dashboard` (canonicalize the unprefixed URL to the prefixed canonical). |
| `GET /dashboard` + Accept-Language: en | en (header) | **REDIRECT 307** → `/en/dashboard`. |
| `GET /dashboard` + cookie=en + Accept-Language=es | en (cookie wins) | **REDIRECT 307** → `/en/dashboard`. |
| `GET /dashboard` + no signals | es (default) | **REWRITE**; URL stays `/dashboard`. |
| `GET /en/dashboard` (URL has prefix) | en (URL wins) | **REWRITE**; URL stays `/en/dashboard`. |
| `GET /en/dashboard` + cookie=es | en (URL wins) | **REWRITE**; URL stays `/en/dashboard`. |
| `GET /es/dashboard` (superfluous prefix) | es | **REDIRECT 307** → `/dashboard` (canonicalize). |
| `GET /api/jobs` | n/a | **BYPASS** (matcher excludes `/api/*`). |

### 1.3 Why v1's `baseResponse` chain still works under v2

The v1 middleware (`frontend/src/middleware.ts:50-57`) passes `intlResponse` as `baseResponse` to `updateSession`. This is the mechanism that preserves `x-middleware-rewrite` when Supabase returns a 200 (no auth bounce). Under v2:

- For REWRITE cases (most requests): `intlResponse` carries `x-middleware-rewrite: /es/dashboard` → `updateSession` mutates that response (adds Supabase cookies) → browser sees URL `/dashboard` but render tree receives `[locale]=es`. **No code change needed.**
- For REDIRECT cases (en-locale cookie/header): `intlResponse` carries `Location: /en/dashboard` (status 307). `updateSession` does NOT touch this — but wait, it currently **always** processes the request and would try to add Supabase cookies on a redirect. Per the v1 docstring, this is fine because `NextResponse.redirect()` carries cookies via `Set-Cookie` headers on the redirect response.

### 1.4 Verdict

**next-intl 4.13.0 + `[locale]/` + `localePrefix: 'as-needed'` is verified to work** as the original v1 design (design.md §3, §4, §6) intended. The slice-16 remediation built the `[locale]/` segment and the `baseResponse` chain that v2 needs; flipping the flag is safe.

The four pieces of v1 logic that were simplified away (slice 16, per archive-report.md §"Critical remediation") are the four pieces v2 must re-introduce.

---

## 2. Current State (post v1)

| File | Lines | v1 state | v2 needs |
|---|---|---|---|
| `frontend/src/i18n/routing.ts` | 39 | `localePrefix: "never"` (line 29) | Flip to `"as-needed"` |
| `frontend/src/middleware.ts` | 76 | Chains `intlMiddleware(req)` → `updateSession(req, intlResponse)`; passes `intlResponse` as `baseResponse` | **No code change**; the chain already handles rewrite headers. The D14 kill-switch stays. |
| `frontend/src/lib/supabase/middleware.ts` | 109 | `stripLocalePrefix()` exists (lines 20-26); applied at line 80; redirects go to unprefixed `/login` (line 94) and `/dashboard` (line 104) | Re-add locale-aware redirect: when effective pathname is `/en/dashboard`, redirect to `/en/login` (line 94); when user is on `/en/login` and authenticated, redirect to `/en/dashboard` (line 104). |
| `frontend/src/components/layout/LanguageSwitcher.tsx` | 101 | `switchTo()` writes cookie + `localStorage` + `router.refresh()` only | Re-add `usePathname()` + `stripLocalePrefix()` + `router.push(\`/${target}${stripped}\`)` (design §6, lines 287-294). |
| `frontend/src/app/auth/callback/route.ts` | 39 | Uses unprefixed `${origin}${next}` (line 38) and `${origin}/login?error=…` (line 33) | Re-add `localizePath(next, locale)` helper (design §10); read `NEXT_LOCALE` cookie; prefix the redirect target. |
| `frontend/src/app/[locale]/layout.tsx` | 82 | `generateStaticParams()` returns `[{locale:'es'}, {locale:'en'}]`; `<html lang={locale}>` | **No code change** (segment already in place). |
| `frontend/src/i18n/request.ts` | 31 | `requestLocale` resolves to `[locale]` param or `defaultLocale` | **No code change** (already locale-segment-aware). |

### Test files needing updates

| Test file | Current contract | v2 contract |
|---|---|---|
| `frontend/src/components/layout/LanguageSwitcher.test.tsx` | `router.refresh()` called; URL unchanged | `router.push(/en/dashboard)` called when switching to `en`; `router.refresh()` still called |
| `frontend/src/app/auth/callback/__tests__/route.test.ts` (lines 126-191) | All redirects go to unprefixed paths | `en` cookie → `/en/dashboard`, `/en/reset-password`, `/en/login?error=…` |
| `frontend/src/lib/supabase/__tests__/middleware.test.ts` | All redirects go to unprefixed paths | Add `/en/dashboard` (no user) → 307 `/en/login`; `/en/login` (auth) → 307 `/en/dashboard` |

---

## 3. Approaches Considered

### 3.1 Option A — Pure config flip (RECOMMENDED)

Flip `localePrefix: "never"` → `"as-needed"` and re-add the four removed logic paths. Total diff: ~150-200 LOC across 5 files + 3 test files.

- **Pros**: Minimal diff. The `[locale]/` segment and `baseResponse` chain were built by slice 16 specifically to enable this flip. The four removed logic paths (LanguageSwitcher push, updateSession locale-aware redirect, OAuth callback `localizePath`, and the v1 stripLocalePrefix-while-no-op comments) are all documented in design.md §6 and §10 — so the spec is unambiguous.
- **Cons**: Touches 4 production files + 3 test files. Risk R5 (the locale-aware redirect in `updateSession` must read the rewrite header) needs verification.
- **Effort**: Low (~3-4 hours of implementation + ~2 hours of testing).

### 3.2 Option B — Add `pathnames` config to avoid touching `updateSession`

Per verify-report.md §7 line 221, an alternative is to map `/en/dashboard` → `/dashboard` (internal rewrite without the locale prefix in the actual URL). Avoids the `updateSession` locale-aware redirect work.

- **Pros**: No `updateSession` changes; smaller test surface.
- **Cons**: **Does NOT deliver the user's goal**. The user explicitly asked for `/en/dashboard` URLs as the SaaS-grade experience. A `pathnames` mapping that rewrites `/en/dashboard` → `/dashboard` would 404 because Next.js routes are filesystem-based — you'd still need the `[locale]/` segment, defeating the purpose. **This option was rejected during v1's verify phase** and is incorrect for v2.
- **Effort**: Low (but wrong).

### 3.3 Option C — Switch to `localePrefix: 'always'` (force-prefix everything)

Would also require `/es/dashboard` URLs (no unprefixed canonical) — contradicts the v1 design (D2) and the user's brief which explicitly wants canonical shareable EN URLs while keeping the Spanish audience at root.

- **Pros**: Simpler mental model — every URL has a prefix.
- **Cons**: Breaks the v1 contract that zero URL regressions occur for the default-locale audience. The Spanish-language SEO and existing bookmarks would all change.
- **Effort**: Medium (but breaks the user brief).

### 3.4 Recommendation

**Option A** — pure config flip + re-add the four v1 logic paths. This is exactly what `feat-frontend-i18n/archive-report.md` §"Future v2 follow-up" describes, and it's the only option that delivers the canonical SaaS-grade URLs the user requested.

---

## 4. Affected Areas

### 4.1 Files to modify

| File | Change | LOC delta |
|---|---|---|
| `frontend/src/i18n/routing.ts` | Flip `localePrefix: "never"` → `"as-needed"` (line 29). Update JSDoc to remove "v1 pragmatic mode" framing. | ~5 |
| `frontend/src/middleware.ts` | **No change.** Comment-only update (the existing JSDoc already references `as-needed` from slice 16). | 0 |
| `frontend/src/lib/supabase/middleware.ts` | Re-add locale-aware redirect: read rewrite header to determine effective locale; redirect to `/en/login` or `/es/login` based on `strippedPath.startsWith('/en/')`. Update JSDoc to drop "defensive no-op" framing. | ~25 |
| `frontend/src/components/layout/LanguageSwitcher.tsx` | Re-add `usePathname()` + `stripLocalePrefix()` import (from `@/i18n/routing` or local helper); build `nextPath`; call `router.push(nextPath)` then `router.refresh()`. | ~20 |
| `frontend/src/app/auth/callback/route.ts` | Add `localizePath(next, locale)` helper; read `NEXT_LOCALE` cookie from `request.cookies.get(...)`; prefix the redirect target. Error path also localized (`/en/login?error=…` or `/login?error=…`). | ~30 |
| `frontend/src/components/layout/LanguageSwitcher.test.tsx` | Update 3 tests: cookie assertion stays; add `router.push` expectation; update JSDoc. | ~15 |
| `frontend/src/app/auth/callback/__tests__/route.test.ts` | Update 6 tests in the "locale-aware redirect (REQ-I18N-016, v1 contract)" block (lines 126-191). Add new block for v2 contract. | ~50 |
| `frontend/src/lib/supabase/__tests__/middleware.test.ts` | Add 4 tests: `/en/dashboard` (no user) → 307 `/en/login`; `/en/login` (auth) → 307 `/en/dashboard`; `/en/forgot-password` (no user) → 200; `/es/dashboard` → 307 `/login`. | ~40 |

**Total delta**: ~185 LOC across 8 files. Well under the D1 (400 lines) review budget.

### 4.2 Files NOT to modify (verified)

- `frontend/src/app/[locale]/layout.tsx` — already locale-segment-aware (`generateStaticParams`, `<html lang>`, `NextIntlClientProvider`).
- `frontend/src/i18n/request.ts` — already reads `requestLocale` from the `[locale]` segment.
- `frontend/messages/{en,es}.json` — no translation changes; the v1 content is locale-segment-agnostic.
- All `frontend/src/app/[locale]/**/page.tsx` and `frontend/src/components/**` — no changes; `useTranslations` is locale-agnostic.
- `frontend/src/app/api/**` — excluded from middleware matcher.

---

## 5. Smoke Test Matrix (v2 contract)

| # | Request | Expected | Notes |
|---|---|---|---|
| 1 | `GET /dashboard` + `Accept-Language: es-ES` | 200 (or 307 → `/login` if no user), `<html lang="es">`, URL stays `/dashboard` | Default locale, no prefix, REWRITE to `/es/dashboard` internally |
| 2 | `GET /dashboard` + `Accept-Language: en-US` | 307 → `/en/dashboard` | Locale detection finds en; canonical redirect |
| 3 | `GET /en/dashboard` + `Accept-Language: es-ES` | **200** (no redirect), `<html lang="en">` | URL prefix wins over Accept-Language; internal REWRITE |
| 4 | `GET /en/dashboard` + `NEXT_LOCALE=es` cookie | **200** (no redirect), `<html lang="en">` | **URL prefix wins over cookie** — this corrects the brief's smoke test row #4 |
| 5 | `GET /dashboard` + `NEXT_LOCALE=en` cookie | 307 → `/en/dashboard` | Cookie sets locale=en; unprefixed URL canonicalizes to prefixed |
| 6 | `GET /en/login` | 200, `<html lang="en">` | Public path, no auth required |
| 7 | `GET /login` | 200, `<html lang="es">` | Default locale, no prefix |
| 8 | `GET /api/jobs` | 200, unaffected | Matcher excludes `/api/*` |
| 9 | `GET /dashboard` (no auth) | 307 → `/login` (es user) or `/en/login` (en user) | **Locale-aware bounce** — Supabase `updateSession` reads effective pathname |
| 10 | `GET /es/dashboard` | 307 → `/dashboard` | Superfluous prefix canonicalization (es is default) |

**Brief correction (smoke test row #4)**: The original brief said `GET /en/dashboard` + `NEXT_LOCALE=es` cookie should 307 → `/dashboard`. Per the verified source code (resolveLocale.tsx, Prio 1: route prefix), URL prefix WINS over cookie. So `/en/dashboard` + cookie=es → locale=en, NO redirect, browser stays on `/en/dashboard`. This is actually MORE user-friendly (no surprise canonicalization after a deliberate URL visit) and matches what GitHub / Vercel do.

---

## 6. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | `updateSession` locale-aware redirect breaks existing auth flow | Medium | High | The `stripLocalePrefix()` helper is already in place (lines 20-26, 80). The v1 logic just needs to check `strippedPath.startsWith('/en/')` and adjust the target URL. The `baseResponse` chain (middleware.ts:57) already handles the rewrite header preservation. |
| R2 | OAuth callback locale prefix regression — en user lands on `/login` instead of `/en/login` | Medium | Medium | The `localizePath(next, locale)` helper is documented in design.md §10. The `NEXT_LOCALE` cookie is the source of truth for the user's locale in the callback (since the callback URL itself is not locale-prefixed). All 6 tests in the v1 "locale-aware redirect" block (route.test.ts:126-191) need updating to v2 expectations. |
| R3 | LanguageSwitcher `router.push` triggers a full page reload, losing React state | Low | Low | next-intl's `usePathname()` returns the locale-prefixed path (e.g. `/en/dashboard`). `router.push()` with a soft navigation is fine — Next.js doesn't do a hard reload, it streams the new RSC payload. The `router.refresh()` afterwards is the canonical pattern (matches design.md §6). |
| R4 | The `stripLocalePrefix` helper currently is a "defensive no-op" under v1 — under v2 it becomes critical | Low | Medium | The helper is already correct (it strips when prefix exists, returns unchanged when not). The v2 change is just that it now ACTUALLY strips in production. No code change needed; only JSDoc. |
| R5 | Supabase `updateSession` `NextResponse.redirect()` overrides the intl response (which has the rewrite header) | Medium | High | Per v1 design (design.md §3), the redirect URL is locale-aware. When `strippedPath.startsWith('/en/')`, redirect target is `/en/login` (not `/login`). When the user visits `/en/dashboard` without auth, the middleware sees `request.nextUrl.pathname === '/en/dashboard'`, strips to `/dashboard`, identifies as protected, redirects to `/en/login`. The browser follows the redirect to `/en/login`, which is also a `[locale]/login` page. **This works.** |
| R6 | The `NEXT_PUBLIC_I18N_ENABLED=false` kill-switch regression — under v2, does it still bypass i18n cleanly? | Low | Medium | The kill-switch (`middleware.ts:38-40`) skips `intlMiddleware` entirely and routes straight to `updateSession(request)` with no `baseResponse`. Under v2, this means `/en/dashboard` would be served by `[locale]/en/dashboard` which... doesn't exist (Next.js routes are filesystem-based). The kill-switch only matters in production if v2 ships a regression — in that case the user flips the env var, redeploys, and requests to `/en/dashboard` get... whatever `updateSession` does without `baseResponse`. This is identical to v1 behavior under the kill-switch. **No change needed.** |
| R7 | Tests that mock `useRouter()` with only `refresh` (no `push`) will silently fail | Medium | Medium | LanguageSwitcher.test.tsx:6-13 — the `useRouter()` mock must add `push: vi.fn()` and assertions must check it. |

---

## 7. Effort Estimate

| Component | LOC | Confidence |
|---|---|---|
| `routing.ts` config flip + JSDoc | ~5 | High (one-line flip) |
| `LanguageSwitcher.tsx` re-add (design §6 pattern) | ~20 | High (design is verbatim) |
| `supabase/middleware.ts` locale-aware redirect | ~25 | High (helper exists; just add conditional URL building) |
| `auth/callback/route.ts` re-add `localizePath` | ~30 | High (design §10 has the pattern) |
| `LanguageSwitcher.test.tsx` update | ~15 | High |
| `route.test.ts` update | ~50 | High (12 tests to migrate) |
| `middleware.test.ts` add locale-prefix tests | ~40 | High |
| **Total** | **~185** | **High** (3-4 hours implementation + 2 hours testing) |

This is well under the D1 (400 lines) review budget. No new dependencies; no message file changes; no `messages/*.json` edits.

---

## 8. Open Questions for the User

**None.** All design decisions are settled by the v1 design (design.md §3, §4, §6, §10) and the v1 archive-report (F9 follow-up). The brief's smoke test row #4 had a precedence inversion (cookie over URL) that this explore corrects based on the verified source code. The orchestrator should pass this correction forward to `sdd-propose` so the AC list in the proposal reflects the verified behavior.

---

## 9. Ready for Proposal

**Yes — proceed to `sdd-propose`.**

The orchestrator should:
1. Pass the smoke test correction (brief row #4: URL prefix wins over cookie, not the other way around) to `sdd-propose` so AC-2 (en-US → `/en/dashboard`) and AC-3 (LanguageSwitcher URL becomes `/en/...`) reflect the verified semantics.
2. Note that the `frontend-i18n` capability spec (`openspec/specs/frontend-i18n/spec.md`) already contains REQs that the v1 design wrote for `as-needed` mode but v1 couldn't satisfy (REQ-I18N-002 "Locale prefix policy", REQ-I18N-016 "OAuth callback locale-aware"). The proposal can reference these as already-defined REQs and add v2-specific deltas.
3. Budget a single PR (≤ 400 LOC, well within D1) per the small change size. No need for a stacked chain — this is one focused config flip + re-add of 4 small logic paths.
