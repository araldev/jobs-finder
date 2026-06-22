# Archive Report — `feat-frontend-i18n-complete-coverage`

> **Status**: closed (verified, archived)
> **Date**: 2026-06-22
> **Project**: jobs-finder (frontend workspace)
> **Branch**: `feat-frontend-i18n-complete-coverage`
> **Tip SHA**: `ab54e2d` (pushed to `origin`)
> **Preflight cache**: Pace A2 · Artifacts hybrid · PRs C4 (single PR) · Review D1 (well under 400) · Strict TDD: false

## Outcome

The change closes **4 of the 7 i18n follow-ups** documented in the v1 archive (and the v2 cycle). Single PR, 2 commits, 18 files, +404/-94 LOC.

### Follow-ups closed

| # | Follow-up | Status |
|---|-----------|--------|
| **F2** | 5 jobs components untranslated | ✅ **CLOSED** (all 5 translated; FavoriteButton already done + en test added) |
| **F3** | `useChat.ts` 3 hardcoded EN error literals | ✅ **CLOSED** (3 stable error codes + AssistantMessage translates by code) |
| **F5** | 3 auth pages partial | ✅ **CLOSED** (signup + reset-password translated; forgot-password already done) |
| **F6** | Footer appears globally on (app) routes | ✅ **CLOSED** (ConditionalFooter component via `useSelectedLayoutSegment('(app)')`) |

### Follow-ups still open (carry-over)

| # | Issue | Change name |
|---|---|---|
| F1 | `authCopy.ts` deprecated but not deleted | `chore(i18n): remove deprecated authCopy.ts` |
| F4 | Landing page partial (~3 of 731 strings translated) | `feat(i18n): landing page EN marketing copy` (needs marketing review) |
| F7 | Spec deltas for cross-cutting capabilities missing | `docs(spec): fold cross-cutting i18n REQs into capability specs` |

### New follow-up surfaced during apply (D5)

- **F8 (new)**: `ChatMessages.tsx` line 17 has a hardcoded EN empty-state string ("Describe the job you are looking for in natural language."). It's F3-adjacent but out of scope for the explore's F3. Add to F5-style chat translation follow-up.

## Per-commit breakdown

```
ab54e2d  feat(i18n): translate GenerateCVModal, useChat errors via codes, ~19 modal keys
ec904cd  feat(i18n): translate auth pages, small jobs components, hide footer in (app) routes
```

| Commit | LOC delta | Files | Acceptance gate |
|---|---|---:|---|
| `ec904cd` (F5 + F2 small + F6) | +181 / −33 | 12 (10 mod + 2 new) | typecheck ✓ / lint ✓ / 273 tests ✓ / build ✓ |
| `ab54e2d` (F2 modal + F3) | +223 / −61 | 6 (5 mod + 1 test rewrite) | typecheck ✓ / lint ✓ / 278 tests ✓ / build ✓ |

## Discoveries (saved to engram)

- **D1** — `useTranslations` returns the namespace-prefixed path for unknown keys (e.g. `"Chat.errors.llm_unavailable"`); `getTranslations` throws. `AssistantMessage` detects missing keys via `translated.startsWith("Chat.errors.")` and falls back to the raw server message.
- **D2** — `useSelectedLayoutSegment('(app)')` returns `null` when no segment in the (app) parallel slot is active. Argument must be the literal route group name (with parens). Works in jsdom + RTL with `vi.mock("next/navigation", ...)`. Client-only — wrap in `"use client"`.
- **D3** — `getTranslations` is server-only. When used in a server component, the test must `vi.mock("next-intl/server", ...)` and provide a tiny lookup.
- **D4** — `Auth.signup.*` keys used voseo ("Creá tu cuenta", "Encontrá tu próximo empleo en minutos.") but the signup page used tuteo ("Crear cuenta", "Registrate para empezar"). Per explore's option A, the page was rewritten to match canonical keys (cleaner than expanding the namespace with two writing styles).
- **D5** — F3-adjacent: `ChatMessages.tsx` line 17 has a hardcoded EN empty-state string. Flagged for future work.

## CI gate final results

| Gate | Status |
|---|---|
| `pnpm run typecheck` | ✅ PASS |
| `pnpm run lint` | ✅ PASS |
| `pnpm run test` | ✅ PASS (278 tests across 44 files) |
| `pnpm run build` | ✅ PASS |

## Smoke tests verified at runtime

| Route | Locale | HTTP | Lang attr | Translation markers |
|---|---|---:|---|---|
| `/dashboard` | es (cookie) | 200 | `lang="es"` | n/a (auth-gated) |
| `/dashboard` | en (cookie) | 200 | `lang="en"` | n/a (auth-gated) |
| `/signup` | es | 200 | `lang="es"` | "Creá tu cuenta", "Continuar con Google", "Contraseña", "Correo electrónico", "Volver al inicio" |
| `/signup` | en | 200 | `lang="en"` | "Create your account", "Continue with Google", "Password", "Email", "Back to home" |
| `/jobs/[id]` | es | 200 | `lang="es"` | "Descripción", "Fuente", "Publicado", "Ubicación", "Ver original", "Generar CV adaptado" |
| `/jobs/[id]` | en | 200 | `lang="en"` | "Description", "Source", "Posted", "Location", "View original", "Generate adapted CV" |

