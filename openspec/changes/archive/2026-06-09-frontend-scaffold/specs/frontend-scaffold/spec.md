# Spec: frontend-scaffold

**Change**: `frontend-scaffold` • **Mode**: `both` • **Strict TDD**: NOT
ACTIVE (test-after for v1; see REQ-TEST-001)

> Spec fundacional para la capability `frontend-scaffold`. No existe
> `openspec/specs/frontend-scaffold/spec.md` previo. Al archivar, este
> spec se promoverá a `openspec/specs/frontend-scaffold/spec.md`.

## Purpose

Construir el primer slice de frontend para `jobs-finder`: una web
app "Soft/Modern Glass" sobre Next.js 15 (App Router) que consume el
backend FastAPI ya existente y ofrece a usuarios finales (1)
búsqueda de empleo a través de `GET /jobs` con un grid responsive
de job cards, y (2) refinamiento por chat consumiendo
`POST /jobs/chat/stream` (SSE) con efecto "typewriter" en tiempo
real. El frontend actúa como capa de presentación: nunca llama al
backend directamente — todo el tráfico pasa por Route Handlers
server-side. La estética prioriza primera-impresión pulida,
accesibilidad WCAG AA, y micro-interacciones funcionales. La
audiencia es end-user (no operadores), por lo que los empty states,
onboarding y estados de error son ciudadanos de primera clase.

