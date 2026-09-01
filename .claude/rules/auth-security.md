---
paths:
  - "backend/services/auth_service.py"
  - "backend/services/turnstile.py"
  - "backend/services/rate_limit.py"
  - "backend/api/auth.py"
  - "backend/services/billing_service.py"
  - "backend/config.py"
  - "frontend/src/auth.ts"
  - "frontend/next.config.ts"
---

## Auth & security

### Auth flow
- Frontend `NextAuth` (Credentials provider, `frontend/src/auth.ts`) → backend `/api/auth/login`.
  Backend issues an HS256 JWT signed with `FINVIEW_SECRET_KEY`; NextAuth stores it as
  `accessToken` and the API client (`src/lib/api.ts`) sends it as `Authorization: Bearer`.
- Passwords: bcrypt (`auth_service.py`). JWT + NextAuth session both last **90 days**.
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
- `/billing/subscription` reports `imports_this_month` alongside the limit, so the 403 is
  explicable. Enforcing a quota nobody can see is worse than not enforcing it.

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
