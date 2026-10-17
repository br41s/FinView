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

| `FINVIEW_CRON_SECRET` | Secreto compartido con Cloud Scheduler | **Obligatorio para que los pipelines corran en prod** (ver "Cloud Scheduler"). Si está vacío, todos los endpoints `/cron` devuelven 403 y nada se ejecuta. |
| `FINVIEW_CREDENTIALS_KEY` | Clave Fernet que cifra los tokens de bróker (conexión directa con IBKR) | Opcional. **Vacía, la conexión con IBKR queda cerrada** (503 y la tarjeta no se muestra); nunca se guarda un token sin cifrar. Generar con `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`, guardarla en Secret Manager y montarla con `gcloud run services update finview-api --region=europe-west1 --update-secrets=FINVIEW_CREDENTIALS_KEY=<secreto>:latest`. Cambiarla deja ilegibles los tokens guardados: cada usuario tendría que reconectar. |
| `FINVIEW_IBKR_FLEX_URL` | Base del Flex Web Service de IBKR | Opcional. Default `https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService`. |
| `FINVIEW_OPENROUTER_API_KEY` | Clave de OpenRouter (análisis IA de opciones, analyst de geo, scorer de zonas) | Opcional. Sin ella, el ciclo corre igual pero sin análisis IA y las señales técnicas se guardan **sin puntuar** (`break_probability = NULL`). |
| `FINVIEW_OPENROUTER_MODEL` | Modelo compartido | **En producción: `deepseek/deepseek-v4.1-flash` desde el 2026-10-10**, fijado en la variable de Cloud Run; el default del código sigue siendo `deepseek/deepseek-v4-flash` y la variable lo sobrescribe. Las dos llamadas de Ideas, las tres de opciones (informe del ciclo, informe por ticker, chat) las dos de la exposición por sector y región (lectura de la nota de segmentos, clasificación) y las dos de la exposición a la IA (citas del informe anual, industria de cada segmento) piden `reasoning: {"effort": "none"}`: antes de cambiar el modelo, mira su objeto `reasoning` en `GET https://openrouter.ai/api/v1/models` — uno con `mandatory: true` rechaza esa petición y tanto Ideas como opciones se quedan sin análisis IA (los ciclos siguen; el chat responde 502). El scorer de zonas no la envía. |
| `FINVIEW_FRED_API_KEY` | Clave FRED (tipo libre de riesgo + régimen macro) | Opcional y gratuita. Sin ella los Greeks usan constantes por divisa y el régimen macro se omite. |
| `FINVIEW_SEC_USER_AGENT` | Contacto para SEC EDGAR | Opcional; el default es el contacto publicado del operador. SEC responde 403 sin un contacto en el User-Agent. |

Otras opcionales (Stripe, notificaciones ntfy/Telegram/email, claves de fuentes geo) declaradas en [backend/config.py](../backend/config.py). `gcloud run deploy` preserva las env vars existentes si no se pasa `--set-env-vars` ni `--clear-env-vars`.

> **Las claves de ingesta van solo aquí, nunca en Vercel.** El frontend no habla con
> ninguna fuente: el navegador llama a `/api`, eso va a `BACKEND_URL` y el ciclo geo corre
> en Cloud Run. Vercel solo necesita `BACKEND_URL`, `AUTH_SECRET`, `NEXT_PUBLIC_SITE_URL`,
> los dos `NEXT_PUBLIC_STRIPE_PRICE_*` y `NEXT_PUBLIC_TURNSTILE_SITE_KEY` (la clave
> *pública* de Turnstile; el secreto es de backend).
>
> Tras un `gcloud run services update --update-env-vars`, **comprueba qué revisión sirve**:
> el rollout fija el tráfico con `--to-revisions`, así que la revisión nueva puede quedarse
> a 0 % y las claves no llegan a producción. `--to-latest` lo resuelve.

