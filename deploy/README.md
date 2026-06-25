# jobs-finder — Production Deployment

## Architecture

```
Browser ──🌐──► Vercel (frontend, Next.js)
                  │
                  │  Route Handler (server-side)
                  │  BACKEND_URL=https://api.tudominio.com
                  ▼
          VPS ──► Caddy (port 443, TLS automático)
                    │
                    ▼
                 Backend API (port 8000, interno)
                    │
                    ▼
              Supabase (PostgreSQL + Auth)
```

- **Frontend**: Vercel (deploy automático desde GitHub)
- **Backend**: Docker Compose en tu VPS (backend + Caddy)
- **Base de datos**: Supabase (externa)

## Requisitos

- Una VPS con Docker y Docker Compose instalados
- Un dominio apuntando a la IP de tu VPS (ej: `api.tudominio.com`)
- Una cuenta en Vercel conectada a tu GitHub
- Una cuenta en Supabase (ya la tenés)

## Deploy del backend

### 1. Preparar el VPS

```bash
# Instalar Docker (si no está instalado)
curl -fsSL https://get.docker.com | sh

# Clonar el repo
git clone https://github.com/araldev/jobs-finder.git
cd jobs-finder/deploy

# Copiar y configurar variables de entorno
cp .env.production.example .env.production
nano .env.production  # Llenar con tus valores reales
```

### 2. Configurar el dominio

Editar `Caddyfile` y reemplazar `API_DOMAIN` con tu dominio real:

```
api.tudominio.com {
    reverse_proxy backend:8000
    ...
}
```

Si querés probar sin dominio primero (solo HTTP):

```caddyfile
:80 {
    reverse_proxy backend:8000
}
```

### 3. Iniciar

```bash
docker compose up -d --build
```

Caddy automáticamente:
- Pide un certificado TLS a Let's Encrypt para tu dominio
- Lo renueva antes de que expire
- Redirige HTTP → HTTPS

### 4. Verificar

```bash
curl https://api.tudominio.com/health
# → {"status":"ok"}
```

## Deploy del frontend (Vercel)

### 1. Conectar el repo

1. Ir a [vercel.com/new](https://vercel.com/new)
2. Importar `araldev/jobs-finder`
3. Configurar:

| Variable | Valor |
|----------|-------|
| `ROOT_DIRECTORY` | `frontend` |
| `FRAMEWORK_PRESET` | Next.js |
| `Build Command` | `pnpm run build` |
| `Output Directory` | `.next` |

### 2. Variables de entorno en Vercel

| Variable | Valor |
|----------|-------|
| `BACKEND_URL` | `https://api.tudominio.com` |
| `BACKEND_API_KEY` | La misma que pusiste en `API_KEYS` del backend |

### 3. Deploy

Vercel hace deploy automático con cada push a `main`.

## Mantenimiento

### Ver logs del backend

```bash
cd jobs-finder/deploy
docker compose logs -f backend
```

### Actualizar backend

```bash
cd jobs-finder/deploy
git pull
docker compose up -d --build backend
```

### Renovar cookies de LinkedIn

Si el auto-refresh falla (2FA, credenciales rotas):

```bash
# En el VPS:
docker compose exec backend uv run --env-file .env.production \
    python scripts/extract_linkedin_cookies.py \
    --output linkedin_cookies.json
```

### Backup de Caddy data (certificados TLS)

Los certificados están en el volumen `caddy_data`. Hacer backup:

```bash
docker run --rm -v caddy_data:/data -v $(pwd):/backup alpine \
    tar czf /backup/caddy_backup_$(date +%Y%m%d).tar.gz -C /data .
```
