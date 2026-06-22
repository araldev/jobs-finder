# Design: `feat-frontend-i18n-locale-prefix-urls`

> **Change**: `feat-frontend-i18n-locale-prefix-urls` • **Phase**: SDD design (post-spec, pre-tasks)
> **Stack**: Next.js 15 App Router · next-intl 4.13.0 · TS strict · vitest
> **Mode**: hybrid (engram canonical + openspec mirror)
> **Mirror**: `openspec/changes/feat-frontend-i18n-locale-prefix-urls/design.md`
> **Upstream**: v1 design at `openspec/changes/feat-frontend-i18n/design.md` (v2 = 4 logic paths re-introduced + 1 config flip)
> **Spec reference**: `openspec/specs/frontend-i18n/spec.md` v2 delta (lines 320–408) + REQ-I18N-002, REQ-I18N-016, REQ-I18N-020, REQ-I18N-021

## Technical Approach

Flip `frontend/src/i18n/routing.ts:29` from `localePrefix: 'never'` → `'as-needed'` (the one-line unlock). Re-introduce the **4 logic paths** v1's slice-16 simplification removed: (1) `LanguageSwitcher.switchTo()` calls `usePathname() + stripLocalePrefix() + router.push()` instead of just `router.refresh()`; (2) `supabase/updateSession` detects locale from the ORIGINAL `request.nextUrl.pathname` and prefixes the auth-bounce target (`/en/dashboard` no-auth → `/en/login`, not `/login`); (3) OAuth callback reads `NEXT_LOCALE` cookie + applies `localizePath(next, locale)` to prefix the redirect target; (4) the now-active `stripLocalePrefix` helper is treated as production-critical (was a defensive no-op in v1). The middleware chain (`middleware.ts:50–57`) needs **zero changes** — `intlResponse` → `updateSession(request, intlResponse)` already preserves the rewrite header under both REWRITE and REDIRECT cases (v1 design D4). `frontend/src/app/[locale]/layout.tsx` and `frontend/src/i18n/request.ts` need **zero changes** — already locale-segment-aware from slice 16.

## Architecture Decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Locale prefix mode | `as-needed` | D2 in v1 design; user explicitly requested canonical SaaS EN URLs while keeping ES at root. `always` would break v1 bookmarks; `never` keeps cookie-only (the v1 compromise being closed). |
| D2 | Locale resolution priority | URL prefix → cookie → `Accept-Language` → `defaultLocale` | Verified against `next-intl@4.x` `resolveLocale.tsx` Prio 1. AC-4 in proposal corrected: URL wins over cookie. |
| D3 | Locale detection in `updateSession` | Iterate `routing.locales` over the **ORIGINAL** `request.nextUrl.pathname` (not the rewritten one) | The rewrite is internal (`x-middleware-rewrite`); the user's URL is still `/en/dashboard`. REQ-I18N-020 mandates `/en/login`, not `/login`. |
| D4 | OAuth callback locale source | `NEXT_LOCALE` cookie only (no `Accept-Language` parsing) | The cookie is set by the login page (locale-aware) before OAuth starts; parsing `Accept-Language` server-side is brittle for non-browser clients. Unknown cookie → default `es` (no prefix). |
| D5 | `localizePath` idempotency | Skip re-prefixing when `path` already matches `/<locale>/...` | Belt-and-suspenders against double-prefix bugs if a `?next=` value is constructed by a future client that already includes `/en/`. |
| D6 | Test mock contract | Add `push: vi.fn()` to `useRouter()` mock; make `usePathname` a `let` variable per test | v1 only tested `router.refresh()` (no `router.push` assertions). v2 MUST assert `router.push` was called with the prefixed path. R7 in explore. |
| D7 | No `middleware.ts` change | The `baseResponse` chain is correct as-is | Verified in explore §1.3: rewrite header survives for REWRITE; redirects in `updateSession` carry their own URL. Slice 16 already built this. |
| D8 | PR shape | 1 PR (≤ 400 LOC) — well under D1 budget | ~185 LOC across 8 files per explore §7. Single coherent work unit (URL-prefix mode is atomic). |
| D9 | Commit shape | 2 commits per `work-unit-commits`: (1) routing flag flip + middleware test additions (independent verifiable unit), (2) LanguageSwitcher + callback + supabase middleware + their tests (logic re-add) | Each commit passes the 4 CI gates standalone; rollback can stop at the config flip without touching the logic re-adds. |

