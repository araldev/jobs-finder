# jobs-finder

> Monorepo for a job search aggregator with a FastAPI backend and Next.js frontend.

## Prerrequisitos

- **Python 3.12** + [`uv`](https://github.com/astral-sh/uv) (gestor de paquetes Python)
- **Node.js 20+** + **npm** (gestor de paquetes Node)
- **Git**

---

## Estructura del proyecto

```
jobs-finder/
├── backend/              # Python 3.12 · FastAPI · Playwright · SQLite
│   ├── src/jobs_finder/ # código fuente (layout src/)
│   ├── tests/           # tests unitarios e integración
│   └── jobs.db          # base de datos SQLite (generada al iniciar)
├── frontend/            # Next.js 15 · React 19 · TypeScript · Tailwind
│   ├── src/            # código fuente de Next.js
│   └── ...             # configuración estándar de Next.js
└── README.md            # este archivo
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
# Editar .env y completar los valores necesarios (ver sección Variables de entorno)

# Arrancar el servidor
uv run uvicorn jobs_finder.main:app --host 0.0.0.0 --port 8000
```

El backend estará disponible en `http://localhost:8000`.

Para verificar que está corriendo:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

Documentación de la API (Swagger): `http://localhost:8000/docs`

---

### 2. Frontend

```bash
cd frontend

# Instalar dependencias
npm install

# Variables de entorno (copiar desde el ejemplo)
cp .env.example .env.local
# Editar .env.local con BACKEND_URL=http://localhost:8000

# Arrancar el servidor de desarrollo
npm run dev
```

El frontend estará disponible en `http://localhost:3000`.

---

## Variables de entorno

### Backend (`backend/.env`)

| Variable | Descripción | Requerido |
|---|---|---|
| `LLM_API_KEY` | API key de MiniMax para el chat con IA | Sí (para chat) |
| `LLM_FILTER_ENABLED` | Habilitar el endpoint de chat | No (default: false) |
| `SCHEDULER_ENABLED` | Habilitar el scheduler de background (scraping automático) | No (default: false) |
| `SCHEDULER_QUERIES` | Queries de búsqueda para el scheduler (JSON array) | No (tiene defaults) |
| `LINKEDIN_LI_AT` | Cookie de sesión de LinkedIn (formato `AQED...`) | No (mejora resultados) |
| `CACHE_TTL_SECONDS` | TTL de la cache en segundos | No (default: 60) |

**Nota:** El scheduler y scraping live requieren cookies de LinkedIn y son propensos a bloqueos anti-bot. Para uso básico, dejar `SCHEDULER_ENABLED=false` y usar el chat para buscar en los jobs cacheados.

### Frontend (`frontend/.env.local`)

| Variable | Descripción | Default |
|---|---|---|
| `BACKEND_URL` | URL del backend | `http://localhost:8000` |

---

## Funcionalidades principales

### Chat con IA

El chat permite buscar trabajos con lenguaje natural (ej: "cocinero en Madrid"). Internamente usa la base de datos SQLite del scheduler para buscar trabajos cacheados.

Para habilitarlo:
1. Obtener API key de MiniMax
2. Configurar `LLM_API_KEY` en `backend/.env`
3. Configurar `LLM_FILTER_ENABLED=true`
4. Reiniciar el backend

### Scheduler (background scraping)

El scheduler puede ejecutar búsquedas automáticamente cada 25-35 minutos y guardar los resultados en SQLite. Esto mantiene la base de datos actualizada sin necesidad de hacer scraping live cuando el usuario usa el chat.

Para habilitarlo:
1. Configurar `SCHEDULER_ENABLED=true` en `backend/.env`
2. Opcional: configurar `SCHEDULER_QUERIES` con las ubicaciones deseadas

**Nota:** El scheduler requiere cookies válidas de LinkedIn para obtener resultados. Sin cookies, los scrapers serán bloqueados por anti-bot.

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

# Type checking
uv run mypy

# Verificación completa (CI local)
bash scripts/check.sh
```

### Frontend

```bash
cd frontend

# Desarrollo
npm run dev

# Production build
npm run build

# Type checking
npm run typecheck

# Linting
npm run lint

# Tests
npm run test
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

El scheduler intenta hacer scraping live de LinkedIn/Indeed/InfoJobs. Sin cookies válidas, los scrapers son bloqueados y el scheduler crashea. **Solución:** dejar `SCHEDULER_ENABLED=false` y usar el chat (que lee de la DB cacheada).

### Error `aiosqlite` o `playwright` not found

```bash
cd backend
uv sync
```

### Error de TypeScript en frontend

```bash
cd frontend
npm install
```

### El chat no responde

1. Verificar que `LLM_API_KEY` está configurado en `backend/.env`
2. Verificar que `LLM_FILTER_ENABLED=true` en `backend/.env`
3. Reiniciar el backend
4. Verificar que hay jobs en la DB: `curl http://localhost:8000/jobs/history?limit=5`