F6 verified via `ConditionalFooter.test.tsx` (3 unit tests). Could not curl-verify the (app) layouts directly because every (app) route redirects unauthenticated visitors to `/login` (middleware auth gate), so the (app) layout never renders for curl probes — the unit test is the canonical check.

## Message namespace additions (20 new keys × 2 locales)

### Under `Jobs.detail` (2 keys)
- `postedLabel`: "Publicado" / "Posted"
- `viewOriginal`: "Ver original" / "View original"

### Under `Jobs.modal` (15 keys)
- `uploadOrSaved`: "Subí tu CV o guardalo primero en Configuración" / "Upload your CV or save it first in Settings"
- `savedCvDownloadFailed`: "No pudimos descargar tu CV guardado" / "We couldn't download your saved CV"
- `generationFailed`: "Error generando el CV" / "Error generating the CV"
- `adaptingFor`: "Adaptando CV para {company} — {title}" / "Adapting CV for {company} — {title}" (ICU interpolation)
- `cvReady`: "Tu CV está listo. Descárgalo y úsalo para aplicar." / "Your CV is ready. Download it and use it to apply."
- `downloadFilename`: "CV-adaptado.pdf" / "Adapted-CV.pdf"
- `download`: "Descargar CV (PDF)" / "Download CV (PDF)"
- `generateAnother`: "Generar otro" / "Generate another"
- `savedCvHint`: "Tu CV guardado — click para cambiar" / "Your saved CV — click to change"
- `dropZoneReplace`: "O arrastrá un PDF diferente para esta postulación" / "Or drag a different PDF for this application"
- `dropZoneInitial`: "Arrastrá tu CV PDF o hacé click para seleccionar" / "Drag your CV PDF or click to select"
- `consent`: rich text with `<b>` + `<privacy>` markers
- `submit`: "Generar CV adaptado" / "Generate adapted CV"
- `savedCvFooter`: "Se usará tu CV guardado. Subí un PDF para usar ese temporalmente." / "Your saved CV will be used. Upload a PDF to use that temporarily."
- `processedByGroq`: rich text with `<b>` + `<more>` markers

### Under `Common` (1 key)
- `backToHome`: "Volver al inicio" / "Back to home"

### Under `Auth.signup` (2 keys)
- `emailPlaceholder`: "tu@email.com" / "you@example.com"
- `loading`: "Creando cuenta..." / "Creating account..."

## Affected files (18 total)

**Modified (16):**
- `frontend/messages/en.json`
- `frontend/messages/es.json`
- `frontend/src/components/jobs/JobDetailContent.tsx`
- `frontend/src/components/jobs/JobDetailAside.tsx`
- `frontend/src/components/jobs/GenerateCVModal.tsx`
- `frontend/src/components/jobs/__tests__/FavoriteButton.test.tsx`
- `frontend/src/hooks/useChat.ts`
- `frontend/src/components/chat/AssistantMessage.tsx`
- `frontend/src/components/chat/__tests__/ChatMessages.test.tsx`
- `frontend/src/app/[locale]/signup/page.tsx`
- `frontend/src/app/[locale]/(auth)/reset-password/page.tsx`
- `frontend/src/app/[locale]/(auth)/reset-password/__tests__/page.test.tsx`
- `frontend/src/app/[locale]/layout.tsx`
- `frontend/src/app/[locale]/layout.test.tsx`

**Created (2):**
- `frontend/src/components/layout/ConditionalFooter.tsx` (F6)
- `frontend/src/components/layout/__tests__/ConditionalFooter.test.tsx` (F6 unit tests)

## Rollback

Single-PR revert (`git revert ec904cd ab54e2d`) is clean — both commits are localized to the i18n layer with no architectural changes outside what was already shipped in v1/v2.

## Carry-over follow-ups (priority order)

1. **F1** — Remove `authCopy.ts` (139 test files still reference `authCopy.X.Y`). Tedious but clean. Cycle 3 candidate.
2. **F4** — Landing page EN marketing copy (~3 of 731 strings translated). Requires marketing review of canonical EN copy.
3. **F7** — Fold cross-cutting i18n REQs (`frontend-dashboard`, `chat-frontend`, `favorites` deltas) into the canonical capability specs. Docs-only.
4. **F8 (new)** — Translate `ChatMessages.tsx` line 17 hardcoded EN empty-state string. Small follow-up, ~5 LOC.

## Next steps

1. **Open the PR** from `feat-frontend-i18n-complete-coverage` against `main` (compare URL: `https://github.com/araldev/jobs-finder/compare/main...feat-frontend-i18n-complete-coverage?expand=1`).
2. After merge: cycle 3 (F1 — `authCopy.ts` removal) if the user wants the final cleanup pass.
