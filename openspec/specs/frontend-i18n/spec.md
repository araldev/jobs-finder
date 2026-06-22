# frontend-i18n Specification

> **Change**: `feat-frontend-i18n` • **Type**: NEW • **Library**: `next-intl@3.x` (pinned exact at apply time)
> **Capability**: locale routing, middleware chain, message storage, provider boundary, switcher widget, locale-aware formatters, pluralization rules.

## Purpose

`frontend-i18n` owns every piece of the localization infrastructure in the frontend workspace: the locale list, default locale, URL prefix policy, message-file storage, the `NextIntlClientProvider` boundary in `app/layout.tsx`, the locale-aware Supabase `publicPaths`, the `LanguageSwitcher` widget, the locale-aware `lib/formatters.ts` refactor, and the pluralization contract (ICU MessageFormat). It establishes a single integration point (`useTranslations` / `getTranslations`) so that domain capabilities (`frontend-dashboard`, `chat-frontend`, `favorites`) own their translation **content** while this capability owns translation **mechanism**. It does NOT translate the legal `privacidad` page in v1, does NOT reformat currency strings (backend contract is out of scope), does NOT add locales beyond `en` + `es`, and does NOT persist locale to the database (cookie + `localStorage` only).

**v2 update (2026-06-22, `feat-frontend-i18n-locale-prefix-urls`)** — URL-prefix mode is now the runtime contract. v1 specified REQ-I18N-002 (`localePrefix: 'as-needed'`) and REQ-I18N-016 (locale-aware OAuth callback) in this file but shipped in cookie-only mode to keep v1 small. v2 flips `frontend/src/i18n/routing.ts` from `'never'` to `'as-needed'`, making canonical `/en/dashboard` and `/en/login` URLs the source of truth. Locale precedence (URL prefix > `NEXT_LOCALE` cookie > `Accept-Language` > `defaultLocale`) is verified in `next-intl@4.x` `resolveLocale.tsx` Prio 1. The delta appended at the end of this file narrows the gap from design-intent (v1) to runtime-evidence (v2).

## Requirements

### REQ-I18N-001: Locale list and default

The system SHALL support exactly two locales: `es` (Spanish) and `en` (English). The default locale MUST be `es`. The locale list and default MUST be declared in `frontend/src/i18n/routing.ts` as the single source of truth, and MUST be referenced by the `createMiddleware` call in `frontend/src/middleware.ts`, by `getLocale()` in `app/layout.tsx`, and by `NEXT_LOCALE` cookie validation in the switcher.

#### Scenario: SCN-I18N-001 — First-time Spanish visitor sees default locale without redirect

- GIVEN no `NEXT_LOCALE` cookie and no `localStorage["NEXT_LOCALE"]` entry
- AND `Accept-Language: es-ES,es;q=0.9,en;q=0.8`
- WHEN the user navigates to `/dashboard`
- THEN the response is HTTP 200 with no `Location` header
- AND the page renders in Spanish (no `/es/dashboard` URL)

#### Scenario: SCN-I18N-002 — First-time English visitor is redirected to prefixed URL

- GIVEN no `NEXT_LOCALE` cookie
- AND `Accept-Language: en-US,en;q=0.9,es;q=0.8`
- WHEN the user navigates to `/dashboard`
- THEN the response is HTTP 307/308 with `Location: /en/dashboard`
- AND `/en/dashboard` renders in English (`<html lang="en">`)

### REQ-I18N-002: Locale prefix policy

The `createMiddleware` call MUST use `localePrefix: 'as-needed'`. The default locale (`es`) SHALL render at root URLs without prefix (`/dashboard`, `/search`, `/login`, `/`). Non-default locales (`en`) SHALL render at prefixed URLs (`/en/dashboard`, `/en/search`, `/en/login`, `/en`). The middleware MUST accept `localeDetection: true`.

#### Scenario: Default-locale URLs preserve current bookmarks

