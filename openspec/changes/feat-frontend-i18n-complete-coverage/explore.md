# Exploration: `feat-frontend-i18n-complete-coverage`

> **Phase**: SDD explore (Pace A2 / B1 hybrid / C4 / D1)
> **Project**: jobs-finder (frontend workspace)
> **Date**: 2026-06-22
> **Change base**: `main`
> **Mirror**: `openspec/changes/feat-frontend-i18n-complete-coverage/explore.md`

---

## 1. Goal

Close 4 of the 7 i18n follow-ups (F2, F3, F5, F6) documented in the v1 archive
and the v2 cycle, in one bundle. F1 (`authCopy.ts` deletion), F4 (landing EN
marketing copy — needs marketing review), and F7 (spec deltas) are out of scope.

---

## 2. Current State (verified against the live tree on `main`)

### 2.1 i18n infrastructure already shipped

- `messages/en.json` and `messages/es.json` are 438 lines each, with 15
  top-level namespaces (`Common`, `Errors`, `Navigation`, `Auth`, `Validation`,
  `Dashboard`, `Jobs`, `Search`, `Favorites`, `Settings`, `Chat`, `JobsErrors`,
  `Landing`, `Footer`).
- `[locale]/layout.tsx` wraps every locale-aware page in
  `<NextIntlClientProvider>` with `getMessages()`.
- Locale switching works (`localePrefix: 'as-needed'` after v2).
- 3 auth forms (`MagicLinkForm`, `ForgotPasswordForm`, `ResetPasswordForm`)
  already use `useTranslations('Auth.*')` (slice 5).
- The `Auth` namespace has both `Auth.signup` and `Auth.login` shapes defined
  (lines 150–173 of both message files).
- `formatRelativeDate(date, locale)` already accepts a `Locale` arg but
  callers in `JobDetailAside` do NOT pass it — falls back to ES.

### 2.2 What is still hardcoded

