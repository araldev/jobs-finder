# Design: `feat-frontend-i18n`

> **Change**: `feat-frontend-i18n` • **Phase**: SDD design (post-spec, pre-tasks)
> **Stack**: Next.js 15 App Router · next-intl 3.x · TS strict · vitest
> **Mode**: hybrid (engram canonical + openspec mirror)
> **Mirror**: `openspec/changes/feat-frontend-i18n/design.md`
> **Spec reference**: `openspec/specs/frontend-i18n/spec.md` (19 REQs, 23 SCNs) + 4 capability deltas

## Technical Approach

Install `next-intl@3.x` with `localePrefix: 'as-needed'` and `defaultLocale='es'`. Wire its middleware BEFORE the Supabase `updateSession` middleware; make Supabase `publicPaths` locale-prefix-aware via a `stripLocalePrefix()` helper. Convert `app/layout.tsx` into an RSC that calls `getLocale()` + `getMessages()` and wraps children in `NextIntlClientProvider`. Store translations in `frontend/messages/{en,es}.json` namespaced by feature; consume via `useTranslations` (client) or `getTranslations` (RSC). Refactor `lib/formatters.ts` to accept `locale: 'es'|'en'`. Build the `LanguageSwitcher` as a Radix `dropdown-menu` mounted in the Header + Footer. Migrate `authCopy.ts` contents into `messages.{Auth,Validation}` and delete the file in slice 15. Slice into 15 stacked PRs (≤ 700 LOC each) per preflight C4/D1.

## Architecture Decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Library | `next-intl@3.x` (exact pin) | Native App Router, RSC `getTranslations`, ~14KB; `authCopy.ts` header already names it as the migration target. |
| D2 | URL prefix policy | `localePrefix: 'as-needed'` | Default-locale URLs (`/dashboard`, `/login`) keep working — zero regression for current Spanish users. `/en/...` becomes shareable, canonical EN URLs. |
| D3 | Default locale | `es` | Preserves `<html lang="es">`, Spanish data sources, current audience, `authCopy.ts` shape. |
| D4 | Middleware order | `intlMiddleware(req)` → `updateSession(req)`, cookies merged onto final response | Required by next-intl "composing other middlewares" doc; ensures Supabase sees locale-aware path AND intl cookies survive. |
| D5 | Supabase `publicPaths` strategy | `stripLocalePrefix(path)` helper applied before the existing `publicPaths.some(...)` check | Minimal diff to existing logic; regex alternative is harder to maintain. |
| D6 | Message storage | `frontend/messages/{en,es}.json`, namespaced by feature | JSON-native to next-intl; per-slice translation is mechanical; no build-step transformation. |
| D7 | Provider boundary | Root `app/layout.tsx` (RSC) → `NextIntlClientProvider`; client components use `useTranslations` | Standard next-intl pattern; single boundary in layout, all descendants can call `useTranslations`. |
| D8 | Pluralization | ICU MessageFormat `{count, plural, one {# x} other {# xs}}` in BOTH `es.json` and `en.json` | Spanish has `uno/otros` distinction; ICU is the only correct contract for `1 trabajo / 2 trabajos / 0 trabajos`. |
| D9 | Switcher persistence | `document.cookie="NEXT_LOCALE=…; path=/; max-age=31536000"` + `localStorage["NEXT_LOCALE"]` + `router.refresh()` | Cookie makes persistence work across sessions/devices; localStorage gives instant client-side read; `router.refresh()` re-renders RSC tree. |
| D10 | Switcher primitive | shadcn `dropdown-menu` (Radix) with `lucide-react/Languages` icon, native-language labels | Already in dep tree; wireframe-compliant tokens (`bg-popover`, `border-border`); no new icon set. |
| D11 | Switcher fallback placement | Header on `(app)` routes; Footer on `/`, `/login`, `/signup`, `/privacidad` (no AppShell) | Per REQ-I18N-007 — switcher visible on every page, no double-mount. |
| D12 | Currency reformat | Deferred (F2 follow-up) | Backend contract change required; v1 displays raw salary strings as-is. |
| D13 | Privacidad page | Spanish-only v1 (F1 follow-up); footer link shows translated "Spanish only" note | Legal text needs review; orchestrator decided. |
| D14 | Feature-flag escape hatch | `process.env.NEXT_PUBLIC_I18N_ENABLED === 'false'` skips `intlMiddleware` in `middleware.ts` | Allows instant rollback if a slice regresses in production. |
| D15 | CI i18n audit | New `pnpm run lint:i18n` script (ripgrep with PCRE2); wired as separate step in CI, NOT inside `pnpm run lint` | Lint budget is already tight; i18n audit is a separate concern; grep is faster than ESLint rule. |

