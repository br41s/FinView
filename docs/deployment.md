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
| `FINVIEW_REQUEST_SCOPED_RUNTIME` | Impide trabajo fuera de una petición HTTP | **Debe ser `true` en Cloud Run.** Desactiva workers y schedulers en proceso; los endpoints manuales terminan su trabajo antes de responder. |
| `FINVIEW_RATE_LIMIT_LOGIN` | Límite de intentos de login por IP | Opcional. Default: `5/minute`. |
| `FINVIEW_RATE_LIMIT_REGISTER` | Límite de intentos de registro por IP | Opcional. Default: `3/minute`. |
| `FINVIEW_TURNSTILE_SECRET` | Secret key de Cloudflare Turnstile (protección anti-bot en login) | Opcional. **Si está vacío, la verificación se omite** (dev/sin configurar). Empareja con `NEXT_PUBLIC_TURNSTILE_SITE_KEY` del frontend. Obtén el par de claves en Cloudflare → Turnstile. |

| `FINVIEW_CRON_SECRET` | Secreto compartido con Cloud Scheduler | **Obligatorio para que los pipelines corran en prod** (ver "Cloud Scheduler"). Si está vacío, los tres endpoints `/cron` devuelven 403 y nada se ejecuta. |
| `FINVIEW_OPENROUTER_API_KEY` | Clave de OpenRouter (análisis IA de opciones, analyst de geo, scorer de zonas) | Opcional. Sin ella, el ciclo corre igual pero sin análisis IA y las señales técnicas se guardan **sin puntuar** (`break_probability = NULL`). |
| `FINVIEW_OPENROUTER_MODEL` | Modelo compartido | Default `deepseek/deepseek-v4-flash`. |
| `FINVIEW_FRED_API_KEY` | Clave FRED (tipo libre de riesgo + régimen macro) | Opcional y gratuita. Sin ella los Greeks usan constantes por divisa y el régimen macro se omite. |

Otras opcionales (Stripe, notificaciones ntfy/Telegram/email, claves de fuentes geo) declaradas en [backend/config.py](../backend/config.py). `gcloud run deploy` preserva las env vars existentes si no se pasa `--set-env-vars` ni `--clear-env-vars`.

---

## Cloud Scheduler — los pipelines NO corren sin esto

> **Estado operativo 2026-08-05:** los tres jobs están `ENABLED` y fallando: el
> servicio está en escalado **manual con 0 instancias**, así que cada llamada muere.
> El estado `PAUSED` que documentaba esta sección el 2026-08-01 ya no es cierto —
> alguien los reanudó el 3 de agosto. Antes de devolver instancias al servicio hay que
> fijarles `--attempt-deadline` y desactivar reintentos (ver abajo), o el incidente de
> coste se reproduce solo.

> **Deadline obligatorio.** Los endpoints `/cron` corren **síncronos**, y el deadline
> por defecto de un job HTTP de Cloud Scheduler es **180 s**. Un ciclo de opciones
> puede tardar minutos: al vencer el deadline Scheduler **reintenta** mientras la
> petición original sigue viva y facturando, y se apilan ciclos duplicados. Cada job
> necesita `--attempt-deadline=1800s` (el máximo HTTP, y el mismo `--timeout` que usa
> Cloud Run) y `--max-retry-attempts=0`.

```bash
for J in geo-intel-cycle options-agent-cycle zonas-clave-cycle; do
  gcloud scheduler jobs update http $J --location=europe-west1 \
    --attempt-deadline=1800s --max-retry-attempts=0
done
```

**La lección más cara del proyecto.** Los tres pipelines (geo, options, zonas-clave) tienen
un `APScheduler` en proceso con botones de start/stop en la UI. **Eso es una comodidad de
desarrollo, no el mecanismo de producción**: con `--min-instances=0` la instancia muere al
quedarse ociosa y se lleva el scheduler por delante. El síntoma es una sección que lee
vacía sin ningún error en ninguna parte — el Options Monitor estuvo así hasta el PR #148.

**La periodicidad de producción son jobs de Cloud Scheduler** golpeando endpoints HTTP,
autenticados con la cabecera `X-Cron-Key` contra `FINVIEW_CRON_SECRET` (comparación en
tiempo constante; secreto vacío = endpoint deshabilitado). Corren **síncronos** para que
Cloud Run mantenga la CPU hasta terminar — no convertirlos en hilos fire-and-forget, la
instancia puede reclamarse tras la respuesta.