- GIVEN the current production URL `/dashboard` is bookmarked by a Spanish user
- WHEN the i18n middleware is deployed
- THEN `/dashboard` continues to resolve with no redirect
- AND no client sees a `/es/dashboard` URL unless they explicitly switch locale

### REQ-I18N-003: Middleware chain order

`frontend/src/middleware.ts` MUST chain `intlMiddleware = createMiddleware(routing).middleware` BEFORE `updateSession(request)` from `@/lib/supabase/middleware`. The chain MUST follow the next-intl "Composing other middlewares" pattern: `intlMiddleware(request)` first to populate locale on the request, then `updateSession(request)` so the Supabase layer sees the locale-aware path. The middleware MUST match the existing `frontend/src/middleware.ts` `config.matcher` pattern (excluding `_next`, `api`, static assets).

#### Scenario: Middleware chain executes in documented order

- GIVEN a request to `/en/dashboard`
- WHEN the middleware runs
- THEN `intlMiddleware` runs first and stamps the request with `locale=en`
- AND `updateSession` runs second with the locale-aware path
- AND the response headers carry both the locale cookie and Supabase auth cookies

### REQ-I18N-004: Supabase publicPaths is locale-prefix-aware

`frontend/src/lib/supabase/middleware.ts` `publicPaths` MUST match both the unprefixed and prefixed forms of every public route. The match MUST be implemented either as a `stripLocalePrefix(path)` helper applied before the existing `publicPaths.some(...)` check, OR as a regex array covering both forms (`/login`, `/es/login`, `/en/login`, etc.). The list MUST cover: `/login`, `/signup`, `/forgot-password`, `/reset-password`, `/auth/callback`, `/jobs`, `/jobs/[id]`.

#### Scenario: SCN-I18N-008 — Public path matching under both locales

- GIVEN an unauthenticated user navigates to `/en/login`
- WHEN the Supabase middleware evaluates `publicPaths`
- THEN the path matches `/login` after stripping the `/en` prefix
- AND the user is NOT redirected to the dashboard
- WHEN the same user navigates to `/login`
- THEN the path matches `/login` directly
- AND the user is NOT redirected

### REQ-I18N-005: Dynamic <html lang>

`frontend/src/app/layout.tsx` MUST set `<html lang={locale}>` where `locale` is derived from `getLocale()` (server-side, in the root layout RSC). The locale MUST be passed to `NextIntlClientProvider` as `locale={locale}` and `messages={messages}` after `await getMessages()` resolves.

#### Scenario: SCN-I18N-004 — <html lang> reflects active locale

- GIVEN the user navigates to `/dashboard`
- WHEN the layout server-renders
- THEN the response HTML contains `<html lang="es">`
- WHEN the user navigates to `/en/dashboard`
- THEN the response HTML contains `<html lang="en">`

### REQ-I18N-006: NEXT_LOCALE cookie + localStorage mirror

The switcher MUST write `document.cookie = "NEXT_LOCALE=<locale>; path=/; max-age=31536000"` (1 year) AND `localStorage.setItem("NEXT_LOCALE", "<locale>")` on every locale change. The cookie MUST be `Path=/` so all routes share it. After writing both, the switcher MUST call `router.refresh()` to re-render the RSC tree with the new locale.

#### Scenario: SCN-I18N-003 — Switcher click persists locale across all storage layers

- GIVEN the user is on `/dashboard` with no cookie set
- WHEN the user opens the switcher and selects "English"
- THEN `document.cookie` contains `NEXT_LOCALE=en; ...`
- AND `localStorage.getItem("NEXT_LOCALE")` equals `"en"`
- AND the URL becomes `/en/dashboard`
- AND the page re-renders in English without a full page reload

### REQ-I18N-007: Switcher widget placement

The `LanguageSwitcher` MUST render next to the `ThemeToggle` in the Header (top-right slot) on every authenticated route (`(app)` route group). On routes WITHOUT `AppShell` (`/`, `/login`, `/signup`, `/privacidad`), the switcher MUST fall back to a footer-mounted variant in `app/layout.tsx`. The widget MUST NOT duplicate on routes that have both placements.