## Architecture Diagram (request lifecycle)

```
Browser → GET /dashboard (or /en/dashboard)
        │
        ▼
┌─ frontend/src/middleware.ts ──────────────────────────────────────┐
│ matcher excludes /api/*, /_next/*, static assets                   │
│                                                                   │
│  1. intlResponse = createIntlMiddleware(routing)(request)         │
│     - reads NEXT_LOCALE cookie (priority)                         │
│     - else parses Accept-Language                                 │
│     - else default 'es'                                           │
│     - returns NextResponse with NEXT_LOCALE cookie set            │
│                                                                   │
│  2. supabaseResponse = await updateSession(request)               │
│     - strips locale prefix from request.nextUrl.pathname          │
│     - matches publicPaths against stripped path                   │
│     - attaches Supabase session cookies                           │
│     - redirects unauth users → /login or /en/login                │
│                                                                   │
│  3. merge intlResponse.cookies → supabaseResponse                 │
│     return supabaseResponse                                       │
└───────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─ frontend/src/app/layout.tsx (RSC) ───────────────────────────────┐
│ const locale = await getLocale()                                  │
│ const messages = await getMessages()                              │
│ setRequestLocale(locale)        ← next-intl 3.x RSC pattern       │
│ <html lang={locale} suppressHydrationWarning>                     │
│   <body>                                                          │
│     <NextIntlClientProvider locale={locale} messages={messages}>  │
│       <Providers> (theme + react-query + sonner)                  │
│         {children}                                                │
│       </Providers>                                               │
│     </NextIntlClientProvider>                                     │
│   </body>                                                         │
│ </html>                                                           │
└───────────────────────────────────────────────────────────────────┘
        │
        ▼ (server component OR client component)
┌─ RSC:  const t = await getTranslations('Namespace')               ┐
│        <h1>{t('title')}</h1>                                      │
│                                                                   │
│ Client:  'use client'; const t = useTranslations('Namespace')      │
│          <p>{t('description')}</p>                                │
│                                                                   │
│ Pluralized: t('jobs.count', { count: n })                         │
│             → es: "5 trabajos"   en: "5 jobs"                     │
└───────────────────────────────────────────────────────────────────┘
```

For `/en/dashboard` (non-default locale): `intlMiddleware` rewrites (no redirect) — the URL stays `/en/dashboard`, locale is read from URL segment first, falls back to cookie/Accept-Language.

## Module / File Layout

```
frontend/
├── messages/                       NEW (slice 1)
│   ├── en.json
│   └── es.json                     (Common, Errors, Validation, Auth,
│                                    DateTime, Navigation, Dashboard,
│                                    Jobs, Search, Favorites, Settings,
│                                    Chat, Landing, Footer)
├── src/
│   ├── i18n/                       NEW (slice 1)
│   │   ├── routing.ts              createSharedPathnamesNavigation,
│   │   │                            locales: ['es','en'], default 'es',
│   │   │                            localePrefix: 'as-needed'
│   │   └── request.ts              getRequestConfig → loads
│   │                                messages/{locale}.json dynamically
│   ├── middleware.ts               REWRITE (slice 1) — chain intl→supabase
│   ├── next.config.ts              UPDATE (slice 1) — wrap with
│   │                                createNextIntlPlugin('./src/i18n/request.ts')
│   ├── lib/
│   │   ├── supabase/middleware.ts  UPDATE (slice 1) — stripLocalePrefix
│   │   ├── formatters.ts           UPDATE (slice 4) — locale parameter
│   │   ├── authCopy.ts             DEPRECATE (slice 5), DELETE (slice 15)
│   │   ├── validation/authSchemas  UPDATE (slice 5) — t('Validation.*')
│   │   └── api-client.ts           UPDATE (slice 5) — error via t()
│   ├── app/
│   │   ├── layout.tsx              UPDATE (slice 2) — dynamic <html lang>,
│   │   │                            NextIntlClientProvider
│   │   ├── page.tsx                UPDATE (slice 11) — 729 LOC landing
│   │   ├── error.tsx               UPDATE (slice 13)
│   │   ├── not-found.tsx           UPDATE (slice 13)
│   │   └── (app)/{dashboard,search,favorites}/page.tsx
│   │                                UPDATE (slices 7, 9) — useTranslations
│   ├── components/
│   │   ├── layout/
│   │   │   ├── LanguageSwitcher.tsx        NEW (slice 3)
│   │   │   ├── LanguageSwitcher.test.tsx   NEW (slice 3)
│   │   │   ├── Header.tsx                  UPDATE (slice 6) — switcher slot
│   │   │   ├── Sidebar.tsx                 UPDATE (slice 6) — navItems→t()
│   │   │   ├── ThemeToggle.tsx             UPDATE (slice 6) — sr-only→t()
│   │   │   ├── Footer.tsx                  UPDATE (slice 14) — switcher +
│   │   │   │                                 privacidad note
│   │   │   └── __tests__/Header.test.tsx   UPDATE (slice 6) — bilingual
│   │   ├── dashboard/*                  UPDATE (slice 7) — useTranslations
│   │   ├── jobs/*                       UPDATE (slice 8) — useTranslations
│   │   ├── search/*                     UPDATE (slice 9) — useTranslations
│   │   ├── settings/*                   UPDATE (slice 9) — useTranslations
│   │   ├── auth/*                       UPDATE (slice 12) — useTranslations
│   │   ├── chat/*                       UPDATE (slice 10) — useTranslations
│   │   └── shared/{EmptyState,ErrorState,ExportButton}.tsx
│   │                                    UPDATE (slices 7,9,11)
│   ├── hooks/{useChat,useStats,useJobs,useJobsInfinite,useJobDetail}.ts
│   │                                    UPDATE (slice 10) — t('errors.*')
│   └── test-utils.tsx                  UPDATE (slice 3) — intl wrapper
└── package.json                       UPDATE (slice 1) — add next-intl
```

