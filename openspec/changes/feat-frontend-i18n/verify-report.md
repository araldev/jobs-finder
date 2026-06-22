# Verification Report — `feat-frontend-i18n`

> **Change**: `feat-frontend-i18n`
> **Branch verified**: `feat-frontend-i18n/slice-15-cleanup`
> **Tip SHA**: `559a71c` (local, one commit ahead of `origin/feat-frontend-i18n/slice-15-cleanup` = `cc04af8`)
> **Date**: 2026-06-22
> **Status**: **FAIL** — the i18n infrastructure is broken at runtime for the non-default locale; the switcher sets a cookie but the URL never reflects the locale because `[locale]/` route segment is missing and the middleware chain discards the intl redirect
> **Mode**: Standard (Strict TDD = false)
> **Preflight cache**: Pace A2 · Artifacts B1 hybrid · PRs C4 · Review budget D1 (400 lines) · Chain `stacked-to-main`

---

## 1. CI Gate Results

| Gate | Result | Notes |
|---|---|---|
| `pnpm run typecheck` | ✅ PASS | `tsc --noEmit` exits 0 |
| `pnpm run lint` | ✅ PASS | "No ESLint warnings or errors" (next-lint deprecation warning is not a failure) |
| `pnpm run test` | ✅ PASS | **43 test files · 267 tests passed (0 failed)** — but stdout is polluted with `IntlError: INVALID_KEY Jobs.errors` and `MISSING_MESSAGE Footer` warnings (see §5) |
| `pnpm run build` | ✅ PASS | Compiled in 6.9s, 19/19 static pages, 102 kB middleware bundle, all routes `ƒ (Dynamic)` |

**4/4 green at the command level.** All test counts match the apply-phase report (267 tests). However, runtime smoke tests (§3) revealed that the green tests do not cover the integration between intl middleware and the rest of the app — they mock `getLocale`/`getMessages` so the broken routing never surfaces in CI.

---

## 2. Per-REQ Coverage (28 REQs)

### `frontend-i18n` (19 REQs from `openspec/specs/frontend-i18n/spec.md`)