#### Scenario: Switcher visible on protected routes via header

- GIVEN the user is on `/dashboard` (authenticated)
- WHEN the header renders
- THEN the `LanguageSwitcher` trigger is visible next to the `ThemeToggle`
- AND the header height remains `h-14`

#### Scenario: Switcher visible on public routes via footer

- GIVEN the user is on `/` (landing, no AppShell)
- WHEN the footer renders
- THEN the `LanguageSwitcher` trigger is visible
- AND no header instance of the widget exists

### REQ-I18N-008: Switcher visual contract

The switcher MUST use shadcn `dropdown-menu` (Radix). The trigger MUST be a ghost icon-only button (`h-9 w-9`, `lucide-react/Languages` icon) with `aria-label="Change language"`. Each menu item MUST display the language name **in its own language** ("English" / "Español"), NEVER a flag. The active item MUST show a `lucide-react/Check` icon and a highlighted background. Hover state MUST show a ring + bg highlight.

#### Scenario: Switcher dropdown shows native-language labels

- GIVEN the user opens the switcher while the active locale is `es`
- WHEN the dropdown menu renders
- THEN items show "English" and "Español"
- AND "Español" has the Check icon and highlighted background
- AND no flag emoji appears

### REQ-I18N-009: Switcher animation

The dropdown content MUST animate via framer-motion `motion.div` with `initial={{opacity:0, scale:0.95}}`, `animate={{opacity:1, scale:1}}`, `transition={{type:"spring", bounce:0.1, duration:0.15}}` to match the `JobCard.tsx` spring language. When `prefers-reduced-motion: reduce` is set, the animation MUST strip the spring and use opacity-only fade (`transition={{duration:0.15}}`).

#### Scenario: Reduced-motion users see opacity-only animation

- GIVEN the user has `prefers-reduced-motion: reduce` set in OS prefs
- WHEN the dropdown opens
- THEN the content fades in without scale transform
- AND no spring physics are applied

### REQ-I18N-010: Switcher accessibility

The trigger MUST expose `aria-haspopup="menu"`, `aria-expanded`, and `aria-label`. The full Radix keyboard model MUST work: Tab focuses the trigger, Enter/Space opens the menu, ArrowUp/ArrowDown navigate items, Enter selects, Escape closes. Focus MUST return to the trigger on close.

#### Scenario: Keyboard navigation works without mouse

- GIVEN the user tabs to the switcher trigger
- WHEN they press Enter
- THEN the dropdown opens with focus on the first item
- WHEN they press ArrowDown twice and Enter
- THEN the locale changes and focus returns to the trigger

### REQ-I18N-011: Switcher theme awareness

The switcher MUST use only CSS variable tokens: `bg-popover`, `text-popover-foreground`, `border-border`, `text-muted-foreground` for inactive items. It MUST NOT hardcode any color value (`bg-white`, `text-gray-500`, etc.). Both light and dark mode MUST render correctly via `next-themes`.

#### Scenario: Switcher adapts to dark mode

- GIVEN dark mode is active
- WHEN the dropdown opens
- THEN `bg-popover` resolves to the dark-mode CSS variable value
- AND all text uses the matching dark-mode tokens

### REQ-I18N-012: Message file structure

Translation messages MUST live at `frontend/messages/en.json` and `frontend/messages/es.json`, namespaced by feature. The namespace set MUST include at minimum: `Common`, `Errors`, `Validation`, `Auth`, `Landing`, `Dashboard`, `Jobs`, `Search`, `Favorites`, `Settings`, `Chat`, `Footer`, `DateTime`. Each namespace MUST contain only the strings owned by that feature (no cross-namespace references). Files MUST be valid JSON with stable key ordering.

#### Scenario: Message file structure matches feature layout

- GIVEN the codebase has components under `src/components/dashboard/`, `src/components/jobs/`, etc.
- WHEN the implementer looks up a translation key
- THEN the namespace matches the component's feature folder
- AND the key path mirrors the component's prop or label name