## Middleware Chain Specification (REQ-I18N-003, REQ-I18N-004, REQ-I18N-016)

**Order**: `intlMiddleware(req)` first, then `updateSession(req)`. Cookies from intl are merged onto the supabase response so `NEXT_LOCALE` survives.

```ts
// frontend/src/middleware.ts
import createIntlMiddleware from 'next-intl/middleware';
import { type NextRequest } from 'next/server';
import { routing } from '@/i18n/routing';
import { updateSession } from '@/lib/supabase/middleware';

const intlMiddleware = createIntlMiddleware(routing);

export async function middleware(request: NextRequest) {
  // Feature-flag escape hatch (D14).
  if (process.env.NEXT_PUBLIC_I18N_ENABLED === 'false') return updateSession(request);

  const intlResponse = intlMiddleware(request);
  const supabaseResponse = await updateSession(request);
  // Copy NEXT_LOCALE cookie from intl response onto supabase response.
  intlResponse.cookies.getAll().forEach(({ name, value }) =>
    supabaseResponse.cookies.set(name, value)
  );
  return supabaseResponse;
}

export const config = {
  matcher: ['/((?!api|_next|.*\\..*).*)'],
};
```

**Supabase `publicPaths` locale-aware** (REQ-I18N-004):

```ts
// frontend/src/lib/supabase/middleware.ts
import { routing } from '@/i18n/routing';

function stripLocalePrefix(path: string): string {
  for (const locale of routing.locales) {
    if (path === `/${locale}`) return '/';
    if (path.startsWith(`/${locale}/`)) return path.slice(locale.length + 1);
  }
  return path;
}

// Existing logic, but matches against the stripped path:
const publicPaths = ['/jobs', '/login', '/signup', '/auth', '/forgot-password', '/reset-password'];
const stripped = stripLocalePrefix(request.nextUrl.pathname);
const isPublic = publicPaths.some((p) => stripped === p || stripped.startsWith(p + '/'));
```

**OAuth callback** (REQ-I18N-016): The callback at `app/auth/callback/route.ts` already reads `next` from query. The Supabase `signInWithOAuth` `redirectTo` must be locale-aware. The `next` value uses sanitized raw paths — we keep the current `${origin}/auth/callback?next=/dashboard` (or `?next=/en/dashboard`) approach and let `sanitizeNext` + the callback pass through. The slice-12 implementation:

```ts
// In login/signup pages — read locale via next-intl's getLocale (RSC)
// or usePathname-based client helper
const locale = useLocale();  // 'es' | 'en'
const dashboardPath = locale === routing.defaultLocale ? '/dashboard' : '/${locale}/dashboard';
await supabase.auth.signInWithOAuth({
  provider: 'google',
  options: { redirectTo: `${location.origin}/auth/callback?next=${dashboardPath}` },
});
```

## Provider Boundary (REQ-I18N-005, REQ-I18N-012)

`app/layout.tsx` is an RSC. It calls `setRequestLocale(locale)` (next-intl 3.x pattern, required for static rendering opt-in), then `getMessages()`, then wraps children in `<NextIntlClientProvider>`. Page audit (current `'use client'` set, all 8 page.tsx files): **all 8 stay client components** because they hold state (auth check, CV upload, search, favorites). They use `useTranslations('Namespace')`. The dashboard RSC opportunity is minimal; no page.tsx gets converted to RSC in v1. Existing `loading.tsx` files (RSC by default) can use `getTranslations` if they render text.

## Messages Namespace Taxonomy

