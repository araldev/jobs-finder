# Exploration: frontend-scaffold

> Investigación del backend existente y de las restricciones del workspace
> para fundamentar la propuesta de un primer slice de frontend.
> Read-only. No se modifica código.

## Contrato del backend (resumen)

El backend expone 4 endpoints `GET` + 1 endpoint `POST` en `backend/src/jobs_finder/presentation/`:

| Endpoint | Método | Query / Body | Respuesta | Headers clave |
| --- | --- | --- | --- | --- |
| `/jobs` (agregador) | GET | `q`, `location`, `limit=20`, `sources=linkedin,indeed,infojobs` | `AggregatedJobsResponse { jobs: AggregatedJobResponse[] }` | `X-Cache: HIT\|MISS[,HIT\|MISS,...]`, `X-Aggregator-Sources`, `X-Aggregator-Errors` (opcional) |
| `/jobs/linkedin` | GET | `keywords`, `location`, `limit=20` | `LinkedInJobsResponse { jobs: JobResponse[] }` | `X-Cache: HIT\|MISS` |
| `/jobs/indeed` | GET | `keywords`, `location`, `limit=20` | `IndeedJobsResponse { jobs: JobResponse[] }` | `X-Cache: HIT\|MISS` |
| `/jobs/infojobs` | GET | `keywords`, `location`, `limit=20` | `InfoJobsJobsResponse { jobs: JobResponse[] }` | `X-Cache: HIT\|MISS` |
| `/jobs/chat` | POST | `{ message: string }` | `ChatResponse { jobs, explanation, total_considered, total_matched, used_fallback }` | `X-RateLimit-*` (rate limit dedicado) |

`JobResponse` (canónico, mismo shape en las 4 fuentes) — 7 campos:

```ts
{
  id: string;
  title: string;
  company: string;
  location: string;
  url: string;          // HttpUrl en Pydantic → string en JSON
  description: string | null;
  posted_at: string | null;  // ISO-8601 datetime
  sources?: string[];   // SOLO en AggregatedJobResponse, ordenado por prioridad
}
```

### Headers adicionales (todas las rutas)

- `X-Request-Id` (UUID) — siempre presente.
- `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` — ausentes en rutas exentas (`/health`, `/docs`).
- `Retry-After` — solo en 429.

### Errores relevantes para el frontend

- **422** — validación (Pydantic o validación de tokens en `sources`).
- **429** — rate limit excedido (cuerpo `{"detail": "rate limit exceeded", "request_id": "..."}`).
- **502** — upstream source no disponible (per-source; el agregador los aísla con `X-Aggregator-Errors`).
- **422 chat** — `LLMResponseParseError`.
- **502 chat** — `LLMUnavailableError`.
- **400 chat** — `message exceeds N chars`.

## CORS — hallazgo CRÍTICO

`backend/src/jobs_finder/presentation/app_factory.py:666`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=effective_settings.cors_allow_origins,  # default ["*"]
    allow_methods=["GET"],
    allow_headers=["*"],
)
```

**`allow_methods` está fijado a `["GET"]`**. El preflight para
`POST /jobs/chat` desde el navegador será rechazado por CORS incluso
con `allow_origins=["*"]`. Esto fuerza una decisión de arquitectura
para el frontend:

> **El frontend DEBE llamar a `/jobs/chat` desde el servidor de Next.js
> (Route Handlers o Server Actions), no directamente desde un client
> component.** Las rutas `GET` SÍ pueden llamarse desde el cliente
> (CORS abierto + GET permitido), pero la homogeneidad y el secret
> del backend justifican centralizar TODAS las llamadas en el
> servidor de Next.js.

Esto queda registrado en la propuesta como **Riesgo #1**.

## Estado del frontend

`frontend/README.md` declara explícitamente que el stack no está
elegido y que el directorio debe permanecer vacío hasta entonces
(excepto tooling). El `AGENTS.md` raíz confirma el monorepo y
establece que el backend vive bajo `backend/src/jobs_finder/`. No
existe `frontend/package.json` ni `components.json`.

## Stack — fit check

- **Next.js App Router + TypeScript strict** → encaja limpiamente;
  CORS server-side elimina la fricción.
- **shadcn/ui** → la skill `shadcn` confirma que la versión actual
  usa Tailwind v4 por defecto + `base` (no Radix) para el preset
  `nova`. Preset recomendado para arrancar: `base-nova` (defensivo,
  bien documentado, usa Geist). Para "soft modern glass" se puede
  migrar después con `npx shadcn@latest apply <code>`.
- **`@tanstack/react-query`** → encaja con Server Components
  hidratando `HydrationBoundary`; permite cache, revalidación y
  reintentos.
- **`react-hook-form` + `zod`** → valida el formulario de búsqueda
  replicando las constraints de Pydantic (`min(1)`, `max(200)`).
- **`motion`** → reemplazó a `framer-motion` (paquete oficial,
  misma API).
- **`sonner`** → viene con el preset de shadcn.

## Variables de entorno relevantes para el frontend

Solo el frontend necesita saber:

| Var | Default sugerido | Propósito |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | URL del backend. Server-only en el runtime de Next.js; los Route Handlers la leen y llaman al backend. |
| `NEXT_PUBLIC_APP_URL` | `http://localhost:3000` | Para construir links canónicos (Open Graph, etc.). Opcional para v1. |