### REQ-I18N-013: ICU MessageFormat pluralization

Every count-bearing string MUST use ICU MessageFormat via `t('namespace.key', { count: n })`. The `es.json` MUST define `{count, plural, one {# <singular>} other {# <plural>}}`; the `en.json` MUST define `{count, plural, one {# <singular>} other {# <plural>}}`. Count callsites that MUST use ICU include: `JobCard`, `CompactJobCard`, `EmptyState`, `StatsCardsRow`, `JobSourceBreakdown`, `SearchBar` result count, `useJobsInfinite` "no more jobs", and any `${count}`-style interpolation.

#### Scenario: SCN-I18N-009 — Spanish pluralization is grammatically correct

- GIVEN the locale is `es` and the result count is 1
- WHEN `t('jobs.count', { count: 1 })` resolves
- THEN the rendered string is "1 trabajo"
- WHEN the count is 2
- THEN the rendered string is "2 trabajos"
- WHEN the count is 0
- THEN the rendered string is "0 trabajos" (Spanish uses `other` for zero)

#### Scenario: English pluralization is grammatically correct

- GIVEN the locale is `en` and the result count is 1
- WHEN `t('jobs.count', { count: 1 })` resolves
- THEN the rendered string is "1 job"
- WHEN the count is 2
- THEN the rendered string is "2 jobs"

### REQ-I18N-014: Locale-aware formatters

`frontend/src/lib/formatters.ts` MUST accept a `locale: 'es' | 'en'` parameter on every exported function (`formatDistanceToNow`, `formatNumber`, `formatDate`). Internally, `formatDistanceToNow` MUST import `es` from `date-fns/locale` and `enUS` from `date-fns/locale`, passing the matching locale to the third arg. `formatNumber(value, locale)` MUST wrap `Intl.NumberFormat(locale).format(value)`. Every caller MUST pass the active locale; no `.toLocaleString()` without an arg and no `Intl.NumberFormat("en-US")` / `Intl.NumberFormat("es-ES")` literals MUST remain after slice 4.

#### Scenario: SCN-I18N-005 — No hardcoded locale strings remain

- GIVEN slice 4 has merged
- WHEN a grep runs for `"en-US"` and `"es-ES"` literals in `frontend/src/**/*.{ts,tsx}`
- THEN zero matches are found outside `messages/*.json` and `privacidad/page.tsx`
- AND zero `.toLocaleString()` without args callsites remain

#### Scenario: formatDistanceToNow respects active locale

- GIVEN a date 3 hours ago and the active locale is `es`
- WHEN `formatDistanceToNow(date, locale)` resolves
- THEN the output uses Spanish relative phrasing (e.g., "hace 3 horas")
- WHEN the active locale is `en`
- THEN the output uses English relative phrasing (e.g., "3 hours ago")

### REQ-I18N-015: Accept-Language detection with cookie override

The middleware MUST use `localeDetection: true` so that on first visit, the `Accept-Language` header determines the initial redirect (to `/en/...` if `en` is preferred, otherwise root for `es`). On every subsequent visit, the `NEXT_LOCALE` cookie MUST take priority over `Accept-Language`. Manual switcher selection MUST write the cookie and take effect on the next request.

#### Scenario: Cookie overrides stale Accept-Language

- GIVEN the user's `NEXT_LOCALE=en` cookie is set
- AND the browser sends `Accept-Language: es-ES`
- WHEN the user navigates to `/dashboard`
- THEN the middleware honors the cookie
- AND redirects to `/en/dashboard` (NOT `/dashboard`)

### REQ-I18N-016: OAuth callback lands on locale-correct dashboard

`/auth/callback` MUST resolve locale-correctly so that after Supabase OAuth completes, the user lands on the locale version of `/dashboard` that matches their `NEXT_LOCALE` cookie (or `Accept-Language` if no cookie). The Supabase `redirectTo` parameter MUST be locale-aware (`${origin}/dashboard` for `es`, `${origin}/en/dashboard` for `en`).

#### Scenario: OAuth callback preserves locale choice