| Namespace | Slice | Source |
|---|---|---|
| `Common` (yes/no/loading/save/cancel/error/empty/retry) | 1 | NEW |
| `Errors` (networkError, notFound, generic) | 1 | NEW |
| `Validation` (emailRequired, passwordMinLength, …) | 5 | FROM authCopy.validation |
| `Auth` (forgot, reset, change, delete, banner, magicLink, globalSignOut) | 5 | FROM authCopy.* (except validation) |
| `Navigation` (dashboard/search/favorites/settings/jobDetail) | 6 | FROM Header ROUTE_META |
| `DateTime` (today, yesterday, hoursAgo, daysAgo, savedOn) | 4 | NEW (replaces "Yesterday" literal) |
| `Dashboard` (stats.*, jobs.totalJobs, jobs.totalJobsWithCount) | 7 | NEW (ICU plurals) |
| `Jobs` (card.title, apply, source, posted, location, count) | 8 | NEW |
| `Search` (placeholder, filter, results) | 9 | NEW |
| `Favorites` (heading, filter, emptyState, count) | 9 | NEW |
| `Settings` (notifications, platform, account) | 9 | NEW |
| `Chat` (fab, panel, placeholder, errors) | 10 | NEW |
| `Landing` (hero, features, cta) | 11 | NEW (extracted from page.tsx) |
| `Footer` (privacy, languageSwitcher, copyright) | 14 | NEW |

**ICU pluralization example** (REQ-I18N-013):

```json
// messages/es.json
{
  "Dashboard": {
    "stats": {
      "totalJobs": "{count, plural, =0 {Sin trabajos} one {# trabajo} other {# trabajos}}"
    }
  }
}

// messages/en.json
{
  "Dashboard": {
    "stats": {
      "totalJobs": "{count, plural, =0 {No jobs} one {# job} other {# jobs}}"
    }
  }
}
```

`useTranslations('Dashboard')` → `t('stats.totalJobs', { count: 5 })` → ES `"5 trabajos"`, EN `"5 jobs"`. Spanish `=0` is included to distinguish "Sin trabajos" (better UX than "0 trabajos").

## LanguageSwitcher Component

```tsx
// frontend/src/components/layout/LanguageSwitcher.tsx
'use client';
import { useLocale, useTranslations } from 'next-intl';
import { usePathname, useRouter } from 'next/navigation';
import { Languages, Check } from 'lucide-react';
import { motion, useReducedMotion } from 'framer-motion';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { routing } from '@/i18n/routing';

const LABELS = { es: 'Español', en: 'English' } as const;
type Locale = 'es' | 'en';

function stripLocalePrefix(path: string): string {
  for (const l of routing.locales) {
    if (path === `/${l}`) return '/';
    if (path.startsWith(`/${l}/`)) return path.slice(l.length + 1);
  }
  return path;
}

export function LanguageSwitcher({ inFooter = false }: { inFooter?: boolean }) {
  const t = useTranslations('Common');
  const locale = useLocale() as Locale;
  const router = useRouter();
  const pathname = usePathname();
  const reducedMotion = useReducedMotion();

  function switchTo(target: Locale) {
    document.cookie = `NEXT_LOCALE=${target}; path=/; max-age=31536000; SameSite=Lax`;
    localStorage.setItem('NEXT_LOCALE', target);
    const stripped = stripLocalePrefix(pathname);
    const nextPath = target === routing.defaultLocale ? stripped : `/${target}${stripped}`;
    router.push(nextPath);
    router.refresh();
  }

  const trigger = inFooter ? (
    <DropdownMenu.Trigger className="inline-flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors">
      <Languages className="h-3.5 w-3.5" />
      {t('switcher.label')}
    </DropdownMenu.Trigger>
  ) : (
    <DropdownMenu.Trigger
      aria-label={t('switcher.label')}
      aria-haspopup="menu"
      className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-background hover:bg-muted transition-colors"
    >
      <Languages className="h-4 w-4" />
    </DropdownMenu.Trigger>
  );

  return (
    <DropdownMenu.Root>
      {trigger}
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={8} asChild>
          <motion.div
            initial={reducedMotion ? { opacity: 0 } : { opacity: 0, scale: 0.95 }}
            animate={reducedMotion ? { opacity: 1 } : { opacity: 1, scale: 1 }}
            transition={reducedMotion ? { duration: 0.15 } : { type: 'spring', bounce: 0.1, duration: 0.15 }}
            className="z-50 min-w-[10rem] overflow-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-md"
          >
            <DropdownMenu.RadioGroup value={locale} onValueChange={(v) => switchTo(v as Locale)}>
              {routing.locales.map((l) => (
                <DropdownMenu.RadioItem
                  key={l}
                  value={l}
                  className="flex cursor-pointer items-center justify-between px-3 py-2 text-sm outline-none data-[highlighted]:bg-muted"
                >
                  <span>{LABELS[l as Locale]}</span>
                  {locale === l && <Check className="h-4 w-4 text-primary" />}
                </DropdownMenu.RadioItem>
              ))}
            </DropdownMenu.RadioGroup>
          </motion.div>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
```