**Dependencia externa clave**: el change backend `chat-streaming`
(archivado el 2026-06-09, obs #313) expone el endpoint SSE
`POST /jobs/chat/stream`. Este spec referencia explícitamente ese
contrato en REQ-CHAT-001 y REQ-CHAT-002.

## Requirements

### REQ-NEXT-001: Next.js 15 App Router scaffold con TypeScript strict

**Statement**: El frontend MUST ser un proyecto Next.js 15 instalado
bajo `frontend/` en la raíz del monorepo, usando App Router
(`frontend/app/`), TypeScript con `strict: true` Y
`noUncheckedIndexedAccess: true`. El `package.json` MUST fijar Next.js
a un rango de patch explícito (ej. `~15.0.0` o `15.1.x`), NUNCA
`latest`. `next.config.ts` (o `next.config.mjs`) MUST existir y
estar commiteado.

**Scenarios**:
- **Given** un checkout limpio del repo • **When** se inspecciona
  `frontend/package.json` • **Then** aparece `next` con un rango
  pinned (no `latest`, no `*`)
- **And** `frontend/tsconfig.json` contiene
  `"strict": true` y `"noUncheckedIndexedAccess": true` en
  `compilerOptions`
- **And** `frontend/next.config.ts` existe
- **And** `cd frontend && npm run dev` arranca en
  `http://localhost:3000` sin errores en consola

### REQ-SHADCN-001: shadcn/ui inicializado con preset base-nova

**Statement**: shadcn/ui MUST estar inicializado con
`npx shadcn@latest init --template next --preset base-nova`. El
archivo `frontend/components.json` MUST estar commiteado con
`style: "nova"`, `base: "base"`, y `tailwind.css` apuntando a
`src/app/globals.css`. Los primitives MUST estar copiados bajo
`frontend/src/components/ui/` (no como dependencia npm). Los
componentes requeridos para v1: `button`, `input`, `card`, `badge`,
`skeleton`, `empty`, `field`, `field-group`, `input-group`,
`scroll-area`, `separator`, `avatar`, `tooltip`, `sonner`,
`spinner`, `dialog`, `tabs`, `sidebar`, `command`, `resizable`.

**Scenarios**:
- **Given** el spec ejecutado • **When** se inspecciona
  `frontend/components.json` • **Then** `style` es `"nova"` y
  `tailwind.css` apunta a `src/app/globals.css`
- **And** los 20 componentes listados existen bajo
  `frontend/src/components/ui/`
- **And** `frontend/src/lib/utils.ts` exporta la función `cn()`
- **And** `npx shadcn@latest info` ejecutado en `frontend/`
  reporta el proyecto correctamente

### REQ-AESTHETIC-001: Tokens de la estética "Soft/Modern Glass"

**Statement**: El sistema de diseño MUST implementar la estética
"Soft/Modern Glass" con: (a) fuente **Geist Sans** para body y
**Geist Mono** para code/numerales, cargadas via `next/font/google`
o el paquete oficial `@vercel/geist`; (b) light mode por defecto,
dark mode auto via `prefers-color-scheme` (sin toggle manual en
v1); (c) tokens semánticos de shadcn (`--background`,
`--foreground`, `--primary`, `--card`, `--muted`,
`--muted-foreground`, `--border`, `--ring`); (d) UN acento
pastel-saturado — el proposal sugiere lavanda `#A78BFA` o peach
`#FDA4AF`; la elección final vive en `design.md`; (e)
glassmorphism MEDIDO: `backdrop-filter: blur(12px)` + `bg-white/60`
solo en el panel de chat y el topbar (NO en cada card); (f) radios
generosos: `rounded-2xl` en cards, `rounded-full` en buttons y
badges.

**Scenarios**:
- **Given** la app corriendo en `localhost:3000` • **When** se
  inspecciona `frontend/src/app/globals.css` • **Then** aparecen
  las CSS variables de los tokens listados bajo `:root` y
  `.dark`
- **And** la fuente Geist está cargada via `next/font` (verificable
  en el `<head>` del HTML renderizado) sin FOUC ni layout shift
- **And** cambiar el `prefers-color-scheme` del browser a dark
  alterna la paleta sin acción del usuario
- **And** el botón "Send" del chat muestra el color de acento
  configurado

### REQ-SEARCH-001: Input de búsqueda + grid de resultados

**Statement**: La página principal MUST tener (1) un search form
en la parte superior con un input de `keywords`, un input de
`location`, y un botón "Buscar" (validado con `react-hook-form` +
`zod`; limits 1..200 chars espejando las constraints Pydantic del
backend), y (2) un grid de resultados debajo consumiendo
`GET /jobs?keywords=...&location=...&limit=20` del backend
(vía Route Handler). Cada job card MUST mostrar: `title`,
`company`, `location`, `posted_at` (formato relativo "hace 3 días"
via `Intl.RelativeTimeFormat`), un `Badge` con el `source`
(LinkedIn / Indeed / InfoJobs) color-coded, y un link a la URL
original del posting.

**Scenarios**:
- **Given** el usuario carga la página sin búsqueda previa
  • **When** se renderiza • **Then** el grid muestra el
  `Empty` de shadcn con icono, headline "Encuentra tu próximo
  puesto", y 3 chips de queries de ejemplo
- **Given** una búsqueda en flight • **When** la query está
  pendiente • **Then** el grid muestra 6 `Skeleton` cards
- **Given** la query resuelve con éxito • **When** llegan
  resultados • **Then** el grid renderiza 1 col en mobile,
  2 en `md`, 3 en `lg`, con cada card mostrando los 5 campos
  listados
- **Given** el backend responde 4xx/5xx • **When** el error
  llega • **Then** el grid muestra un `Alert` con el código
  del error y un botón "Reintentar" que re-dispara la query
- **And** hover sobre una card MUST elevar la card 2px y
  aumentar la sombra (REQ-MICRO-001)

### REQ-SEARCH-002: Búsqueda debounced + default-on-mount

**Statement**: El input MUST debouncear 400ms antes de disparar
la request al backend (no submit-on-every-keystroke). En el mount
inicial, la página MUST ejecutar una búsqueda con un query
default sensato (ej. `keywords="Software Engineer"`,
`location="Madrid"`, `limit=20`) para que los first-time visitors
vean resultados inmediatamente, sin pasar por el empty state.

**Scenarios**:
- **Given** el usuario tipea en el input de keywords • **When**
  tipea 5 caracteres en 2s • **Then** se dispara UNA sola
  request (no 5), 400ms después del último keystroke
- **Given** la página en first load • **When** se monta
  • **Then** se ejecuta una búsqueda default
  (`Software Engineer` + `Madrid` + `limit=20`) sin interacción
- **Given** el input es vaciado • **When** pasan 400ms
  • **Then** se restaura la búsqueda default automáticamente
- **And** la request en flight muestra el estado de loading
  (REQ-SEARCH-001 segundo scenario)

### REQ-CHAT-001: Panel de chat streaming consumiendo /jobs/chat/stream

**Statement**: Un panel de chat MUST estar adyacente a los
resultados de búsqueda (a la derecha en desktop, abajo en mobile)
y MUST consumir el endpoint `POST /jobs/chat/stream` (SSE) del
backend. El panel renderiza los chunks de texto a medida que
llegan (efecto typewriter) usando `motion` para la animación de
entrada. El contrato SSE MUST coincidir con el spec archivado
`openspec/specs/chat-streaming/spec.md`:
- **`event: meta`** (opcional, primero) — payload
  `{"intent": <Intent JSON>}`; se muestra como banner "Buscando:
  Madrid, junior, ..."
- **`event: text`** (uno o más) — payload `{"delta": "<chunk>"}`;
  se acumula y renderiza con efecto typewriter (~30-50ms por chunk)
- **`event: done`** (terminal) — payload
  `{"jobs":[...], "explanation":"...", "total_considered":N,
  "total_matched":M, "used_fallback":bool, "request_id":"..."}`; el
  frontend MUST reemplazar el grid de resultados con el subset
  `jobs` del done
- **`event: error`** (terminal alternativo) — payload
  `{"code": "<machine_code>", "message": "..."}`; se muestra un
  `Alert` con el código y mensaje

**Scenarios**:
- **Given** el panel de chat sin mensajes • **When** se
  renderiza inicialmente • **Then** muestra el `Empty` de
  shadcn con icono, headline "Refina tus resultados en lenguaje
  natural", y 3 chips de prompts de ejemplo
- **Given** el usuario tipea "busco junior en Madrid" y presiona
  Enter • **When** la request se dispara • **Then** el botón
  Send muestra un spinner y queda deshabilitado
- **Given** el servidor emite `event: meta` con un intent
  • **When** el browser lo recibe • **Then** el panel muestra
  un banner "Buscando: <intent_text>" en la parte superior
- **Given** el servidor emite 5 `event: text` chunks • **When**
  llegan secuencialmente • **Then** el texto aparece
  progresivamente con delay de 30-50ms entre chunks (typewriter)
- **Given** el servidor emite `event: done` con `jobs: [...]`
  • **When** llega el evento terminal • **Then** el grid de
  resultados MUST actualizarse al subset `jobs` del done y el
  botón Send vuelve a su estado normal
- **Given** el servidor emite `event: error` con
  `code: "llm_unavailable"` • **When** llega • **Then** el panel
  MUST mostrar un `Alert` con el código y mensaje; el grid
  previo permanece intacto
- **Given** la `explanation` del done dice "Sin coincidencias"
  • **When** se renderiza • **Then** el chat MUST mostrar "Sin
  coincidencias" + un botón "Limpiar filtro" que restaura el
  grid completo

### REQ-CHAT-002: Consumo SSE via Next.js Route Handler (proxy server-side)

**Statement**: El Next.js Route Handler
`frontend/src/app/api/chat/stream/route.ts` MUST actuar como
proxy server-side: (1) lee el body JSON `{message: string}` de
la request entrante, (2) hace POST a
`${BACKEND_URL}/jobs/chat/stream` con el mismo body
(server-to-server, sin CORS), (3) lee la respuesta SSE del
backend, (4) re-emite los eventos al browser a través de un
`ReadableStream` con `Content-Type: text/event-stream`,
preservando el orden (`meta?` → `text*` → `done|error`) y los
nombres de eventos verbatim. La variable de entorno `BACKEND_URL`
controla la URL del backend (default `http://localhost:8000`).
El browser NUNCA llama al backend directamente.

**Scenarios**:
- **Given** la app corriendo • **When** se inspecciona el
  código • **Then** ningún componente cliente importa `fetch` a
  `${BACKEND_URL}/...`; todo pasa por `/api/chat/stream` o
  `/api/jobs`
- **Given** el backend emite `event: meta` → `event: text`
  → `event: done` • **When** el Route Handler re-emite al browser
  • **Then** los eventos llegan en el mismo orden y con los
  mismos nombres
- **Given** la conexión del backend se interrumpe mid-stream
  • **When** el Route Handler detecta el corte • **Then** emite
  `event: error` con code `"stream_interrupted"` y cierra la
  conexión del browser
- **Given** `BACKEND_URL=http://staging.example.com:8000` en
  `frontend/.env.local` • **When** se reinicia `npm run dev`
  • **Then** el Route Handler llama al backend de staging
  (verificable con logs)

### REQ-API-001: Tipos TypeScript espejo de los schemas del backend

**Statement**: El frontend MUST definir tipos TypeScript
manualmente en `frontend/src/lib/types.ts` (sin codegen en v1;
los Pydantic schemas del backend son source of truth y los
cambios allí MUST disparar un sync manual de los tipos). Los
tipos MUST cubrir: `Job`, `JobListResponse`,
`ChatStreamMetaEvent`, `ChatStreamTextEvent`,
`ChatStreamDoneEvent`, `ChatStreamErrorEvent`. El tipo `Job`
MUST incluir al menos: `id`, `title`, `company`, `location`,
`source` (`'linkedin' | 'indeed' | 'infojobs'`), `link`, y
`posted_at` (string ISO-8601 o null).

**Scenarios**:
- **Given** el repo • **When** se inspecciona
  `frontend/src/lib/types.ts` • **Then** aparecen los 6 tipos
  listados
- **And** el tipo `source` es un union literal
  `'linkedin' | 'indeed' | 'infojobs'` (no `string`)
- **And** un cambio intencional al schema `Job` del backend
  que no se refleje en `types.ts` produce error de TypeScript
  al compilar (verificable con `npm run typecheck`)
- **And** el union `source` se corresponde exactamente con
  los 3 sources de `infrastructure/linkedin|indeed|infojobs/`

### REQ-ERROR-001: Manejo de errores unificado

**Statement**: Todas las llamadas a la API (search, chat, etc.)
MUST pasar por una capa unificada en
`frontend/src/lib/api.ts` que mapea errores del backend a
instancias tipadas `ApiError{code: string, message: string,
requestId?: string}`. Los componentes MUST mostrar errores
transitorios via `toast()` de `sonner` y errores context-bound
via `Alert` inline. Los códigos HTTP MUST mapearse a mensajes
amigables en español (audiencia end-user).

**Scenarios**:
- **Given** el backend responde 401 o 403 • **When** el error
  llega • **Then** se muestra un toast "Autenticación requerida"
- **Given** el backend responde 404 • **When** el error llega
  • **Then** se muestra un toast "Recurso no encontrado"
- **Given** el backend responde 429 con header `Retry-After: 30`
  • **When** el error llega • **Then** se muestra un toast
  "Demasiadas solicitudes, espera 30 segundos"
- **Given** el backend responde 5xx • **When** el error llega
  • **Then** se muestra un toast "Error del servidor, intenta
  de nuevo"
- **Given** un error de red (backend no alcanzable) • **When**
  el fetch falla • **Then** se muestra un `Alert` inline en el
  componente relevante (no toast)
- **And** TODOS los errores MUST preservar el `request_id` del
  header `X-Request-Id` para soporte

### REQ-EMPTY-001: Empty states pulidos para first-time users

**Statement**: La app MUST tener empty states amigables para
tres contextos: (a) no search yet, (b) zero results para el
search actual, (c) chat sin mensajes. Cada empty state usa el
componente `Empty` de shadcn con icono, headline, descripción, y
una acción sugerida (chip clickeable o botón).

**Scenarios**:
- **Given** la página en first load (con la búsqueda default
  habilitada por REQ-SEARCH-002 este caso es edge; verificar
  manualmente forzando empty) • **When** no hay search previa
  • **Then** aparece Empty con icono de búsqueda, headline
  "Encuentra tu próximo puesto", descripción, y 3 chips de
  ejemplo
- **Given** una búsqueda que no devuelve resultados • **When**
  el array `jobs` está vacío • **Then** aparece Empty con icono
  "no results", headline "No encontramos puestos para X",
  descripción "Prueba con una búsqueda más amplia u otra
  ubicación", y un botón "Limpiar filtros"
- **Given** el chat sin mensajes • **When** se renderiza
  • **Then** aparece Empty con icono de chat, headline "Refina
  tus resultados en lenguaje natural", descripción, y 3 chips
  de prompts de ejemplo

### REQ-ONBOARDING-001: Onboarding de first-time visitor

**Statement**: First-time visitors MUST ver un overlay de
onboarding breve (1-2 pantallas, dismissible, con botón
"Entendido") que explica las dos features principales: (1)
búsqueda agregada en 3 fuentes, (2) chat para refinar. El
estado de onboarding MUST persistirse en `localStorage` (clave
ej. `jobs-finder:onboarding-v1`) para que usuarios recurrentes
no lo vean. La prop es "dismiss" — no hay "step 2" obligatorio
en v1; el overlay es una sola pantalla.

**Scenarios**:
- **Given** un browser sin la clave en `localStorage`
  • **When** se carga la página • **Then** el overlay aparece
  sobre el contenido (semi-transparente, `aria-modal="true"`)
- **And** al hacer click en "Entendido" • **When** el botón se
  presiona • **Then** el overlay desaparece y la clave
  `jobs-finder:onboarding-v1` se setea en `localStorage`
- **And** recargar la página • **When** la clave existe
  • **Then** el overlay NO aparece
- **And** un shortcut oculto de teclado (ej. `Ctrl+Shift+R`)
  limpia la clave para re-ver el onboarding (útil para QA)

### REQ-A11Y-001: Baseline de accesibilidad

**Statement**: Todos los elementos interactivos MUST ser
accesibles por teclado. Todas las imágenes MUST tener alt
text. El contraste de color MUST cumplir WCAG AA. El panel de
chat MUST tener un `aria-live="polite"` region para los chunks
de texto. Los inputs MUST tener labels visibles (no usar
`placeholder` como único label). El skip-link "Saltar al
contenido principal" MUST estar presente.

**Scenarios**:
- **Given** la página renderizada • **When** se hace Tab desde
  el inicio • **Then** el primer focusable es el skip-link,
  seguido de: input keywords → input location → botón Buscar →
  input chat → botón Send
- **And** un screen reader anuncia los nuevos mensajes del chat
  a medida que llegan (verificable con `aria-live="polite"`
  en el contenedor de mensajes)
- **And** todos los inputs tienen `<label htmlFor>` o
  `aria-label` (no solo `placeholder`)
- **And** la paleta de tokens pasa WCAG AA contrast checks
  (verificable manualmente con axe DevTools o `pa11y` en un
  follow-up change)

### REQ-RESPONSIVE-001: Layout mobile-responsive

**Statement**: El layout MUST adaptarse a mobile (≤768px),
tablet (768-1024px), y desktop (≥1024px). En mobile, el panel
de chat colapsa a un tab/bottom-sheet debajo de los resultados.
En tablet, side-by-side con chat más angosto. En desktop,
side-by-side con chat de ancho completo.

**Scenarios**:
- **Given** viewport de 375px (mobile) • **When** se renderiza
  • **Then** los resultados ocupan el ancho completo y el chat
  está colapsado en un tab/bottom-sheet
- **Given** viewport de 768px (tablet) • **When** se renderiza
  • **Then** los resultados ocupan 60% y el chat 40%
  side-by-side
- **Given** viewport de 1280px (desktop) • **When** se renderiza
  • **Then** los resultados ocupan 65% y el chat 35%
  side-by-side
- **And** los 3 breakpoints se verifican manualmente
  redimensionando la ventana

### REQ-ENV-001: Configuración de entorno

**Statement**: El frontend MUST leer `BACKEND_URL` desde
`process.env` (convención Next.js server-side), con default
`http://localhost:8000` para dev local. El archivo
`frontend/.env.example` MUST estar commiteado documentando la
variable. En v1 la variable es server-only (el Route Handler
corre en el runtime de Node), por lo que NO es necesario el
prefijo `NEXT_PUBLIC_`.

**Scenarios**:
- **Given** el repo • **When** se inspecciona
  `frontend/.env.example` • **Then** aparece
  `BACKEND_URL=http://localhost:8000` con un comentario
  descriptivo
- **And** el Route Handler lee `process.env.BACKEND_URL` (no
  hardcoded)
- **And** cambiar `BACKEND_URL` en `frontend/.env.local`
  redirige el frontend al backend configurado (verificable
  en dev)

### REQ-MICRO-001: Micro-interacciones pulidas

**Statement**: Las siguientes micro-interacciones MUST estar
implementadas usando `motion` para casos complejos o CSS
transitions para casos simples: (a) botón Search: scale `0.97`
on press; (b) job card: hover eleva 2px + aumenta shadow;
(c) chat Send: estado disabled con spinner mientras in flight;
(d) chat text chunks: cada chunk nuevo fade-in con 100ms delay
(efecto typewriter acumulativo); (e) tab/badge: transición
sutil de color on hover; (f) empty state chips: hover scale
`1.02` + color change.

**Scenarios**:
- **Given** la app corriendo • **When** se interactúa
  • **Then** las 6 micro-interacciones listadas son visibles
- **And** la media query `prefers-reduced-motion: reduce`
  desactiva las animaciones no esenciales (motion tiene
  soporte built-in via `useReducedMotion`)

### REQ-DOCS-001: README + AGENTS.md actualizados

**Statement**: El frontend MUST tener un `frontend/README.md`
(reemplazando el placeholder actual) cubriendo: stack, setup,
scripts (`dev`, `build`, `start`, `lint`, `typecheck`),
estructura de directorios, variables de entorno, "Cómo
consumir el backend API", y una sección "Design system"
documentando los tokens de la estética. El `AGENTS.md` raíz
MUST actualizarse para documentar el workspace frontend.

**Scenarios**:
- **Given** el repo • **When** se inspecciona
  `frontend/README.md` • **Then** el archivo existe y no está
  vacío
- **And** el README enlaza al `backend/README.md` para
  detalles del HTTP API
- **And** el `AGENTS.md` raíz tiene una sección "Workspaces"
  actualizada con el frontend (stack, scripts, comandos)

### REQ-FALLBACK-001: Degradación elegante cuando el streaming no está disponible

**Statement**: Si el endpoint `POST /jobs/chat/stream` no está
disponible (404, 502, o el backend tiene
`LLM_FILTER_ENABLED=false`), el panel de chat MUST mostrar un
aviso no-bloqueante ("El filtro por chat está desactivado
actualmente") y el panel de búsqueda MUST seguir funcionando
normalmente. El usuario puede seguir navegando resultados sin
chat.

**Scenarios**:
- **Given** el backend devuelve 404 en `/api/chat/stream`
  • **When** el Route Handler propaga el error • **Then** el
  panel de chat muestra un estado disabled con un tooltip
  ("Activa el chat en el backend con `LLM_FILTER_ENABLED=true`
  y `LLM_API_KEY=<key>`")
- **Given** el backend devuelve 502 (transient) • **When** el
  Route Handler propaga • **Then** mismo UI que el 404
- **Given** `LLM_FILTER_ENABLED=false` en el backend • **When**
  el endpoint responde 404 • **Then** mismo UI que arriba
- **And** en TODOS los casos el panel de búsqueda sigue
  funcional (no se afecta)
- **And** el Route Handler MUST traducir el 404 del backend
  a una respuesta estructurada (ej. `200 { available: false,
  reason: "llm_disabled" }`) para no contaminar la UI de
  errores con 404s esperados

### REQ-TEST-001: Política de testing para v1 (test-after + selective unit)

**Statement**: Este change NO usa strict TDD (TDD es una
convención Python-only en este proyecto; ver AGENTS.md sección
"Conventions" #1). La política para v1 es **test-after
selectivo**: (1) hooks y utility functions puras MUST tener
unit tests escritos junto a la implementación (son baratos y
aíslan complejidad); (2) componentes UI, Route Handlers, y
flujos end-to-end se verifican manualmente siguiendo la
checklist del README en v1. Cobertura automatizada completa
(vitest + @testing-library/react + MSW + Playwright) es
follow-up change `frontend-test-coverage`. La estructura MUST
dejar espacio para los tests (`frontend/src/__tests__/` o
`frontend/tests/`) aunque esté vacía en v1.

**Scenarios**:
- **Given** un hook custom o utility function pura (ej.
  `formatRelativeTime`, `useDebouncedValue`, `parseSSEStream`)
  • **When** se implementa • **Then** existe un archivo de
  test sibling con casos happy path + edge case
- **And** `cd frontend && npm run lint` y `npm run typecheck`
  corren en CI/pre-commit
- **And** el README documenta la política de testing y referencia
  el follow-up change para cobertura completa

## Out of scope

Explícitamente NO en alcance de v1 (será follow-up o nunca):

- Toggle manual de dark mode (usa `prefers-color-scheme`)
- i18n / internacionalización (UI monolingüe español)
- PWA / offline / service worker
- Analytics / tracking
- Configuración de deploy (Vercel/Docker) más allá de
  `.env.example`
- Auth (el backend no la tiene)
- Tabs por fuente (LinkedIn / Indeed / InfoJobs por separado)
- Job tracker / saved searches / bookmarks
- Settings page
- Cobertura de tests automatizados completa (vitest +
  @testing-library + MSW + Playwright) → change
  `frontend-test-coverage`
- SSR optimizations (RSC streaming, partial prerendering, etc.)
- Cache edge del Route Handler
- Reemplazo de `POST /jobs/chat` (v1) — sigue siendo el
  fallback no-streaming del backend; el frontend NO lo consume
- WebSocket alternative al SSE
- Multi-turn conversation history

## Open questions

**None para bloquear el design phase.** Tres notas para el
equipo de `sdd-design`:

1. **Color de acento**: el proposal sugiere lavanda `#A78BFA` o
   peach `#FDA4AF`. La decisión final es del design phase
   (REQ-AESTHETIC-001).
2. **Hex de light mode "blanco hueso"**: el proposal menciona
   "blanco hueso" sin hex exacto. El design phase debe elegir
   (sugerencia: `#FAFAF9` o `#F5F5F4`).
3. **Comportamiento exacto del chat `done` event**: el spec
   archivado `chat-streaming` confirma que `event: done` lleva
   el array completo `jobs` (no `matching_ids`), así que el
   frontend reemplaza el grid directamente con esos jobs
   (REQ-CHAT-001). Esto se alinea con el proposal original.
4. **Discrepancia menor en el launch prompt**: el prompt del
   orchestrator describió el payload de `done` como
   `{matching_ids, explanation, request_id, cache_status}`,
   pero el spec archivado canónico (`openspec/specs/chat-streaming/spec.md`
   REQ-SSE-001 + REQ-PARSE-001) confirma el shape como
   `{jobs, explanation, total_considered, total_matched,
   used_fallback, request_id}`. **Este spec usa el shape
   canónico** — el frontend consume `jobs` directamente. Si
   en el futuro el equipo decide cambiar el shape, abrir un
   change `chat-streaming-v2` y propagar el delta. Flagged
   como risk en el envelope.

## Acceptance criteria

Checklist para `sdd-verify`:

- [ ] Todos los REQ-* cubiertos por verificación manual
      (test-after policy, REQ-TEST-001)
- [ ] `cd frontend && npm run build` exitoso sin errores
- [ ] `cd frontend && npm run lint` exitoso
- [ ] `cd frontend && npm run typecheck` exitoso
      (strict + noUncheckedIndexedAccess)
- [ ] `cd frontend && npm run dev` arranca sin errores en
      consola del browser
- [ ] Las 6 micro-interacciones de REQ-MICRO-001 son visibles
      en la app corriendo
- [ ] WCAG AA color contrast verificado vía axe DevTools
      (puede automatizarse en `frontend-test-coverage`)
- [ ] Navegación por teclado funciona (Tab order de REQ-A11Y-001)
- [ ] Los 3 breakpoints (375/768/1280) renderizan correctamente
- [ ] `frontend/README.md` existe, no está vacío, y es accurate
- [ ] `frontend/.env.example` documenta `BACKEND_URL`
- [ ] El chat renderiza chunks progresivamente (typewriter
      effect visible)
- [ ] El chat maneja `event: error` gracefully (Alert + código
      preservado)
- [ ] Search panel muestra empty / loading / error / success
      states correctamente
- [ ] **Backwards compat**: el frontend NO consume
      `POST /jobs/chat` (v1) — solo el streaming endpoint
- [ ] Los 5 contratos v1 del backend son respetados:
      `GET /jobs`, `GET /jobs/linkedin`, `GET /jobs/indeed`,
      `GET /jobs/infojobs`, `GET /health` (el frontend
      consume solo `/jobs` y `/jobs/chat/stream`)
- [ ] **NO se confía en CORS** — todas las llamadas al
      backend pasan por Route Handlers server-side
- [ ] La política de testing de REQ-TEST-001 está documentada
      en el README
- [ ] El contract SSE consumido (4 event types: `meta`,
      `text`, `done`, `error`) coincide verbatim con el spec
      archivado `openspec/specs/chat-streaming/spec.md`
