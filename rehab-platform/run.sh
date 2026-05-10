#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDS=()

cleanup() {
  echo
  echo "Stopping services..."
  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
}

open_browser() {
  local url="http://localhost:5173"

  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 &
  elif command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 &
  elif command -v cmd.exe >/dev/null 2>&1; then
    cmd.exe /c start "$url" >/dev/null 2>&1 &
  else
    echo "Open $url in your browser."
  fi
}

trap cleanup INT TERM EXIT

cd "$ROOT_DIR"

if [ -f "$ROOT_DIR/backend/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$ROOT_DIR/backend/.venv/bin/activate"
elif [ -f "$ROOT_DIR/backend/.venv/Scripts/activate" ]; then
  # shellcheck disable=SC1091
  source "$ROOT_DIR/backend/.venv/Scripts/activate"
fi

export PYTHONPATH="$ROOT_DIR/backend:${PYTHONPATH:-}"
uvicorn backend.main:app --reload &
PIDS+=("$!")

cd "$ROOT_DIR/frontend"
npm run dev -- --host 0.0.0.0 &
PIDS+=("$!")

sleep 2
open_browser

echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo "Press Ctrl+C to stop all services"

wait