**Variants**: Header (`inFooter={false}`, icon-only `h-9 w-9`, between `AuthStatus` and `ThemeToggle`); Footer (`inFooter={true}`, text + icon, uses `t('switcher.label')`). Mounted in `AppShell` for protected routes and in `Footer` for public routes (no AppShell).

## formatters.ts Migration (REQ-I18N-014)

```ts
// frontend/src/lib/formatters.ts — slice 4
import { formatDistanceToNow, format, isToday, isYesterday } from 'date-fns';
import { es, enUS } from 'date-fns/locale';
import type { Locale } from '@/i18n/routing';  // 'es' | 'en'

export function formatRelativeDate(dateStr: string | null, locale: Locale = 'es'): string {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  const dfnsLocale = locale === 'es' ? es : enUS;
  if (isToday(date)) return formatDistanceToNow(date, { addSuffix: true, locale: dfnsLocale });
  if (isYesterday(date)) return locale === 'es' ? 'Ayer' : 'Yesterday';
  return format(date, locale === 'es' ? "d 'de' MMM 'de' yyyy" : 'MMM d, yyyy');
}

export function formatNumber(n: number, locale: Locale = 'es'): string {
  return new Intl.NumberFormat(locale).format(n);
}
```

**Rollout**: slice 4 lands the new API. Each caller (`StatsCardsRow`, `RightSidebar`, `UserCVCard`, `JobCard`, `CompactJobCard`, `JobDetailContent`) is updated in its own slice (7, 8, 9, 10) to pass `locale` explicitly. Default arg `'es'` preserves current behavior until each callsite is touched.

## authCopy.ts Deprecation Path

- **Slice 5**: copy all 50 strings from `authCopy.ts` into `messages/{en,es}.json` under `Auth` (forgot/reset/change/delete/banner/magicLink/globalSignOut) + `Validation`. Replace the 8 import sites (`DeleteAccountDialog`, `ChangePasswordForm`, `GlobalSignoutButton`, `ForgotPasswordForm`, `MagicLinkForm`, `ResetPasswordForm`, `EmailVerificationBanner`, `validation/authSchemas`, `auth/callback/route` tests, `login/page` test) with `useTranslations('Auth')` / `useTranslations('Validation')`. **Keep `authCopy.ts` present (unused).**
- **Slice 15**: delete `src/lib/authCopy.ts`, `src/lib/__tests__/authCopy.test.ts`, and any test that imports `authCopy` (replace `getByLabelText(authCopy.change.currentPasswordLabel)` with `getByLabelText(/current password|contraseña actual/i)` or use a translation lookup). Verify `git grep "authCopy"` returns zero matches outside the changelog.

## Test Strategy

| Layer | Tool | Coverage |
|---|---|---|
| Unit (vitest) | `@testing-library/react` + new `renderWithIntl` | `LanguageSwitcher.test.tsx` (cookie + URL + re-render, both locales); `Header.test.tsx` bilingual; per-component ICU plural snapshots |
| Integration | `renderWithIntl` + mounted `NextIntlClientProvider` | `<html lang>` attribute (slice 2); `useTranslations` resolves both locales |
| E2E (manual) | curl + Playwright (not in CI per AGENTS.md rule 1) | `Accept-Language: es-ES` → no redirect; `Accept-Language: en-US` → 307 to `/en/dashboard` |
| CI grep audit | ripgrep PCRE2 in `pnpm run lint:i18n` | Zero hardcoded user-facing strings outside `messages/*.json` + `privacidad/page.tsx` + tests |

**`renderWithIntl` wrapper** (added to `src/test-utils.tsx` in slice 3):

```tsx
import { NextIntlClientProvider } from 'next-intl';
import esMessages from '../../messages/es.json';
import enMessages from '../../messages/en.json';

export function renderWithIntl(
  ui: React.ReactElement,
  { locale = 'es', messages = locale === 'es' ? esMessages : enMessages }: { locale?: 'es' | 'en'; messages?: Record<string, unknown> } = {}
) {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem={false}>
        <NextIntlClientProvider locale={locale} messages={messages}>{ui}</NextIntlClientProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
```

## CI grep-audit (AC-12, REQ-I18N-012)

New `pnpm run lint:i18n` script (added in slice 1, enforced from slice 6 onward):