| REQ | Status | Evidence (1 line) |
|---|---|---|
| REQ-I18N-001 (Locale list and default) | ✅ COMPLIANT | `src/i18n/routing.ts:18-23` — `locales: ["es","en"]`, `defaultLocale: "es"`, type `Locale` exported |
| REQ-I18N-002 (Locale prefix policy) | ❌ FAIL | `localePrefix: "as-needed"` set in `routing.ts:21`, but `/en/dashboard`, `/en/login`, `/en/signup`, `/en/jobs/123` all 404 because the route structure has no `[locale]/` segment. SCN-I18N-002 fails at runtime. |
| REQ-I18N-003 (Middleware chain order) | ⚠️ PARTIAL | `src/middleware.ts:34-51` chains `intlMiddleware → updateSession` in the right order, but returns `supabaseResponse` (line 50) instead of `intlResponse`, so any intl 307 redirect is discarded |
| REQ-I18N-004 (Supabase publicPaths locale-prefix-aware) | ✅ COMPLIANT | `src/lib/supabase/middleware.ts:20-26` — `stripLocalePrefix()` applied at line 72; locale-aware redirect targets at lines 92-99, 110-117 |
| REQ-I18N-005 (Dynamic `<html lang>`) | ✅ COMPLIANT | `src/app/layout.tsx:44` — `<html lang={locale}>`; `getLocale()` at line 36; covered by `src/app/layout.test.tsx` (2/2 tests pass) |
| REQ-I18N-006 (NEXT_LOCALE cookie + localStorage mirror) | ✅ COMPLIANT | `src/components/layout/LanguageSwitcher.tsx:53-55` — `document.cookie = "NEXT_LOCALE=…; path=/; max-age=31536000; SameSite=Lax"` + `localStorage.setItem("NEXT_LOCALE", target)`; `router.push + router.refresh` at lines 62-63 |
| REQ-I18N-007 (Switcher placement) | ✅ COMPLIANT | `Header.tsx:107` mounts `<LanguageSwitcher />` for `(app)` routes; root `layout.tsx:50` mounts `<Footer />` which contains the footer variant |
| REQ-I18N-008 (Switcher visual contract) | ✅ COMPLIANT | `LanguageSwitcher.tsx:72-79` — `h-9 w-9` icon-only button with `lucide-react/Languages`; `aria-label`, `aria-haspopup="menu"`; native labels (Español/English) at line 106; `Check` icon for active item at line 107 |
| REQ-I18N-009 (Switcher animation) | ✅ COMPLIANT | `LanguageSwitcher.tsx:86-93` — `initial={{opacity:0, scale:0.95}}`, `transition={{type:"spring", bounce:0.1, duration:0.15}}`; reduced-motion branch strips the spring at lines 90-91 |
| REQ-I18N-010 (Switcher accessibility) | ✅ COMPLIANT | Radix `dropdown-menu` provides Tab/Enter/Arrow/Escape handling; trigger exposes `aria-haspopup="menu"`; full keyboard model asserted in `LanguageSwitcher.test.tsx:91-105` |
| REQ-I18N-011 (Switcher theme awareness) | ✅ COMPLIANT | `LanguageSwitcher.tsx:94` uses `bg-popover text-popover-foreground border-border`; no hardcoded colors |
| REQ-I18N-012 (Message file structure) | ⚠️ PARTIAL | All required namespaces present (`Common`, `Errors`, `Validation`, `Auth`, `Landing`, `Dashboard`, `Jobs`, `Search`, `Favorites`, `Settings`, `Chat`, `Footer`, `DateTime`) — but `messages/en.json:349` and `messages/es.json:349` have a structural bug: top-level key `"Jobs.errors"` (literal `.` in name) breaks next-intl 4.x's `validateMessages` (warning in every test run) |
| REQ-I18N-013 (ICU pluralization) | ✅ COMPLIANT | 9 ICU `plural` keys in en.json, 9 matching in es.json (one per Jobs/Dashboard/Search/Favorites namespace) |
| REQ-I18N-014 (Locale-aware formatters) | ⚠️ PARTIAL | `lib/formatters.ts:21-42` accepts `locale: Locale` and is fully locale-aware; but 6 caller-side violations remain: `StatsCardsRow.tsx:71,78,96,103,110,135` and `RightSidebar.tsx:44` use `.toLocaleString()` without arg; `UserCVCard.tsx:161` uses `toLocaleDateString("es-ES")` |
| REQ-I18N-015 (Accept-Language detection with cookie override) | ❌ FAIL | `Accept-Language: en-US,en;q=0.9` to `/dashboard` returns 307 to `/login` (default locale, no `/en/` prefix) with **no `NEXT_LOCALE` cookie set** — the intl middleware's redirect is discarded by the supabase chain. SCN-I18N-002 fails at runtime. |
| REQ-I18N-016 (OAuth callback lands on locale-correct dashboard) | ⚠️ UNTESTED | Cannot verify without a live Supabase + OAuth flow; the middleware chain bug suggests the locale-aware `redirectTo` will be discarded, but this requires manual E2E |
| REQ-I18N-017 (Test wrapper for NextIntlClientProvider) | ✅ COMPLIANT | `src/test-utils.tsx:37-56` — `renderWithIntl(ui, { locale: 'es'\|'en', messages })` wraps in `<NextIntlClientProvider>`; used by `LanguageSwitcher.test.tsx`, `Header.test.tsx` |
| REQ-I18N-018 (Cross-cutting dependency on job-domain) | ✅ COMPLIANT | Informational note in spec; no schema change; consumers go through `lib/formatters.ts` |
| REQ-I18N-019 (Privacidad page remains Spanish-only in v1) | ✅ COMPLIANT | `Footer.tsx:30` renders `t("privacyNote")` — en.json has `"Spanish only — English version coming soon"`, es.json has `"Solo en español — versión en inglés próximamente"` |

### Cross-cutting Deltas (9 REQs referenced in `tasks.md` and `frontend-i18n/spec.md:290-298` but **NOT defined in any spec file**)

