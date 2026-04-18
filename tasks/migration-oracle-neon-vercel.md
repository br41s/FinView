# Migración: Render → Oracle Cloud + Neon + Vercel

Objetivo: salir del free tier de Render (512MB RAM, sleep 15min, DB expira 30 días) a una stack gratuita sin caducidad.

- **DB**: Neon (Postgres serverless, 0.5 GB free, sin caducidad)
- **Backend**: Oracle Cloud Free ARM VM (Ubuntu 24.04, 4 vCPU / 24GB RAM siempre gratis)
- **Frontend**: Vercel (Hobby free, builds ilimitadas para uso personal)

Fase 1 (fix `strftime` SQLite→Postgres) ya está en `main` — commit `9ec770e`.

---

## 0. Pre-requisitos locales

```bash
# Verifica que pg_dump esté disponible (si no):
brew install libpq && brew link --force libpq
```

## 1. Neon — crear DB y migrar datos

1. Crear cuenta en https://neon.tech (login con GitHub).
2. Crear **project** "finview" → región **AWS eu-central-1** (Frankfurt, baja latencia con Oracle Madrid/Frankfurt).
3. Copiar el **connection string** (formato `postgresql://user:pass@host/db?sslmode=require`).
4. Copiar el **External Database URL** de Render (dashboard → finview-db → Connect).
5. Ejecutar localmente:
   ```bash
   cd /Users/brais/VSCODE/FinView
   RENDER_DATABASE_URL="<url-externa-render>" \
   NEON_DATABASE_URL="<url-neon>" \
   ./infra/oracle/migrate_db.sh
   ```
6. Verificar que los conteos coinciden con lo que ves en la UI actual.

## 2. Oracle Cloud — crear VM

1. https://signup.cloud.oracle.com → cuenta gratuita (requiere tarjeta para verificación, no cobra).
2. Home region: **Frankfurt** (eu-frankfurt-1) o **Madrid** (eu-madrid-1).
3. **Compute → Instances → Create**:
   - Shape: **VM.Standard.A1.Flex** (Ampere ARM, Always Free)
   - CPU: 4 OCPU, Memory: 24 GB
   - Image: **Canonical Ubuntu 24.04**
   - Generar SSH key → guardar `.key` en `~/.ssh/oracle_finview.key`
   - Network: crear VCN nuevo, **asignar IP pública**
4. Tras crear, ir a **VCN → Subnet → Security Lists → Default** y añadir ingress rules:
   - Source `0.0.0.0/0`, TCP port **80**
   - Source `0.0.0.0/0`, TCP port **443**

## 3. Backend — bootstrap en la VM

```bash
# SSH
chmod 600 ~/.ssh/oracle_finview.key
ssh -i ~/.ssh/oracle_finview.key ubuntu@<public-ip>

# Subdominio gratis con nip.io (sin dominio propio): api-<ip-con-guiones>.nip.io
# Ej: IP 132.226.12.34 → api-132-226-12-34.nip.io

git clone https://github.com/braisntext/FinView.git
cd FinView/infra/oracle

# Primera pasada: crea .env.production vacío y sale
API_DOMAIN="api-132-226-12-34.nip.io" \
LETSENCRYPT_EMAIL="braisn@gmail.com" \
./bootstrap.sh

# Editar secrets:
nano /home/ubuntu/FinView/.env.production
# Rellenar:
#   FINVIEW_DATABASE_URL = string de Neon
#   FINVIEW_SECRET_KEY   = openssl rand -hex 32
#   FINVIEW_AUTH_SECRET  = (tendrá que coincidir con AUTH_SECRET en Vercel)
#   FINVIEW_FRONTEND_URL = https://<tu-proyecto>.vercel.app   (temporal, se ajusta tras deploy Vercel)

# Segunda pasada: instala systemd + nginx + certbot
API_DOMAIN="api-132-226-12-34.nip.io" \
LETSENCRYPT_EMAIL="braisn@gmail.com" \
./bootstrap.sh

# Smoke test
curl https://api-132-226-12-34.nip.io/api/health
# {"status":"ok"}
```

## 4. Frontend — deploy en Vercel

1. https://vercel.com → **Add New → Project → Import** `braisntext/FinView`.
2. Configure Project:
   - **Root Directory**: `frontend`
   - **Framework Preset**: Next.js (auto-detecta)
   - Build command por defecto (`pnpm build` vía `vercel.json` del repo, o auto).
3. **Environment Variables**:
   - `BACKEND_URL` = `https://api-132-226-12-34.nip.io`
   - `AUTH_SECRET` = mismo valor que `FINVIEW_AUTH_SECRET` en la VM
   - `NEXTAUTH_URL` = `https://<tu-proyecto>.vercel.app` (pondré el definitivo tras primer deploy)
4. **Deploy**. Copiar URL final (ej. `finview-brais.vercel.app`).
5. En la VM, actualizar `.env.production`:
   ```
   FINVIEW_FRONTEND_URL=https://finview-brais.vercel.app
   ```
   y `sudo systemctl restart finview-api`.
6. En Vercel, actualizar `NEXTAUTH_URL` al dominio real → redeploy.

## 5. Smoke test end-to-end

- [ ] `https://finview-brais.vercel.app` carga la UI
- [ ] Login funciona (el CORS del backend acepta la URL Vercel)
- [ ] Subir un PDF BBVA → import OK (verifica que el fix de Fase 1 quedó desplegado)
- [ ] Ver Portfolio → datos iguales a Render
- [ ] Ver Fiscal → casillas iguales

## 6. Apagar Render

Cuando todo esté verde durante al menos un día:

1. Render dashboard → Suspender los 3 servicios (`finview-api`, `finview-web`, `finview-db`).
2. Hacer un último `pg_dump` de la DB como backup y guardarlo local.
3. Borrar servicios tras 7 días si no hay sorpresas.

---

## Troubleshooting

- **VM inalcanzable en puerto 80/443**: revisa Security List en VCN **y** `sudo iptables -L` — Oracle Ubuntu por defecto bloquea todo salvo SSH. El `bootstrap.sh` intenta abrir 80/443 con iptables pero confirma con `sudo iptables -L INPUT -n`.
- **502 Bad Gateway en nginx**: `sudo journalctl -u finview-api -n 100` — típicamente falta alguna env var o la URL de Neon está mal.
- **CORS bloqueado**: `FINVIEW_FRONTEND_URL` debe ser exactamente la URL Vercel sin barra final.
- **AUTH errors "invalid token"**: `AUTH_SECRET` en Vercel y `FINVIEW_AUTH_SECRET` en la VM deben ser idénticos carácter a carácter.
