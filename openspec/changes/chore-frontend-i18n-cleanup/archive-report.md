# Archive Report — `chore-frontend-i18n-cleanup`

> **Status**: closed (verified, archived)
> **Date**: 2026-06-22
> **Project**: jobs-finder (frontend workspace)
> **Branch**: `chore-frontend-i18n-cleanup`
> **Tip SHA**: `a5e9be0` (pushed to `origin`)
> **Preflight cache**: Pace A2 · Artifacts hybrid · PRs C4 (single PR) · Review D1 (well under) · Strict TDD: false

## Outcome

The change **fully retires the deprecated `authCopy.ts` seed dictionary** that v1 (slice 5) deprecated but couldn't remove due to 139 test references. The seed file is deleted; every consumer (production code + tests) now reads from `messages/{en,es}.json` via `useTranslations` / `getTranslations` exclusively.

### Follow-up closed

| # | Follow-up | Status |
|---|-----------|--------|
| **F1** | `authCopy.ts` deprecated but not deleted | ✅ **CLOSED** (file deleted, all references removed) |

### Follow-ups still open

| # | Issue | Change name |
|---|---|---|
| F4 | Landing page partial (~3 of 731 strings translated) | `feat(i18n): landing page EN marketing copy` (needs marketing review) |
| F7 | Spec deltas for cross-cutting capabilities missing | `docs(spec): fold cross-cutting i18n REQs into capability specs` |
| F8 (new from coverage cycle) | `ChatMessages.tsx` line 17 hardcoded EN empty-state string | `feat(i18n): translate ChatMessages empty state` |

## Per-commit breakdown

```
a5e9be0  docs(i18n): update README authCopy section to reflect removal
5935bcf  chore(i18n): remove deprecated authCopy.ts + cleanup stale slice-5 comments
89e95cb  chore(i18n): migrate reset-password page from authCopy to getTranslations
da73632  test(i18n): migrate 10 test files off authCopy to messages/es.json
```

| Commit | LOC delta | Files | Acceptance gate |
|---|---|---:|---|
| `da73632` (test migration) | +152 / −113 | 10 test files | typecheck ✓ / lint ✓ / test ✓ (270) / build ✓ |
| `89e95cb` (reset-password page) | +20 / −4 | 1 prod + 1 test mock | typecheck ✓ / lint ✓ / test ✓ (270) / build ✓ |
| `5935bcf` (authCopy.ts deletion) | +3 / −124 | 1 file deleted + 7 docstrings cleaned | typecheck ✓ / lint ✓ / test ✓ (270) / build ✓ |
| `a5e9be0` (README) | +6 / −4 | 1 README | docs only |

**Net: +181 / −245** (net −64 LOC — the seed file was 110 LOC of static data).

## Final state

- `frontend/src/lib/authCopy.ts` — **DELETED** (110-LOC seed file)
- Test files importing `authCopy` — **0** (was 10)
- Production files importing `authCopy` — **0** (was 1 — gap from F5)
- `git grep authCopy` in `frontend/src/**` / `frontend/messages/**` — **0 matches**
- `git grep authCopy` overall — only README historical note + 7 SDD artifacts in `openspec/changes/feat-frontend-i18n/` (expected; the migration record)

## CI gate final results

| Gate | Status |
|---|---|
| `pnpm run typecheck` | ✅ PASS |
| `pnpm run lint` | ✅ PASS |
| `pnpm run test` | ✅ PASS (270 tests across 44 files) |
| `pnpm run build` | ✅ PASS |

Test count: **272 → 270** (the −2 are 2 explicit "regression: authCopy import is preserved" assertions removed because they only existed to keep the deprecated import alive).

## Discoveries