| REQ | Status | Evidence |
|---|---|---|
| REQ-DASH-I18N-001..003 | ⚠️ UNDEFINED | Referenced in `tasks.md:446` as "Closes" but never written to `openspec/specs/frontend-dashboard/spec.md`; the 3 dashboard slices (7/8/9) shipped but the formal REQ IDs don't exist. This is a spec-process gap, not a code gap. |
| REQ-CHAT-I18N-001..003 | ⚠️ UNDEFINED | Referenced in `tasks.md:616`; never written to `openspec/specs/chat-frontend/spec.md`. Slice 10 shipped `useChat` partial migration (3 hardcoded English errors remain) |
| REQ-FAV-I18N-001..003 | ⚠️ UNDEFINED | Referenced in `tasks.md:555`; never written to `openspec/specs/favorites/spec.md`. Slice 9 shipped |
| `job-domain` cross-cutting note | ✅ COMPLIANT | `openspec/specs/job-domain/spec.md` (informational note can be added in sdd-archive) |

**19/19 main REQs are wired in code, but 2 of them (REQ-I18N-002 and REQ-I18N-015) FAIL at runtime. 9 cross-cutting REQs are referenced but not formally defined.**

---

## 3. Per-SCN Coverage (12 ACs from spec §"Acceptance Scenarios")

| AC | Status | Evidence |
|---|---|---|
| AC-1 / SCN-I18N-001 (es-ES → `/dashboard` no redirect) | ⚠️ PARTIAL | `curl -H "Accept-Language: es-ES" /dashboard` returns 307 to `/login` (Supabase auth, not intl) with `set-cookie: NEXT_LOCALE=es`. The page itself doesn't redirect (correct for default locale), but the test couldn't see Spanish content because the unauthenticated user is bounced. **Note**: route does not 307 to `/es/dashboard` either, which is the desired `as-needed` behavior — so this AC is technically met, but for the wrong reason. |
| AC-2 / SCN-I18N-002 (en-US → `/en/dashboard`) | ❌ FAIL | `curl -H "Accept-Language: en-US,en;q=0.9" /dashboard` returns 307 to `/login` (NOT `/en/dashboard`). The intl middleware's redirect to `/en/dashboard` is **discarded** by the supabase chain. `/en/dashboard` itself returns 307 to `/en/login` (Supabase), but `/en/login`, `/en/signup`, `/en/jobs/123` all return 404 (no `[locale]/` route segment) |
| AC-3 / SCN-I18N-003 (switcher click → cookie + localStorage + URL + re-render) | ✅ COMPLIANT | `LanguageSwitcher.test.tsx:50-78` asserts all four invariants with real `renderWithIntl` + `userEvent`; the switcher writes cookie (line 60), `localStorage` (line 61), calls `router.push` (line 62) and `router.refresh` (line 63) |
| AC-4 / SCN-I18N-004 (`<html lang>` matches locale) | ✅ COMPLIANT | `src/app/layout.tsx:44` — `<html lang={locale}>`; verified at runtime: `/` (no cookie) returns `<html lang="es">` |
| AC-5 / SCN-I18N-005 (no hardcoded `"en-US"`/`"es-ES"`, no `.toLocaleString()` w/o arg) | ❌ FAIL | 1 hardcoded `"es-ES"` in `UserCVCard.tsx:161`; 6 `.toLocaleString()` callsites in `StatsCardsRow.tsx:71,78,96,103,110,135` + `RightSidebar.tsx:44` |
| AC-6 / SCN-I18N-006 (no hardcoded EN errors in useChat) | ❌ FAIL | `useChat.ts:175,209,336` — 3 hardcoded English error strings ("Something went wrong. Please try again.", "Connection failed — no response body.") |
| AC-7 / SCN-I18N-007 (vitest pass for switcher + Header in both locales) | ✅ COMPLIANT | `LanguageSwitcher.test.tsx` (9 tests, both locales) + `Header.test.tsx` (6 routes × 2 locales = 12 assertions) pass; `pnpm run test --run LanguageSwitcher` and `--run Header` confirm |
| AC-8 / SCN-I18N-008 (Supabase publicPaths locale-prefix-aware) | ✅ COMPLIANT | `supabase/middleware.ts:20-26` + `72-78` — `stripLocalePrefix` applied; locale-aware redirect to `/en/login` (line 92-99) when on `/en/*`; smoke test confirms `/en/dashboard` → 307 `/en/login` for unauthenticated user |
| AC-9 / SCN-I18N-009 (ICU plurals correct) | ✅ COMPLIANT | `messages/{en,es}.json` — 9 plural keys each, both locales; formatters.test.ts indirectly covers via the data the components render; dashboard `StatsCardsRow` is the only fully implemented count site (others are present but may have unmigrated callers) |
| AC-10 / SCN-I18N-010 (privacidad footer note in EN) | ⚠️ PARTIAL | Footer privacy note keys exist in both en.json (`"Spanish only — English version coming soon"`) and es.json (`"Solo en español — versión en inglés próximamente"`). However, because the URL routing is broken, the user can never actually see the English note — visiting `/dashboard` with `NEXT_LOCALE=en` cookie renders the page in Spanish (`getLocale()` returns the default because the URL has no `/en/` prefix and no route rewrite happens) |
| AC-11 / SCN-I18N-011 (4 CI gates pass) | ✅ COMPLIANT | See §1. All 4 gates green. |
| AC-12 / SCN-I18N-012 (grep audit clean) | ❌ FAIL | `pnpm run lint:i18n` reports 60+ matches: 60+ in `src/app/page.tsx` (landing page), 4 in `src/app/signup/page.tsx`. Script intentionally exits 0 (per its own design) but the matches are real. |

