# Despliegue FinView

Referencia única para entender cómo vive FinView en producción. Si cambia algo aquí, actualiza este archivo.

## Topología

```
Browser  ──►  Vercel (frontend Next.js, fin-view-topaz.vercel.app)
                  │
                  │  Vercel rewrites /api/* (configurado en next.config.ts)
                  ▼
              Cloud Run: finview-api (europe-west1)
              image: europe-west1-docker.pkg.dev/finview-brais-2026/cloud-run-source-deploy/finview-api
                  │
                  ▼
              Neon Postgres (ep-mute-rain-alwkqvfz, eu-central-1)
```

- **Proyecto GCP:** `finview-brais-2026` (número `748911075551`)
- **Región Cloud Run:** `europe-west1` — única, no hay otras regiones activas
- **Región Neon:** `eu-central-1` (AWS Frankfurt)
- **Frontend URL:** https://fin-view-topaz.vercel.app

## Servicios activos

| Pieza | URL / Identificador | Propietario |
|---|---|---|
| Frontend | https://fin-view-topaz.vercel.app | Vercel, conectado a `braisntext/FinView` branch `main` |
| Backend | https://finview-api-748911075551.europe-west1.run.app | Cloud Run, servicio `finview-api` |
| DB | `ep-mute-rain-alwkqvfz.c-3.eu-central-1.aws.neon.tech/neondb` | Neon |
| CI backend | Cloud Build trigger `finview-api-deploy` | GCP, vinculado al repo via Cloud Build GitHub App |

## Variables de entorno

### Cloud Run (`finview-api`)
Configuradas via `gcloud run services update --set-env-vars`:

| Variable | Propósito | Notas |
|---|---|---|
| `FINVIEW_DATABASE_URL` | Cadena de conexión a Neon | Formato `postgresql://user:pass@host/db?sslmode=require&channel_binding=require` |
| `FINVIEW_AUTH_SECRET` | Secreto compartido con NextAuth | **Debe coincidir** con `AUTH_SECRET` del frontend, o login falla con "Invalid token" |
| `FINVIEW_SECRET_KEY` | Firma de JWTs internos | Mismo valor que `AUTH_SECRET` por simplicidad |
| `FINVIEW_FRONTEND_URL` | CORS y redirects de Stripe | `https://fin-view-topaz.vercel.app` |
| `FINVIEW_ENV` | Modo de entorno | **Debe ser `production`** en producción para que el validador de secretos se active en startup. Default: `local` (sin validación). |
| `FINVIEW_RATE_LIMIT_LOGIN` | Límite de intentos de login por IP | Opcional. Default: `5/minute`. |
| `FINVIEW_RATE_LIMIT_REGISTER` | Límite de intentos de registro por IP | Opcional. Default: `3/minute`. |
| `FINVIEW_TURNSTILE_SECRET` | Secret key de Cloudflare Turnstile (protección anti-bot en login) | Opcional. **Si está vacío, la verificación se omite** (dev/sin configurar). Empareja con `NEXT_PUBLIC_TURNSTILE_SITE_KEY` del frontend. Obtén el par de claves en Cloudflare → Turnstile. |

Otras opcionales (Stripe, Anthropic, notificaciones) declaradas en [backend/config.py](../backend/config.py). `gcloud run deploy` preserva las env vars existentes si no se pasa `--set-env-vars` ni `--clear-env-vars`.

### Vercel (frontend)
Configuradas en Vercel → Project Settings → Environment Variables:

| Variable | Propósito | Valor |
|---|---|---|
| `BACKEND_URL` | Destino del rewrite `/api/*` → backend | `https://finview-api-748911075551.europe-west1.run.app` |
| `AUTH_SECRET` | Secreto de NextAuth | Mismo que `FINVIEW_AUTH_SECRET` en Cloud Run |
| `AUTH_TRUST_HOST` | `true` | Necesario para NextAuth en entornos tras proxy |
| `NEXTAUTH_URL` | `https://fin-view-topaz.vercel.app` | URL canónica |
| `NEXT_PUBLIC_TURNSTILE_SITE_KEY` | Site key de Cloudflare Turnstile | Opcional. **Si está vacío, el widget no se renderiza** y el login funciona sin captcha. Empareja con `FINVIEW_TURNSTILE_SECRET` del backend. Es público (se expone al navegador). Build-time: requiere redeploy tras cambiarla. |

**Importante:** `BACKEND_URL` se lee en [frontend/next.config.ts](../frontend/next.config.ts) **en build-time**. Tras cambiarla, **redeploy manual en Vercel** (o nuevo push) es obligatorio.

## CI/CD

### Frontend
- **Cómo:** Vercel auto-detecta push a `main` del repo conectado y construye.
- **Sin config en repo.** Todo vive en Vercel Project Settings.