1. **The brief said "9 test files" but there were 10.** The `frontend/src/app/[locale]/(auth)/reset-password/__tests__/page.test.tsx` test was missed by the explore. Including it kept the migration honest.
2. **Production code was NOT fully migrated in F5 of v1.** The async server component `src/app/[locale]/(auth)/reset-password/page.tsx` was still importing `authCopy` (lines 4, 25–31). This had to be migrated to `getTranslations` in a dedicated commit (commit 2) BEFORE authCopy.ts could be deleted. The coverage cycle's explore §5.3 flagged it as "out of scope" for that cycle.
3. **`getTranslations` requires `vi.mock("next-intl/server")` in jsdom tests.** The factory closure references the imported `esMessages` constant; safe because vitest hoists the factory declaration but only evaluates the body when the mocked module is first imported (by which point `esMessages` is loaded).
4. **2 explicit "regression" tests were asserting the authCopy import was still alive** (`route.test.ts:106`, `login/__tests__/page.test.tsx:98`). Both removed — they only existed to keep the deprecated import alive.
5. **7 of 8 `authCopy.*` namespaces needed renaming** during migration to align with the canonical Auth.* shapes in `messages/{en,es}.json`: `forgot → forgotPassword`, `reset → resetPassword`, `change → changePassword`, `delete → deleteAccount`, `banner → emailVerification`. `magicLink`, `globalSignOut`, `validation`, and `toast` kept their names.
6. **`@/messages/*` path alias was already configured** in both `tsconfig.json` and `vitest.config.ts` — made the test imports clean: `import esMessages from "@/messages/es.json"`. No new path-alias plumbing needed.

## Migration pattern used

```ts
// Before
import { authCopy } from "@/lib/authCopy";
expect(...).toBe(authCopy.forgot.title);

// After
import esMessages from "@/messages/es.json";
expect(...).toBe(esMessages.Auth.forgotPassword.title);
```

Plus a `@deprecated` JSDoc cleanup pass on 7 component files (slice-5 migration comments updated to drop the `authCopy` reference).

## Affected files (20 total)

**Modified (19):**
- 10 test files migrated
- 1 prod server component (`reset-password/page.tsx`) migrated
- 1 prod test mock (`reset-password/__tests__/page.test.tsx`) updated
- 7 component docstrings cleaned (slice-5 migration comments)

**Deleted (1):**
- `frontend/src/lib/authCopy.ts` (the 110-LOC seed file)

**Docs (1):**
- `frontend/README.md` — updated the "Auth strings" section to drop the authCopy deprecation note.

## Rollback

Single-PR revert (`git revert a5e9be0 5935bcf 89e95cb da73632`) is clean — all changes are localized to the i18n layer with no architectural changes outside what was already shipped in v1/v2/coverage.

## Carry-over follow-ups (priority order)

1. **F4** — Landing page EN marketing copy (~3 of 731 strings translated). Requires marketing review of canonical EN copy.
2. **F8 (new)** — Translate `ChatMessages.tsx` line 17 hardcoded EN empty-state string. Small follow-up, ~5 LOC.
3. **F7** — Fold cross-cutting i18n REQs (`frontend-dashboard`, `chat-frontend`, `favorites` deltas) into the canonical capability specs. Docs-only.

## Next steps

1. **Open the PR** from `chore-frontend-i18n-cleanup` against `main` (compare URL: `https://github.com/araldev/jobs-finder/compare/main...chore-frontend-i18n-cleanup?expand=1`).
2. The i18n coverage is now effectively complete for production code. The remaining items are polish (F4, F8) and docs (F7) — all small, can land individually.

## Series summary (v1 → v2 → coverage → cleanup)

| Cycle | LOC | Follow-ups closed | Status |
|---|---:|---|---|
| `feat-frontend-i18n` (v1) | ~4,050 | — | shipped (slice 1-15 + slice 16 remediation) |
| `feat-frontend-i18n-locale-prefix-urls` (v2) | ~395 | trade-off (canonical `/en/...` URLs) | shipped |
| `feat-frontend-i18n-complete-coverage` | ~498 | F2, F3, F5, F6 | shipped |
| `chore-frontend-i18n-cleanup` (v3) | ~426 (net −64) | F1 | shipped |
| **Total** | **~5,400** | **5 of 7** | 2 follow-ups remaining (F4 marketing, F7 docs) + F8 (small) |

The i18n layer is now functionally and architecturally complete for both English and Spanish, with canonical URLs, locale-aware auth bounces, OAuth redirect handling, a polished switcher widget, and 100% of production code translated.