**7/12 ACs pass cleanly. 5 ACs fail (AC-2, AC-5, AC-6, AC-12 outright; AC-1 partial; AC-10 partial).**

---

## 4. Follow-up Audit (5 documented partial migrations from apply)

| # | Follow-up | Status | Severity | Evidence |
|---|---|---|---|---|
| F1 | `authCopy.ts` not deleted | PARTIAL (acceptable per design) | INFO | `src/lib/authCopy.ts` is `@deprecated` (line 2) and has no production callers; only 7 test files import it (line 4-10 of grep). Apply slice 15 removed the redundant `authCopy.test.ts` (per apply-progress). The file itself is intentionally kept as the deprecation landing site for the remaining test imports. **Acceptable per design §8** (deferred deletion of `authCopy.ts` to a follow-up). |
| F2 | `JobDetailContent`, `JobDetailAside`, `JobList`, `GenerateCVModal`, `SalaryBadge` not migrated | NOT DONE | WARNING | `grep -cE "useTranslations" src/components/jobs/{JobDetailContent,JobDetailAside,JobList,GenerateCVModal,SalaryBadge}.tsx` returns **0** for all 5 files. Spec said these get translated in slice 8. |
| F3 | `useChat.ts` inline English errors | NOT DONE | WARNING | `useChat.ts:175` (`"Something went wrong. Please try again."`), `:209` (`"Connection failed — no response body."`), `:336` (same as 175). Spec AC-6 explicitly forbids this. |
| F4 | Landing page partial | PARTIAL | WARNING | `src/app/page.tsx` is 731 lines, has only 1 `useTranslations` call (`Landing`) and 3 `t()` calls (only `Landing.upload.*` keys for error states). 60+ hardcoded Spanish strings remain. `pnpm run lint:i18n` lists all of them. |
| F5 | `signup`, `forgot-password`, `reset-password` partial | NOT DONE (signup), PARTIAL (reset) | WARNING | `signup/page.tsx`: 170 lines, **0** `useTranslations` calls, 4 hardcoded Spanish strings (`"Volver al inicio"`, `"Crear cuenta"`, `"Registrate para…"`, `"Continuar con Google"`, `"Iniciá sesión"`). `forgot-password/page.tsx` is a 5-line redirect. `reset-password/page.tsx` has 1 `useTranslations` call (via child component). |

**Summary**: 0 of 5 follow-ups are fully addressed. 1 (F1) is acceptable per design. 4 are still open (F2, F3, F4, F5).

---

## 5. Discoveries Audit (6 from apply-progress)

| # | Discovery | File:line | Confirmed? |
|---|---|---|---|
| D1 | `pnpm install --ignore-scripts` workaround | Used during install (ran successfully) | ✅ |
| D2 | `@/messages/*` tsconfig + vitest alias | `vitest.config.ts:24` — `{ find: /^@\/messages\/(.*)$/, replacement: path.resolve(__dirname, "./messages/$1") }` (note: ordered BEFORE the generic `@` alias, line 25) | ✅ |
| D3 | `window.matchMedia` jsdom stub | `vitest.setup.ts:6-19` — `if (typeof window !== "undefined" && !window.matchMedia) { Object.defineProperty(window, "matchMedia", { ... }) }` | ✅ |
| D4 | `useLocale() as Locale` cast pattern | `LanguageSwitcher.tsx:47` — `const locale = useLocale() as Locale;` (next-intl 4.x types `useLocale` as `string`) | ✅ |
| D5 | Zod translation-keys migration pattern | `src/components/auth/ForgotPasswordForm.tsx:33-35,75-77` — components import `useTranslations('Validation')` and call `t(schema.translationKey)`; Zod schemas store the translation key as a string in `.message` | ✅ |
| D6 | ripgrep fallback in `scripts/audit-i18n.sh` | `scripts/audit-i18n.sh:48-71` — `if command -v rg >/dev/null 2>&1; then rg …; elif grep -P 'a' <<<'a' >/dev/null 2>&1; then grep -RInP …; else echo "WARNING: neither ripgrep nor grep -P available; skipping audit."; fi` | ✅ |