## Data Flow

```
Browser GET /en/dashboard
       │
       ▼
┌─ frontend/src/middleware.ts ──────────────────────────────────┐
│  1. intlResponse = createIntlMiddleware(routing)(request)     │
│     - URL prefix resolves locale=en (Prio 1, no cookie check) │
│     - REWRITES to /es/dashboard (header x-middleware-rewrite) │
│     - sets NEXT_LOCALE=en cookie (matches URL)                │
│                                                                │
│  2. updateSession(request, intlResponse)                       │
│     - request.nextUrl.pathname = '/en/dashboard' (ORIGINAL)   │
│     - detectLocale(originalPathname) → '/en'                  │
│     - stripLocalePrefix('/en/dashboard') → '/dashboard'       │
│     - isProtected('/dashboard') && !user → redirect /en/login │
│       (locale-aware target, baseResponse discarded)            │
└────────────────────────────────────────────────────────────────┘
       │ (no user → redirected)
       ▼
Browser GET /en/login  →  intlMiddleware rewrites  →  /es/login
       │
       ▼
[locale]/login/page.tsx renders ES login form (locale=en forced by URL)
```

For an authenticated user on `/en/login`: middleware sees the `/en/` prefix, `strippedPath === '/login'` matches public path bypass (auth user), then the second branch (lines 99-106) redirects `/en/login` (auth) → `/en/dashboard`. URL preserved, locale intact.

## File Changes

