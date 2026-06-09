# Propuesta: frontend-scaffold

## Intención

Construir el primer slice de frontend para `jobs-finder`: una SPA en
Next.js (App Router) que consume el backend FastAPI ya existente y
ofrece a usuarios finales una experiencia de búsqueda + chat con
estética "Soft/Modern Glass". Este cambio NO agrega endpoints al
backend ni introduce lógica de scraping; cierra la brecha
"backend existe, no hay cliente" entregando una UI mínima
"lovable" que valida el contrato HTTP, demuestra el flujo end-to-end
y sienta las bases de diseño para iteraciones siguientes.

## Alcance

### Dentro de alcance (v1, "minimum lovable")

- Scaffold Next.js 15 (App Router) + TypeScript strict.
- `npx shadcn@latest init --template next --preset base-nova` + Tailwind v4.
- Layout global con tokens semánticos, fuentes Geist, dark mode por
  `prefers-color-scheme` (sin toggle en v1).
- UI de búsqueda: input de keywords + input de location + botón
  "Buscar" (react-hook-form + zod; límites 1..200 chars replican
  Pydantic).
- Grid de resultados consumiendo `GET /jobs` (el agregador).
  Cada card muestra title, company, location, posted_at relativo
  ("hace 3 días") y badges por source (`linkedin`/`indeed`/`infojobs`).
- Panel de chat adyacente a los resultados, consumiendo
  `POST /jobs/chat`. Muestra la respuesta del LLM (jobs filtrados
  + explicación en español) en una sola "burbuja" tras la espera
  (spinner + skeleton, sin streaming — ver Riesgos).
- Estados básicos: empty, loading (Skeleton), error (Alert con
  detail + botón "Reintentar"). El 404 del chat (feature OFF en
  backend) se maneja con degradación elegante.
- `app/api/jobs/route.ts` y `app/api/chat/route.ts` como Route
  Handlers que hacen de proxy server-side al backend. Ver
  "Integración con la API" abajo para la justificación.
- Tanstack Query (`@tanstack/react-query`) con un `QueryClient`
  provider y un `HydrationBoundary` por si en el futuro se
  pre-cargan datos en el server.
- `motion` para micro-interacciones: stagger del grid, fade-in de
  cards, "thinking dots" en el chat mientras espera.
- `sonner` para toasts de error.
- `.env.example` con `NEXT_PUBLIC_API_BASE_URL` apuntando a
  `http://localhost:8000`.
- `README.md` que reemplaza el placeholder actual.
- **Sin tests automatizados en v1** (ver Riesgos → testing).

### Fuera de alcance (v1)

- Tabs por fuente (LinkedIn / Indeed / InfoJobs por separado).
- Job tracker / saved searches / bookmarks.
- Settings page.
- Auth (ni la hay en el backend).
- Optimizaciones SSR (RSC streaming, partial prerendering, etc.).
- Toggle de dark mode (usa `prefers-color-scheme`).
- PWA / offline / service worker.
- i18n (UI monolingüe español para coincidir con el chat).
- Analytics / tracking.
- Deploy config (Vercel/Docker) más allá de `.env.example`.
- Streaming del chat (SSE / NDJSON). Requiere cambio en el backend.

## Dirección estética — "Soft/Modern Glass"

Display: **Geist** (sans geométrica humanista, de Vercel — el preset
`base-nova` la trae por defecto; es legible y de carácter
moderado, evita el "AI slop" de Inter). Body: **Geist Sans** en
weight 400/500. Numerales tabulares en el grid.

Paleta: blanco hueso / gris grafito en light, charcoal con acento
lavanda apagado en dark. **Un solo acento saturado pastel** (azul
lavanda `#8b85ff` o similar) reservado para CTA primario + bordes
de focus. No más de 2 colores de acento en total. CSS variables
semánticas (`--background`, `--foreground`, `--primary`,
`--ring`, `--muted`, `--muted-foreground`, `--border`).