```json
// package.json
"scripts": {
  "lint:i18n": "bash scripts/audit-i18n.sh"
}
```

```bash
#!/usr/bin/env bash
# scripts/audit-i18n.sh
set -euo pipefail
rg -n --type=ts --type=tsx \
  -g '!frontend/messages/**' \
  -g '!frontend/src/app/privacidad/**' \
  -g '!frontend/src/test-utils.tsx' \
  -g '!frontend/src/**/*.test.{ts,tsx}' \
  -g '!frontend/src/**/__tests__/**' \
  -g '!frontend/scripts/**' \
  --pcre2 '(?x)
    (?<=["'"'"'])                  # preceded by quote
    [A-Z][a-z]+(?: [A-Za-z]+)*     # capitalized word(s)
    (?=["'"'"'])                   # followed by quote
  ' frontend/src \
  | rg -v ':\s*\*\s' || { echo "i18n audit failed: hardcoded string in JSX/aria"; exit 1; }
```

Wired as a SEPARATE `pnpm run lint:i18n` step (not bundled into `pnpm run lint`) so failures are attributed clearly. README mentions it as an opt-in for pre-commit. CI runs it on every PR.

## Per-slice design summary (15 slices, stacked-to-main)

| # | Title | LOC | Files touched | Acceptance gate | Risks | Rollback | Depends |
|---|---|---:|---|---|---|---|---|
| 1 | Install next-intl + middleware chain + messages skeleton | 250 | NEW `messages/{en,es}.json`, `src/i18n/{routing,request}.ts`; REWRITE `src/middleware.ts`, `next.config.ts`; UPDATE `lib/supabase/middleware.ts`; UPDATE `package.json` (+next-intl, exact); NEW `scripts/audit-i18n.sh` | typecheck + lint + build pass; `/` still ES; `/en/dashboard` returns 200; `lint:i18n` runs (zero matches) | Wrong middleware order breaks auth | Revert middleware; `NEXT_PUBLIC_I18N_ENABLED=false` kill-switch | — |
| 2 | Root layout dynamic `<html lang>` + provider | 80 | UPDATE `src/app/layout.tsx` (RSC: getLocale/getMessages, NextIntlClientProvider) | `<html lang>` flips ES↔EN; integration test | RSC/client boundary leak | Revert layout to hardcoded `lang="es"` | 1 |
| 3 | LanguageSwitcher widget + Header slot + test wrapper | 300 | NEW `components/layout/LanguageSwitcher.{tsx,test.tsx}`; UPDATE `Header.tsx` (mount slot, ROUTE_META→t()); UPDATE `test-utils.tsx` (renderWithIntl) | vitest passes both locales; cookie + URL + refresh | Switcher breaks Header layout | Hide switcher; revert Header | 1, 2 |
| 4 | `lib/formatters.ts` locale-aware refactor | 120 | UPDATE `lib/formatters.ts`; NEW `lib/__tests__/formatters.test.ts` | tests pass both locales; zero `"en-US"`/`"es-ES"` literals | Default arg hides missing callers | Revert formatters | 1 |
| 5 | authCopy.ts → messages Auth + Validation namespaces | 250 | UPDATE `messages/{en,es}.json` (Auth, Validation); UPDATE 8 import sites; UPDATE `validation/authSchemas.ts`; keep `authCopy.ts` present but unused | All auth/validation tests pass both locales | ESLint stale import warning | Revert imports to authCopy | 1, 2 |
| 6 | Layout chrome (Header, Sidebar, ThemeToggle, AppShell) | 200 | UPDATE Header ROUTE_META, Sidebar navItems, ThemeToggle sr-only, AppShell; UPDATE `Header.test.tsx` (bilingual) | bilingual vitest passes; sr-only text translated | Sidebar active-state broken | Revert per-component | 3, 5 |
| 7 | Dashboard components + RightSidebar + StatsCardsRow + ICU plurals | 300 | UPDATE `components/dashboard/*`; UPDATE `app/(app)/dashboard/page.tsx` | ICU plurals correct; both locales | Mixed-language files produce wrong translations | Revert per-component | 3, 4, 5 |
| 8 | Jobs components (JobCard, CompactJobCard, JobDetailContent, JobDetailAside, JobList, GenerateCVModal, FavoriteButton) | 500 | UPDATE `components/jobs/*`; UPDATE `app/jobs/[id]/page.tsx` (en route uses `useTranslations`, OAuth `redirectTo` locale-aware) | bilingual tests; ICU plurals; OAuth redirect→locale-correct dashboard | Mixed-language JobDetailAside | Revert per-component | 3, 4, 5 |
| 9 | Search + Settings components + favorites page | 500 | UPDATE `components/search/*`, `components/settings/*`, `app/(app)/search/page.tsx`, `app/(app)/favorites/page.tsx`, `lib/validation/authSchemas.ts` (already in 5) | bilingual tests; auth forms via `messages.Auth` | Settings zod schema i18n timing | Revert per-component | 3, 4, 5 |
| 10 | Chat components + `useChat` error i18n | 250 | UPDATE `components/chat/*`; UPDATE `hooks/{useChat,useStats,useJobs,useJobsInfinite,useJobDetail}.ts`; UPDATE `lib/api-client.ts`; UPDATE `app/api/{jobs/[id],cv/generate,jobs/chat/stream,stats}/route.ts` | bilingual tests; toasts localized; zero hardcoded EN errors | Toast appears before NextIntlClientProvider mounts (RSC boundary violation) | Revert useChat to EN errors | 3, 4, 5 |
| 11 | Landing page `app/page.tsx` (729 LOC) | 700 | UPDATE `app/page.tsx`; UPDATE `components/landing/*` if extracted | `/` renders both locales; marketing review | File is `use client` — extra care for `useTranslations` hook call sites | Revert landing to ES only | 1, 2, 3 |
| 12 | Auth pages (login, signup, forgot-password, reset-password) | 400 | UPDATE `app/login/page.tsx`, `app/signup/page.tsx`, `app/(auth)/{forgot-password,reset-password}/page.tsx`, `app/auth/callback/route.ts`; UPDATE `components/auth/*` | bilingual tests; OAuth `redirectTo` uses locale; E2E lands on locale-correct `/dashboard` | OAuth callback path mismatch | Revert per-page | 5, 8 |
| 13 | `error.tsx` + `not-found.tsx` + api error JSON | 80 | UPDATE `app/error.tsx`, `app/not-found.tsx`, API route error JSON via `next-intl/server` | bilingual rendering; API JSON localized | RSC getTranslations in route handlers | Revert per-file | 1, 2 |
| 14 | Privacidad decision (footer note + link) | 20 | UPDATE `components/layout/Footer.tsx`; mount `LanguageSwitcher` (footer variant) | EN footer link works; translated note shown in active locale | — | Hide note | 3 |
| 15 | Remove deprecated `authCopy.ts` + final cleanup | 100 | DELETE `src/lib/authCopy.ts`, `src/lib/__tests__/authCopy.test.ts`; UPDATE auth/settings test files (replace `authCopy.*` references) | `git grep authCopy` = 0; all 4 CI gates green | Stale test references | `git restore src/lib/authCopy.ts` | 5, 6, 9 |
| **Total** | | **~4,050** | | | | | |