- GIVEN the user started the OAuth flow with `NEXT_LOCALE=en` set
- WHEN Supabase redirects back to `${origin}/auth/callback`
- THEN the callback handler reads the locale cookie
- AND the final redirect destination is `/en/dashboard`
- AND the dashboard renders in English

### REQ-I18N-017: Test wrapper for NextIntlClientProvider

`frontend/src/test-utils.tsx` MUST be extended to wrap rendered components in a `<NextIntlClientProvider locale="es" messages={esMessages}>` (default) OR `<NextIntlClientProvider locale="en" messages={enMessages}>` (opt-in via a prop). Existing `Header.test.tsx` and new `LanguageSwitcher.test.tsx` MUST use this wrapper and pass for both locales.

#### Scenario: SCN-I18N-007 — vitest tests pass in both locales

- GIVEN the extended `test-utils.tsx` is in place
- WHEN `pnpm run test` runs
- THEN `Header.test.tsx` passes with `locale="es"` (asserts Spanish labels) and `locale="en"` (asserts English labels)
- AND `LanguageSwitcher.test.tsx` passes for both locales

### REQ-I18N-018: Cross-cutting dependency on job-domain

This capability declares a non-breaking cross-cutting dependency on the `job-domain` capability. The string-bearing fields on the `Job` value object (`title`, `company`, `location`, `salary`) are display-only and locale-formatted via `lib/formatters.ts`. There is NO schema delta to `job-domain` — the frontend simply consumes the existing fields through locale-aware formatters. Documented here for traceability; see `openspec/specs/job-domain/spec.md` "Frontend i18n note" appendix.

#### Scenario: Job fields render through locale-aware formatters

- GIVEN a `Job` object with `title="Senior Backend Engineer"` and `location="Madrid, Spain"`
- AND the active locale is `es`
- WHEN the `JobCard` renders
- THEN `title` renders as-is (raw string, no formatter)
- AND `location` renders as-is (raw string, no formatter)
- AND `posted_at` renders through `formatDistanceToNow(date, "es")` producing Spanish relative time

### REQ-I18N-019: Privacidad page remains Spanish-only in v1

`frontend/src/app/privacidad/page.tsx` MUST remain Spanish-only in v1. In the EN locale footer, the link MUST point to `/privacidad` (the Spanish page) and MUST render a small translated note in the active locale ("Spanish only — English version coming soon" in EN, the equivalent translation in ES). Translation of the legal page itself opens as a follow-up change.

#### Scenario: SCN-I18N-010 — EN footer link notes Spanish-only legal page

- GIVEN the user is on `/en/dashboard` with the EN footer visible
- WHEN they click the "Privacidad" link in the footer
- THEN the link navigates to `/privacidad` (Spanish page)
- AND the footer shows the translated note "Spanish only — English version coming soon"
- WHEN the user is on `/dashboard` (ES)
- THEN the footer link works identically but the note is in Spanish

## Acceptance Scenarios (AC traceability)

| AC | Scenario | Verification |
|----|----------|--------------|
| AC-1 | SCN-I18N-001 | curl with `Accept-Language: es-ES` to `/dashboard` returns 200 + Spanish HTML |
| AC-2 | SCN-I18N-002 | curl with `Accept-Language: en-US` to `/dashboard` returns 307 + `Location: /en/dashboard` |
| AC-3 | SCN-I18N-003 | vitest click test asserts cookie, localStorage, URL change, re-render |
| AC-4 | SCN-I18N-004 | integration test mounts `app/layout.tsx` and asserts `<html lang>` |
| AC-5 | SCN-I18N-005 | grep test in CI fails the build on any hardcoded locale literal |
| AC-6 | SCN-I18N-006 | grep test in CI fails the build on any `useChat`/`useStats`/etc. hardcoded EN error string |
| AC-7 | SCN-I18N-007 | `pnpm run test` exit code 0 in both locales |
| AC-8 | SCN-I18N-008 | integration test asserts `/en/login` matches `publicPaths` after prefix strip |
| AC-9 | SCN-I18N-009 | vitest ICU test asserts `{count: 0\|1\|2}` for both locales |
| AC-10 | SCN-I18N-010 | vitest footer test renders the translated note in both locales |
| AC-11 | SCN-I18N-011 | CI gates (`pnpm run typecheck && pnpm run lint && pnpm run test && pnpm run build`) green per slice |
| AC-12 | SCN-I18N-012 | ripgrep step in CI excludes `messages/*.json` + `privacidad/page.tsx` + test fixtures + JSDoc; expects zero matches |