Glassmorphism **medido**: `backdrop-filter: blur(12px)` + `bg-white/60`
en cards flotantes y panel de chat; bordes 1px con `--border/50` y
sombras suaves (`shadow-[0_8px_30px_rgb(0_0_0/0.04)]`). No cristal
sobre cristal recursivo: solo 1 nivel de glass, el resto son
superficies planas con jerarquía por sombra y densidad.

Composición: hero centrado con búsqueda (max-width 720px), grid
de cards 1 col en mobile / 2 en `md` / 3 en `lg`, panel de chat
como `Sheet` deslizable en mobile y columna fija de 380px en
`lg+`. Generous padding (24-48px), `tracking-tight` en headings,
leading relajado (1.6) en body.

Motion: stagger 60ms en mount del grid, fade-in + translate-y 8px
en cada card, spring suave en la apertura del Sheet del chat.
Sin animaciones decorativas: cada movimiento tiene función.

**Por qué encaja**: el público (end-users buscando trabajo) pasa
mucho tiempo leyendo cards y respuestas de chat; el glass aporta
"calma visual" y separa la zona activa (input + chat) del
contenido escaneable (grid). El acento único evita fatiga en
sesiones largas. La estética es moderna pero no avasallante, que
es lo que diferencia un buscador de empleo de un dashboard de
métricas.

## Stack y versiones

Next.js `^15` (App Router) + React `^19` + TypeScript `^5.6` strict
(`noUncheckedIndexedAccess: true`, cero `any`) + Tailwind `^4` (default
del preset, `@theme inline` en `globals.css`). shadcn via CLI
`latest` (componentes copiados, no dependencia). `@tanstack/react-query`
`^5` para cache/reintentos. `react-hook-form` `^7` + `zod` `^3` +
`@hookform/resolvers` `^3` (validación espejo de Pydantic). `motion`
`^11` (reemplazo oficial de framer-motion). `sonner` `^1` para toasts.
`lucide-react` para iconos. `clsx` + `tailwind-merge` para el helper
`cn()` canónico de shadcn.

**Preset shadcn elegido**: `base-nova`. Justificación: es el
preset oficial por defecto, usa Geist, tiene documentación
extensa y la skill `shadcn` (su regla `rules/styling.md`) lo
trata como base segura. Si la estética "glass" necesita ajustes
(blur, sombras, paleta), se hace con `apply <code>` posterior o
editando `globals.css` directamente — el preset no es un
callejón sin salida.

## Estructura de archivos

```
frontend/
├── app/
│   ├── layout.tsx, page.tsx, globals.css
│   └── api/{jobs,chat}/route.ts
├── components/
│   ├── ui/                     # shadcn: button, input, card, sheet, skeleton,
│   │                           # alert, empty, badge, sonner, field, input-group
│   ├── search/{search-form,job-card,job-list,job-skeleton}.tsx
│   └── chat/{chat-panel,chat-message,chat-empty}.tsx
├── lib/
│   ├── api/{client,schemas}.ts        # fetch tipado + zod
│   ├── query/{client,keys}.ts         # react-query setup
│   └── utils.ts                       # cn()
├── hooks/{use-search-jobs,use-chat}.ts
├── types/api.ts
├── .env.example, .gitignore, components.json, next.config.ts,
│   package.json, tsconfig.json, postcss.config.mjs, README.md
```

## Integración con la API

**Decisión**: TODAS las llamadas al backend pasan por Route Handlers
de Next.js (`app/api/jobs/route.ts`, `app/api/chat/route.ts`). El
cliente (componentes) llama a `/api/jobs` y `/api/chat` (rutas
relativas del propio Next), nunca al host del backend.

**Justificación**:

1. **CORS bloquea el `POST /jobs/chat` desde el navegador.**
   `app_factory.py:666` define `allow_methods=["GET"]`. Ampliar la
   lista es un cambio de backend (out of scope de este slice).
