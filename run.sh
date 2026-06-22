#!/usr/bin/env bash
# Start SynthLaunch locally. First run sets up a venv and installs deps.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "==> creating virtualenv"
  python3 -m venv .venv
  ./.venv/bin/python -m pip install --quiet --upgrade pip
  ./.venv/bin/python -m pip install --quiet -r requirements.txt
fi

[ -f .env ] || { [ -f .env.example ] && cp .env.example .env && echo "==> created .env (edit to add an API key)"; }

# Build the React/shadcn frontend (Vite) if it hasn't been built yet.
if [ ! -d frontend/dist ]; then
  if command -v npm >/dev/null 2>&1; then
    echo "==> building frontend (first run)"
    ( cd frontend && npm install --no-audit --no-fund && npm run build )
  else
    echo "WARN: npm/Node not found — frontend not built. Install Node 18+, then:"
    echo "      npm --prefix frontend install && npm --prefix frontend run build"
  fi
fi

PORT="${PORT:-8000}"
echo "==> SynthLaunch on http://localhost:${PORT}"
exec ./.venv/bin/python -m uvicorn app:app --app-dir backend --host 0.0.0.0 --port "${PORT}" "$@"
