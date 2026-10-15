---
paths:
  - "backend/services/auth_service.py"
  - "backend/services/turnstile.py"
  - "backend/services/rate_limit.py"
  - "backend/api/auth.py"
  - "backend/api/users.py"
  - "backend/services/user_data.py"
  - "backend/services/billing_service.py"
  - "backend/config.py"
  - "backend/services/credentials_crypto.py"
  - "backend/api/brokers.py"
  - "frontend/src/auth.ts"
  - "frontend/next.config.ts"
---

## Auth & security

### Auth flow
- Frontend `NextAuth` (Credentials provider, `frontend/src/auth.ts`) → backend `/api/auth/login`.
  Backend issues an HS256 JWT signed with `FINVIEW_SECRET_KEY`; NextAuth stores it as
  `accessToken` and the API client (`src/lib/api.ts`) sends it as `Authorization: Bearer`.
- Passwords: bcrypt (`auth_service.py`). JWT + NextAuth session both last **90 days**, and
  both slide: the cookie rolls forward on activity, and `auth.ts`'s `jwt` callback swaps the
  token for a fresh one via `POST /api/auth/refresh` once fewer than 7 days remain
  (`src/lib/tokenExpiry.ts`). Refresh needs a still-valid token and an active user, so it can
  extend a live session but never revive one; a failed refresh is retried an hour later. Before
  2026-10-14 the token was only minted at login and a daily-used session still died on day 90.
- `FINVIEW_AUTH_SECRET` (backend) **must equal** `AUTH_SECRET` (frontend) or every request
  fails with "Invalid token".

### Secret enforcement
- `config.py` blocks startup if `FINVIEW_ENV ∈ {staging,production,prod}` and `secret_key`
  or `auth_secret` is missing / still the insecure default. **`FINVIEW_ENV=production` must
  be set on Cloud Run** or the guard never fires and JWTs sign with the public default.

### Turnstile (bot protection on login)
- Cloudflare Turnstile gates login. Token: login page → NextAuth `authorize` →
  backend body `turnstile_token` → `services/turnstile.py` verifies via Cloudflare siteverify.
- **No-op when `FINVIEW_TURNSTILE_SECRET` is unset** (dev/unconfigured deploys work unchanged).
  Frontend widget renders only when `NEXT_PUBLIC_TURNSTILE_SITE_KEY` is set.
- **Fail-closed**: missing/invalid token or any verify error → 403. Flip the `except` in
  `turnstile.py` to fail-open if a Cloudflare outage blocking logins is unacceptable.
- Login only (not register) — register Turnstile is a deferred follow-up.

### Machine auth: the cron shared secret
- The three `/cron` endpoints (geo, options, zonas-clave) are gated by `require_cron_key`
  in `api/auth.py`, applied as a **route dependency** (`dependencies=[CronKey]`) rather
  than a line in each handler. It was copy-pasted into all three bodies; one definition
  beats three chances to get `hmac.compare_digest` or the empty-secret case wrong.
- **An unset `FINVIEW_CRON_SECRET` closes these endpoints, not opens them.**
- A new cron endpoint must carry `dependencies=[CronKey]`. `test_cron_auth.py` asserts
  every cron route has it *and* that no other route does — a human-facing endpoint behind
  a machine secret would lock users out.

### Plan limits
- `check_account_limit` (accounts) and `check_import_limit` (imports) both live in
  `billing_service.py`. The import gate is a route dependency on all six upload endpoints;
  `test_import_quota.py` asserts all six carry it.
- Window is the calendar month in UTC, counted from `ImportRecord`. A re-upload of an
  already-imported file does not consume allowance — the `(file_hash, broker)` unique
  constraint means it never created a second row.
- **An unreadable tier falls back to Free, never to unlimited.** A quota must not fail open.
- Imports made by a broker sync (`import_records.origin` set) are not uploads and are not
  counted: a full-history backfill alone would spend a Free month several times over.
  `/pricing` and `/legal/condiciones` say "importaciones de archivos" for that reason.
- `/billing/subscription` reports `imports_this_month` alongside the limit, so the 403 is
  explicable. Enforcing a quota nobody can see is worse than not enforcing it.

### Broker credentials (IBKR Flex token)
- Encrypted at rest with Fernet under `FINVIEW_CREDENTIALS_KEY` (`services/credentials_crypto.py`).
  **Unset closes the feature** — `/api/brokers/*` answers 503 and the card hides — instead
  of storing tokens in clear. A rotated key makes stored tokens unreadable: sync answers 409
  and the user reconnects.
- Write-only from the client: accepted on `PUT /api/brokers/ibkr`, never returned (only the
  last four characters), and excluded from the data export (`user_data._NEVER_EXPORTED`).
- Set the key once on Cloud Run from Secret Manager (`--update-secrets`); `cloudbuild.yaml`
  only touches `FINVIEW_ENV` and `FINVIEW_REQUEST_SCOPED_RUNTIME`, so it persists across deploys.

### HTTP security headers
- Set on every response in `frontend/next.config.ts` (`headers()`): `X-Frame-Options: DENY`,
  CSP `frame-ancestors 'none'`, HSTS, `X-Content-Type-Options`, `Referrer-Policy`,
  `Permissions-Policy`. **Intentionally no content-CSP** (`script-src` etc.) — would break
  Next.js inline scripts / Recharts. Don't add one without testing every page.

### Rate limiting
- slowapi per-IP on login (`5/minute`) and register (`3/minute`), in-memory per instance.
  Client IP = **rightmost** `X-Forwarded-For` entry (the value Cloud Run's GFE appended;
  leftmost is spoofable). See `services/rate_limit.py`.

### Privacy mode (dashboard)
- Eye toggle in the dashboard header sets `data-privacy` on `<main>`; CSS blurs any
  `.fv-sensitive` value (`globals.css`). Persisted in `localStorage` (`fv-privacy`).
  Currently tags StatsCards money only — add the class to extend to tables/charts.

### Consent and data rights
- **Terms acceptance** is proof, not decoration: `POST /auth/register` rejects a body without
  `accept_terms: true` and stamps `users.terms_version` / `terms_accepted_at`. The backend
  owns the version (`TERMS_VERSION` in `auth_service.py`); `/auth/me` reports
  `terms_accepted`, and `TermsBanner` on the dashboard asks anyone on another version —
  including accounts created before acceptance was recorded — to accept.
- **The account endpoints live under `/users/me`, not `/auth`.** The Next rewrite forwards
  only `/api/auth/(login|register|me)` to the backend; every other `/api/auth/*` path is
  NextAuth's. Do not widen that regex for a new endpoint.
- **Export and deletion share one definition of ownership** (`services/user_data.py`), derived
  from the schema. The export streams row by row — `options_snapshots` is never pruned — and
  never includes `password_hash`.
- **Deletion asks for the password again** (the session lasts 90 days) and is rate-limited
  like login. It deletes the Stripe customer first, which cancels any subscription, and
  returns 502 without deleting anything if Stripe fails. Rows go children-first;
  `test_user_data.py` runs with SQLite foreign keys enforced so a wrong order fails locally
  the way it would on Postgres.
- **Health data**: `PUT /fiscal/profile/{year}` returns 422 when `disability` is set without
  `health_data_consent`. Clearing the field clears `health_data_consent_at`.
- The system user that owns the shared Ideas is inactive and has no password, so it can
  neither log in nor be deleted through these endpoints.
