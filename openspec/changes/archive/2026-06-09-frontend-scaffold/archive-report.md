# Archive Report: frontend-scaffold

## Status

**Closed** — implementación completa, verificación **PASS WITH WARNINGS**
(0 CRITICAL, 1 WARNING non-blocking, 4 SUGGESTION non-blocking). El
frontend es una web app Next.js 15 / React 19 / TypeScript strict /
Tailwind v4 / shadcn-ui (preset `base-nova`) / TanStack Query / motion /
sonner que proxifica el backend FastAPI a través de 3 Route Handlers
(`/api/jobs`, `/api/chat/stream`, `/api/health`). Las 4 quality gates
(typecheck, lint, test, build) pasan en verde. Dev server arranca y
sirve `/` con HTTP 200. Los 18 REQ tienen implementación verificada, 16
de ellos con cobertura automatizada.

## Traceability — observation IDs de los artefactos del change

| Topic | Observation ID | Status |
|---|---|---|
| `sdd/frontend-scaffold/explore` | #304 | explored |
| `sdd/frontend-scaffold/proposal` | #305 | proposed (`status: archived` después de este report) |
| `sdd/frontend-scaffold/spec` | #315 | specified |
| `sdd/frontend-scaffold/design` | #316 | designed |
| `sdd/frontend-scaffold/tasks` | #317 | planned |
| `sdd/frontend-scaffold/apply-progress` | #318 | applied |
| `sdd/frontend-scaffold/verify-report` | #319 | verified (PASS WITH WARNINGS) |
| `sdd/frontend-scaffold/archive-report` | #320 (este report) | archived |

## Type

`feature` — primer slice del cliente web de `jobs-finder` (no es una
extensión de capability existente; es una capability nueva).

## Capability name