## File Changes Summary

| File | Action | Slice |
|---|---|---|
| `frontend/messages/{en,es}.json` | CREATE | 1, then augmented per slice |
| `frontend/src/i18n/{routing,request}.ts` | CREATE | 1 |
| `frontend/src/middleware.ts` | REWRITE | 1 |
| `frontend/src/app/layout.tsx` | UPDATE | 2 |
| `frontend/src/components/layout/LanguageSwitcher.{tsx,test.tsx}` | CREATE | 3 |
| `frontend/src/lib/formatters.ts` | UPDATE | 4 |
| `frontend/src/lib/authCopy.ts` | DELETE | 15 (deprecated in 5) |
| `frontend/src/lib/supabase/middleware.ts` | UPDATE | 1 |
| `frontend/src/next.config.ts` | UPDATE | 1 |
| `frontend/src/test-utils.tsx` | UPDATE | 3 |
| `frontend/package.json` | UPDATE (add next-intl, scripts) | 1, 3 |
| `frontend/src/app/page.tsx` | UPDATE (729 LOC) | 11 |
| `frontend/src/app/error.tsx`, `not-found.tsx` | UPDATE | 13 |
| `frontend/src/app/{login,signup}/page.tsx`, `app/auth/callback/route.ts` | UPDATE | 12 |
| `frontend/src/components/layout/{Header,Sidebar,ThemeToggle,AppShell,Footer}.tsx` | UPDATE | 6, 14 |
| `frontend/src/components/{dashboard,jobs,search,settings,auth,chat,shared}/*` | UPDATE | 7, 8, 9, 10, 12 |
| `frontend/src/hooks/{useChat,useStats,useJobs,useJobsInfinite,useJobDetail}.ts` | UPDATE | 10 |
| `frontend/src/app/api/{jobs/[id],cv/generate,jobs/chat/stream,stats}/route.ts` | UPDATE | 10, 13 |
| `frontend/src/lib/validation/authSchemas.ts`, `lib/api-client.ts` | UPDATE | 5, 10 |
| `frontend/scripts/audit-i18n.sh` | CREATE | 1 |