> **Rotar `FINVIEW_OPENROUTER_API_KEY` (hecho el 2026-10-09: clave `finview` de la cuenta de OpenRouter de Biglobster LLC).**
> El servicio tiene el tráfico fijado a una revisión con nombre, así que el orden seguro es:
> 1. `gcloud run services update finview-api … --update-env-vars="FINVIEW_OPENROUTER_API_KEY=$K" --no-traffic`
>    (la clave se lee con `read -rs`, nunca como texto en el comando; `gcloud` guarda los argumentos
>    en `~/.config/gcloud/logs`, así que ese fichero conserva la clave).
> 2. Comparar la revisión nueva con la que sirve (`gcloud run revisions describe … --format=json`):
>    solo debe diferir esa variable, y debe estar `Ready`.
> 3. `gcloud run services update-traffic finview-api --to-latest`; marcha atrás con
>    `--to-revisions=<revisión anterior>=100`.
> 4. Esperar al siguiente ciclo (`geo-intel-cycle` corre en el minuto :00): `/api/geo/cron` debe
>    devolver 200 y no debe aparecer `User not found`. Los jobs del Scheduler no se pausan (no es un build).
>
> Cambiar el modelo (`FINVIEW_OPENROUTER_MODEL`) se hace en otra revisión: el scorer de zonas está
> calibrado con resultados y un modelo distinto mueve sus puntuaciones.
>
> **Cambio a `deepseek/deepseek-v4.1-flash` (2026-10-10).** Mismo procedimiento (revisión `--no-traffic`,
> comparar, `update-traffic --to-latest`). Antes de moverlo se comprobó, con una petición real, que acepta
> `reasoning: {effort: "none"}` junto con `provider.data_collection: deny` (su objeto `reasoning` en
> `GET /api/v1/models` dice `mandatory: false`). Primeros ciclos tras el cambio: `/api/geo/cron` 200 en 58 s y
> `/api/geo/audit` 200 en 17 s, sin avisos del LLM. **Pendiente de observar:** la primera ejecución del scorer
> de Zonas Clave con el modelo nuevo (22:15 UTC, lunes a viernes): sus puntuaciones pueden desplazarse y el
> umbral que aprende de resultados mezclará los medidos con el modelo anterior y con este. Marcha atrás:
> `gcloud run services update-traffic finview-api --to-revisions=<revisión anterior>=100` (la anterior fue
> `finview-api-025014b`).

| Clave de fuente | Qué desbloquea | Sin ella |
|---|---|---|
| `FINVIEW_FIRMS_MAP_KEY` | 5 reglas de incendio | `fire` no se emite nunca |
| `FINVIEW_OPENSKY_CLIENT_ID` + `_SECRET` | 8 reglas de espacio aéreo y presencia militar | Anónimo: limitado hasta leerse como «sin vuelos» |
| `FINVIEW_WINDY_API_KEY` | 11 reglas de clima extremo | Ninguna se evalúa. ~480 llamadas/día de un presupuesto de ~500 |

---

## Cloud Scheduler — los pipelines NO corren sin esto

> **Estado operativo 2026-08-05:** los tres jobs están `ENABLED` y fallando: el
> servicio está en escalado **manual con 0 instancias**, así que cada llamada muere.
> El estado `PAUSED` que documentaba esta sección el 2026-08-01 ya no es cierto —
> alguien los reanudó el 3 de agosto. Antes de devolver instancias al servicio hay que
> fijarles `--attempt-deadline` y desactivar reintentos (ver abajo), o el incidente de
> coste se reproduce solo.

> **El rollout los pausa y ahora los reanuda él mismo (2026-09-04).** El paso de
> tráfico de `cloudbuild.yaml` pausa los tres jobs antes de mover tráfico, y **nada
> los reanudaba**: cada despliegue dejaba producción sin periodicidad con el build
> en verde. El síntoma no es un error, es una sección que deja de actualizarse.
> Ahora la reanudación es un `trap ... EXIT`, así que cubre también el camino de
> rollback y el de build superseded, y el build **falla** si algún job no vuelve a
> `ENABLED`. Única excepción: una promoción fallida cuya restauración no devuelve el
> servicio a una revisión que sirve deja los jobs pausados a propósito (ver CI/CD →
> "Promoción fallida"). Tras cualquier despliegue, comprobar:
>
> ```bash
> gcloud scheduler jobs list --location=europe-west1 \
>   --format='table(name.basename(),state,schedule,lastAttemptTime)'
> ```
>
> Si alguno quedó `PAUSED` de un despliegue anterior a este cambio:
> `gcloud scheduler jobs resume <job> --location=europe-west1`.

