# Exploration: `feat-frontend-i18n`

> **Phase**: SDD explore (Pace A2 / B1 hybrid / C4 / D1)
> **Author**: sdd-explore sub-agent
> **Date**: 2026-06-22
> **Project**: jobs-finder (frontend workspace)

---

## Current State

The frontend is a Next.js 15.5.19 App Router monorepo at `frontend/` (React 19, TS 5.9.2 strict + `noUncheckedIndexedAccess`, Tailwind 3.4, shadcn/ui slate, `next-themes` for dark/light, `@tanstack/react-query`, `framer-motion`, `sonner`, lucide-react, date-fns). The codebase has **no i18n library installed** and **no localization infrastructure** beyond `<html lang="es">` hardcoded in `src/app/layout.tsx`.

### Route map (verified by directory listing)

```
src/app/
├── layout.tsx                  → <html lang="es"> ← MUST become dynamic
├── page.tsx                    → 729-line CV landing (Spanish)
├── error.tsx                   → English
├── not-found.tsx               → English
├── loading.tsx                 → no strings
├── providers.tsx               → no user-facing strings
├── (app)/                      → protected (auth-middleware gated)
│   ├── layout.tsx              → AppShell + EmailVerificationBanner
│   ├── dashboard/page.tsx      → dashboard (uses StatsCardsRow, RightSidebar, SearchBar)
│   ├── search/page.tsx         → search with filters
│   ├── settings/page.tsx       → composes UserCVCard + PlatformConfigCard + NotificationSettings + AccountSection
│   ├── settings/loading.tsx
│   └── favorites/page.tsx
├── (auth)/                     → public auth layout
│   ├── layout.tsx              → centered logo + card
│   ├── forgot-password/page.tsx → composes ForgotPasswordForm
│   └── reset-password/page.tsx  → server-component session check
├── jobs/[id]/page.tsx          → public job detail (auth-aware)
├── login/page.tsx              → standalone page
├── signup/page.tsx             → standalone page
├── auth/callback/route.ts      → OAuth callback
├── privacidad/page.tsx         → 478-line Spanish legal document (FLAG)
└── api/                        → server route handlers (no UI strings)
```

### Language state (the problem)

The codebase is **already bilingual in a chaotic way**:

| Area | Language | Evidence |
|---|---|---|
| `app/layout.tsx` `<html lang>` | `es` (hardcoded) | Must become dynamic |
| Auth (`authCopy.ts` + `(auth)/*`) | Spanish | `authCopy.ts` centralizes ~50 keys |
| `app/login/page.tsx`, `app/signup/page.tsx` | Spanish | hardcoded literals |
| `app/page.tsx` (landing, 729 lines) | Spanish | CV marketing copy |
| `app/error.tsx`, `app/not-found.tsx` | English | hardcoded |
| `components/layout/Header.tsx`, `Sidebar.tsx` | English | `ROUTE_META.label: "Dashboard"`, etc. |
| `components/dashboard/StatsCardsRow.tsx` | **MIXED** | "Total en base de datos" (ES) + "Active Platforms" (EN, in NotificationSettings) |
| `components/dashboard/RightSidebar.tsx` | English | "Summary", "Total jobs", "Latest Jobs" |
| `components/jobs/JobCard.tsx` / `CompactJobCard.tsx` | **MIXED** | "Abierta" badge (ES) + "Apply"/"Unknown" (EN) |
| `components/jobs/JobDetailContent.tsx` | English | "Description" heading |
| `components/jobs/JobDetailAside.tsx` | **MIXED** | "Source"/"Posted"/"Location"/"View Original" (EN) + "Generar CV adaptado" (ES) |
| `components/jobs/GenerateCVModal.tsx` | Spanish | consent text + error messages |
| `components/jobs/FavoriteButton.tsx` | English | "Removed from favorites", "Added to favorites" |
| `components/search/FilterPanel.tsx`, `SearchBar.tsx`, `LocationBar.tsx` | English | "Filters", "Clear", "Search..." |
| `components/settings/UserCVCard.tsx` | Spanish | "Tu CV", "Subí tu CV...", "Cargando...", "Actualizar CV" |
| `components/settings/AccountSection.tsx` | Spanish | "Cuenta", "Cambiá tu contraseña..." |
| `components/settings/NotificationSettings.tsx` | English | "Notifications", "Save Preferences" |
| `components/settings/PlatformConfigCard.tsx` | English | "Active Platforms" |
| `components/auth/AuthStatus.tsx` | Spanish | "Cerrar sesión", "Iniciar sesión" |
| `components/chat/ChatPanel.tsx` / `ChatMessages.tsx` / `AssistantMessage.tsx` | English | "Job Assistant", "Connecting", "Searching", "Done" |
| `components/chat/ChatDialog.tsx` | Spanish | "Abrir asistente IA", "Chat con IA" |
| `components/shared/EmptyState.tsx`, `ErrorState.tsx`, `ExportButton.tsx` | English | "No results found", "Something went wrong", "Export CSV" |
| `hooks/useChat.ts` | English | "Something went wrong. Please try again.", "Connection failed — no response body." |
| `lib/formatters.ts` | English | `Intl.NumberFormat("en-US")`, `formatDistanceToNow` (default EN) |
| `app/privacidad/page.tsx` | Spanish-only legal | 478-line document |
| `app/jobs/[id]/page.tsx` | **MIXED** | "Jobs Finder" (EN) + "Volver atrás", "Reintentar", "Cerrar sesión", "Registrarse" (ES) |