2. **Secrets del backend nunca llegan al bundle del cliente.**
   El Route Handler corre en el runtime de Node y puede leer
   headers / cookies / config del servidor.
3. **Homogeneidad**: una sola capa de fetch (en el Route Handler)
   con reintentos, timeouts, mapeo de errores, normalización de
   headers (`X-Request-Id` propagado al cliente, etc.).
4. **Cache edge-friendly en el futuro**: los Route Handlers se
   pueden marcar `revalidate` o `cache: 'force-cache'` sin tocar
   el cliente.

El Route Handler de `/api/jobs` acepta `?q=&location=&limit=`,
reenvía al backend, normaliza la respuesta a la forma que el
cliente consume (zod-parseada), y devuelve el JSON. El de
`/api/chat` acepta `{ message }`, reenvía a `/jobs/chat`, y
devuelve `ChatResponse`.

## Riesgos y preguntas abiertas

1. **[BLOQUEANTE CONDICIONAL] CORS `allow_methods=["GET"]`.** El
   chat NO puede llamarse directo del navegador. Mitigación: Route
   Handlers server-side (decisión ya tomada). Si en el futuro se
   quiere cliente → backend directo, hay que ampliar la lista
   `allow_methods` en `app_factory.py` (cambio de 1 línea, propio
   backend, follow-up change).

2. **[NO STREAMING] Chat devuelve respuesta completa en una sola
   request (5-8s con 2-stage LLM).** El "ultramodern token-by-
   token" no es posible en v1. Mitigación: spinner + skeleton
   animado con "thinking dots" durante la espera. El usuario
   percibe progreso sin streamear. Si se quiere streaming real,
   requiere un cambio en el backend (SSE o NDJSON en `/jobs/chat`).