> **Deadline obligatorio.** Los endpoints `/cron` corren **síncronos**, y el deadline
> por defecto de un job HTTP de Cloud Scheduler es **180 s**. Un ciclo de opciones
> puede tardar minutos: al vencer el deadline Scheduler **reintenta** mientras la
> petición original sigue viva y facturando, y se apilan ciclos duplicados. Cada job
> necesita `--attempt-deadline=1800s` (el máximo HTTP, y el mismo `--timeout` que usa
> Cloud Run) y `--max-retry-attempts=0`.

```bash
for J in geo-intel-cycle geo-intel-audit options-agent-cycle zonas-clave-cycle ibkr-sync-daily; do
  gcloud scheduler jobs update http $J --location=europe-west1 \
    --attempt-deadline=1800s --max-retry-attempts=0
done
```

> **`geo-intel-audit` (2026-09-25).** El aprendizaje geo (checkpoints, re-puntuación en
> vivo de cada señal activa y `confidence_mod` derivado de la precisión) corre cada 4 h en
> su propio job contra `POST /api/geo/audit`, separado del ciclo de ingesta horario.
> Se creó con las mismas cabeceras y deadline que `geo-intel-cycle`:
>
> ```bash
> gcloud scheduler jobs create http geo-intel-audit --location=europe-west1 \
>   --schedule='0 */4 * * *' --time-zone=Etc/UTC --http-method=POST \
>   --uri="$SERVICE_URL/api/geo/audit" --headers="X-Cron-Key=$FINVIEW_CRON_SECRET" \
>   --attempt-deadline=1800s --max-retry-attempts=0
> ```
>
> Está en la lista `SCHEDULER_JOBS` de `cloudbuild.yaml`: el rollout lo pausa y lo reanuda,
> y el build falla si no vuelve a `ENABLED`.

> **`ibkr-sync-daily` (2026-10-15).** Sincroniza cada día todas las conexiones directas con
> IBKR contra `POST /api/brokers/cron` (`broker_sync.sync_all`): el año en curso, más el
> anterior hasta el 31 de marzo, y continúa cualquier carga de historial a medias. Presupuesto
> de **300 s** para todas las conexiones juntas (`CRON_BUDGET_SECONDS`); lo que no termina
> se reanuda al día siguiente desde la fila. Omite las conexiones con el token caducado o la
> Flex Query mal configurada (solo el usuario puede arreglarlo) y nunca pasa de 10 peticiones
> por minuto y token. Responde **500** solo si el paso de algún usuario lanzó una excepción;
> un error de IBKR de un usuario es su estado y se ve en su tarjeta.
>
> **Créalo pausado antes de desplegar el código.** Está en `SCHEDULER_JOBS`, y el bucle de
> pausa del rollout corre con `bash -e`: si el job no existe, `describe` falla y el
> despliegue se aborta (antes de mover tráfico, pero abortado). Creado y pausado, el rollout
> lo reanuda en cuanto la revisión que tiene el endpoint sirve el 100 %:
>
> ```bash
> gcloud scheduler jobs create http ibkr-sync-daily --location=europe-west1 \
>   --schedule='20 6 * * *' --time-zone=Etc/UTC --http-method=POST \
>   --uri="$SERVICE_URL/api/brokers/cron" --headers="X-Cron-Key=$FINVIEW_CRON_SECRET" \
>   --attempt-deadline=1800s --max-retry-attempts=0
> gcloud scheduler jobs pause ibkr-sync-daily --location=europe-west1
> ```

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
| `geo-intel-cycle` | `/api/geo/cron` | `0 * * * *` | Los eventos geopolíticos no cierran de noche. Horario desde el 2026-10-01 (antes `*/30`, y antes `*/10`). GDELT lee las 2 últimas horas, así que un ciclo perdido no pierde noticias |
| `options-agent-cycle` | `/api/options/agent/cron` | `5,35 7-22 * * 1-5` | Solo horario de mercado (EU+US). MEFF rate-limita el scraping; de madrugada no hay nada que leer. Cada 30 min desde el 2026-10-01 (antes `*/15`). En el minuto 5, no en el 0, desde el 2026-10-14: con una sola instancia, el tick de las :00 coincidía con el ciclo geo y Cloud Run lo rechazaba con 429 "no available instance" (3 veces en un mes); es además el único job con reintentos (2, backoff 60–120 s), porque el 500 de los jobs geo es una señal a propósito |
| `geo-intel-audit` | `/api/geo/audit` | `0 */4 * * *` | Checkpoints y aprendizaje de reglas; sus horizontes (+1h…+7d) no necesitan más frecuencia |
| `zonas-clave-cycle` | `/api/zonas-clave/cron` | `15 22 * * 1-5` | Diario tras el cierre de NY; también refresca una vez ECB/FRED/CNMV para mantener esas descargas fuera de los ciclos de geo y opciones |
| `ibkr-sync-daily` | `/api/brokers/cron` | `20 6 * * *` | Los informes Flex terminan ayer (fecha UTC), así que basta una vez al día. A las 06:20 UTC no coincide con geo (minuto 0) ni con opciones (desde las 7). No está comprobado contra el horario de cierre de IBKR: si un día llega incompleto, el del día siguiente lo reemplaza entero |