| File | Action | LOC | Description |
|---|---|---:|---|
| `frontend/src/i18n/routing.ts` | Modify | ~5 | Line 29: `localePrefix: "never"` → `"as-needed"`. JSDoc: drop "v1 pragmatic mode" framing; document URL prefix policy. |
| `frontend/src/middleware.ts` | NO CHANGE | 0 | `baseResponse` chain already handles v2 REWRITE + REDIRECT. JSDoc already references `as-needed`. |
| `frontend/src/app/[locale]/layout.tsx` | NO CHANGE | 0 | Already locale-segment-aware (`generateStaticParams`, `<html lang>`). |
| `frontend/src/i18n/request.ts` | NO CHANGE | 0 | Already reads `requestLocale` from `[locale]` segment. |
| `frontend/src/components/layout/LanguageSwitcher.tsx` | Modify | ~20 | Re-add `usePathname` import, `stripLocalePrefix` helper (local), build `nextPath`, call `router.push(nextPath)` before `router.refresh()`. Update JSDoc. |
| `frontend/src/lib/supabase/middleware.ts` | Modify | ~25 | Add `detectLocalePrefix(originalPathname)` helper (~10 LOC); modify redirect at lines 92-95 and 99-105 to use `${localePrefix}/login` and `${localePrefix}/dashboard`. Update JSDoc to drop "defensive no-op" framing. |
| `frontend/src/app/auth/callback/route.ts` | Modify | ~30 | Add `readLocalePrefix(request)` + `localizePath(path, localePrefix)` helpers; apply to `?next=` redirect and `/login?error=` fallback. |
| `frontend/src/components/layout/LanguageSwitcher.test.tsx` | Modify | ~15 | `useRouter()` mock adds `push: vi.fn()`; `usePathname` becomes a `let` per test; 3 tests assert `routerPushMock.toHaveBeenCalledWith(...)`. |
| `frontend/src/app/auth/callback/__tests__/route.test.ts` | Modify | ~50 | Rename `describe("...v1 contract")` → `...v2 contract`; update 6 locale tests to expect `/en/...` prefixes; add 1 test for `localizePath` idempotency (don't double-prefix). |
| `frontend/src/lib/supabase/__tests__/middleware.test.ts` | Modify | ~40 | Add 4 tests: `/en/dashboard` no-auth → 307 `/en/login`; `/en/login` auth → 307 `/en/dashboard`; `/en/forgot-password` no-auth → 200; `/dashboard` auth-no-locale-cookie → 307 `/login` (regression guard). |
| **Total** | | **~185** | **8 files modified, 0 new** |

## Interfaces / Contracts

### `LanguageSwitcher.switchTo(target: Locale)` (re-introduced)

```tsx
// frontend/src/components/layout/LanguageSwitcher.tsx
"use client";
import { useLocale, useTranslations } from "next-intl";
import { usePathname, useRouter } from "next/navigation";  // ← re-add usePathname
import { routing, LOCALE_LABELS, type Locale } from "@/i18n/routing";

function stripLocalePrefix(path: string): string {
  for (const l of routing.locales) {
    if (path === `/${l}`) return "/";
    if (path.startsWith(`/${l}/`)) return path.slice(l.length + 1);
  }
  return path;
}

export function LanguageSwitcher({ inFooter = false }: LanguageSwitcherProps) {
  const t = useTranslations("Common");
  const locale = useLocale() as Locale;
  const router = useRouter();
  const pathname = usePathname();                              // ← re-add
  const reducedMotion = useReducedMotion();

  function switchTo(target: Locale) {
    document.cookie = `NEXT_LOCALE=${target}; path=/; max-age=31536000; SameSite=Lax`;
    try { localStorage.setItem("NEXT_LOCALE", target); } catch {}
    const stripped = stripLocalePrefix(pathname);              // ← re-add
    const nextPath = target === routing.defaultLocale          // ← re-add
      ? stripped
      : `/${target}${stripped}`;
    router.push(nextPath);                                     // ← re-add
    router.refresh();                                          // keep (RSC re-render)
  }
  // ... trigger + DropdownMenu JSX unchanged from v1 ...
}
```

### `updateSession` locale-aware redirect (D3)

```ts
// frontend/src/lib/supabase/middleware.ts
function detectLocalePrefix(originalPathname: string): string {
  for (const l of routing.locales) {
    if (originalPathname === `/${l}` || originalPathname.startsWith(`/${l}/`)) {
      return l === routing.defaultLocale ? "" : `/${l}`;
    }
  }
  return "";
}

// Inside updateSession(...):
const localePrefix = detectLocalePrefix(request.nextUrl.pathname);  // ORIGINAL, not rewritten
const strippedPath = stripLocalePrefix(request.nextUrl.pathname);
const isPublic = publicPaths.some(/* unchanged */);

// Auth bounce — REQ-I18N-020: locale-aware target
if (!user && !isPublic && !isRoot && !isApi) {
  const url = request.nextUrl.clone();
  url.pathname = `${localePrefix}/login`;
  url.search = "";  // v1 didn't set ?error=; preserve v1's behavior to minimize churn
  return NextResponse.redirect(url);
}

// Authenticated user on login → dashboard (locale preserved)
if (user && (strippedPath === "/login" || strippedPath.startsWith("/login/"))) {
  const url = request.nextUrl.clone();
  url.pathname = `${localePrefix}/dashboard`;
  return NextResponse.redirect(url);
}
```

**Why ORIGINAL pathname, not stripped**: `request.nextUrl.pathname` is the URL the browser actually requested (`/en/dashboard`). The internal rewrite (`x-middleware-rewrite: /es/dashboard`) is in `intlResponse.headers`, NOT in `request.nextUrl`. Using the stripped path (`/dashboard`) would lose the `/en/` signal and break REQ-I18N-020.

### OAuth callback `localizePath` (D4, D5)

```ts
// frontend/src/app/auth/callback/route.ts
import { routing, type Locale } from "@/i18n/routing";

function readLocalePrefix(request: NextRequest): string {
  const cookie = request.cookies.get("NEXT_LOCALE")?.value;
  if (cookie && (routing.locales as readonly string[]).includes(cookie)) {
    return cookie === routing.defaultLocale ? "" : `/${cookie}`;
  }
  return "";  // default locale (no prefix)
}

function localizePath(path: string, localePrefix: string): string {
  if (!localePrefix) return path;
  if (path === "/") return localePrefix;
  // D5: idempotent — skip if already prefixed
  for (const l of routing.locales) {
    if (path === `/${l}` || path.startsWith(`/${l}/`)) return path;
  }
  return `${localePrefix}${path}`;
}

export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = sanitizeNext(searchParams.get("next"));     // validated, unprefixed
  const localePrefix = readLocalePrefix(request);

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (error) {
      return NextResponse.redirect(
        `${origin}${localizePath("/login", localePrefix)}?error=${encodeURIComponent(error.message)}`,
      );
    }
  }
  return NextResponse.redirect(`${origin}${localizePath(next, localePrefix)}`);
}
```

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit (vitest) — `LanguageSwitcher.test.tsx` | (a) Click "English" on `/dashboard` → `routerPushMock("/en/dashboard")` + `routerRefreshMock()` called. (b) Click "Español" on `/en/dashboard` → `routerPushMock("/dashboard")` + `routerRefreshMock()`. (c) Click "English" on `/en/login` → `routerPushMock("/en/login")` (idempotent). (d) Keyboard nav still triggers `router.push` + `router.refresh`. | Mock `useRouter` with `{ refresh, push }`; mock `usePathname` with a `let pathnameMock = "/dashboard"` rebindable per test. |
| Unit (vitest) — `auth/callback/__tests__/route.test.ts` | (a) 6 v1 locale tests migrated: `NEXT_LOCALE=en` → `/en/dashboard`, `/en/reset-password`, `/en/jobs/123`, `/en/login?error=…`. (b) New: `?next=/en/dashboard` + no cookie → `/en/dashboard` (idempotency, D5). (c) `NEXT_LOCALE=fr` unknown → still `/dashboard` (graceful fallback). | Existing `makeRequest({ locale })` already injects cookie. |
| Unit (vitest) — `supabase/__tests__/middleware.test.ts` | (a) `/en/dashboard` no-auth → 307 `/en/login`. (b) `/en/login` auth → 307 `/en/dashboard`. (c) `/en/forgot-password` no-auth → 200 (public path, D3 stripping still works). (d) `/dashboard` auth-no-locale-cookie → 307 `/login` (regression guard for default-locale path). | Pass `pathname` directly to `runMiddleware`; assert `res.headers.get("location")`. |
| Manual smoke (NOT in CI, AGENTS.md rule 1) | curl matrix per explore §5 (10 rows including AC-4 correction). | `curl -i -H "Accept-Language: en-US" http://localhost:3000/dashboard` |

**Test count delta**: +10 tests (3 switcher + 1 callback idempotency + 4 supabase middleware + 2 callback migrations = net new). No deletions; v1 cookie-only assertions become the regression floor.

## Per-file Implementation Steps (Apply Input)

1. **`frontend/src/i18n/routing.ts`** — single-line flip:
   - Line 29: `"never"` → `"as-needed"`
   - Lines 6-22 JSDoc: rewrite to "v2: URL-prefix mode (`localePrefix: 'as-needed'`) — default locale `es` URLs stay unprefixed; non-default `en` URLs are prefixed. Closes REQ-I18N-002. See `feat-frontend-i18n-locale-prefix-urls` for rationale."

2. **`frontend/src/components/layout/LanguageSwitcher.tsx`** — re-add `usePathname` + `stripLocalePrefix` + `router.push`:
   - Line 4: `import { useRouter } from "next/navigation"` → `import { usePathname, useRouter } from "next/navigation"`
   - Lines 16-30 JSDoc: add "v2 navigates to the locale-prefixed URL (`router.push`) before `router.refresh()` (REQ-I18N-021)."
   - Lines 37-49 `switchTo()`: replace with the v2 version from §Interfaces above.

3. **`frontend/src/lib/supabase/middleware.ts`** — locale-aware redirect:
   - Lines 5-19 JSDoc: rewrite to drop "defensive no-op" framing.
   - After line 26 (end of `stripLocalePrefix`), add `detectLocalePrefix` helper (~10 LOC).
   - Line 80 area: add `const localePrefix = detectLocalePrefix(request.nextUrl.pathname);`
   - Lines 93-95: `url.pathname = "/login"` → `url.pathname = \`${localePrefix}/login\``
   - Lines 103-105: `url.pathname = "/dashboard"` → `url.pathname = \`${localePrefix}/dashboard\``
   - Lines 67-71 JSDoc: drop the "v1 uses localePrefix: 'never'" block.

4. **`frontend/src/app/auth/callback/route.ts`** — re-add helpers + apply:
   - Lines 1-22 JSDoc: rewrite to describe v2 contract.
   - Add `readLocalePrefix` + `localizePath` helpers after imports.
   - Line 24 area: add `const localePrefix = readLocalePrefix(request);`
   - Line 33: `${origin}/login?error=...` → `${origin}${localizePath("/login", localePrefix)}?error=...`
   - Line 38: `${origin}${next}` → `${origin}${localizePath(next, localePrefix)}`

5. **`frontend/src/components/layout/LanguageSwitcher.test.tsx`** — mock + assertions:
   - Line 6: add `const routerPushMock = vi.fn();`
   - Lines 8-13: mock `useRouter: () => ({ refresh: routerRefreshMock, push: routerPushMock })`; replace `usePathname: () => "/dashboard"` with `let pathnameMock = "/dashboard"; usePathname: () => pathnameMock`.
   - `beforeEach` (line 28): add `routerPushMock.mockClear(); pathnameMock = "/dashboard";`
   - Lines 44-56: add `expect(routerPushMock).toHaveBeenCalledWith("/en/dashboard")` after the refresh assertion.
   - Lines 58-68: add `pathnameMock = "/en/dashboard"` before render; add `expect(routerPushMock).toHaveBeenCalledWith("/dashboard")`.
   - Lines 70-84: add `expect(routerPushMock).toHaveBeenCalled()` after the refresh assertion.

6. **`frontend/src/app/auth/callback/__tests__/route.test.ts`** — migrate + add:
   - Line 126: rename describe block from "...v1 contract" → "...v2 contract".
   - Lines 127-144: update 3 tests to expect `/en/...` URLs when cookie=en.
   - Lines 145-155: keep but update expected URLs.
   - Lines 157-164: keep but update expected URLs.
   - Lines 166-177: update expected URL to `/en/login?error=...`.
   - Lines 179-190: keep (default-locale fallback unchanged).
   - Add: idempotency test — `?next=/en/dashboard` no cookie → `/en/dashboard` (D5).

7. **`frontend/src/lib/supabase/__tests__/middleware.test.ts`** — 4 new tests:
   - Add: `/en/dashboard` no-auth → 307 + `/en/login`.
   - Add: `/en/login` auth → 307 + `/en/dashboard`.
   - Add: `/en/forgot-password` no-auth → 200 (regression: stripping still works).
   - Add: `/dashboard` no-locale-cookie auth path is the existing v1 assertion (regression guard).

8. **No changes** to: `frontend/src/middleware.ts`, `frontend/src/app/[locale]/layout.tsx`, `frontend/src/i18n/request.ts`, any `frontend/messages/*.json`, any `frontend/src/app/[locale]/**/page.tsx`.

## Migration / Rollout

- **No data migration** — `NEXT_LOCALE` cookie and `localStorage` are client-side.
- **Cutover** = merge to `main`. Users with the cookie set will see a 307 canonical redirect on their next request to a non-prefixed URL (per AC-5). Users who bookmarked `/en/dashboard` (already supported by the `[locale]/` segment since slice 16) will see correct rendering.
- **Pre-commit gates** (per AGENTS.md): `cd frontend && pnpm run typecheck && pnpm run lint && pnpm run test && pnpm run build`.
- **Feature-flag escape hatch** (v1 D14): `NEXT_PUBLIC_I18N_ENABLED=false` in `frontend/.env.local` short-circuits intl → revert to cookie-only mode in < 2 minutes, no redeploy. Under v2 the kill-switch preserves v1 behavior identically (still bypasses prefix logic).
- **Cookie wipe**: clearing `NEXT_LOCALE` + `localStorage` → `Accept-Language` → root URLs (default `es`).

## Open Questions

**None.** All design decisions settled by:
- v1 design (D1–D15) at `openspec/changes/feat-frontend-i18n/design.md` §3, §4, §6, §10.
- v1 archive-report F9 follow-up.
- Explore §1.1 verification of `next-intl@4.x` `resolveLocale.tsx` priority order.
- Explore §3.1 (Option A) chosen over §3.2/§3.3 alternatives.

The brief correction on smoke-test row #4 (URL prefix wins over cookie, not vice versa) is incorporated in AC-4, REQ-I18N-002, and SCN-I18N-013.