`frontend-scaffold` — añade el workspace `frontend/` con una web app
Next.js 15 completa que consume el agregador `GET /jobs` del backend
y el nuevo endpoint SSE `POST /jobs/chat/stream` (archivado en
`2026-06-09-chat-streaming`, obs #313). El frontend NUNCA habla
directo al backend: todo el tráfico pasa por 3 Route Handlers
server-side.

## Commits (11, branch `feature/frontend-scaffold`)

| Hash | Subject |
|---|---|
| `674bd2c` | chore(frontend): scaffold Next.js 15 with TypeScript strict and Tailwind v4 |
| `06d7ed0` | chore(frontend): init shadcn/ui with nova preset and 14 components |
| `15db1a3` | feat(frontend): add Soft/Modern Glass aesthetic tokens and Geist font wiring |
| `0b61215` | feat(frontend): add lib (types, api, backend, format, forwarder) and hooks |
| `e4c593a` | feat(frontend): add Route Handlers for /api/jobs, /api/chat/stream, /api/health |
| `8d04763` | feat(frontend): add root layout, providers, page shell, topbar, onboarding |
| `b4921f7` | feat(frontend): add search components and useDebouncedJobsSearch hook |
| `a48c208` | feat(frontend): add chat components and useChatStream hook |
| `69c8657` | test(frontend): add unit tests for api, chat-stream-forwarder, useDebouncedValue |
| `9e6439c` | docs(frontend): add README and update root AGENTS.md |
| `d996e0e` | docs(openspec): track design and tasks artifacts for frontend-scaffold |

> Tip: 10 work units + 1 doc commit. Diff vs `main` total: ~4,987
> effective LOC (vs design forecast ~2,980; delta ~2,000 por los 16
> shadcn primitives generados en `src/components/ui/`). 19 unit tests
> in-scope, 4 quality gates verde, 0 CRITICAL findings.

## PRs

Per la preflight `ask-always`, el orchestrator decidirá. La rama
`feature/frontend-scaffold` está lista para `git push` + open PR. El
orchestrator deberá promptar al user.

## Specs promovidos al source of truth

### `frontend-scaffold` (spec fundacional — promoted to canonical)

El delta spec del change
(`openspec/changes/frontend-scaffold/specs/frontend-scaffold/spec.md`)
era **fundacional** (no existía main spec previo). Se promovió completo a:

```
openspec/changes/frontend-scaffold/specs/frontend-scaffold/spec.md
  → openspec/specs/frontend-scaffold/spec.md
```

Contiene 18 REQ-* ADDED (REQ-NEXT-001, REQ-SHADCN-001,
REQ-AESTHETIC-001, REQ-SEARCH-001/002, REQ-CHAT-001/002, REQ-API-001,
REQ-ERROR-001, REQ-EMPTY-001, REQ-ONBOARDING-001, REQ-A11Y-001,
REQ-RESPONSIVE-001, REQ-ENV-001, REQ-MICRO-001, REQ-DOCS-001,
REQ-FALLBACK-001, REQ-TEST-001) — todas ADDED (no MODIFIED, no
REMOVED, porque es una capability nueva).

> **Cero MODIFIED/REMOVED en otras capabilities.** El change es
> netamente additive: introduce la capability `frontend-scaffold` y
> deja intactas las 2 capabilities backend ya canónicas
> (`chat-streaming`, `aggregator-and-routes`).

## Pre-condiciones para el próximo change

1. `feature/frontend-scaffold` está lista para push y open PR (NO
   pusheada aún — orchestrator decide per preflight `ask-always`).
2. El 1 WARNING (REQ-A11Y-001 parcial: skip-link ausente +
   `aria-live` ausente en el contenedor del chat) es non-blocking
   pero conviene cerrarlo en un follow-up.
3. Los 4 SUGGESTIONs (SearchBar `whileTap`, tsconfig `incremental`
   cache location, `oklch` browser support, lucide-react pin policy)
   son non-blocking y pueden abordarse en un follow-up.
4. **La v1 frontend usa test-after, NO strict TDD.** Un follow-up
   change `frontend-test-coverage` está planeado para añadir E2E
   tests, component tests, MSW para HTTP mocking, y auditoría a11y
   con axe/pa11y. NO está en scope de `frontend-scaffold`.

## Archive contents

```
openspec/changes/archive/2026-06-09-frontend-scaffold/
├── explore.md         ✅
├── proposal.md        ✅
├── design.md          ✅
├── tasks.md           ✅ (10/10 tasks complete)
├── verify-report.md   ✅ (PASS WITH WARNINGS)
└── specs/
    └── frontend-scaffold/
        └── spec.md    ✅ (18 REQ-* ADDED, 0 MODIFIED, 0 REMOVED)
```

Source of truth actualizado:

- `openspec/specs/frontend-scaffold/spec.md` (canonical, promoted)

## Próximos recomendados

- `feature/frontend-scaffold` → `git push` + open PR (orchestrator
  prompta al user per preflight `ask-always`)
- Follow-up change `frontend-test-coverage` — añadir E2E + component
  tests + auditoría a11y (cierra REQ-A11Y-001 y los 4 SUGGESTIONs)
- Follow-up change `frontend-a11y-fixes` (más pequeño, 1-2h) — solo
  skip-link + `aria-live` en ChatPanel (puede fusionarse con
  `frontend-test-coverage` si se prefiere un solo PR)

## Discoveries / decisions worth remembering for future changes

- **El frontend usa `fetch + ReadableStream` (no `EventSource`) para
  el chat stream** porque necesitamos POST con body. Este patrón es
  reusable para cualquier future streaming endpoint. Justificación
  documentada en `useChatStream.ts:22` ("EventSource does not support
  POST") y en `design.md` §"Data flow — chat (SSE)".
- **El 404 → 200 conversion en el Route Handler (chat stream) es un
  patrón defense-in-depth**: la UI no tiene que manejar 404 como caso
  especial. El `useChatStream` hook además chequea defensivamente
  `{available: false}` en el body. Test cubre ambos paths
  (`chat-stream-forwarder.test.ts` test "emits onDone({available: false})
  defensively when status is 404").
- **Los tipos TS en `src/lib/types.ts` son el source of truth para
  el frontend.** Cuando los Pydantic schemas del backend cambien, el
  sync manual es el cuello de botella. Un future change podría
  generar tipos TS desde el schema OpenAPI (FastAPI auto-genera en
  `/openapi.json`).
- **Test-after para el frontend v1 fue la decisión correcta:** 10
  work units, 11 commits, ~4,987 effective LOC, 19 unit tests
  focused en la lógica pura testable (api error mapping, SSE
  forwarder, debounce hook), 4 quality gates verde. El trade-off
  fue apropiado.
- **El preset `base-nova` de shadcn encajó bien con la estética
  "Soft/Modern Glass".** La fuente Geist (vía `next/font/google`) es
  la decisión correcta para 2026 — sin Inter/Roboto, sin FOUC, sin
  layout shift.
- **Las 11 desviaciones del design respecto al spec original** (todas
  aprobadas por el user) fueron fixes que alinearon el spec con el
  backend canónico. Patrón saludable: el spec phase hace asunciones,
  el design phase valida contra la realidad, y el user aprueba
  correcciones ANTES de que el apply phase shippee asunciones
  rotas. Las 11 desviaciones están listadas y verificadas en
  `design.md` §"Deviations from the proposal / spec" y
  `verify-report.md` §"Design deviations".
- **Las 4 quality gates del frontend** son
  `npm run typecheck` (tsc --noEmit) + `npm run lint` (next lint) +
  `npm run test` (vitest run) + `npm run build` (next build). Las 4
  corren en pre-commit y en CI. Esta es la convención
  `frontend/AGENTS.md` que cualquier futuro change frontend debe
  respetar.
- **`describe` del `Job` (`description: string | null`) está en el
  type pero NO se renderiza en v1** (defer a job-detail follow-up).
  Misma lógica para `formatRelativeTime` y los tabs por fuente —
  incluidos en el type system pero no en la UI de v1.

## Skill resolution

`paths-injected` (orchestrator pre-resolvió `sdd-archive/SKILL.md` +
`_shared/sdd-phase-common.md` + `openspec-convention.md` references).