> **Por qué esa cadencia (2026-10-01).** `finview-api` factura **por petición**
> (`--cpu-throttling`), y la capa gratuita de ese modo es **180.000 vCPU-s/mes**
> (240.000 es la de facturación por instancia, que no aplica aquí; comprobado en
> cloud.google.com/run/pricing el 2026-10-01). Medido: los crons de opciones y geo eran
> el **97 %** del tiempo de petición de Cloud Run, ~268k vCPU-s/mes, muy por encima de
> los 180k. Pasar geo de 48 a 24 ciclos/día y opciones de 64 a 32 ciclos por día
> laborable divide ese 97 % entre dos: **~138k vCPU-s/mes estimados**, suponiendo que
> cada ciclo dura lo mismo. Es una estimación, no una medida: confírmala en la
> facturación del mes siguiente antes de volver a acortar un horario.

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

**Cloud Run primero, luego todos los jobs.** Al revés, los jobs dan 403 hasta que el
servicio recargue. Y si te dejas uno, **falla en silencio**: el job sigue en ENABLED y
solo lo delata un 403 en los logs.

```bash
NEW=$(openssl rand -hex 24)
gcloud run services update finview-api --region=europe-west1 --update-env-vars="FINVIEW_CRON_SECRET=${NEW}"
for J in geo-intel-cycle geo-intel-audit options-agent-cycle zonas-clave-cycle ibkr-sync-daily; do
  gcloud scheduler jobs update http $J --location=europe-west1 --update-headers="X-Cron-Key=${NEW}"
done
```

> ⚠️ `gcloud scheduler jobs describe` **imprime el secreto en claro**. Usa siempre
> `--format` acotado a los campos que necesitas; no pegues la salida completa en ningún
> sitio. (Ya pasó una vez: hubo que rotar.)