| # | File | Hardcoded strings | Notes |
|---|------|-------------------|-------|
| **F2** | `components/jobs/JobDetailContent.tsx` | 1 EN literal (`"Description"` line 210) | `Jobs.detail.description` already covers it in both languages |
| **F2** | `components/jobs/JobDetailAside.tsx` | 4 EN literals + 1 ES literal + locale-aware formatter not wired | All have reuse candidates |
| **F2** | `components/jobs/JobList.tsx` | 0 in this file | But `EmptyState` defaults it renders ARE hardcoded EN (see Risk #5) |
| **F2** | `components/jobs/GenerateCVModal.tsx` | ~18 ES literals (incl. nested JSX) | Largest single piece of work in the cycle |
| **F2** | `components/jobs/FavoriteButton.tsx` | 0 | **Already fully translated** — see Risk #6 below |
| **F3** | `hooks/useChat.ts` | 3 EN error literals (lines 175, 209, 336) | All rendered by `AssistantMessage.tsx` |
| **F5** | `app/[locale]/signup/page.tsx` | ~13 ES literals | Client component, trivial `useTranslations` migration |
| **F5** | `app/[locale]/(auth)/forgot-password/page.tsx` | 0 | Already a 1-liner wrapper around the translated form |
| **F5** | `app/[locale]/(auth)/reset-password/page.tsx` | 0 (uses deprecated `authCopy`) | Server component — needs `getTranslations` not `useTranslations` |
| **F6** | `app/[locale]/layout.tsx` | n/a — Footer renders globally | Architectural fix |

---

## 3. F2: 5 jobs components — file-by-file breakdown

### 3.1 `JobDetailContent.tsx` (221 LOC)

| # | Line | Hardcoded | Action | Namespace |
|---|------|-----------|--------|-----------|
| 1 | 210 | `"Description"` | Replace with `t("description")` | **`Jobs.detail.description`** (already exists: ES `"Descripción"`, EN `"Description"`) |

**LOC**: 3 lines of change + 1 unit test addition.
**New keys needed**: **0** — reuse existing.

> **Non-string concern**: the `STANDALONE_HEADERS` / `HEADER_WITH_PUNCTUATION`
> / `ITEM_STARTERS` / `LIST_TO_HEADER` constants at the top of the file are
> Spanish-only enrichment heuristics for scraped `job.description`. These are
> NOT UI copy and must remain as-is — they're data-shaping regex, not
> translations.

### 3.2 `JobDetailAside.tsx` (78 LOC)

| # | Line | Hardcoded | Action | Namespace |
|---|------|-----------|--------|-----------|
| 1 | 21 | `"Source"` (label) | Replace | **`Jobs.card.source`** (already exists) |
| 2 | 32 | `"Posted"` (label) | Replace | **`Jobs.detail.postedLabel`** (NEW) |
| 3 | 36 | `formatRelativeDate(job.posted_at)` — no locale | Pass locale | `formatRelativeDate(job.posted_at, locale)` |
| 4 | 45 | `"Location"` (label) | Replace | **`Jobs.card.location`** (already exists) |
| 5 | 60 | `"View Original"` (button) | Replace | **`Jobs.detail.viewOriginal`** (NEW) |
| 6 | 71 | `"Generar CV adaptado"` (trigger button) | Replace | **`Jobs.modal.generate`** (already exists) |

**LOC**: ~25 lines of change + 1 unit test for the locale-aware date.
**New keys needed**: 2 (`Jobs.detail.postedLabel`, `Jobs.detail.viewOriginal`).

### 3.3 `JobList.tsx` (101 LOC)

- **0 hardcoded UI strings** in this file itself — it only composes
  `JobCard` and `EmptyState` and renders skeletons.
- The empty-state copy shown via `<EmptyState variant={...} />` defaults to
  English strings in `EmptyState.tsx` lines 16–37 (`"No results found"`, etc.).
  Those defaults are used by `JobList` AND by `dashboard`, `search`, and
  `favorites` pages (4 callers).

**Two valid approaches** (see Risk #5):

- **A (recommended)**: thread translated `title`/`description` props from
  `JobList` (and the other 3 callers) using `useTranslations('Jobs.emptyState.*')`.
  Per-caller cost: ~5 lines.
- **B**: translate the `defaults` table inside `EmptyState.tsx` itself
  (one-shot fix, but requires `EmptyState` to call `useTranslations`, which
  makes every consumer need a NextIntlClientProvider boundary — already
  satisfied everywhere via `[locale]/layout.tsx`).

**LOC for F2 in `JobList.tsx`**: ~5 lines (option A) + 0 in the file if we
pick option B (moved to `EmptyState.tsx`).
**New keys** under option A: 3 (`Jobs.emptyState.noResults.*`, `.noJobs.*`,
`.error.*`).

### 3.4 `GenerateCVModal.tsx` (355 LOC) — the biggest piece

| # | Line | Hardcoded (ES) | Action | Namespace |
|---|------|----------------|--------|-----------|
| 1 | 80, 93 | `"Solo se aceptan archivos PDF"` | Replace | **`Landing.upload.pdfOnly`** (already exists) |
| 2 | 106 | `"Subí tu CV o guardalo primero en Settings"` | Replace | **`Jobs.modal.uploadOrSaved`** (NEW) |
| 3 | 125 | `"No pude descargar tu CV guardado"` | Replace | **`Jobs.modal.savedCvDownloadFailed`** (NEW) |
| 4 | 151 | `"Unknown error"` (catch fallback) | Replace | **`Common.error`** (already exists) |
| 5 | 159 | `"Error generando el CV"` | Replace | **`Jobs.modal.generationFailed`** (NEW) |
| 6 | 187 | `"Generar CV adaptado"` (modal title) | Replace | **`Jobs.modal.title`** (already exists) |
| 7 | 190 | `"Adaptando CV para "` | Replace with interpolation | **`Jobs.modal.adaptingFor`** (NEW: `"Adaptando CV para {company} — {title}"`) |
| 8 | 200 | `"Tu CV está listo. Descárgalo y úsalo para aplicar."` | Replace | **`Jobs.modal.cvReady`** (NEW) |
| 9 | 204 | `download="CV-adaptado.pdf"` | Translate filename | **`Jobs.modal.downloadFilename`** (NEW: `"CV-adaptado.pdf"` / `"Adapted-CV.pdf"`) |
| 10 | 208 | `"Descargar CV (PDF)"` | Replace | **`Jobs.modal.download`** (NEW) |
| 11 | 220 | `"Generar otro"` | Replace | **`Jobs.modal.generateAnother`** (NEW) |
| 12 | 237 | `"Tu CV guardado — click para cambiar"` | Replace | **`Jobs.modal.savedCvHint`** (NEW) |
| 13 | 272 | `"Quitar"` | Replace | **`Common.delete`** (already exists as `"Eliminar"`) — or NEW `Jobs.modal.remove` |
| 14 | 280 | `"O arrastrá un PDF diferente para esta postulación"` | Replace | **`Jobs.modal.dropZoneReplace`** (NEW) |
| 15 | 281 | `"Arrastrá tu CV PDF o click para seleccionar"` | Replace | **`Jobs.modal.dropZoneInitial`** (NEW) |
| 16 | 302–311 | `"Entiendo y acepto que mi CV sea procesado por"` + `"Groq (EE.UU.)"` + `"Ver Política de Privacidad"` (mixed JSX) | Replace with `t.rich()` | **`Jobs.modal.consent`** (NEW, uses `.rich()` for `<strong>` and `<Link>`) |
| 17 | 324 | `"Generando CV..."` | Replace | **`Jobs.modal.downloading`** (already exists) |
| 18 | 327 | `"Generar CV adaptado"` (submit) | Replace | **`Jobs.modal.submit`** (NEW) OR reuse `Jobs.modal.title` |
| 19 | 333–334 | `"Se usará tu CV guardado. Subí un PDF para usar ese temporalmente."` | Replace | **`Jobs.modal.savedCvFooter`** (NEW) |
| 20 | 339–346 | `"Tu CV será procesado por Groq (EE.UU.)."` + `"Más información"` (mixed JSX) | Replace with `t.rich()` | **`Jobs.modal.processedByGroq`** (NEW) |

**LOC**: ~80–100 lines of JSX → `t()` rewrites (the nested JSX on lines 302–311
and 339–346 require `t.rich()` to keep the `<strong>` and `<Link>` tags).
**New keys needed**: ~14.

> The component is 355 LOC today; after migration it grows by ~30 LOC
> (each `t()` adds chars; `t.rich()` callbacks add more). Net delta: +30 LOC.

### 3.5 `FavoriteButton.tsx` (54 LOC)

- **Already fully translated** — uses `useTranslations("Jobs.favorite")` and
  pulls `add`/`remove` from the existing namespace (lines 256–259 of both
  message files).
- The user listed this under F2 likely as a sanity item. **No code change needed.**
- **LOC**: 0.
- **Verification only**: confirm the test suite (`FavoriteButton.test.tsx`)
  covers both `es` and `en` renders — currently only `es` is exercised.
  Add 1 en-rendered test (~15 LOC) to prove parity.

> **Risk #6** explains why this was listed in F2 despite being done.

### 3.6 F2 totals

| File | LOC change | New keys |
|------|-----------:|---------:|
| `JobDetailContent.tsx` | ~3 | 0 |
| `JobDetailAside.tsx` | ~25 | 2 |
| `JobList.tsx` (+ optional `EmptyState.tsx`) | ~5 (or ~25) | 3 (or 3 inside `EmptyState`) |
| `GenerateCVModal.tsx` | ~80–100 | 14 |
| `FavoriteButton.tsx` (test only) | ~15 | 0 |
| **Subtotal** | **~130–150** | **~16–19** |

---

## 4. F3: `useChat.ts` errors

### 4.1 The 3 hardcoded literals

| # | Line | Literal | Trigger |
|---|------|---------|---------|
| 1 | 175 | `"Something went wrong. Please try again."` | Fallback when `response.ok === false` and the error body isn't parseable JSON (catch on line 181 swallows parse failure) |
| 2 | 209 | `"Connection failed — no response body."` | `response.body?.getReader()` returned `undefined` — i.e. the server returned 2xx but no stream |
| 3 | 336 | `err instanceof Error ? err.message : "Something went wrong. Please try again."` | Catch-all in the outer `.catch()` — network failure or non-`AbortError` unhandled stream error |

### 4.2 Render path

`AssistantMessage.tsx` line 132 renders `{message.error.message}` directly —
no translation, no `useTranslations` boundary at this point. `ChatMessages.test.tsx`
line 117 asserts on the literal English string `"The AI assistant is currently unavailable."`,
which would have to be updated when the key changes.

### 4.3 Recommended pattern — **error.code → Chat.errors translation key**

**Option A (recommended, smallest blast radius)**:

1. In `useChat`, **stabilize** the `error.code` emitted:
   - Server-error path (line 178): keep `err.code` if present, else `"internal"`.
   - No-body path (line 209): use code `"connection_failed"` (matches existing `Chat.errors.connectionFailed`).
   - Catch-all (line 332): use code `"internal"` (matches `Chat.errors.generic`).
2. Keep the human `message` populated from the server's `err.detail` /
   `err.message` so backend-driven Spanish messages still flow through
   (no regression on the locale-aware backend errors).
3. In `AssistantMessage`, render `t(Chat.errors.${code}) ?? message` — i.e.
   translate by code, fall back to the raw server message.

This keeps `useChat` hook-only (no React i18n dependency), surfaces 4
existing translation keys (`streamFailed`, `connectionFailed`, `generic`,
`rateLimit`), and adds NO new keys.

**LOC**:
- `useChat.ts`: ~10 line edits (assign codes + add comments).
- `AssistantMessage.tsx`: ~6 lines (add `useTranslations('Chat.errors')`,
  wrap `message.error.message` render).
- `ChatMessage` type in `types/chat.ts`: optional `{ code: string; message: string }`
  already covers it — no change.
- `ChatMessages.test.tsx`: ~20 lines (replace literal text assertion with
  either i18n-aware render or mock `useTranslations`).

**Total F3 LOC**: ~35. **New keys**: 0.

---

## 5. F5: 3 auth pages

### 5.1 `signup/page.tsx` (170 LOC) — client component, the bulk

| # | Line | Hardcoded | Namespace |
|---|------|-----------|-----------|
| 1 | 66 | `"Volver al inicio"` | **`Common.backToHome`** (NEW) — or reuse `Common.back` |
| 2 | 74 | `"Jobs Finder"` (logo alt / wordmark) | Brand stays literal (proper noun) |
| 3 | 76 | `"Crear cuenta"` (heading) | **`Auth.signup.title`** (already exists as `"Creá tu cuenta"`) — page uses different wording; either (a) change page to match existing key, or (b) add new `Auth.signup.heading` |
| 4 | 78 | `"Registrate para empezar a usar Jobs Finder"` | **`Auth.signup.subtitle`** (exists as `"Encontrá tu próximo empleo en minutos."`) — page uses different copy; add `Auth.signup.tagline` (NEW) or change page text |
| 5 | 85 | `"Email"` | **`Auth.signup.emailLabel`** (already exists) |
| 6 | 92 | `"tu@email.com"` | **`Auth.signup.emailPlaceholder`** (NEW) — could share with `Auth.deleteAccount.confirmPlaceholder` |
| 7 | 99 | `"Contraseña"` | **`Auth.signup.passwordLabel`** (already exists) |
| 8 | 105 | `"••••••••"` (mask) | Stays literal |
| 9 | 121 | `"Creando cuenta..."` | **`Auth.signup.loading`** (NEW) |
| 10 | 121 | `"Crear cuenta"` (button) | **`Auth.signup.submit`** (already exists as `"Crear cuenta"`) — matches |
| 11 | 131 | `"o continuá con"` | **`Auth.signup.orContinueWith`** (already exists) |
| 12 | 158 | `"Continuar con Google"` | **`Auth.signup.continueWithGoogle`** (already exists) |
| 13 | 162 | `"¿Ya tenés cuenta?"` | **`Auth.signup.haveAccount`** (already exists) |
| 14 | 164 | `"Iniciá sesión"` | **`Auth.signup.signIn`** (already exists) |

**Decision point**: the page's literal copy differs from the existing
`Auth.signup.*` keys (tú vs. vos, different subtitle). Three options:

- (a) **Change page text to match existing keys** — 0 new keys, ~5 LOC.
- (b) **Add new keys for the page's exact wording** — ~4 new keys, ~0 LOC.
- (c) **Update existing `Auth.signup.*` keys to merge both wordings under
  stable keys with optional alternatives** — discouraged (mixes two writing
  styles in the same namespace).

**Recommendation**: (a). The existing `Auth.signup.*` keys were written by
slice 5 and reviewed; "Creá tu cuenta" / "Encontrá tu próximo empleo en
minutos" is canonical. The page just used inline copy without consulting
the keys. Bringing the page in line is the right call.

**LOC for signup**: ~30 lines (rewrite the JSX to use `useTranslations`,
collapse the two `"Crear cuenta"` instances to one button + one heading).
**New keys**: 3 (`Common.backToHome`, `Auth.signup.emailPlaceholder`,
`Auth.signup.loading`).

### 5.2 `forgot-password/page.tsx` (5 LOC)

```tsx
export default function ForgotPasswordPage() {
  return <ForgotPasswordForm />;
}
```

**Already done.** The form component is fully translated. **LOC: 0.**

### 5.3 `reset-password/page.tsx` (38 LOC) — async server component

Uses **deprecated** `import { authCopy } from "@/lib/authCopy"` on lines 4, 25–31.
Three keys consumed: `invalidLinkTitle`, `invalidLinkDescription`, `resendLink` —
all exist in `Auth.resetPassword` (lines 85–88 of both message files).

**Migration**: server components cannot use `useTranslations`. Must use
`getTranslations` from `next-intl/server`:

```tsx
import { getTranslations } from "next-intl/server";

export default async function ResetPasswordPage() {
  const supabase = await createClient();
  const t = await getTranslations("Auth.resetPassword");
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) {
    return (
      <div>
        <h1>{t("invalidLinkTitle")}</h1>
        <p>{t("invalidLinkDescription")}</p>
        <Link href="/forgot-password">{t("resendLink")}</Link>
      </div>
    );
  }
  return <ResetPasswordForm />;
}
```

**LOC**: ~10 lines (1 import swap, 1 `const t = await getTranslations(...)`,
3 key calls, drop `authCopy` import).
**New keys**: 0.

### 5.4 F5 totals

| File | LOC change | New keys |
|------|-----------:|---------:|
| `signup/page.tsx` | ~30 | 3 |
| `(auth)/forgot-password/page.tsx` | 0 | 0 |
| `(auth)/reset-password/page.tsx` | ~10 | 0 |
| **Subtotal** | **~40** | **3** |

---

## 6. F6: Footer scope bug

### 6.1 Current state (verified)

`app/[locale]/layout.tsx` line 75 unconditionally renders `<Footer />` after
`<div className="flex-1">{children}</div>`.

**Why it's visible on (app) routes**:

```
[locale]/layout.tsx        (app)/layout.tsx
┌──────────────────────┐   ┌─────────────────────────────┐
│ <div min-h-screen>   │   │ <AppShell> h-screen          │
│   <div flex-1>       │   │   <Sidebar />                │
│     <AppShell>       │◄──│   <Header />                 │
│   </div>             │   │   <main overflow-y-auto />   │
│   <Footer />         │   │   <ChatDialog />             │
│ </div>               │   │ </AppShell>                  │
└──────────────────────┘   └─────────────────────────────┘
```

`AppShell` is `h-screen overflow-hidden` so the inner app scrolls inside
`<main>`. The outer flex column has `min-h-screen` and Footer as a sibling.
Because `AppShell` consumes exactly `100vh`, Footer renders **below** the
viewport — users on `/dashboard`, `/search`, `/favorites`, `/settings` can
scroll the outer document past AppShell and see a dangling Footer. That's
the "double-footer bug" — Footer is rendered twice in the DOM sense: once
where it shouldn't be (below AppShell) and once where it should (on every
public route).

### 6.2 Fix approaches

| Approach | Description | Files | LOC |
|----------|-------------|------:|----:|
| **A (recommended): `useSelectedLayoutSegment('(app)')` guard** | Wrap Footer in a tiny client component that returns `null` when the (app) route group is active | 1 new file + 1 edit in `[locale]/layout.tsx` | ~20 |
| **B: Move Footer to each public layout/page** | Remove Footer from `[locale]/layout.tsx`, add to `(auth)/layout.tsx`, `login/page.tsx`, `signup/page.tsx`, `privacidad/page.tsx`, `jobs/[id]/page.tsx`, `landing/page.tsx` | 1 edit + 6 adds | ~35 |
| **C: Introduce `(public)` route group** | Move `/login`, `/signup`, `/privacidad`, `/jobs/[id]`, `/` into a `(public)` group with a new layout | Many edits | ~80+ |

**Recommendation: Approach A.**

Why:

- Single source of truth for "where does Footer live".
- No duplication across 7 layouts/pages.
- Zero risk of forgetting to add Footer to a future public route (it just
  shows up).
- Works with Next.js 15's `useSelectedLayoutSegment('(app)')` — returns
  the active segment within the `(app)` parallel slot, or `null` when the
  route is outside the group.

**LOC**: ~20.

```tsx
// new: src/components/layout/ConditionalFooter.tsx
"use client";
import { useSelectedLayoutSegment } from "next/navigation";
import { Footer } from "./Footer";

export function ConditionalFooter() {
  const appSegment = useSelectedLayoutSegment("(app)");
  if (appSegment !== null) return null; // (app) route group is active
  return <Footer />;
}
```

```tsx
// edit: src/app/[locale]/layout.tsx
-import { Footer } from "@/components/layout/Footer";
+import { ConditionalFooter } from "@/components/layout/ConditionalFooter";
 ...
-              <Footer />
+              <ConditionalFooter />
```

**New keys**: 0. **New component**: 1. **LOC**: ~20.

> **Verification path**: after the fix, on `/[locale]/dashboard` the Footer
> is absent from the DOM (verifiable with `document.querySelector('footer')`
> returning null); on `/[locale]/login` it's present. Add a `ConditionalFooter.test.tsx`
> mocking `useSelectedLayoutSegment` for both cases (~30 LOC, optional).

---

## 7. Message namespace plan

### 7.1 Existing namespaces (15)

`Common`, `Errors`, `Navigation`, `Auth`, `Validation`, `Dashboard`,
`Jobs`, `Search`, `Favorites`, `Settings`, `Chat`, `JobsErrors`, `Landing`,
`Footer`.

### 7.2 Reuse (no new key needed)

| Use site | Existing key | Value ES | Value EN |
|----------|--------------|----------|----------|
| `JobDetailContent` "Description" | `Jobs.detail.description` | `"Descripción"` | `"Description"` |
| `JobDetailAside` "Source" | `Jobs.card.source` | `"Fuente"` | `"Source"` |
| `JobDetailAside` "Location" | `Jobs.card.location` | `"Ubicación"` | `"Location"` |
| `JobDetailAside` trigger button | `Jobs.modal.generate` | `"Generar CV adaptado"` | `"Generate adapted CV"` |
| `GenerateCVModal` PDF-only error | `Landing.upload.pdfOnly` | `"Solo se aceptan archivos PDF"` | `"PDF files only"` |
| `GenerateCVModal` Unknown error | `Common.error` | `"Algo salió mal"` | `"Something went wrong"` |
| `GenerateCVModal` "Generando CV..." | `Jobs.modal.downloading` | `"Generando…"` | `"Generating…"` |
| `GenerateCVModal` "Quitar" | `Common.delete` (or new `Jobs.modal.remove`) | `"Eliminar"` | `"Delete"` |
| `signup` "Email" | `Auth.signup.emailLabel` | `"Correo electrónico"` | `"Email"` |
| `signup` "Contraseña" | `Auth.signup.passwordLabel` | `"Contraseña"` | `"Password"` |
| `signup` "Crear cuenta" (button) | `Auth.signup.submit` | `"Crear cuenta"` | `"Create account"` |
| `signup` "o continuá con" | `Auth.signup.orContinueWith` | `"O continuá con"` | `"Or continue with"` |
| `signup` "Continuar con Google" | `Auth.signup.continueWithGoogle` | `"Continuar con Google"` | `"Continue with Google"` |
| `signup` "¿Ya tenés cuenta?" | `Auth.signup.haveAccount` | `"¿Ya tenés cuenta?"` | `"Already have an account?"` |
| `signup` "Iniciá sesión" | `Auth.signup.signIn` | `"Iniciar sesión"` | `"Sign in"` |
| `signup` heading "Crear cuenta" | `Auth.signup.title` (canonical form "Creá tu cuenta") | `"Creá tu cuenta"` | `"Create your account"` |
| `signup` subtitle | `Auth.signup.subtitle` | `"Encontrá tu próximo empleo en minutos."` | `"Find your next role in minutes."` |
| `useChat` errors | `Chat.errors.{streamFailed,connectionFailed,generic,rateLimit}` | already defined | already defined |

### 7.3 New keys — under `Jobs` (F2)

```jsonc
"Jobs": {
  // ...existing keys...
  "detail": {
    // ...existing keys...
    "postedLabel": "Publicado",            // EN: "Posted"
    "viewOriginal": "Ver original",        // EN: "View original"
    "emptyResults": "No hay resultados",   // EN: "No results" (for EmptyState)
  },
  "emptyState": {                          // NEW branch (option A for JobList)
    "noResults": {
      "title": "No se encontraron resultados",
      "description": "Ajustá tu búsqueda o filtros"
    },
    "noJobs": {
      "title": "Aún no hay trabajos",
      "description": "Los trabajos aparecerán cuando el backend los indexe"
    },
    "error": {
      "title": "Algo salió mal",
      "description": "No pudimos cargar los datos. Intentá de nuevo."
    }
  },
  "modal": {
    // ...existing keys...
    "uploadOrSaved": "Subí tu CV o guardalo primero en Configuración",  // EN: "Upload your CV or save it in Settings first"
    "savedCvDownloadFailed": "No pudimos descargar tu CV guardado",    // EN: "We couldn't download your saved CV"
    "generationFailed": "Error generando el CV",                        // EN: "Error generating the CV"
    "adaptingFor": "Adaptando CV para {company} — {title}",             // EN: "Adapting CV for {company} — {title}"
    "cvReady": "Tu CV está listo. Descárgalo y úsalo para aplicar.",    // EN: "Your CV is ready. Download it and use it to apply."
    "downloadFilename": "CV-adaptado.pdf",                              // EN: "Adapted-CV.pdf"
    "download": "Descargar CV (PDF)",                                   // EN: "Download CV (PDF)"
    "generateAnother": "Generar otro",                                  // EN: "Generate another"
    "savedCvHint": "Tu CV guardado — click para cambiar",               // EN: "Your saved CV — click to change"
    "dropZoneReplace": "O arrastrá un PDF diferente para esta postulación", // EN: "Or drag a different PDF for this application"
    "dropZoneInitial": "Arrastrá tu CV PDF o hacé click para seleccionar", // EN: "Drag your CV PDF or click to select"
    "consent": "Entiendo y acepto que mi CV sea procesado por <b>Groq (EE.UU.)</b> para generar el CV adaptado. <privacy>Ver Política de Privacidad</privacy>", // EN equivalent; uses .rich()
    "submit": "Generar CV adaptado",                                    // EN: "Generate adapted CV"
    "savedCvFooter": "Se usará tu CV guardado. Subí un PDF para usar ese temporalmente.", // EN: "Your saved CV will be used. Upload a PDF to use that one temporarily."
    "processedByGroq": "Tu CV será procesado por <b>Groq (EE.UU.)</b>. <more>Más información</more>", // EN equivalent; uses .rich()
  }
}
```

### 7.4 New keys — under `Common` (F5)

```jsonc
"Common": {
  "backToHome": "Volver al inicio",  // EN: "Back to home"
}
```

### 7.5 New keys — under `Auth` (F5)

```jsonc
"Auth": {
  "signup": {
    "emailPlaceholder": "tu@email.com",  // EN: "you@example.com"
    "loading": "Creando cuenta...",      // EN: "Creating account..."
  }
}
```

### 7.6 New keys — none for F3 or F6

- **F3**: existing `Chat.errors.*` covers all 4 server-side codes.
- **F6**: no copy change, just conditional rendering.

### 7.7 Total new keys

**~16 new keys** spread across `Jobs`, `Common`, `Auth`.

---

## 8. Effort estimate

| Follow-up | LOC change | Files touched | New keys | New components |
|-----------|-----------:|--------------:|---------:|---------------:|
| F2 — `JobDetailContent` | 3 | 1 | 0 | 0 |
| F2 — `JobDetailAside` | 25 | 1 | 2 | 0 |
| F2 — `JobList` (option A) | 5 | 1 | 3 | 0 |
| F2 — `GenerateCVModal` | 90 | 1 | 14 | 0 |
| F2 — `FavoriteButton` (test only) | 15 | 1 | 0 | 0 |
| F3 — `useChat` + `AssistantMessage` + test | 35 | 3 | 0 | 0 |
| F5 — `signup/page.tsx` | 30 | 1 | 3 | 0 |
| F5 — `reset-password/page.tsx` | 10 | 1 | 0 | 0 |
| F5 — `forgot-password/page.tsx` | 0 | 0 | 0 | 0 |
| F6 — `ConditionalFooter` + layout edit | 20 | 2 | 0 | 1 |
| **Total** | **~230** | **12** | **~22** | **1** |

### 8.1 PR-budget check

- **400-line PR review budget** (D1).
- **Total estimated LOC: ~230** (well under budget).
- **Decision needed before apply: No**.
- **Chained PRs recommended: No**.
- **400-line budget risk: Low**.

If `EmptyState` option B is picked instead of option A, add ~25 LOC
(`EmptyState.tsx` rewrite + 4 caller updates that stop passing defaults).
Still well under 400.

### 8.2 Suggested work-unit grouping

Single PR is fine, but a 2-commit split within the PR improves review:

- **Commit 1**: F5 (auth pages) + F2 (small files: `JobDetailContent`,
  `JobDetailAside`, `JobList`). Small, easy to review.
- **Commit 2**: F2 (`GenerateCVModal`) + F3 (chat errors) + F6 (Footer
  fix). Touches 4 files; one is large (`GenerateCVModal`).

---

## 9. Risks

| # | Risk | Severity | Mitigation |
|---|------|---------:|------------|
| 1 | **`GenerateCVModal` consent text is nested JSX** (lines 302–311, 339–346) with `<strong>` and `<Link>` interleaved. Naive `t()` wrap breaks the markup. | **High** | Use `t.rich('Jobs.modal.consent', { b: (c) => <strong>{c}</strong>, privacy: (c) => <Link href="/privacidad">{c}</Link> })` — add a unit test that asserts the `<Link>` renders with the right `href`. |
| 2 | **`useChat` `ChatMessage.error` is persisted to localStorage** (`saveChatStorage` in `lib/chat-storage.ts`). Changing the shape breaks existing browser sessions. | **Medium** | Keep both fields — `code` (machine) and `message` (human, may be the existing English fallback) — and translate by code in `AssistantMessage`. Backwards-compatible. |
| 3 | **`reset-password/page.tsx` is an async server component**; `useTranslations` is client-only. Wrong import will silently break SSR. | **Low** | Use `getTranslations` from `next-intl/server`. Verify `pnpm run build` succeeds (it does static rendering for `[locale]` per `generateStaticParams`). |
| 4 | **`useSelectedLayoutSegment('(app)')` API** — Next.js 15 supports passing a parallel segment slot name; returning `null` means no segment in that slot is active. Must verify exact semantics against the running Next.js version (15.5.19). | **Low** | Add `ConditionalFooter.test.tsx` with a `next/navigation` mock; manually smoke-test on `/dashboard` (no footer) and `/login` (footer present). |
| 5 | **`EmptyState` defaults are hardcoded EN** (lines 16–37) and used by 4 pages (`JobList`, `dashboard`, `search`, `favorites`). Translating only `JobList` creates inconsistency. | **Medium** | Pick option B (translate `EmptyState` defaults via `useTranslations('Jobs.emptyState.*')` or move to a dedicated `EmptyStateCopy` namespace). One component, one call site, one place to keep in sync. |
| 6 | **`FavoriteButton` is listed under F2 but is already fully translated**. Risk of redundant rework or a "test gap" misread as "code gap". | **Low** | Verify in the spec: F2.FavoriteButton scope is "confirm tests cover EN locale" — no code change. |
| 7 | **`JobDetailAside.formatRelativeDate(job.posted_at)` doesn't pass locale** — currently always renders in Spanish. Easy to miss because the string itself isn't hardcoded. | **Low** | Add `const locale = useLocale();` and `formatRelativeDate(job.posted_at, locale)`. Covered by an existing `formatters.test.ts` pattern (line 8 `formatRelativeDate — bilingual`). |
| 8 | **`Auth.signup.*` keys exist but with different copy than the page**. Decision needed: rewrite page to match keys, or expand keys. | **Low** | Recommendation is to rewrite the page to match canonical keys (smaller change, keeps the i18n namespace clean). Surface this in the spec as an explicit decision. |

---

## 10. Affected Areas (file inventory)

```
frontend/src/components/jobs/JobDetailContent.tsx       # F2
frontend/src/components/jobs/JobDetailAside.tsx        # F2
frontend/src/components/jobs/JobList.tsx               # F2
frontend/src/components/jobs/GenerateCVModal.tsx       # F2
frontend/src/components/jobs/FavoriteButton.tsx        # F2 (test only)
frontend/src/components/jobs/__tests__/FavoriteButton.test.tsx  # F2 (add EN test)
frontend/src/components/shared/EmptyState.tsx          # F2 (option B) — secondary
frontend/src/hooks/useChat.ts                          # F3
frontend/src/components/chat/AssistantMessage.tsx      # F3
frontend/src/components/chat/__tests__/ChatMessages.test.tsx  # F3
frontend/src/app/[locale]/signup/page.tsx              # F5
frontend/src/app/[locale]/(auth)/reset-password/page.tsx  # F5
frontend/src/app/[locale]/layout.tsx                   # F6
frontend/src/components/layout/ConditionalFooter.tsx   # F6 (NEW)
frontend/messages/en.json                              # all
frontend/messages/es.json                              # all
```

15 files touched, 1 new component created. No backend changes.

---

## 11. Ready for Proposal

**Yes.**

The next phase is **SDD propose** — produce
`openspec/changes/feat-frontend-i18n-complete-coverage/proposal.md` that
documents:

- **Intent**: close F2, F3, F5, F6 in one bundle.
- **Scope**: 15 files (12 modified, 1 new, 2 message files), frontend only.
- **Approach**: 2-commit split (small i18n pass → larger modal + chat + footer).
- **Out of scope**: F1 (`authCopy.ts` deletion), F4 (landing EN marketing copy),
  F7 (spec deltas), F-anything-else from v1/v2 archives.
- **Risk**: 8 risks captured (Section 9). Severity-weighted mitigations ready.
- **Trade-off**: option A vs B for `EmptyState` (recommendation: B).
- **Trade-off**: rewrite signup page to match canonical keys vs expand keys
  (recommendation: rewrite).

The proposal can be written without re-reading any code — all the file
contents are captured in this exploration. Spec and tasks phases can proceed
in parallel once the proposal is approved.