**All 6 discoveries are documented in code.** Good discipline from apply.

---

## 6. Runtime Smoke Tests (additional, not in spec)

```
$ curl -sS -o /dev/null -D - -H "Accept-Language: en-US,en;q=0.9" http://localhost:3000/dashboard
HTTP/1.1 307 Temporary Redirect
location: /login
(no Set-Cookie header)

$ curl -sS -o /dev/null -D - -H "Accept-Language: en-US" http://localhost:3000/en/dashboard
HTTP/1.1 307 Temporary Redirect
location: /en/login

$ curl -sS -o /dev/null -D - -H "Accept-Language: en-US" http://localhost:3000/en/login
HTTP/1.1 404 Not Found

$ curl -sS -o /dev/null -D - -H "Accept-Language: es-ES" http://localhost:3000/login
HTTP/1.1 200 OK
(no Set-Cookie header)
```

**The 404 on `/en/login` is the smoking gun**: the route structure has no `[locale]/` dynamic segment, so any URL with `/en/` (or any other locale prefix) returns 404. The only way `/en/*` URLs would work is if the next-intl middleware successfully rewrote them to unprefixed URLs with the `getLocale()` header. But because of the middleware chain bug (Supabase returns its own response), the rewrite never reaches the page render.

---

## 7. Findings

### CRITICAL (3)

**C1 — Missing `[locale]/` route segment** blocks every `/en/*` URL with 404.
- **Files**: `src/app/**/page.tsx` (no `[locale]/` segment anywhere in the route tree); `.next/server/app/` build output contains no `en/` directory
- **Symptom**: `/en/login`, `/en/signup`, `/en/jobs/123` all 404; `/en/dashboard`, `/en/search`, `/en/settings` 307 (Supabase) to `/en/login` which 404s
- **Spec impact**: REQ-I18N-002 (locale prefix policy), REQ-I18N-015 (Accept-Language detection), REQ-I18N-016 (OAuth callback) all fail
- **Fix**: Either (a) restructure all routes under `app/[locale]/...` (mechanical but invasive — 20+ files to move + `[[...locale]]` opt-out for `/api`), or (b) add a `pathnames` config to `src/i18n/routing.ts` that maps `/en/dashboard` → `/dashboard` with the locale header (less invasive). Option (b) is the standard next-intl 4.x "no [locale] segment" pattern.
- **Effort**: ~30 min for option (b); ~2 hours for option (a)

**C2 — Middleware chain discards the intl redirect** (the `localePrefix: 'as-needed'` 307 to `/en/dashboard` is thrown away when Supabase returns its own 307 to `/login`).
- **File**: `src/middleware.ts:42-50`
  ```ts
  const intlResponse = intlMiddleware(request);
  const supabaseResponse = await updateSession(request);
  intlResponse.cookies.getAll().forEach(({ name, value }) =>
    supabaseResponse.cookies.set(name, value),
  );
  return supabaseResponse;  // ← always returns supabase, even if intl redirected
  ```
- **Symptom**: `Accept-Language: en-US` to `/dashboard` returns 307 to `/login` (no `/en/` prefix) with **no `Set-Cookie: NEXT_LOCALE=en`**. The intl middleware's redirect never reaches the client.
- **Spec impact**: SCN-I18N-002, AC-2 fail. The cookie override mechanism (REQ-I18N-006) works for the switcher (which directly writes the cookie client-side), but the server-side first-visit detection is broken.
- **Fix**: Detect the intl redirect and return it:
  ```ts
  const intlResponse = intlMiddleware(request);
  if (intlResponse.headers.get('x-middleware-rewrite') || /* intl returned a redirect */) {
    return intlResponse;
  }
  // Otherwise run Supabase
  ```
  Or restructure the chain so the rewritten request is passed to Supabase, not the original.