**Si añades otro pipeline programado, necesita su propio job** (y entrar en `SCHEDULER_JOBS`, creado antes del despliegue). El APScheduler solo
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
- **Build + despliegue seguro:** [cloudbuild.yaml](../cloudbuild.yaml) construye la imagen, demuestra localmente que escucha en `PORT=8080`, crea una revisión candidata privada con **0% de tráfico**, valida configuración y startup, cancela rollouts anteriores del mismo trigger, pausa los jobs de `SCHEDULER_JOBS` antes de cambiar tráfico, promueve al 100% y comprueba `/api/health/ready` en la URL pública. Solo el build activo más nuevo puede mutar tráfico; un rollback automático tras fallar el check público exige que su revisión siga siendo simultáneamente la última creada y la que sirve el 100%. Los callers se reanudan al salir del paso (trap `EXIT`, ver "Cloud Scheduler").
- **Promoción fallida (2026-09-30):** `update-traffic` escribe `spec.traffic` *antes* de que la revisión demuestre que arranca. Si falla el startup probe, el comando sale con error, `status.traffic` sigue en la revisión anterior pero `spec.traffic` queda apuntando a la fallida, con el servicio `Ready=False`, y todo `gcloud run deploy` posterior falla con *"Revision ... is not ready and cannot serve traffic"*. El rollback del check público no lo cubría: `bash -e` salía en esa línea y su condición mira `status.traffic`, que nunca se movió. Ahora el paso captura la revisión que sirve (`status.traffic`) antes de promover y, si la promoción falla **y `spec.traffic` sigue conteniendo la escritura de este build**, vuelve a `--to-revisions=<anterior>=100`. Si `spec` apunta a otra cosa no restaura nada: no es suyo. Los callers solo se reanudan si el servicio vuelve a `Ready=True` sirviendo el 100% en la anterior; si no converge, el build falla y los jobs **se quedan pausados** a propósito. Probado con un `gcloud` falso en `backend/tests/test_cloudbuild_rollout.py`.
- **Flags de runtime (críticos):** `--cpu-throttling` (facturación por petición), `--min-instances=0`, `--max-instances=1`, `--memory=1Gi`, `FINVIEW_ENV=production` y `FINVIEW_REQUEST_SCOPED_RUNTIME=true`. Producción falla al arrancar si falta ese modo, si los secretos de auth son inseguros o si la base de datos cae al SQLite efímero por defecto. No sustituir `--cpu-throttling` por `--no-cpu-throttling`: con jobs cada 30–60 minutos y hasta 15 minutos de retención ociosa, cada ciclo dejaría además hasta un cuarto de hora de instancia facturando aunque `min=0`.
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
- Cada cambio de tráfico pausa los cuatro jobs y el propio paso los reanuda al salir.
  La única salida que los deja pausados es una promoción fallida cuya restauración no
  vuelve a una revisión `Ready` sirviendo el 100%: el build queda en rojo y reanudarlos
  es manual, después de arreglar el tráfico.
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
- **Artifact Registry conserva solo las 10 imágenes más recientes.** Cada commit deja una
  imagen y el almacenamiento se factura aunque el servicio esté parado. Desde el
  2026-10-08 el repositorio `cloud-run-source-deploy` (europe-west1) tiene dos políticas
  de limpieza, fuera del modo de prueba: `keep-newest-10` (las 10 versiones más recientes
  de cada paquete) y `delete-the-rest` (todo lo demás); si una imagen cumple las dos,
  gana la de conservar. Google las aplica una vez al día, así que el tamaño baja con un
  día de retraso. Antes había 55 imágenes de `finview-api` (~7 GB), un registro
  abandonado de abril en `europe-west3` (1.4 GB) y el servicio antiguo `finview-backend`
  con sus dos imágenes, sin tráfico; los tres se borraron ese día. No está comprobado si
  Cloud Run puede arrancar instancias de una revisión cuya imagen ya se borró: para un
  rollback manual, elegir una revisión de las 10 más recientes. Comprobar la política:
  `gcloud artifacts repositories describe cloud-run-source-deploy --location=europe-west1 --format='yaml(cleanupPolicies,sizeBytes)'`.
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

### GitHub Actions — sí se usa (CI, no deploy)
`.github/workflows/ci.yml` corre ruff + pytest (backend) y typecheck + vitest + build
(frontend) en cada PR y en cada push a main.

Esta sección decía antes **"no añadir workflows"**, porque se creía que Actions estaba
deshabilitada en la cuenta. Era falso: Actions se ejecuta con normalidad, incluso en
repos privados como éste. Sobre esa premisa equivocada se borró el workflow de la
PR #210 (commit 168ed92) y el repo se quedó ~7 semanas sin ejecutar los tests — tiempo
en el que `test_enagas_dividend` estuvo en rojo en main sin que nadie lo viera.

Lo que sí es cierto es que **branch protection no está disponible** en el plan Free
(403: *"Upgrade to GitHub Pro or make this repository public"*). Un check en rojo no
puede bloquear el merge por sí solo; es señal, no barrera. Por eso el workflow dispara
también en `push: main`, para detectar lo que entre sin PR.

Las otras dos barreras siguen vigentes y no quedan sustituidas: `.githooks/pre-push`
(los mismos checks, en local, antes del push) y el preview de Vercel.