**No exponer `LLM_API_KEY`** al bundle del cliente (regla del propio
backend; la ruta de chat está protegida por el secret del LLM en el
servidor, no por auth de usuario).

## Estructura de archivos propuesta (resumen)

```
frontend/
├── app/
│   ├── layout.tsx              # html, body, font, theme provider
│   ├── page.tsx                # home: search + results + chat
│   ├── api/
│   │   ├── jobs/route.ts      # proxy GET /jobs (agregador)
│   │   └── chat/route.ts      # proxy POST /jobs/chat
│   └── globals.css             # tokens semánticos + glass utility
├── components/
│   ├── ui/                     # shadcn primitives
│   ├── search/
│   │   ├── search-form.tsx     # client; react-hook-form + zod
│   │   ├── job-card.tsx        # server-safe
│   │   ├── job-list.tsx        # grid + empty/loading/error
│   │   └── job-skeleton.tsx
│   └── chat/
│       ├── chat-panel.tsx      # client; useChat (tanstack/react-query)
│       ├── chat-message.tsx
│       └── chat-empty.tsx
├── lib/
│   ├── api/
│   │   ├── client.ts           # fetch tipado al backend (server)
│   │   └── schemas.ts          # zod mirror de JobResponse / ChatResponse
│   ├── query/
│   │   └── keys.ts             # react-query keys canónicas
│   └── utils.ts                # cn() helper
├── hooks/
│   ├── use-search-jobs.ts      # useQuery
│   └── use-chat.ts             # useMutation con optimistic
├── types/
│   └── api.ts                  # tipos compartidos (zod-inferred)
├── .env.example
├── .env.local                  # gitignored
├── components.json             # shadcn config
├── next.config.ts
├── package.json
├── tsconfig.json               # strict + noUncheckedIndexedAccess
├── tailwind.config.ts          # v4 usa @theme inline en globals.css
└── README.md
```

## Áreas afectadas (lectura realizada)

- `backend/README.md` — contrato HTTP completo, headers, env vars, manual verification.
- `backend/.env.example` — todas las env vars (239 líneas).
- `backend/src/jobs_finder/presentation/schemas.py` — modelos Pydantic.
- `backend/src/jobs_finder/presentation/routes/aggregator.py` — `/jobs` route.
- `backend/src/jobs_finder/presentation/routes/linkedin.py` — `/jobs/linkedin`.
- `backend/src/jobs_finder/presentation/routes/indeed.py` — `/jobs/indeed`.
- `backend/src/jobs_finder/presentation/routes/infojobs.py` — `/jobs/infojobs`.
- `backend/src/jobs_finder/presentation/routes/chat.py` — `/jobs/chat` (NO streaming).
- `backend/src/jobs_finder/presentation/app_factory.py:660-668` — CORS middleware (CRÍTICO).
- `backend/src/jobs_finder/infrastructure/config.py:144` — `cors_allow_origins` default `["*"]`.
- `backend/src/jobs_finder/domain/job.py` — value object `Job` (no se traduce literal; el frontend consume `JobResponse`).
- `backend/src/jobs_finder/main.py` — entry point.
- `backend/tests/integration/test_cors.py` — confirma comportamiento de CORS.
- `frontend/README.md` — placeholder, sin stack.
- `README.md` (raíz) — workspace index.
- `AGENTS.md` (raíz) — convenciones del monorepo.

## Limitaciones / cosas que el backend NO hace (importantes para el frontend)

1. **Chat NO streamea.** `/jobs/chat` devuelve un `ChatResponse`
   completo en una sola respuesta (5-8s end-to-end con la 2-stage
   LLM). El "efecto ultramoderno" de typing-token-by-token
   requiere un cambio separado en el backend (SSE / NDJSON). El
   frontend v1 mostrará un spinner + skeleton durante la espera.
2. **El LLM está OFF por default.** `LLM_FILTER_ENABLED=false` y
   `LLM_API_KEY=None` → la ruta devuelve 404. El frontend debe
   detectar el 404 y degradar la UI (esconder el panel de chat o
   mostrar un mensaje "Activa el chat en el backend").
3. **No hay paginación cliente en el agregador.** El `limit` se
   envía al backend; no hay cursor / `next` token. Para v1
   basta con `limit=20..50` y un botón "Buscar de nuevo" o un
   `infinite scroll` con `start` calculado en cliente (no es
   parte del contrato actual — ver Riesgos).
4. **El agregador NO pagina entre fuentes.** Cuando una fuente
   tiene más de `limit` resultados, los scrapers internamente
   auto-paginan hasta `MAX_PAGES`, pero el agregador solo
   devuelve hasta `limit` después del dedup.

## Preguntas abiertas para el orchestrator

Ninguna bloqueante. Las decisiones de stack y arquitectura están
fundamentadas con la lectura del backend.

## Listo para propuesta

Sí. Las decisiones de stack (Next.js App Router, shadcn `base-nova`,
Tailwind v4, react-query, RHF+zod, motion, sonner) y la decisión
arquitectónica de centralizar el API en Route Handlers (por CORS) ya
están justificadas. La propuesta puede entrar a `sdd-propose`.