| Job | Endpoint | Horario | Por qué ese horario |
|---|---|---|---|
| `geo-intel-cycle` | `/api/geo/cron` | `*/30 * * * *` | Los eventos geopolíticos no cierran de noche. A 10 minutos el ciclo consumía ~259k vCPU-s/mes y se salía de la capa gratuita (240k); a 30 cabe con margen incluso con opciones y zonas encima |
| `options-agent-cycle` | `/api/options/agent/cron` | `*/15 7-22 * * 1-5` | Solo horario de mercado (EU+US). MEFF rate-limita el scraping; de madrugada no hay nada que leer |
| `zonas-clave-cycle` | `/api/zonas-clave/cron` | `15 22 * * 1-5` | Diario tras el cierre de NY; también refresca una vez ECB/FRED/CNMV para mantener esas descargas fuera de los ciclos de 10/15 min |

Listar y comprobar el último intento (`status.code` vacío = OK):

```bash
gcloud scheduler jobs list --location=europe-west1
gcloud scheduler jobs describe <job> --location=europe-west1 --format='value(status.code,lastAttemptTime)'
```

Ver las respuestas HTTP reales (**imprime solo el código, nunca la cabecera**):

```bash
gcloud logging read 'resource.labels.service_name="finview-api" AND httpRequest.requestUrl:"agent/cron"' \
  --limit=5 --format='value(timestamp,httpRequest.status)'
```

### Rotar `FINVIEW_CRON_SECRET`

**Cloud Run primero, luego los tres jobs.** Al revés, los jobs dan 403 hasta que el
servicio recargue. Y si te dejas uno, **falla en silencio**: el job sigue en ENABLED y
solo lo delata un 403 en los logs.

```bash
NEW=$(openssl rand -hex 24)
gcloud run services update finview-api --region=europe-west1 --update-env-vars="FINVIEW_CRON_SECRET=${NEW}"
for J in geo-intel-cycle options-agent-cycle zonas-clave-cycle; do
  gcloud scheduler jobs update http $J --location=europe-west1 --update-headers="X-Cron-Key=${NEW}"
done
```

> ⚠️ `gcloud scheduler jobs describe` **imprime el secreto en claro**. Usa siempre
> `--format` acotado a los campos que necesitas; no pegues la salida completa en ningún
> sitio. (Ya pasó una vez: hubo que rotar.)

**Si añades un cuarto pipeline programado, necesita su propio job.** El APScheduler solo
nunca es suficiente.

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
- **Disparadores:** push a `main` que toque `backend/**`, `scripts/**`, `Dockerfile`, `pyproject.toml` o `cloudbuild.yaml`.
- **Build + despliegue seguro:** [cloudbuild.yaml](../cloudbuild.yaml) construye la imagen, demuestra localmente que escucha en `PORT=8080`, crea una revisión candidata privada con **0% de tráfico**, valida configuración y startup, cancela rollouts anteriores del mismo trigger, pausa los tres jobs antes de cambiar tráfico, promueve al 100% y comprueba `/api/health/ready` en la URL pública. Solo el build activo más nuevo puede mutar tráfico; un rollback automático exige que su revisión siga siendo simultáneamente la última creada y la que sirve el 100%, y deja los callers pausados.
- **Flags de runtime (críticos):** `--cpu-throttling` (facturación por petición), `--min-instances=0`, `--max-instances=1`, `--memory=1Gi`, `FINVIEW_ENV=production` y `FINVIEW_REQUEST_SCOPED_RUNTIME=true`. Producción falla al arrancar si falta ese modo, si los secretos de auth son inseguros o si la base de datos cae al SQLite efímero por defecto. No sustituir `--cpu-throttling` por `--no-cpu-throttling`: con jobs cada 10 minutos y hasta 15 minutos de retención ociosa, la instancia puede quedar facturando continuamente aunque `min=0`.
- **Trabajo periódico:** Cloud Scheduler llama endpoints síncronos. Cloud Run no inicia AIS, ECB, FRED, CNMV ni preload Eurex como hilos de instancia. Eurex se carga bajo demanda; el job diario de zonas refresca ECB/FRED/CNMV una sola vez y AIS degrada a las fuentes HTTP disponibles.
- **Guard fail-closed:** [scripts/verify_cloud_run_service.py](../scripts/verify_cloud_run_service.py) valida directamente la condición `Ready` de la revisión candidata (una candidata a 0% no actualiza todavía `latestReadyRevisionName`) y rechaza facturación por instancia, **escalado manual** (`run.googleapis.com/scalingMode: manual`, que anula silenciosamente `minScale`/`maxScale`), mínimos distintos de cero, el máximo de revisión ausente o mayor de uno, puerto distinto de 8080 y tráfico prematuro. El máximo **a nivel de servicio** solo se comprueba si existe: `gcloud run deploy --max-instances` escribe la anotación de la plantilla, no la del servicio, y exigirla hacía fallar todos los despliegues reales. El startup ya ejecuta la inicialización SQL; si Neon no responde, la revisión nunca llega a `Ready=True`. La ruta pública de readiness no consulta la DB en cada llamada para evitar amplificación.
- **Service account del trigger:** `github-actions-deployer@finview-brais-2026.iam.gserviceaccount.com` con roles `run.admin`, `iam.serviceAccountUser`, `cloudbuild.builds.editor`, `cloudscheduler.admin`, `storage.admin`, `artifactregistry.writer`, `logging.viewer`, `logging.logWriter`. El permiso de Scheduler es necesario para que el rollout pause callers antes de mutar tráfico. Proyectos nuevos de GCP **no permiten** usar la SA por defecto (`<PROJECT_NUM>@cloudbuild.gserviceaccount.com`) — siempre user-managed.
- **Gotcha `includedFiles`:** el trigger debe incluir también `scripts/**`, porque el guard forma parte del despliegue. En la UI del wizard hay que introducir **cada patrón en su propia línea** (Enter entre patrones). Si los pegas separados por espacios se guardan como una sola cadena y el trigger no matchea nada. Si se rompe, exportar con `gcloud beta builds triggers export finview-api-deploy --region=global`, arreglar el YAML y reimportar.