### Pre-existing assets to reuse

- **`frontend/src/lib/authCopy.ts`** is **already** a centralized, `Object.freeze`-d, i18n-ready dictionary for ~50 auth strings, with a comment explicitly saying it is "the seed for a next-intl / next-translate translation source. The shape (grouped by capability) is i18n-friendly." This is a strong hint the team was planning for i18n. The implementation should **promote `authCopy.ts` into `messages/{en,es}.json`** rather than maintain two parallel sources.
- **`frontend/src/lib/validation/authSchemas.ts`** already imports from `authCopy.ts` for zod messages; the migration to next-intl is mechanical.
- **`frontend/src/middleware.ts`** is **already** wrapped around `updateSession()` (Supabase auth middleware). `next-intl` middleware **chains before** it — proven pattern in next-intl docs.

### Pre-existing locale bugs to fix

| File:Line | Issue |
|---|---|
| `app/layout.tsx:17` | `<html lang="es">` hardcoded; will desync for English users |
| `lib/formatters.ts:12` | `Intl.NumberFormat("en-US")` hardcoded |
| `lib/formatters.ts:6-8` | `formatDistanceToNow(date, { addSuffix: true })` — uses English |
| `components/settings/UserCVCard.tsx:161` | `toLocaleDateString("es-ES")` hardcoded |
| `hooks/useChat.ts:175,209,336` | English hardcoded error strings — must move to messages |
| `components/dashboard/StatsCardsRow.tsx:73-137` | `.toLocaleString()` without locale arg — defaults to browser locale (unpredictable) |
| `components/dashboard/RightSidebar.tsx:40` | `.toLocaleString()` same as above |

---

## Affected Areas

Every user-facing string in `frontend/src/**`. See the full file-by-file coverage table below. Top hot-spots by string count:

1. `app/page.tsx` (landing, 729 lines) — **~80 strings**, almost entirely marketing copy
2. `app/privacidad/page.tsx` (legal) — **~80 strings**, but **legal text — flag as decision**
3. `components/settings/UserCVCard.tsx` — **~25 strings** (mostly ES)
4. `components/jobs/GenerateCVModal.tsx` — **~25 strings** (mostly ES)
5. `lib/authCopy.ts` — **~50 strings** (already centralized ES, seed for messages)
6. `components/settings/DeleteAccountDialog.tsx` — **~25 strings** (via authCopy)
7. `components/settings/ChangePasswordForm.tsx` — **~15 strings** (via authCopy)
8. `app/login/page.tsx`, `app/signup/page.tsx` — **~35 strings combined** (hardcoded ES)
9. `components/dashboard/StatsCardsRow.tsx` — **~12 strings** (mixed)
10. `components/chat/*` — **~15 strings** (mostly EN)

**No backend code is touched** — the backend is out of scope per the change brief.

---

## Approaches Considered

### 1. i18n library choice

| Library | Size | TS strict | App Router | Complexity | Lock-in | Verdict |
|---|---|---|---|---|---|---|
| **`next-intl`** | ~14 KB | First-class | Native (middleware + `[locale]` + server components) | Low | Low (file-based, droppable) | ✅ **Recommend** |
| `next-i18next` | ~40 KB + i18next | OK | Poor (Pages-router focus; App Router needs hacks) | High | High | ❌ Reject (legacy) |
| `react-i18next` + i18next alone | ~45 KB | OK | Manual (no middleware, manual SSR hydration) | High | Medium | ❌ Reject (reinvents middleware) |
| Custom server-component solution (Accept-Language + Context) | 0 KB | OK | Custom (must build hydration, pluralization, message lookup) | High | High | ❌ Reject (reinvents the wheel) |

**Why `next-intl` wins**:
1. **App Router is its home turf** — server components can call `getTranslations('Dashboard')` without client-side hydration. We have ~13 pages, many with `"use client"`, but the middleware and root layout stay server-side.
2. **`localePrefix: 'as-needed'`** gives us a hybrid: default locale at root URL (no migration), opt-in locales at `/es/...`. This is exactly the brief's Option B but implemented by `next-intl` in 6 lines of config.
3. **ICU MessageFormat** for Spanish pluralization (`{count, plural, one {# trabajo} other {# trabajos}}`), which we need for `JobCard`, `EmptyState`, `StatsCardsRow`.
4. **TypeScript strict + `noUncheckedIndexedAccess` safe** — `next-intl` ships its own `GlobalConfig`-style types and is widely deployed in TS strict codebases.
5. **`<html lang>` becomes automatic** — `next-intl` wraps the layout and sets `lang` from the active locale.

### 2. Routing strategy

