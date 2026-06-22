# jobs-finder — frontend

Next.js 15 App Router frontend for the jobs-finder monorepo.

## Stack

- Next.js 15.5.19 (App Router, RSC, Route Handlers)
- React 19.1.0
- TypeScript 5.9.2 (strict + `noUncheckedIndexedAccess`)
- Tailwind CSS 3.4.17
- shadcn/ui (slate / default)
- next-intl 4.13.0 (internationalization — see below)
- @tanstack/react-query 5.101.0 (server-state)
- next-themes 0.4.6 (dark/light mode)
- sonner 2.0.7 (toasts)
- framer-motion 11.15.0 (animations)

## Commands

```bash
pnpm install
pnpm run dev          # http://localhost:3000
pnpm run typecheck    # tsc --noEmit
pnpm run lint         # next lint
pnpm run lint:i18n    # i18n grep audit (see "Internationalization")
pnpm run test         # vitest run --passWithNoTests
pnpm run build        # production build
```

The four CI gates the project enforces on every PR are
`typecheck`, `lint`, `test`, `build` (in that order). `lint:i18n` is
wired as a separate step from slice 6 onward.

## Internationalization

The frontend ships bilingual (Spanish default, English optional) via
[next-intl](https://next-intl.dev/).

### Locales

| Locale | Default | URL prefix |
|--------|---------|------------|
| `es`   | yes     | none — `/dashboard` resolves to Spanish |
| `en`   | no      | required — `/en/dashboard` |

Spanish is the default locale and keeps the current unprefixed URLs
working with zero regression (`localePrefix: 'as-needed'`). English
always carries the `/en/...` prefix.

### How locale is detected

The middleware chain in `src/middleware.ts` reads the locale in this
priority order:

1. `NEXT_LOCALE` cookie (set by the `LanguageSwitcher`).
2. `Accept-Language` request header.
3. Default — `'es'`.

### Killing the i18n layer (escape hatch)

Set `NEXT_PUBLIC_I18N_ENABLED=false` in `.env.local` to short-circuit
the `next-intl` middleware and route requests straight to the Supabase
`updateSession` layer. The app behaves exactly as it did before slice
1. Documented in `.env.example`.

### Messages

All user-facing strings live in `frontend/messages/{en,es}.json`,
namespaced by feature (`Common`, `Errors`, `Auth`, `Validation`,
`Navigation`, `Dashboard`, `Jobs`, `Search`, `Favorites`, `Settings`,
`Chat`, `Landing`, `Footer`).

Add a new key in BOTH `en.json` AND `es.json`. Consume via
`useTranslations('Namespace')` in client components or
`getTranslations('Namespace')` in RSC.

### Pluralization

ICU MessageFormat is used for any count-dependent string so both
languages stay grammatically correct:

```jsonc
// messages/es.json
"Dashboard": {
  "stats": {
    "totalJobs": "{count, plural, =0 {Sin trabajos} one {# trabajo} other {# trabajos}}"
  }
}
```

```jsonc
// messages/en.json
"Dashboard": {
  "stats": {
    "totalJobs": "{count, plural, =0 {No jobs} one {# job} other {# jobs}}"
  }
}
```

### Auth strings

All auth-related copy lives in `messages/{en,es}.json` under the
`Auth` and `Validation` namespaces. Use `useTranslations('Auth.<area>')`
in auth/settings components. The legacy `src/lib/authCopy.ts` file
is marked `@deprecated` and will be deleted once the test files
migrate off the `authCopy.X.Y` lookups. New code MUST use
`useTranslations`.

`useTranslations('Dashboard').then(t => t('stats.totalJobs', { count: 5 }))`
→ ES `"5 trabajos"` · EN `"5 jobs"`.

### i18n grep audit (`pnpm run lint:i18n`)

A heuristic ripgrep-based audit (`scripts/audit-i18n.sh`) flags quoted
capitalized phrases that look like untranslated user-facing strings.
Excludes: the messages files themselves, the Spanish-only
`app/privacidad/` legal page, test files, and the test-utils wrapper.

The audit is intentionally permissive during the migration — matches
are expected until slice 15 lands. From slice 6 onward, CI runs it as
a separate step so failure attribution is clear.