Monitorizar builds: https://console.cloud.google.com/cloud-build/builds?project=finview-brais-2026

### Controles de coste

- El presupuesto de la cuenta de facturación está activo y cubre todos los proyectos
  GCP, con umbrales al 50%, 90% y 100%. Es la red de seguridad transversal; no crear
  presupuestos duplicados por proyecto sin revisar primero este alcance.
- Cada deploy limita `finview-api` a una instancia a nivel de servicio y revisión.
- Cada cambio de tráfico pausa los tres jobs. Reanudarlos es un paso manual posterior
  al guard remoto y a confirmar que la revisión lista es la que sirve el 100%.
- Si un despliegue no puede verificarse antes de terminar una sesión, pausar primero
  los jobs que lo invocan y dejar la revisión sin tráfico. Nunca abandonar un candidato
  fallido con llamadas periódicas activas.
- **El crédito de prueba tapó el problema durante semanas.** Del 1 al 17 de julio de
  2026 el proyecto consumió €26.08 y facturó €0.00: el Free Trial lo absorbía todo.
  El crédito venció el **18 de julio de 2026** con €224.32 sin usar y el mismo consumo
  pasó a costar €26.04 en catorce días. Un gasto que "aparece de golpe" sin ningún
  cambio de infraestructura suele ser esto. Revisar la página de Créditos antes de
  buscar una regresión.
- **La facturación por instancia casi no tiene capa gratuita.** En julio, 1.34M
  vCPU-s por instancia recibieron €0.39 de descuento sobre €21.18. En agosto, ya con
  facturación por petición, €1.39 de uso bruto quedaron en €0.01 netos. No es solo
  "gastar menos": es el nivel de precio en el que esta carga es gratis.
- **Artifact Registry acumula una imagen por commit.** Hay 123 revisiones y ninguna
  política de limpieza; el almacenamiento se factura aunque el servicio esté parado.
  Mantener una política que conserve las últimas 10 versiones.
- **El trigger compila en `global`.** Empujar la imagen a un registro europeo desde
  ahí sale a internet: €2.13 de "Network Data Transfer Out ... within North America"
  en dos semanas. Mover el trigger a `europe-west1` lo elimina.
- El enforcement de presupuesto de FinView solo cubre **Cloud Run** y mide coste
  **bruto**, antes de la capa gratuita. Cloud Build, Artifact Registry y Cloud Storage
  quedan fuera del límite.
- Auditoría rápida sin imprimir configuración sensible:

```bash
gcloud scheduler jobs list --location=europe-west1 --format='table(name.basename(),state,schedule)'
gcloud run services describe finview-api --region=europe-west1 \
  --format='table(status.conditions[0].status,status.latestCreatedRevisionName,status.latestReadyRevisionName)'
python3 scripts/verify_cloud_run_service.py --project=finview-brais-2026 \
  --region=europe-west1 --service=finview-api --revision=<revision> --phase=live
```

No usar `gcloud run services describe` sin `--format`: las variables de entorno de
Cloud Run pueden contener secretos y acabar copiadas a logs o chats.

### GitHub Actions — no se usa
Workload Identity Federation quedó pre-configurada por si algún día se rehabilita GitHub Actions en la cuenta (está deshabilitada por GitHub). SA `github-actions-deployer@finview-brais-2026` y pool `github` siguen vivos pero sin workflow activo.

**No añadir workflows.** Un `.github/workflows/*.yml` nunca se ejecuta en esta cuenta:
parece una barrera de calidad sin serlo. Se intentó una vez (PR #210) y hubo que
retirarlo. Las dos barreras reales son `.githooks/pre-push` (ruff + pytest en cambios
de backend; typecheck + vitest + build en frontend) y el preview de Vercel. Si un
check importa, va en el hook.

## Deploy manual (solo recuperación)

No desplegar `--source` directamente sobre tráfico productivo. Si el trigger cae,
reproducir su secuencia `candidate` → guard → promoción. El rollback sí es una
operación aislada y segura:

```bash
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
| Opciones europeas (.DE/.PA/.AS…) tardan tras idle | Con facturación por petición, Eurex se carga bajo demanda en el primer acceso | Esperar esa primera carga; no activar CPU permanente para ocultar la latencia |
| Build rojo en Cloud Build | SA sin permisos o Dockerfile roto | Logs: https://console.cloud.google.com/cloud-build/builds |
| Cloud Run dice que no escuchó en `PORT=8080` | Mensaje genérico: el proceso pudo fallar antes de abrir el puerto (por ejemplo, Neon sin cuota) | Leer el traceback de la revisión. La inicialización SQL ocurre antes de que el proceso quede listo |
| `/api/health` da 200 pero `/api/health/ready` da 503 | Producción arrancó sin `FINVIEW_REQUEST_SCOPED_RUNTIME=true` | Corregir el flag; el pipeline no debe promover esa revisión |
| `min=0` pero hay una instancia facturable constante | Facturación por instancia más peticiones más frecuentes que la ventana de retención ociosa | Pausar jobs, fijar `--cpu-throttling`, verificar `max=1` y reanudar solo tras el guard |
| **Una sección lee vacía sin ningún error** (Monitor de opciones, Técnico, Ideas) | El job de Cloud Scheduler no existe, está paused, o su secreto no coincide con Cloud Run → el pipeline no corre. El APScheduler de la UI no cuenta: muere con `--min-instances=0` | `gcloud scheduler jobs list --location=europe-west1` y comparar con los endpoints `/cron` que existen en el código. Ver "Cloud Scheduler" |
| Cron devuelve **403** | `FINVIEW_CRON_SECRET` de Cloud Run ≠ cabecera `X-Cron-Key` del job (típico: se rotó uno y no los otros) | Rotar de nuevo siguiendo el orden Cloud Run → los tres jobs |
| Cron devuelve **404** | El endpoint aún no está desplegado (PR mergeado pero Cloud Build sin terminar) | Esperar al build; comprobar `gcloud builds list --limit=1` |
| Señales técnicas todas "sin puntuar" | El scorer LLM falla: sin `FINVIEW_OPENROUTER_API_KEY`, o el modelo devolvió 200 con cuerpo vacío | `gcloud logging read '... textPayload:"zone scoring failed"'`. El log incluye `finish_reason` y `usage`. **`break_probability = NULL` es correcto en ese caso** — nunca se coerciona a 0, que leería como "seguro que no rompe" |
| El ciclo de zonas corre pero emite 0 señales | Normal si ningún precio está a <2% de una zona. Ojo: `_already_open()` bloquea duplicados del mismo ticker+nivel durante 20h, así que relanzarlo a mano el mismo día no emite nada | Comprobar la línea `N signals (M alerting)` en los logs |

## Historial de migraciones

- **Render** (`render.yaml` borrado) — stack inicial, abandonado por límites del plan Free.
- **Azure Container Apps** (`azure.yaml`, `.azure/`, `infra/*.bicep` borrados) — experimento, nunca llegó a prod.
- **Vercel + Cloud Run + Neon** (actual, desde abril 2026) — stack definitivo.