**C3 — The combination of C1 and C2 means the English locale is functionally unreachable** at runtime. A first-time visitor with `Accept-Language: en-US` is bounced to Spanish `/login` and gets no cookie. A user who clicks the LanguageSwitcher sets the cookie client-side, but the URL never updates to `/en/...` and the page never re-renders in English (because the cookie alone doesn't trigger a route rewrite, and no route exists at `/en/...`).
- **Spec impact**: The entire user-facing value of the feature (English locale) is broken.
- **Fix**: Address C1 and C2 first; this is the emergent symptom.

### WARNING (9)

**W1 — `Jobs.errors` structural bug** in `messages/en.json:349` and `messages/es.json:349`. Top-level key with literal `.` in the name (`"Jobs.errors"`) breaks next-intl 4.x's `validateMessages` — every test run logs `IntlError: INVALID_KEY Namespace keys cannot contain the character "."`. No code currently consumes it, so no user impact, but the key is structurally broken. **Fix**: nest under the existing `"Jobs"` namespace (line 232-263) as `"errors": { "loadFailed": ..., "detailFailed": ..., "statsFailed": ... }`.

**W2 — `UserCVCard.tsx:161` hardcoded `"es-ES"`** in `toLocaleDateString("es-ES")`. Violates REQ-I18N-014 / SCN-I18N-005. The whole "Guardado el …" line is also hardcoded Spanish (no `t()`), so even the EN locale will show the Spanish date format. **Fix**: use `formatDate(savedCV.created_at, locale)` and translate `"Guardado el"` to a key.

**W3 — 6 `.toLocaleString()` callsites without locale arg** in `StatsCardsRow.tsx:71, 78, 96, 103, 110, 135` and `RightSidebar.tsx:44`. All should be `formatNumber(value, locale)` per the slice-4 refactor. **Fix**: replace each callsite with the helper.

**W4 — `useChat.ts` 3 hardcoded English error strings** (lines 175, 209, 336). Violates AC-6. **Fix**: replace with `useTranslations('Chat.errors')` and look up `t('streamFailed')`, `t('connectionFailed')`, `t('generic')` (the `Chat.errors` namespace already has these keys at `messages/en.json:342-347` and `messages/es.json:342-347`).

**W5 — F2 partial migration: 5 of 9 jobs components untranslated** (`JobDetailContent`, `JobDetailAside`, `JobList`, `GenerateCVModal`, `SalaryBadge` — all 0 `useTranslations` calls). The slices 8 docs claim these were migrated. **Fix**: per-component migration in a follow-up slice.

**W6 — F4 partial migration: landing page** (`src/app/page.tsx`, 731 lines, only 3 `t()` calls). 60+ hardcoded Spanish strings; `pnpm run lint:i18n` lists all of them. **Fix**: dedicated landing-page slice; the messages already have the `Landing` namespace keys (validated at `messages/en.json:354-` and `messages/es.json:354-`).

**W7 — F5 partial migration: `signup` page** (`src/app/signup/page.tsx`, 170 lines, 0 `useTranslations` calls). 5 hardcoded Spanish strings. **Fix**: replace with `useTranslations('Auth.signup')` + `useTranslations('Common')` (the messages already have these keys).

**W8 — 11 other untranslated components** with 0 `useTranslations` calls: `PlatformDistribution`, `UserCVCard`, `NotificationSettings`, `PlatformConfigCard`, `ChatInput`, `ChatPanel`, `ChatMessages`, `AssistantMessage`, `EmptyState`, `ErrorState`, `LocationBar`. These are documented partial migrations in the apply phase but worth surfacing in the report.

**W9 — `layout.test.tsx` test pollution**. The layout test mocks `getMessages` to return `dummyMessages = { Common: { loading: "Cargando…" } }`, which doesn't include the `Footer` namespace. When the test renders the layout, the mounted `<Footer />` calls `useTranslations("Footer")` and emits `IntlError: MISSING_MESSAGE: Could not resolve Footer in messages for locale 'es'/'en'` (8 warnings total). The tests still pass because the assertions only check `<html lang>` and `setRequestLocale`, but the warning noise is real. **Fix**: add `"Footer": { "privacyNote": "x", "privacy": "x", "copyright": "x" }` to `dummyMessages` at `src/app/layout.test.tsx:21`.

### SUGGESTION (3)

**S1 — Spec deltas for modified capabilities are missing.** `openspec/specs/frontend-dashboard/spec.md`, `chat-frontend/spec.md`, and `favorites/spec.md` do NOT contain the `REQ-DASH-I18N-001..003`, `REQ-CHAT-I18N-001..003`, `REQ-FAV-I18N-001..003` that the i18n spec promises (line 290-298) and the tasks.md claims to close (line 446, 555, 616). This is a spec-process gap, not a code gap — sdd-archive should fold the deltas into the main specs (or add a note that the REQ IDs are informal aliases).

**S2 — next-intl version mismatch.** The spec says `next-intl@3.x` (line 4 of `frontend-i18n/spec.md`); the installed version is `4.13.0` (`package.json`). Likely a documentation lag — the design was written against 3.x and the apply phase installed 4.x. The 4.x API is similar enough that the migration is mostly transparent, but the spec should be updated for traceability.

**S3 — OpenSpec convention violation.** The new `frontend-i18n` spec was created at `openspec/specs/frontend-i18n/spec.md` (main specs folder), not at `openspec/changes/feat-frontend-i18n/specs/frontend-i18n/spec.md` (change folder). Per the openspec-convention reference, the delta should live in the change folder and be merged to main during `sdd-archive`. The current placement is functionally correct (the spec is reachable) but breaks the convention. **Fix**: in sdd-archive, move the change folder under `archive/YYYY-MM-DD-feat-frontend-i18n/` and verify the spec lands in the right place.

---

## 8. Verdict

**FAIL** — 3 CRITICAL findings block the merge. The core value of the feature (reaching the English locale for first-time en-US visitors) is non-functional. The 9 WARNING findings are documented partial migrations + spec compliance gaps that can be fixed in a single remediation slice after the CRITICAL issues.

---

## 9. Merge Recommendation

**`merge_recommended: false`**

The i18n infrastructure is broken at runtime. PRs cannot be merged into `main` because the English locale is unreachable for first-time visitors. A remediation slice (which would become **slice 16**) is required before the PRs can be safely opened.

**Recommended remediation** (smallest delta that unblocks the merge):

1. **Fix C1 + C2 in a single slice** (`slice-16-route-routing-fix`):
   - **Option A** (preferred, ~30 min): add a `pathnames` config to `src/i18n/routing.ts` that maps `/en/dashboard` → `/dashboard` etc. (without the locale prefix in the actual URL — the middleware rewrites in-memory). The next-intl 4.x docs cover this in the "Without i18n routing" section. This avoids restructuring 20+ files.
   - **Option B** (~2 hours): restructure all routes under `app/[locale]/...` with a `[[...locale]]` opt-out for `/api/*`.
   - Fix `src/middleware.ts` to honor the intl redirect: detect a non-200 intl response and return it instead of always returning `supabaseResponse`.
   - Verify SCN-I18N-002 passes (curl en-US → 307 `/en/dashboard`), SCN-I18N-015 passes (cookie override works), `/en/login` no longer 404s.

2. **Address the 9 WARNINGs in the same slice or a follow-up `slice-17-i18n-completeness`**:
   - W1: fix the `Jobs.errors` structural bug (5 min, 2 lines)
   - W2 + W3: fix the `toLocaleString()` and `toLocaleDateString("es-ES")` callsites (30 min, 7 lines)
   - W4: fix the 3 hardcoded English errors in `useChat.ts` (15 min, 3 lines)
   - W5 + W6 + W7: migrate the 5 jobs components + landing page + signup page (2-3 hours, ~1000 lines if mechanical)
   - W8: optionally migrate the 11 other untranslated components in a separate `slice-18-i18n-deep-cleanup` (medium effort)
   - W9: add `Footer` namespace to `layout.test.tsx` `dummyMessages` (1 min, 4 lines)

3. **Open the 15 PRs against `main`** (user opens from GitHub web UI tomorrow per `PR_GUIDE.md`).

4. **Then run `sdd-archive`** to merge the spec deltas and move the change folder to `archive/2026-06-22-feat-frontend-i18n/`.

---

## 10. Next Phase

**`sdd-archive`** (after `sdd-apply` runs the remediation slice).