## Cross-cutting deltas

Three existing capabilities receive ADDED Requirements to consume `useTranslations`. The deltas are appended directly to the main spec files:

- `openspec/specs/frontend-dashboard/spec.md` → REQ-DASH-I18N-001..003
- `openspec/specs/chat-frontend/spec.md` → REQ-CHAT-I18N-001..003
- `openspec/specs/favorites/spec.md` → REQ-FAV-I18N-001..003

One existing capability receives a non-breaking informational note:

- `openspec/specs/job-domain/spec.md` → "Frontend i18n note" appendix (no REQ added)

## Out of scope

- Translation of `app/privacidad/page.tsx` (478-line legal document — Spanish-only in v1; opens as follow-up change F1)
- Currency reformatting (backend returns raw salary strings; v1 displays them as-is; follow-up F2)
- Locales beyond `en` + `es` (routing + middleware are extensible)
- RTL support (neither `en` nor `es` requires it)
- Backend changes (FastAPI untouched)
- Database / persistence of locale (cookie + `localStorage` only)

## Acceptance criteria (sdd-verify)

- [ ] AC-1..AC-12 from the proposal are all green
- [ ] All 4 frontend CI gates pass (`typecheck`, `lint`, `test`, `build`)
- [ ] grep audit: zero hardcoded user-facing strings outside `messages/*.json` + `privacidad/page.tsx`
- [ ] Switcher visible on every page (Header on protected, Footer on public)
- [ ] Both `es` and `en` render correctly end-to-end
- [ ] OAuth flow lands on locale-correct dashboard

## Delta — v2 (URL-prefix mode, applied 2026-06-22)

This delta modifies the v1 spec to reflect the runtime behavior after flipping `frontend/src/i18n/routing.ts` from `localePrefix: 'never'` → `'as-needed'`. v1 specified URL prefixes in REQ-I18N-002 and REQ-I18N-016 but shipped in cookie-only mode to keep v1's 15-slice plan small. v2 (`feat-frontend-i18n-locale-prefix-urls`) makes the implementation match the spec.

### Modified Requirements

**REQ-I18N-002** (modified): Locale prefix policy is now `as-needed` (was `never`).

- Default locale `es` URLs stay unprefixed: `/dashboard`, `/login`, `/`.
- Non-default locale `en` URLs are prefixed: `/en/dashboard`, `/en/login`, `/en`.
- Locale precedence (verified in `next-intl@4.x` `resolveLocale.tsx` Prio 1):
  1. URL path prefix (`/en/...`)
  2. `NEXT_LOCALE` cookie
  3. `Accept-Language` header
  4. `defaultLocale` (`es`)

(Previously: requirement text was identical, but the v1 implementation set `localePrefix: 'never'` in `frontend/src/i18n/routing.ts:29`, so URL-prefixed URLs would 404 and the entire locale surface was carried by cookie + `localStorage`.)

**REQ-I18N-016** (modified): OAuth callback `/auth/callback` redirects to locale-prefixed paths.

- For default locale (`es` cookie or no cookie): redirect to `/dashboard`, `/reset-password`, etc. (no prefix).
- For non-default locale (`en` cookie): redirect to `/en/dashboard`, `/en/reset-password`, etc.
- Implementation: `localizePath(next, locale)` helper reads `NEXT_LOCALE` cookie and prefixes the redirect target; `locale` falls back to `Accept-Language` parsing → `'es'`.

