#!/usr/bin/env bash
# FinView — arrancar backend + frontend
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Liberar puertos si están ocupados
for port in 8000 3000; do
  pid=$(lsof -ti :$port 2>/dev/null || true)
  if [ -n "$pid" ]; then
    echo "⚠ Puerto $port ocupado (PID $pid) — liberando..."
    kill $pid 2>/dev/null
    sleep 1
  fi
done

cleanup() {
  echo ""
  echo "Parando FinView..."
  kill $PID_BACK $PID_FRONT 2>/dev/null
  wait $PID_BACK $PID_FRONT 2>/dev/null
  echo "Parado."
}
trap cleanup EXIT INT TERM

# Backend
echo "▶ Backend en http://localhost:8000"
source .venv/bin/activate
uvicorn backend.app:app --port 8000 &
PID_BACK=$!

# Frontend
echo "▶ Frontend en http://localhost:3000"
cd frontend
pnpm dev --port 3000 &
PID_FRONT=$!
cd ..

echo ""
echo "✓ FinView listo → http://localhost:3000"
echo "  Ctrl+C para parar"
echo ""

wait
