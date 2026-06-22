# jobs-finder

> Monorepo for a job search aggregator with a FastAPI backend and Next.js frontend.
> Buscador de empleo multi-fuente con dashboard en tiempo real.

## Prerrequisitos

- **Python 3.12** + [`uv`](https://github.com/astral-sh/uv) (gestor de paquetes Python)
- **Node.js 20+** + **pnpm** (gestor de paquetes Node)
- **Git**

---

## Estructura del proyecto

```
jobs-finder/
├── backend/                # Python 3.12 · FastAPI · Playwright
│   ├── .env.example        # template — copiar a backend/.env
│   ├── .python-version
│   ├── pyproject.toml      # PEP 621 metadata + tool config
│   ├── scripts/
│   │   └── check.sh        # local CI: ruff + mypy + pytest
│   ├── config/
│   │   ├── default.toml    # defaults operacionales versionados
│   │   └── local.toml      # overrides locales (gitignored)
│   ├── supabase/           # migraciones + config de Supabase
│   ├── src/jobs_finder/   # código fuente (layout src/)
│   │   ├── main.py         # composition root + uvicorn entry
│   │   ├── domain/         # Job value object, excepciones base
│   │   ├── application/    # puertos (JobSearchPort, CachePort), use cases
│   │   │   └── usecases/   # un use case por fuente + cached wrapper
│   │   ├── infrastructure/ # scrapers (linkedin, indeed, infojobs), cache, throttles
│   │   │   ├── linkedin/   # LinkedInPlaywrightScraper + parsers
│   │   │   ├── indeed/     # IndeedPlaywrightScraper + parsers
│   │   │   ├── infojobs/   # InfoJobsPlaywrightScraper + parsers
│   │   │   ├── cache/      # InMemoryTTLCache + RedisCache
│   │   │   ├── location/   # resolutor de provincias InfoJobs
│   │   │   ├── pagination.py  # helper paginado compartido
│   │   │   └── config.py   # configuración vía pydantic-settings
│   │   └── presentation/   # FastAPI app, routes, middleware, schemas
│   │       └── routes/     # linkedin, indeed, infojobs, aggregator, stats, health, chat
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── fixtures/       # HTML inline para tests de parsers
│   │   ├── unit/           # parsers, throttles, use cases, scrapers, cache
│   │   └── integration/    # FastAPI app + composition root
│   ├── uv.lock
│   └── README.md           # documentación completa del backend
└── frontend/               # Next.js 15 · React 19 · TypeScript · Tailwind · shadcn/ui
    ├── .env.example         # template — copiar a frontend/.env.local
    ├── .gitignore
    ├── components.json      # shadcn config (style: default, baseColor: slate)
    ├── next.config.ts
    ├── package.json
    ├── tailwind.config.ts
    ├── tsconfig.json
    ├── vitest.config.ts
    ├── vitest.setup.ts
    ├── public/
    └── src/
        ├── app/             # App Router (RSC + Route Handlers)
        │   ├── [locale]/    # rutas localizadas (es/en) con next-intl
        │   │   ├── (app)/   # layout app con Header + Sidebar
        │   │   │   └── dashboard/  # dashboard con RSC streaming
        │   │   ├── (auth)/  # layout auth (login/signup)
        │   │   ├── jobs/    # listado + detalle de trabajos
        │   │   ├── search/  # búsqueda con filtros
        │   │   ├── settings/# configuración de plataformas
        │   │   ├── layout.tsx    # layout localizado con Providers
        │   │   ├── page.tsx     # landing page
        │   │   ├── login/       # login con Supabase
        │   │   └── signup/      # signup
        │   ├── api/         # Route Handlers (proxy al backend)
        │   │   ├── health/
        │   │   ├── jobs/
        │   │   │   ├── [id]/
        │   │   │   └── route.ts
        │   │   └── stats/
        │   ├── globals.css  # Tailwind + CSS vars (light/dark) + fuentes self-hosted
        │   ├── layout.tsx   # Root layout con next/font/google (self-hosted)
        │   └── providers.tsx  # ThemeProvider > QueryClientProvider > Toaster
        ├── components/
        │   ├── ui/          # shadcn primitives (button, card, input, badge, …)
        │   ├── layout/      # AppShell, Sidebar, Header, ThemeToggle, LanguageSwitcher
        │   ├── dashboard/   # StatCard, PlatformDistribution, JobTimeline, RightSidebar
        │   ├── jobs/        # JobCard, JobList, JobDetailContent, SalaryBadge
        │   ├── search/      # SearchBar, FilterPanel
        │   ├── settings/    # PlatformConfigCard, NotificationSettings
        │   └── shared/      # EmptyState, ErrorState, Skeleton
        ├── hooks/           # useStats, useJobs, useJobsInfinite, useJobDetail, useDebounce
        ├── lib/             # api-client (server-only), formatters, types
        ├── i18n/            # next-intl routing + request config
        └── types/           # job.ts, stats.ts
```

---

## Levantar el proyecto

### 1. Backend

```bash
cd backend

# Instalar dependencias
uv sync

# Variables de entorno (copiar desde el ejemplo)
cp .env.example .env
# Editar .env y completar los valores necesarios

# Arrancar el servidor
uv run uvicorn jobs_finder.main:app --host 0.0.0.0 --port 8000
```

El backend estará disponible en `http://localhost:8000`.

Para verificar:
```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

Documentación de la API (Swagger): `http://localhost:8000/docs`

### 2. Frontend — modo desarrollo

```bash
cd frontend

# Instalar dependencias
pnpm install

# Variables de entorno (copiar desde el ejemplo)
cp .env.example .env.local
# Editar .env.local con BACKEND_URL=http://localhost:8000

# Arrancar servidor de desarrollo
pnpm run dev
```

El frontend estará disponible en `http://localhost:3000`.

### 3. Frontend — modo producción (para medir performance real)

```bash
cd frontend

# Build de producción
pnpm run build

# Arrancar servidor de producción
pnpm run start
```

**Importante**: las optimizaciones de `next/font/google` (self-hosting de fuentes),
RSC streaming, y minificación de bundles SOLO se activan en producción.
No uses `pnpm dev` para medir performance con Lighthouse.

---

## Variables de entorno

### Backend (`backend/.env`)

El backend lee ~46 variables de entorno via `pydantic-settings`.
El template completo está en `backend/.env.example`. Las principales:

| Variable | Descripción | Requerido |
|---|---|---|
| `LLM_API_KEY` | API key del proveedor LLM (MiniMax / Groq) | Sí (para chat) |
| `LLM_FILTER_ENABLED` | Habilitar endpoints de chat | No (default: false) |
| `SCHEDULER_ENABLED` | Habilitar scheduler de background | No (default: false) |
| `LINKEDIN_LI_AT` | Cookie de sesión de LinkedIn | No (mejora resultados) |
| `CACHE_TTL_SECONDS` | TTL de caché en segundos | No (default: 60) |
| `CACHE_BACKEND` | `memory` o `redis` | No (default: memory) |
| `RATE_LIMIT_ENABLED` | Rate limiting por IP | No (default: true) |
| `DB_PATH` | Ruta a BD SQLite para scheduler | No |
| `SUPABASE_AUTH_REDIRECT_URL` | URL de callback para auth | No (default: localhost) |

Para defaults operacionales no-sensibles (throttles, timeouts, dominios),
ver `backend/config/default.toml`.

### Frontend (`frontend/.env.local`)

| Variable | Descripción | Default |
|---|---|---|
| `BACKEND_URL` | URL del backend | `http://localhost:8000` |
| `BACKEND_API_KEY` | API key para autenticación backend | — |
| `NEXT_PUBLIC_SUPABASE_URL` | URL del proyecto Supabase | — |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Anon key de Supabase | — |
| `NEXT_PUBLIC_I18N_ENABLED` | Habilitar i18n (next-intl) | `true` |

---

## Endpoints principales

### Backend

| Endpoint | Descripción |
|---|---|
| `GET /health` | Health check |
| `GET /jobs/linkedin?keywords=&location=` | Búsqueda en LinkedIn |
| `GET /jobs/indeed?keywords=&location=` | Búsqueda en Indeed |
| `GET /jobs/infojobs?keywords=&location=` | Búsqueda en InfoJobs |
| `GET /jobs?q=&location=&sources=` | Agregador multi-fuente con dedup |
| `GET /jobs/stats` | Estadísticas consolidadas para dashboard |
| `GET /jobs/history` | Historial paginado desde BD |
| `GET /scheduler/status` | Estado del scheduler |

### Frontend (Route Handlers — proxy al backend)

| Endpoint | Descripción |
|---|---|
| `GET /api/health` | Health check proxy |
| `GET /api/jobs` | Jobs proxy |
| `GET /api/jobs/[id]` | Job detail proxy |
| `GET /api/stats` | Stats proxy |

---

## Comandos útiles

### Backend

```bash
cd backend

# Tests
uv run pytest

# Linting
uv run ruff check
uv run ruff format --check

# Type checking (strict)
uv run mypy

# Verificación completa (CI local)
bash scripts/check.sh
```

### Frontend

```bash
cd frontend

# Desarrollo
pnpm run dev

# Type checking
pnpm run typecheck

# Linting
pnpm run lint

# Tests
pnpm run test

# Production build
pnpm run build

# Servir producción localmente
pnpm run start
```

---

## Legal Notice

> **ATENCIÓN. Leer antes de ejecutar.**
>
> Este proyecto hace scraping de LinkedIn, Indeed e InfoJobs. **Hacer scraping puede violar los Términos de Servicio** de estas plataformas y puede exponer al operador a responsabilidad civil y/o penal según la jurisdicción.
>
> - Asumes **todo** el riesgo legal. Los autores no aceptan ninguna responsabilidad.
> - No es un agregador de empleo para producción. Es un ejercicio educativo.
> - No usar para redistribuir datos, evadir anti-bots, o fines comerciales.
>
> Si no estás seguro de que tu uso es legal, **consulta con un abogado** antes de ejecutar.

---

## Troubleshooting

### El backend se cae al arrancar con `SCHEDULER_ENABLED=true`

El scheduler intenta scraping live. Sin cookies válidas de LinkedIn, los scrapers son bloqueados. **Solución:** dejar `SCHEDULER_ENABLED=false`.

### Error `aiosqlite` o `playwright` not found

```bash
cd backend
uv sync
```

### Error de TypeScript en frontend

```bash
cd frontend
pnpm install
pnpm run typecheck
```

### El chat no responde

1. Verificar `LLM_API_KEY` en `backend/.env`
2. Verificar `LLM_FILTER_ENABLED=true` en `backend/.env`
3. Reiniciar el backend

### Lighthouse da resultados pesimos en local

Estás corriendo en `pnpm dev`. Las optimizaciones de `next/font/google` (self-hosting),
RSC streaming, y minificación SOLO funcionan en producción. Usá:

```bash
pnpm run build && pnpm run start
```

Luego corre Lighthouse contra `http://localhost:3000`.