(Previously: v1 implemented cookie-only locale awareness; redirect targets carried no `/en/` prefix, so an `en` user landed on `/dashboard` rendered in English rather than `/en/dashboard`.)

### New Requirements

**REQ-I18N-020**: Supabase `updateSession` middleware MUST redirect unauthenticated users to a locale-aware login path.

- For request on `/en/dashboard` (no user): redirect to `/en/login?error=...` (NOT `/login`).
- For request on `/dashboard` (no user, default locale): redirect to `/login?error=...`.
- Detection: `stripLocalePrefix(request.nextUrl.pathname)` then `startsWith('/en/')` → use `/en/` prefix on the redirect target.
- Closes the locale-aware auth bounce gap identified in slice-16 (v1's `updateSession` always used `/login`, dropping the user out of the `/en/` namespace).

**REQ-I18N-021**: `LanguageSwitcher` MUST navigate to the locale-prefixed URL on switch.

- For target `en`: `router.push(\`/en${strippedPath}\`)`.
- For target `es`: `router.push(strippedPath)` (no prefix for default locale).
- Implementation re-introduces `usePathname()` + `stripLocalePrefix()` (both were removed in v1 slice-16 simplification).
- Behavior: clicking the switcher changes the URL AND the locale atomically; `router.refresh()` follows to re-render RSC `<html lang>`.

### Modified Scenarios

**SCN-I18N-002** (modified): A first-time visitor with `Accept-Language: en-US` is redirected to `/en/dashboard`.

- GIVEN no `NEXT_LOCALE` cookie
- AND `Accept-Language: en-US,en;q=0.9,es;q=0.8`
- WHEN the user navigates to `/dashboard`
- THEN the response is HTTP 307/308 with `Location: /en/dashboard`
- AND `/en/dashboard` renders in English (`<html lang="en">`)
- (Previously: under v1 cookie-only mode, `/dashboard` rendered in English without a redirect; the URL never carried the locale. URL prefix is now the source of truth.)

**SCN-I18N-003** (modified): Switcher selection persists locale AND navigates the URL.

- GIVEN the user is on `/dashboard` with no cookie set
- WHEN the user opens the switcher and selects "English"
- THEN `document.cookie` contains `NEXT_LOCALE=en; path=/; max-age=31536000`
- AND `localStorage.getItem("NEXT_LOCALE")` equals `"en"`
- AND the URL becomes `/en/dashboard`
- AND `router.refresh()` re-renders the RSC tree (`<html lang="en">`)
- (Previously: under v1 cookie-only mode, the URL stayed at `/dashboard` and the user landed on the Spanish dashboard rendered in English, breaking bookmark/sharing semantics.)

### New Scenarios

**SCN-I18N-013**: URL prefix wins over cookie.

- GIVEN a request to `GET /en/dashboard` with `NEXT_LOCALE=es` cookie
- WHEN the middleware resolves the locale
- THEN the response is HTTP 200 with `<html lang="en">`
- AND no redirect is issued (URL prefix has priority Prio 1 in `resolveLocale.tsx`).

**SCN-I18N-014**: Locale-aware auth bounce for non-default locale.

- GIVEN an unauthenticated request to `GET /en/dashboard`
- WHEN `updateSession` evaluates auth
- THEN the response is HTTP 307 with `Location: /en/login?error=...`
- AND NOT `/login?error=...`.

**SCN-I18N-015**: Canonical redirect from cookie on root URL.

- GIVEN a request to `GET /dashboard` with `NEXT_LOCALE=en` cookie
- WHEN the middleware resolves the locale
- THEN the response is HTTP 307 with `Location: /en/dashboard`
- AND the canonical URL is preserved for bookmarking/sharing.

### Rollback

v2 satisfies v1's contract under the `NEXT_PUBLIC_I18N_ENABLED=false` kill-switch (URLs revert to cookie-only mode without code change). Single-PR revert is also clean — the 8-file diff reverts in one step. Cookie wipe (clear `NEXT_LOCALE` + `localStorage`) falls back to `Accept-Language` and root URLs.