## Interfaces / Contracts

```ts
// frontend/src/i18n/routing.ts
export const routing = defineRouting({
  locales: ['es', 'en'] as const,
  defaultLocale: 'es',
  localePrefix: 'as-needed',
  localeDetection: true,
});
export type Locale = 'es' | 'en';

// frontend/src/i18n/request.ts
export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = (routing.locales as readonly string[]).includes(requested ?? '')
    ? (requested as Locale)
    : routing.defaultLocale;
  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});

// frontend/src/lib/supabase/middleware.ts (signature unchanged; publicPaths stripped via helper)
export async function updateSession(request: NextRequest): Promise<NextResponse>;

// frontend/src/lib/formatters.ts (slice 4)
export function formatRelativeDate(dateStr: string | null, locale?: Locale): string;
export function formatNumber(n: number, locale?: Locale): string;
export function getPlatformColorClass(platform: string): string;  // unchanged
```

## Migration / Rollout

- **No data migration** — cookie + `localStorage` only.
- **No DB writes** — locale persistence is client-side.
- **Cutover** = the moment slice 15 lands. After that, the i18n layer is mandatory for new UI; pre-existing literals are gone.
- **Pre-cutover**: each slice lands in order; CI green after each.
- **Feature-flag escape hatch** (D14): `NEXT_PUBLIC_I18N_ENABLED=false` skips `intlMiddleware` in `middleware.ts` and returns `updateSession(request)` unchanged. Documented in `frontend/.env.example` with default `true`.

## Open Questions

**None — proceed to `sdd-tasks`.** All architectural decisions resolved:
- Library, routing policy, default locale, middleware order, message storage, provider boundary, pluralization contract, switcher primitive + persistence + variants, formatters API, authCopy deprecation timeline, CI grep-audit shape, and per-slice ordering all locked.
- Five open follow-ups (F1 privacidad translation, F2 backend currency schema, F3 client-side salary parsing, F4 additional locales, F5 ICU lint rule) are explicitly deferred per proposal §"Out-of-Scope Follow-Ups" — not blockers.

## Architectural decisions the design had to make that the proposal didn't specify

1. **`stripLocalePrefix` regex vs. helper function** (D5): proposal said "small stripper helper"; design picks the **iteration-over-locales helper** (not regex) because it's easier to read in code review and tests are simpler to write. Alternative regex `^/(en|es)(/|$)` was considered and rejected for readability.
2. **`createNextIntlPlugin` wrapping in `next.config.ts`** (not in proposal): required by next-intl to auto-call `getRequestConfig`. Standard pattern; design documents it explicitly under D1 + module layout.
3. **`setRequestLocale(locale)` call in RSC layout** (REQ-I18N-005 addition): next-intl 3.x requires this call when static rendering is enabled. The proposal didn't mention it; the spec REQ doesn't either — but it's a hard requirement to avoid "static rendering not enabled" warnings. Documented in §Provider Boundary.
4. **Footer-mounted switcher is a separate component variant**, not a duplicate (REQ-I18N-007 elaboration): the design uses one `LanguageSwitcher` component with an `inFooter: boolean` prop instead of two parallel components (D11). Avoids duplication; single source of truth for menu items + animation.
5. **`formatters.ts` default arg `'es'`** (REQ-I18N-014 safety net): every function gets `locale: Locale = 'es'` so callers that haven't been migrated yet still work. Each slice migrates its callers; the default keeps `pnpm run build` green between slices.
6. **Cookie `SameSite=Lax`** (D9 elaboration): proposal didn't specify SameSite; design adds `Lax` because OAuth `redirectTo` flow crosses origins; `Strict` would block the post-OAuth cookie.
7. **Spanish `=0` ICU variant** (D8 elaboration): `=0 {Sin trabajos}` distinct from `other {# trabajos}`. Better UX than `"0 trabajos"`. English gets `=0 {No jobs}`.
8. **`pnpm run lint:i18n` is separate from `pnpm run lint`** (D15 elaboration): proposal said "grep-audit in CI"; design puts it in its own script so failure attribution is clear and the lint budget is unaffected.
9. **`Router.refresh()` after locale switch** (D9 detail): not just `router.push(nextPath)` — `refresh()` re-renders RSC tree so the layout's `<html lang>` and `getTranslations` calls update. Documented explicitly to avoid the common bug where only client components update.
10. **`page.tsx` files stay `'use client'`** (REQ-I18N-005 application): the proposal mentioned RSC `getTranslations` as an option; the design audit confirms all 8 page.tsx files currently use `'use client'` (auth check, CV upload, search state, favorites state) and **none get converted to RSC in v1** — every page uses `useTranslations`. Saves a v1 refactor; can revisit in a follow-up.