### Backend
- **Cómo:** Cloud Build trigger `finview-api-deploy` escucha GitHub via Cloud Build GitHub App (1ª gen, región `global`).
- **Disparadores:** push a `main` que toque `backend/**`, `Dockerfile`, `pyproject.toml` o `cloudbuild.yaml`.
- **Build + deploy:** definido en [cloudbuild.yaml](../cloudbuild.yaml). Construye imagen Docker, la sube a Artifact Registry, y llama `gcloud run deploy finview-api --image=... --region=europe-west1`. Preserva env vars existentes.
- **Flags de runtime (críticos):** el deploy fija `--no-cpu-throttling`, `--cpu-boost`, `--min-instances=0` y `--memory=1Gi`. Sin `--no-cpu-throttling` Cloud Run estrangula la CPU fuera de las requests y los hilos de arranque en background (**Eurex RDF ~63s**, ECB FX-sync, catálogo CNMV) nunca terminan → las opciones europeas no cargan. `--memory=1Gi` da margen para parsear el RDF de 27.5 MB (el default 512Mi arriesga OOM). `--min-instances=0` escala a cero en idle (coste ~0), pero cada cold start repaga el preload de Eurex (~63s) → la primera request de opciones europeas tras un idle puede ir lenta. Subir a `--min-instances=1` mantiene una instancia caliente con el chain parseado en memoria (siempre instantáneo) a cambio de ~1 instancia 24/7 (~€45/mes).
- **Service account del trigger:** `github-actions-deployer@finview-brais-2026.iam.gserviceaccount.com` con roles `run.admin`, `iam.serviceAccountUser`, `cloudbuild.builds.editor`, `storage.admin`, `artifactregistry.writer`, `logging.viewer`, `logging.logWriter`. Proyectos nuevos de GCP **no permiten** usar la SA por defecto (`<PROJECT_NUM>@cloudbuild.gserviceaccount.com`) — siempre user-managed.
- **Gotcha `includedFiles`:** en la UI del wizard hay que introducir **cada patrón en su propia línea** (Enter entre patrones). Si los pegas separados por espacios se guardan como una sola cadena y el trigger no matchea nada. Si se rompe, exportar con `gcloud beta builds triggers export finview-api-deploy --region=global`, arreglar el YAML y reimportar.

Monitorizar builds: https://console.cloud.google.com/cloud-build/builds?project=finview-brais-2026

### GitHub Actions — no se usa
Workload Identity Federation quedó pre-configurada por si algún día se rehabilita GitHub Actions en la cuenta (está deshabilitada por GitHub). SA `github-actions-deployer@finview-brais-2026` y pool `github` siguen vivos pero sin workflow activo.

## Deploy manual (fallback)

Desde local, si el trigger cae o para un rollback:

```bash
# Redeploy del código actual local
gcloud run deploy finview-api \
  --source . \
  --region europe-west1 \
  --project finview-brais-2026 \
  --allow-unauthenticated

# Actualizar solo env vars sin rebuild
gcloud run services update finview-api \
  --region europe-west1 \
  --update-env-vars "FINVIEW_FOO=bar"

# Rollback a revisión anterior
gcloud run services update-traffic finview-api \
  --region europe-west1 \
  --to-revisions finview-api-00XXX-abc=100
```

Ver revisiones: `gcloud run revisions list --service finview-api --region europe-west1`.

## Base de datos (Neon)

- Consola: https://console.neon.tech
- Branch de producción: `main`
- Migraciones: sin Alembic — SQLAlchemy crea tablas en `startup` (`Base.metadata.create_all`) en [backend/database.py](../backend/database.py). Cambios destructivos al esquema requieren script manual.
- Backups: Neon hace PITR 7 días en plan Free. Dumps puntuales vía `pg_dump` están en el repo como `finview-YYYYMMDD-HHMMSS.dump` (gitignored).

## Troubleshooting

| Síntoma | Causa probable | Fix |
|---|---|---|
| Frontend muestra 400 "Solo PDF" subiendo CSV | `BACKEND_URL` de Vercel apunta a revisión vieja | Actualizar env var en Vercel → Redeploy |
| "Invalid token" en todos los endpoints | `FINVIEW_AUTH_SECRET` ≠ `AUTH_SECRET` del frontend | Alinear ambos secretos, recargar sesión en navegador |
| "No hay datos" tras desplegar | Cloud Run sin `FINVIEW_DATABASE_URL` → usa SQLite efímero | Setear env var con la URL de Neon, redeploy |
| Opciones europeas (.DE/.PA/.AS…) no cargan | Cloud Run estrangula CPU → preload Eurex en background no termina | Verificar que el deploy lleva `--no-cpu-throttling` (ver [cloudbuild.yaml](../cloudbuild.yaml)). Si tarda solo tras un periodo de idle, es el cold start repagando el preload (~63s) por `--min-instances=0` |
| Build rojo en Cloud Build | SA sin permisos o Dockerfile roto | Logs: https://console.cloud.google.com/cloud-build/builds |
| 500 en `/api/health` | Cold start lento o Neon durmiendo | Esperar 10s; Neon serverless tarda en despertar |

## Historial de migraciones

- **Render** (`render.yaml` borrado) — stack inicial, abandonado por límites del plan Free.
- **Azure Container Apps** (`azure.yaml`, `.azure/`, `infra/*.bicep` borrados) — experimento, nunca llegó a prod.
- **Vercel + Cloud Run + Neon** (actual, desde abril 2026) — stack definitivo.