El deploy **no** pasa por Actions: sigue siendo Cloud Build. Workload Identity
Federation quedó pre-configurada por si algún día se usa Actions para desplegar. SA
`github-actions-deployer@finview-brais-2026` y pool `github` siguen vivos pero ningún
workflow los usa.

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
| `gcloud run deploy` falla con *"Revision 'finview-api-X' is not ready and cannot serve traffic"* | Una promoción anterior falló y dejó `spec.traffic` en la revisión X (antes del 2026-09-30, o la restauración automática no convergió: el build lo dice con *"Restore to ... did not converge"*). El servicio queda `Ready=False` / `RoutesReady=False` aunque `status.traffic` siga en la buena | Ver qué sirve de verdad: `gcloud run services describe finview-api --region europe-west1 --format='json(status.traffic)'`. Devolver el spec a esa revisión: `gcloud run services update-traffic finview-api --region europe-west1 --to-revisions <revisión-que-sirve>=100`. Después reanudar los jobs que sigan `PAUSED` y relanzar el build |
| Cloud Run dice que no escuchó en `PORT=8080` | Mensaje genérico: el proceso pudo fallar antes de abrir el puerto (por ejemplo, Neon sin cuota) | Leer el traceback de la revisión. La inicialización SQL ocurre antes de que el proceso quede listo |
| `/api/health` da 200 pero `/api/health/ready` da 503 | Producción arrancó sin `FINVIEW_REQUEST_SCOPED_RUNTIME=true` | Corregir el flag; el pipeline no debe promover esa revisión |
| `min=0` pero hay una instancia facturable constante | Facturación por instancia más peticiones más frecuentes que la ventana de retención ociosa | Pausar jobs, fijar `--cpu-throttling`, verificar `max=1` y reanudar solo tras el guard |
| **Una sección lee vacía sin ningún error** (Monitor de opciones, Técnico, Ideas) | El job de Cloud Scheduler no existe, está paused, o su secreto no coincide con Cloud Run → el pipeline no corre. El APScheduler de la UI no cuenta: muere con `--min-instances=0` | `gcloud scheduler jobs list --location=europe-west1` y comparar con los endpoints `/cron` que existen en el código. Ver "Cloud Scheduler" |
| **Ideas no produce señales nuevas** | Empezar por la cabecera de `/geo-intel`: la línea de estado dice cuándo corrió el último ciclo, si falló y qué ingirió. Sin ejecuciones o muy antiguas → es el job de Scheduler; ejecuciones recientes con **todas las fuentes a cero** → salida de red o claves de ingesta; ejecución fallida → el error va en la propia línea | `GET /api/geo/scheduler/status` devuelve lo mismo (`last_run`) sin abrir la UI. `POST /api/geo/cron` responde **500** si ningún ciclo termina, así que un job en rojo es diagnóstico, no ruido |
| Cron devuelve **403** | `FINVIEW_CRON_SECRET` de Cloud Run ≠ cabecera `X-Cron-Key` del job (típico: se rotó uno y no los otros) | Rotar de nuevo siguiendo el orden Cloud Run → todos los jobs |
| Cron devuelve **404** | El endpoint aún no está desplegado (PR mergeado pero Cloud Build sin terminar) | Esperar al build; comprobar `gcloud builds list --limit=1` |
| Señales técnicas todas "sin puntuar" | El scorer LLM falla: sin `FINVIEW_OPENROUTER_API_KEY`, o el modelo devolvió 200 con cuerpo vacío | `gcloud logging read '... textPayload:"zone scoring failed"'`. El log incluye `finish_reason` y `usage`. **`break_probability = NULL` es correcto en ese caso** — nunca se coerciona a 0, que leería como "seguro que no rompe" |
| El ciclo de zonas corre pero emite 0 señales | Normal si ningún precio está a <2% de una zona. Ojo: `_already_open()` bloquea duplicados del mismo ticker+nivel durante 20h, así que relanzarlo a mano el mismo día no emite nada | Comprobar la línea `N signals (M alerting)` en los logs |

## Historial de migraciones

- **Render** (`render.yaml` borrado) — stack inicial, abandonado por límites del plan Free.
- **Azure Container Apps** (`azure.yaml`, `.azure/`, `infra/*.bicep` borrados) — experimento, nunca llegó a prod.
- **Vercel + Cloud Run + Neon** (actual, desde abril 2026) — stack definitivo.
