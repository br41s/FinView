#!/usr/bin/env bash
# Dump current Render Postgres and restore into Neon.
# Run locally — requires pg_dump + psql (postgresql-client).
#
# Usage:
#   RENDER_DATABASE_URL="postgres://..."  # External URL from Render dashboard
#   NEON_DATABASE_URL="postgres://...?sslmode=require"
#   ./migrate_db.sh
set -euo pipefail

: "${RENDER_DATABASE_URL:?set RENDER_DATABASE_URL (external URL from Render)}"
: "${NEON_DATABASE_URL:?set NEON_DATABASE_URL}"

DUMP_FILE="finview-$(date +%Y%m%d-%H%M%S).dump"

echo "==> dumping Render DB to $DUMP_FILE"
pg_dump --no-owner --no-acl --format=custom \
    --dbname="$RENDER_DATABASE_URL" \
    --file="$DUMP_FILE"

echo "==> restoring into Neon (will drop conflicting objects first)"
pg_restore --no-owner --no-acl --clean --if-exists \
    --dbname="$NEON_DATABASE_URL" \
    "$DUMP_FILE"

echo "==> verify row counts"
psql "$NEON_DATABASE_URL" -c "
SELECT 'users' AS t, COUNT(*) FROM users UNION ALL
SELECT 'accounts',    COUNT(*) FROM accounts UNION ALL
SELECT 'transactions',COUNT(*) FROM transactions UNION ALL
SELECT 'tax_lots',    COUNT(*) FROM tax_lots;
"

echo "==> done. Dump kept at $DUMP_FILE (gitignored)."