3. **[DEGRADACIÓN] `LLM_FILTER_ENABLED=false` (default en
   backend) → `POST /jobs/chat` devuelve 404.** El frontend debe
   detectar el 404 y mostrar el panel de chat deshabilitado con
   un mensaje claro ("Activa el chat en el backend con
   `LLM_FILTER_ENABLED=true` y `LLM_API_KEY=<key>`"). El Route
   Handler traduce 404 → `200 { available: false }` para no
   contaminar la UI de errores.

4. **[ENV VARS] Solo `NEXT_PUBLIC_API_BASE_URL` es estrictamente
   necesaria para v1.** `NEXT_PUBLIC_APP_URL` opcional para OG
   metadata. `LLM_API_KEY` NUNCA se expone al cliente (la ruta de
   chat ya está protegida por el secret del LLM en el backend).

5. **[TESTING] TDD OFF en el backend. Propuesta para v1:
   test-after con un follow-up change.** El scaffold v1 entrega
   valor visible rápido; el equipo prefiere iterar sobre diseño
   que escribir tests sobre un cromo que va a cambiar. Si tras
   1-2 iteraciones el cromo se estabiliza, se abre un change
   "frontend-test-coverage" con vitest + @testing-library/react
   (componentes), MSW para mock de Route Handlers, y Playwright
   para un smoke e2e del flujo búsqueda → resultados.

6. **[RATE LIMIT] El backend impone 20 req/min/IP y 20 req/min/IP
   en chat.** El frontend NO debe deshabilitar esto. Si el
   usuario ve un 429, mostrar Alert "Demasiadas búsquedas,
   espera un momento" con el `Retry-After` en el mensaje.

7. **[PRESCINDIBLE] Sin paginación "ver más" en v1.** El backend
   no expone cursor; el frontend puede usar un `limit` mayor
   (hasta 100) y un scroll infinito client-side sobre el array
   recibido. Decisión: `limit=30` por defecto, sin paginación
   visible en v1. Si se necesita paginación real, sigue siendo
   un follow-up.

8. **[SEGURIDAD] No exponer el backend completo al público.** El
   Route Handler de Next SOLO expone `/jobs` (agregador) y
   `/chat`. NO se exponen los endpoints por fuente ni `/health`
   del backend.

## Estimación de volumen de código (LOC)

~2900 LOC totales: ~200 (config) + ~300 (layout/page/globals) + ~350
(Route Handlers + zod schemas) + ~450 (componentes search) + ~300
(componentes chat) + ~200 (hooks/query setup) + ~150 (tipos) + ~800
(primitives shadcn generados) + ~150 (README). Bien dentro del budget
de 5000 — **PR único, sin split**.

**Veredicto budget**: el cambio cabe en un solo PR. NO se
recomienda split a chained PRs; un solo slice cohesivo es más
fácil de revisar y de revertir.

## Forma del trabajo (tasks tentativos para `sdd-tasks`)

Estos son los work units que el orchestrator verá. NO son el
breakdown formal — eso es trabajo de `sdd-tasks`.

- **T1. Bootstrap del proyecto Next.js + shadcn.** `create-next-app`
  con TS strict, `shadcn init --preset base-nova`, añadir los 10
  primitives necesarios (button, input, card, sheet, skeleton,
  alert, empty, badge, sonner, field, input-group). Verificar
  que `npm run dev` arranca.
- **T2. Layer de API server-side.** `lib/api/client.ts` con un
  `fetchBackend<T>(path, init)` tipado, zod schemas espejo de
  Pydantic (`JobResponse`, `AggregatedJobResponse`, `ChatRequest`,
  `ChatResponse`), y los Route Handlers `app/api/jobs/route.ts` +
  `app/api/chat/route.ts`. Mapeo de errores (404 chat → degraded,
  429 → retry, 502 → Alert). Smoke test manual con curl.
- **T3. UI de búsqueda + grid de resultados.** `search-form.tsx`
  (RHF + zod con `min(1) max(200)`), `job-list.tsx` (grid
  responsive + estados empty/loading/error), `job-card.tsx`
  (server-safe, con `formatRelativeTime` para `posted_at`),
  `job-skeleton.tsx`. Hook `use-search-jobs` con react-query
  (`enabled` solo cuando hay q+location, `staleTime: 60_000`).
- **T4. UI de chat.** `chat-panel.tsx` (Sheet en mobile, columna
  fija en `lg+`), `chat-message.tsx` (burbuja assistant con la
  explanation + grid de JobCards filtradas), `chat-empty.tsx`
  (estado inicial con ejemplos), `chat-degraded.tsx` (cuando el
  backend devuelve 404). Hook `use-chat` (useMutation, sin
  streaming, con optimistic update opcional).
- **T5. Composición + estética.** `app/layout.tsx` con fuentes
  Geist, `app/globals.css` con tokens semánticos + utility
  `glass`, `app/page.tsx` que combina `search-form`,
  `job-list`, `chat-panel`. Ajustes de motion (stagger del grid,
  spring en Sheet).
- **T6. Documentación + calidad.** `README.md` con setup, scripts
  (`dev`, `build`, `start`, `lint`, `typecheck`), troubleshooting
  común (CORS, 404 chat, 429). `tsc --noEmit` y `eslint` clean.
  Manual smoke test siguiendo la checklist del README.

**No hay tasks de tests automatizados** en este change (ver
Riesgo #5). Si el usuario quiere TDD desde día 1, abrir
`frontend-test-coverage` como follow-up.

## Decisiones que el orchestrator puede ratificar o ajustar

- **Preset `base-nova`** vs `lyra` u otro más "glass" — cambio
  barato via `npx shadcn@latest apply <code>`.
- **`limit=30`** por defecto (sweet spot entre 20 default y 100 max).
- **TDD follow-up** vs día-1 (recomendado: follow-up `frontend-test-coverage`).
- **PR único** recomendado (dentro del budget).

## Listo para spec

Sí. El contrato HTTP, los riesgos abiertos y la estructura están
claros. La fase de `sdd-spec` puede traducir esto en deltas
concretos (`requirements.md` + `design.md`).
