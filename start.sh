#!/usr/bin/env bash
# APIGuard - start backend (FastAPI :8000) and frontend (React :5173)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Backend (FastAPI)"
cd "$ROOT/backend"
if [ ! -d ".venv" ]; then
  echo "    creating virtual environment..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "==> Frontend (React)"
cd "$ROOT/frontend"
if [ ! -d "node_modules" ]; then
  echo "    installing npm packages (first run)..."
  npm install --no-audit --no-fund
fi
npm run dev &
FRONTEND_PID=$!

cleanup() {
  echo ""
  echo "==> Stopping services"
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo ""
echo "  Dashboard : http://localhost:5173"
echo "  API docs  : http://localhost:8000/docs"
echo "  Metrics   : http://localhost:8000/metrics"
echo "  Press Ctrl+C to stop."
wait