| Option | What changes | Effort | SEO/Sharing | Refactor scope |
|---|---|---|---|---|
| **A. `[locale]` dynamic segment** (every page moves one level deeper; full URL change) | `/[locale]/dashboard`, `/[locale]/login`, etc. — even `/` becomes `/[locale]` | **High** | Best (every URL carries locale; canonical tags straightforward) | Touches ~13 page files, both layouts, all `<Link>` hrefs |
| **B. `localePrefix: 'as-needed'`** (default at root, others at `/xx/...`) | `es` default keeps `/dashboard` working; English becomes `/en/dashboard` | **Medium** | Good (default-locale URLs unchanged; non-default gets shareable prefix) | Touches middleware + config only; pages stay put |
| **C. Cookie-only locale, NO URL change** | URLs identical, locale in cookie | **Low** | Bad (no locale in URL → no SEO, can't share a language preference, broken social previews) | Minimal but undermines the brief's "professional SaaS-grade" bar |

**Recommendation: Option B** (`localePrefix: 'as-needed'`).
- The brief explicitly calls for "SaaS-grade" + "let the user easily change language" + "shareability", so Option C fails on bar.
- Option A forces a wholesale move-everything refactor and breaks every current URL even at the default locale. With `~80 marketing strings on /` and a working app, we don't need to do that.
- `next-intl` + `localePrefix: 'as-needed'` keeps the existing `/`, `/dashboard`, `/search`, etc. URLs serving the default locale, and adds `/en/...` for English. This is exactly the pattern GitHub, Vercel, and Notion use.

### 3. Default locale: `es` (not `en`)

**Reasoning**:
1. **Primary user audience is Spanish-speaking** — all three data sources (LinkedIn ES, Indeed ES, InfoJobs) return Spanish content.
2. **Current `<html lang="es">` already encodes this decision** — changing the default would silently flip the entire app's language for current users, which is a regression.
3. **URL preservation**: with `es` as default + `localePrefix: 'as-needed'`, the current routes (`/dashboard`, `/search`, etc.) keep serving Spanish exactly as today. `/en/dashboard` is the opt-in English path.
4. **Developer convenience is secondary** — ENG contributors can either type `/en/...`, set their browser's `Accept-Language: en`, or click the switcher. This is a tiny price for not regressing the Spanish audience.
5. **`authCopy.ts` is already Spanish-shaped** — the seed dictionary reads in natural Spanish; flipping the default to `en` would mean the seed becomes the "other" translation and we ship an EN/EN product with no real coverage.

(If the orchestrator wants to override, this is **the** decision point worth flagging — see Open Questions.)

### 4. Detection mechanism

```
locale resolution order (highest priority first):
1. Cookie `NEXT_LOCALE`  (set by the LanguageSwitcher; persists user choice)
2. `Accept-Language` header  (browser default; matched against supported locales)
3. DEFAULT_LOCALE = "es"  (final fallback)
```

Implementation:
- `next-intl` ships `createMiddleware({ locales, defaultLocale, localePrefix, localeDetection })` — set `localeDetection: true` (default) and it handles cookie + Accept-Language automatically.
- The switcher writes `NEXT_LOCALE` via `document.cookie` and triggers `router.refresh()` (or `router.replace(newPath)`) — `next-intl`'s `useLocale()` + `useRouter()` pattern.
- A `localStorage["NEXT_LOCALE"]` mirror gives **instant hydration on subsequent visits** so the switcher shows the right flag/name without a flash. (This is the SaaS-grade detail — most naive implementations flash the wrong locale on hydration.)

### 5. Translation storage

```
frontend/messages/
├── en.json     (~250-300 keys)
└── es.json     (~250-300 keys, mostly copy-paste from authCopy.ts + current literals)
```

Namespace taxonomy (matches the existing folder structure so per-page translation work is mechanical):

```
Common      → "loading", "retry", "save", "cancel", "yes", "no", "close"
Errors      → "generic", "network", "notFound", "tryAgain"
Validation  → "emailRequired", "emailInvalid", "passwordMinLength", ... (seed from authCopy.validation)
Auth        → "forgot.*", "reset.*", "change.*", "delete.*", "banner.*", "magicLink.*", "globalSignOut.*", "toast.*" (seed from authCopy)
Landing     → all of app/page.tsx marketing copy
Dashboard   → StatsCardsRow, RightSidebar, JobSourceBreakdown labels
Jobs        → JobCard, CompactJobCard, JobDetailContent, JobDetailAside, JobList, GenerateCVModal
Search      → SearchBar, LocationBar, FilterPanel, SearchPage
Favorites   → FavoritesPage
Settings    → UserCVCard, NotificationSettings, PlatformConfigCard, AccountSection + form titles/submits
Chat        → ChatDialog, ChatPanel, ChatMessages, AssistantMessage, ChatInput
Footer      → "version", "privacy", "terms"
DateTime    → ICU pluralization strings for date-fns wrappers
```

### 6. Switcher widget spec

**Recommendation: shadcn `dropdown-menu`** (already in the dep tree, `@radix-ui/react-dropdown-menu: 2.1.6`).

Why dropdown, not popover or command palette:
- Popover is "open any content" — heavier, no keyboard nav built in.
- Command palette is overkill for 2 locales.
- Dropdown matches the existing pattern (Header already imports `AuthStatus` + `ThemeToggle`; switcher slots in next to `ThemeToggle`).

**Visual + interaction contract**:
- **Label**: language name in **its own language** ("English" / "Español") — NOT a flag. Flags are technically incorrect for languages (Spanish is spoken in 20+ countries, each with a different flag).
- **Trigger button**: subtle ghost variant, `h-9 w-9` icon-only OR `h-9` with two-letter ISO code (`EN` / `ES`). Recommend the icon-only with `aria-label="Change language"` for the SaaS-grade compact look that matches `ThemeToggle`.
- **Icon**: `lucide-react` `Languages` icon (already available in the icon set).
- **Dropdown items**: each item shows the language name + a check icon (`lucide-react` `Check`) on the currently active one. Subtle ring + bg highlight on hover.
- **Placement**:
  - **Header** (`components/layout/Header.tsx`) — primary, next to `ThemeToggle`. The header already has `flex items-center gap-3` for `AuthStatus` + `ThemeToggle`; add `LanguageSwitcher` between them or at the leftmost position.
  - **Footer fallback** — for unauthenticated routes (`/`, `/login`, `/signup`, `/privacidad`) that don't render `AppShell`. Add a compact switcher in the footer of `app/page.tsx` landing.
- **Keyboard**: full Radix dropdown keyboard model — Tab to focus, Enter/Space to open, Arrow keys to navigate, Enter to select, Escape to close.
- **ARIA**: `aria-label="Change language"`, `aria-haspopup="menu"`, `aria-expanded`.
- **Animation**: framer-motion `motion.div` with `initial={{ opacity: 0, scale: 0.95 }}`, `animate={{ opacity: 1, scale: 1 }}`, `transition={{ type: "spring", bounce: 0.1, duration: 0.15 }}` — matches the existing spring language (`JobCard.tsx` uses `bounce: 0.1`).
- **Theme-aware**: use existing CSS variables (`bg-popover`, `text-popover-foreground`, `border-border`) — already wireframe-compliant.
- **Persistence**:
  - `document.cookie = "NEXT_LOCALE=en; path=/; max-age=31536000"` (1 year) — read by middleware.
  - `localStorage["NEXT_LOCALE"] = "en"` — mirror for instant client hydration.
  - On mount, `useLocale()` from next-intl already reflects the cookie; the mirror is for the **switcher's visual state** (so the active check is correct on first paint).
- **Loading state**: `skeleton-shimmer` placeholder while next-intl messages are being loaded (rare, but possible on first navigation). Use the existing `Skeleton` primitive + the global `skeleton-shimmer` class.
- **Reduced motion**: `prefers-reduced-motion: reduce` → drop the spring, use opacity-only fade.

---

## File-by-file Translation Coverage

| File | ~Strings | Lang today | Risk | Notes |
|---|---:|---|---|---|
| `app/layout.tsx` | 1 (metadata) | ES (hardcoded `lang`) | **High** | Becomes `next-intl` `<RootLayout>`; `<html lang>` becomes dynamic |
| `app/page.tsx` (landing, 729 LOC) | ~80 | ES | **High** | Marketing copy; biggest single file |
| `app/error.tsx` | 3 | EN | Low | Single component |
| `app/not-found.tsx` | 3 | EN | Low | Single component |
| `app/loading.tsx` | 0 | — | None | Skeleton only |
| `app/(app)/layout.tsx` | 0 | — | None | Composition only |
| `app/(app)/dashboard/page.tsx` | ~5 | EN | Low | Hardcoded placeholders ("Search jobs...") |
| `app/(app)/search/page.tsx` | ~5 | EN | Low | "Search by title, company...", "jobs found" |
| `app/(app)/settings/page.tsx` | 0 | — | None | Composition only |
| `app/(app)/settings/loading.tsx` | 0 | — | None | Skeleton only |
| `app/(app)/favorites/page.tsx` | ~4 | EN | Low | "Filter favorites...", "No matching favorites", "No favorites yet" |
| `app/(auth)/layout.tsx` | 1 (alt text) | EN | Low | "Jobs Finder" |
| `app/(auth)/forgot-password/page.tsx` | 0 | — | None | Composition only |
| `app/(auth)/reset-password/page.tsx` | 3 | ES (via authCopy) | Low | Uses `authCopy.reset.invalidLinkTitle/Description/resendLink` |
| `app/jobs/[id]/page.tsx` | ~6 | **MIXED** | Medium | "Volver atrás", "Reintentar", "Cerrar sesión", "Registrarse", "Jobs Finder" alt |
| `app/login/page.tsx` | ~20 | ES | Medium | Hardcoded literals, needs full i18n refactor |
| `app/signup/page.tsx` | ~15 | ES | Medium | Same pattern as login |
| `app/privacidad/page.tsx` | ~80 | ES | **DECISION** | Legal text — see Open Questions #1 |
| `app/auth/callback/route.ts` | 0 (technical) | — | None | OAuth error redirect only |
| `app/api/jobs/route.ts` | 0 (technical) | — | None | JSON only |
| `app/api/jobs/[id]/route.ts` | 2 (errors) | EN | Low | `{ error: "Job not found" }`, `"Backend unreachable"` |
| `app/api/stats/route.ts` | 0 | — | None | Pure JSON |
| `app/api/health/route.ts` | 0 | — | None | Pure JSON |
| `app/api/cv/generate/route.ts` | 3 (errors) | EN | Low | `"Backend API key not configured"`, `"Invalid form data"`, `"Backend error ..."` |
| `app/api/jobs/chat/stream/route.ts` | 1 (error) | EN | Low | `"Backend returned empty response"` |
| `components/layout/AppShell.tsx` | 0 | — | None | Composition only |
| `components/layout/Header.tsx` | ~12 | EN | **High** | `ROUTE_META[]` is hardcoded labels + descriptions |
| `components/layout/Sidebar.tsx` | ~6 | EN | **High** | `navItems[].label` hardcoded |
| `components/layout/ThemeToggle.tsx` | 1 | EN | Low | `sr-only` text "Toggle theme" |
| `components/layout/Logo.tsx` | 0 | — | None | SVG only |
| `components/layout/PageTransition.tsx` | 0 | — | None | Composition only |
| `components/auth/AuthStatus.tsx` | 2 | ES | Low | "Cerrar sesión", "Iniciar sesión" |
| `components/auth/EmailVerificationBanner.tsx` | 0 | — | None | All via `authCopy.banner.*` |
| `components/auth/ForgotPasswordForm.tsx` | 0 | — | None | All via `authCopy.forgot.*` |
| `components/auth/MagicLinkForm.tsx` | 0 | — | None | All via `authCopy.magicLink.*` |
| `components/auth/ResetPasswordForm.tsx` | 0 | — | None | All via `authCopy.reset.*` |
| `components/chat/ChatDialog.tsx` | 2 | ES | Low | "Abrir asistente IA", "Chat con IA" |
| `components/chat/ChatPanel.tsx` | ~8 | EN | Medium | "Job Assistant", "Connecting", "Searching", "Done", "Error", "Reset" |
| `components/chat/ChatMessages.tsx` | 1 | EN | Low | "Describe the job you are looking for..." |
| `components/chat/ChatInput.tsx` | 2 | EN | Low | placeholder, "Send message" aria-label |
| `components/chat/AssistantMessage.tsx` | ~5 | EN | Medium | "Thinking", "Looking for:", "Matching jobs", "No matching jobs found", "Analyzing your request..." |
| `components/dashboard/StatCard.tsx` | 0 | — | None | Generic, takes `label` prop |
| `components/dashboard/StatsCardsRow.tsx` | ~12 | **MIXED** | **High** | "Total en base de datos" (ES), "Jobs de hoy" (ES), "Última sincronización" (ES), "Ofertas clicadas" (ES), "CVs adaptados" (ES), "Favoritos" (ES), "Jobs por plataforma" (ES), "Failed to load stats" (EN) |
| `components/dashboard/JobSourceBreakdown.tsx` | ~4 | EN | Medium | "No platform data available yet", "% of total", "Last synced" |
| `components/dashboard/PlatformDistribution.tsx` | 1 | EN | Low | "No data" |
| `components/dashboard/RightSidebar.tsx` | ~10 | EN | Medium | "Summary", "Total jobs", "Sources", "Last sync", "Latest Jobs", "No jobs yet", "View all jobs" |
| `components/jobs/JobCard.tsx` | 3 | **MIXED** | Medium | "Abierta" (ES), "Unknown" (EN), "Apply" (EN) |
| `components/jobs/CompactJobCard.tsx` | 3 | **MIXED** | Medium | "Abierta" (ES), "Unknown" (EN) |
| `components/jobs/JobList.tsx` | 0 | — | None | Uses EmptyState |
| `components/jobs/JobDetailContent.tsx` | 1 | EN | Low | "Description" |
| `components/jobs/JobDetailAside.tsx` | ~5 | **MIXED** | Medium | "Source" (EN), "Posted" (EN), "Location" (EN), "View Original" (EN), "Generar CV adaptado" (ES) |
| `components/jobs/GenerateCVModal.tsx` | ~25 | ES | **High** | Consent text, error messages, file upload instructions |
| `components/jobs/FavoriteButton.tsx` | 4 | EN | Low | "Save to favorites", "Remove from favorites", "Added to favorites", "Removed from favorites" (toast) |
| `components/jobs/PlatformBadge.tsx` | 0 | — | None | Auto-capitalizes platform name |
| `components/jobs/SalaryBadge.tsx` | 0 | — | None | Just renders salary string |
| `components/search/SearchBar.tsx` | 2 | EN | Low | "Search..." default placeholder |
| `components/search/LocationBar.tsx` | 3 | EN | Low | "Filter by location...", aria-labels |
| `components/search/FilterPanel.tsx` | ~8 | EN | Medium | "Filters", "Clear", "Platform", "Location", "City, province..." |
| `components/settings/UserCVCard.tsx` | ~25 | ES | **High** | "Tu CV", "Subí tu CV...", "Cargando...", "Subiendo...", "Subir CV (PDF)", "Actualizar CV", error messages |
| `components/settings/AccountSection.tsx` | ~5 | ES | Medium | "Cuenta", "Cambiá tu contraseña...", "Cargando…" |
| `components/settings/NotificationSettings.tsx` | ~6 | EN | Medium | "Notifications", "Configure alerts...", "Enable Notifications", "Receive alerts...", "Save Preferences", "Notification settings saved (local only)" |
| `components/settings/PlatformConfigCard.tsx` | ~5 | EN | Medium | "Active Platforms", "Choose which job platforms...", "Active", "Disabled", "Save Preferences" |
| `components/settings/ChangePasswordForm.tsx` | 0 | — | None | All via `authCopy.change.*` |
| `components/settings/DeleteAccountDialog.tsx` | 0 | — | None | All via `authCopy.delete.*` |
| `components/settings/GlobalSignoutButton.tsx` | 0 | — | None | All via `authCopy.globalSignOut.*` |
| `components/shared/EmptyState.tsx` | ~12 | EN | Medium | 4 variants × {title, description} |
| `components/shared/ErrorState.tsx` | ~4 | EN | Low | "Error", "Something went wrong", "Try again" |
| `components/shared/ExportButton.tsx` | 2 | EN | Low | "Exporting...", "Export CSV" |
| `hooks/useStats.ts` | 1 (error) | EN | Low | `Failed to fetch stats: ${res.status}` |
| `hooks/useJobs.ts` | 1 (error) | EN | Low | `Failed to fetch jobs: ${res.status}` |
| `hooks/useJobsInfinite.ts` | 1 (error) | EN | Low | Same as above |
| `hooks/useJobDetail.ts` | 1 (error) | EN | Low | `Failed to fetch job: ${res.status}` |
| `hooks/useChat.ts` | 4 (errors) | EN | **High** | "Something went wrong. Please try again.", "Connection failed — no response body." (×2) |
| `hooks/useFavorites.ts` | 0 | — | None | No strings |
| `hooks/usePlatformConfig.ts` | 0 | — | None | No strings |
| `hooks/useCVAdapted.ts` | 0 | — | None | No strings |
| `hooks/useDebounce.ts` | 0 | — | None | No strings |
| `lib/authCopy.ts` | ~50 | ES | **High** | **Becomes the seed for `messages/es.json` Auth namespace** |
| `lib/formatters.ts` | 2 (locale) | EN (hardcoded) | **High** | `Intl.NumberFormat("en-US")`, `formatDistanceToNow` (default EN) — see risk #3 |
| `lib/api-client.ts` | 1 (error) | EN | Low | `Backend error: ${res.status}` |
| `lib/chat-storage.ts` | 0 (just doc) | — | None | "Abierta" only in JSDoc |

**TOTALS**
- **Files touched**: ~50 component/page files + 4 route handlers + 4 hooks + 3 lib + 2 root (layout/page) + new files
- **~500-600 unique string keys** × 2 locales = **~1000-1200 translation entries**
- **High-risk files**: `app/page.tsx` (landing, 729 LOC), `app/privacidad/page.tsx` (decision), `lib/authCopy.ts` (centralized, migration source), `lib/formatters.ts` (locale-aware refactor), `components/jobs/GenerateCVModal.tsx` (consent + errors), `hooks/useChat.ts` (errors), `components/settings/UserCVCard.tsx`, `components/layout/Header.tsx`, `components/layout/Sidebar.tsx`, `components/dashboard/StatsCardsRow.tsx`

---

## Risks & Mitigations

### R1. **HIGH — Routing rewrites break existing bookmarks + OAuth redirects**
- **What**: The Supabase middleware (`lib/supabase/middleware.ts`) hardcodes `/dashboard`, `/login`, `/forgot-password`, `/auth/callback`. If we change route structure, these breaks.
- **Why**: `next-intl` middleware MUST run before the Supabase middleware; combining them is non-trivial.
- **Mitigation**:
  - Use `localePrefix: 'as-needed'` so default-locale URLs are unchanged.
  - Build a single `middleware.ts` that chains `createMiddleware(...).middleware` → `updateSession(...)`. Reference: https://next-intl-docs.vercel.app/docs/routing/middleware#composing-other-middlewares
  - Update Supabase `publicPaths` to be locale-prefix-aware (`/login`, `/es/login`, `/en/login`, etc.).
  - Run `pnpm run build` + smoke-test OAuth before merging.

### R2. **HIGH — Mixed-language strings already exist in components (e.g., `StatsCardsRow`, `JobCard`, `JobDetailAside`)**
- **What**: Many components already have a hand-mixed EN/ES literal set. Migrating means deciding which language is canonical for each key.
- **Why**: A naive "wrap in `t()`" pass will produce wrong translations.
- **Mitigation**:
  - Treat the migration as **translation work**, not a refactor. For each file, decide: this key → `es.json`, this key → `en.json`, this key → both.
  - Default rule (documented in the design.md): when in doubt, use the language the **end user sees today**. So "Abierta" → `es.json` only (or both, with "Opened" in `en.json`), "Apply" → `en.json` only (or both, with "Postular" in `es.json`).
  - Acceptable to ship v1 with English fallback for any key that's only in one language — `next-intl` has a `getMessageFallback` hook for this.

### R3. **HIGH — Locale-aware formatting for dates and numbers**
- **What**: `formatDistanceToNow` from date-fns uses English by default. `Intl.NumberFormat("en-US")` is hardcoded. `toLocaleString()` (no arg) defaults to browser locale, which is unpredictable.
- **Why**: An English user should see "2 hours ago", Spanish user "hace 2 horas", not mixed.
- **Mitigation**:
  - Refactor `lib/formatters.ts` to accept an optional `locale` arg (`'es' | 'en'`) and use `date-fns/locale` for `formatDistanceToNow` (`es` → `import { es } from 'date-fns/locale'`, `en` → `import { enUS } from 'date-fns/locale'`).
  - For `Intl.NumberFormat`, use `new Intl.NumberFormat(locale).format(n)`.
  - For `.toLocaleString()` calls without an arg in components, wrap them in `formatNumber(value, locale)` from the new helper.
  - Currency: **separate concern**, not in scope of v1 i18n. Salaries are display-only and the backend already returns raw strings (e.g. `"30.000 €"`). v1 just keeps the strings as-is. Future change: parse + reformat with `Intl.NumberFormat(locale, { style: 'currency', currency })`.

### R4. **MEDIUM — `app/privacidad/page.tsx` (478-line legal document)**
- **What**: This is a Spanish-only legal privacy policy. Translating it requires legal review and is outside typical SaaS i18n scope.
- **Why**: i18n libraries handle UI chrome well but bulk static content poorly.
- **Mitigation**:
  - **Decision needed** (see Open Questions #1).
  - Default option (if no user input): keep `/privacidad` Spanish-only for v1. The footer link stays Spanish. This is a common pattern — privacy/T&C pages are often monolingual per legal jurisdiction.
  - Alternative: wrap it in a `[locale]` route (`/privacidad` + `/en/privacidad`) with a "this is the Spanish version, English translation coming soon" placeholder.

### R5. **MEDIUM — Locale-aware pluralization (Spanish `otro/otros`)**
- **What**: Spanish pluralizes nouns differently from English (`1 trabajo / 2 trabajos / 0 trabajos`). Many of our strings have counts.
- **Why**: Naive string replacement will produce ungrammatical Spanish.
- **Mitigation**:
  - Use next-intl's ICU MessageFormat: `t('jobs.count', { count: n })` with `messages.es.json: "jobs.count": "{count, plural, one {# trabajo} other {# trabajos}}"`.
  - `messages.en.json`: `"jobs.count": "{count, plural, one {# job} other {# jobs}}"`.
  - Audit point: search the codebase for `\.length\b`, `${count}`, `toLocaleString()` to find all pluralization callsites.

### R6. **MEDIUM — Sonner toasts in client-only hooks don't see next-intl provider**
- **What**: `useChat` (client-only) calls `toast.success("Something went wrong...")` and `toast.error(...)` in 4 places. Client-only hooks CAN call `useTranslations`, but every call has to be inside a component or hook inside the `NextIntlClientProvider` boundary.
- **Mitigation**: Wrap the entire app in `<NextIntlClientProvider locale={locale} messages={messages}>` inside `app/layout.tsx` (this is the next-intl default pattern). Then `useTranslations` works in any client component, including `useChat`. Add a regression test that exercises an error toast in a component test.

### R7. **LOW — `Header.test.tsx` asserts on English literals**
- **What**: `Header.test.tsx` checks `expect(h1?.textContent).toContain(label)` with `label: "Dashboard"` etc. After i18n, the test must work for both locales.
- **Mitigation**:
  - Update the test to use `next-intl`'s test wrapper (`/test-utils.tsx` already exists at `src/test-utils.tsx` — extend it).
  - Add a second describe block with locale=es asserting on Spanish equivalents ("Panel", "Buscar", "Favoritos", "Ajustes", "Detalle del trabajo").
  - For `Sidebar.tsx` nav items, no test exists today but the test for the switcher should also assert both locales.

### R8. **LOW — Existing Supabase email-template redirect URLs hardcode paths**
- **What**: `MagicLinkForm`, `ForgotPasswordForm` call `supabase.auth.resetPasswordForEmail(email, { redirectTo: ...path })` with hardcoded `/auth/callback?next=/dashboard`.
- **Why**: Adding `/en/...` prefix means these callback paths could be locale-mismatched (user clicks magic link from English locale, lands on `/dashboard` not `/en/dashboard`).
- **Mitigation**: Make `redirectTo` dynamic based on `useLocale()`. Test: click magic link from `/en/login`, verify landing on `/en/dashboard`, not `/dashboard`.

---

## Effort Estimate

LOC delta (additions + modifications) by slice:

| Slice | LOC | Notes |
|---|---:|---|
| `pnpm add next-intl@3.x` (pin exact) + `pnpm install` | ~5 | Just dep + lockfile |
| `messages/en.json` + `messages/es.json` (~500 keys each) | ~1,000 | Translation entries, mostly copy-paste from existing literals |
| `src/i18n/request.ts` + `src/i18n/routing.ts` (next-intl config) | ~80 | Standard next-intl boilerplate |
| `src/middleware.ts` rewrite (chain next-intl + Supabase) | ~120 | Includes locale-aware publicPaths |
| `src/app/layout.tsx` (wrap with NextIntlClientProvider + dynamic `<html lang>`) | ~50 | Replaces the current 25-line layout |
| `src/components/layout/LanguageSwitcher.tsx` + `LanguageSwitcher.test.tsx` | ~250 | Switcher widget + tests |
| `src/components/layout/Header.tsx` (i18n labels + slot switcher) | ~80 | Includes header test update |
| `src/components/layout/Sidebar.tsx` (i18n labels) | ~30 | |
| `src/components/shared/EmptyState.tsx`, `ErrorState.tsx`, `ExportButton.tsx` | ~120 | 4 × EmptyState variants, etc. |
| `src/components/dashboard/*` (StatsCardsRow, JobSourceBreakdown, RightSidebar, PlatformDistribution) | ~200 | High-risk mixed-language files |
| `src/components/jobs/*` (JobCard, CompactJobCard, JobDetailContent, JobDetailAside, JobList, FavoriteButton, GenerateCVModal, PlatformBadge, SalaryBadge) | ~400 | GenerateCVModal is the biggest |
| `src/components/search/*` (SearchBar, LocationBar, FilterPanel) | ~120 | |
| `src/components/settings/*` (UserCVCard, AccountSection, NotificationSettings, PlatformConfigCard) | ~250 | UserCVCard + AccountSection are heavy |
| `src/components/auth/*` (AuthStatus only — rest already use `authCopy`) | ~30 | |
| `src/components/chat/*` (ChatDialog, ChatPanel, ChatMessages, AssistantMessage, ChatInput) | ~150 | |
| `src/app/page.tsx` (landing, 729 LOC) | ~700 | Largest single file — 80 strings × ~7 LOC/string average |
| `src/app/error.tsx`, `not-found.tsx`, `loading.tsx` | ~30 | Small |
| `src/app/(app)/dashboard/page.tsx`, `search/page.tsx`, `favorites/page.tsx` | ~80 | |
| `src/app/(app)/settings/page.tsx`, `settings/loading.tsx` | ~20 | |
| `src/app/(auth)/layout.tsx`, `forgot-password/page.tsx`, `reset-password/page.tsx` | ~30 | |
| `src/app/jobs/[id]/page.tsx` | ~80 | Mixed-language |
| `src/app/login/page.tsx` | ~150 | 20 strings × ~7 LOC |
| `src/app/signup/page.tsx` | ~120 | |
| `src/app/privacidad/page.tsx` (if translated) | ~400 | Optional — see Open Questions |
| `src/lib/authCopy.ts` → deprecate (move to `messages/{en,es}.json`) | ~30 | Update imports in 8 files |
| `src/lib/formatters.ts` (locale-aware) | ~80 | date-fns locale imports + Intl.NumberFormat |
| `src/lib/api-client.ts` (error messages) | ~10 | Move to messages |
| `src/hooks/useChat.ts` (errors → messages) | ~50 | 4 hardcoded error strings |
| `src/hooks/useStats.ts`, `useJobs.ts`, `useJobsInfinite.ts`, `useJobDetail.ts` | ~40 | Each: pass locale or use messages |
| `src/test-utils.tsx` (next-intl test wrapper) | ~30 | For Header.test.tsx + new tests |
| API route handlers (4 files, error JSON) | ~40 | Small |
| **TOTAL** | **~5,000 LOC** | **Confidence range: 4,000 – 6,000 LOC** |

### Review Workload Guard (per sdd-phase-common §E)

- Budget per the preflight: **400 changed lines**.
- Estimated total: **~5,000 LOC** (12× over budget).
- **Forecast**:
  - `Decision needed before apply: Yes` (chained-PR decision)
  - `Chained PRs recommended: Yes` (mandatory — single PR would be ~12× the budget)
  - `400-line budget risk: **High**`

### Proposed PR slice ordering (for `sdd-tasks` to flesh out)

| Slice | Name | LOC | Verification |
|---|---|---:|---|
| 1 | `chore(i18n): install next-intl + middleware chain + messages skeleton` | ~250 | `pnpm run typecheck && pnpm run lint && pnpm run build` |
| 2 | `feat(i18n): root layout dynamic `<html lang>` + NextIntlClientProvider` | ~80 | Build + smoke test `/` and `/dashboard` |
| 3 | `feat(i18n): LanguageSwitcher widget + header slot + tests` | ~300 | vitest + visual check |
| 4 | `feat(i18n): lib/formatters.ts locale-aware refactor` | ~120 | formatters.test.ts update |
| 5 | `feat(i18n): authCopy.ts → messages/{en,es}.json Auth namespace + components` | ~250 | All auth tests pass for both locales |
| 6 | `feat(i18n): layout chrome (Header, Sidebar, ThemeToggle, AppShell)` | ~200 | Header.test.tsx for both locales |
| 7 | `feat(i18n): dashboard + RightSidebar + JobSourceBreakdown + StatsCardsRow` | ~300 | Snapshot both locales |
| 8 | `feat(i18n): jobs components (JobCard, CompactJobCard, JobDetailContent, JobDetailAside, JobList, GenerateCVModal, FavoriteButton)` | ~500 | All jobs tests |
| 9 | `feat(i18n): search + settings components` | ~500 | All settings tests |
| 10 | `feat(i18n): chat components (ChatDialog, ChatPanel, ChatMessages, AssistantMessage, ChatInput) + useChat error i18n` | ~250 | Chat integration tests |
| 11 | `feat(i18n): landing page (app/page.tsx, 729 LOC)` | ~700 | Manual review |
| 12 | `feat(i18n): auth pages (login, signup, forgot-password, reset-password, jobs/[id])` | ~400 | Auth flow E2E |
| 13 | `feat(i18n): error/not-found + api error JSON` | ~80 | All tests pass |
| 14 | `feat(i18n): privacy page (DECISION — see Open Questions #1)` | ~400 (or 0) | Optional slice |
| 15 | `chore(i18n): remove deprecated authCopy.ts + final cleanup` | ~100 | typecheck + lint + tests green |

---

## Open Questions for the User

1. **`app/privacidad/page.tsx` (478-line legal)**: translate to English, or keep Spanish-only with a footer note?
   - **If translate**: opens ~400 LOC of translation work and a legal-review request.
   - **If skip**: legal page stays Spanish; v1 ships with `Common.privacyPolicy` URL hardcoded to `/privacidad`. Footer link in English locale still goes to the Spanish page (acceptable for a v1; flag with "Spanish only — English version coming soon" if desired).
   - **Default recommendation**: skip for v1, flag in spec, open a follow-up change.

2. **Currency formatting scope**: salaries display as raw strings from the backend (`"30.000 €"`, `"$2,500 USD"`). Should v1 of i18n parse and reformat via `Intl.NumberFormat(locale, { style: 'currency', currency: 'EUR' | 'USD' })`, or leave as-is?
   - **Default recommendation**: leave as-is. Currency display is a separate concern (the backend would need to expose structured currency data, not just a string).

3. **Default locale: confirm `es` (not `en`)** — see "Recommendation #3" above. The brief asks me to justify and the orchestrator may want to override.

4. **`Accept-Language` first-visit behavior for users who speak neither English nor Spanish**: next-intl will fall back to the default (`es`) which is reasonable. If the user wants a third locale later (Portuguese, French), the routing + middleware are already extensible; only `messages/fr.json` (or `pt.json`) needs to be added.

**No other blocking questions** — the orchestrator can proceed to proposal with the recommendation above.