#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment…"
  python3 -m venv .venv
fi

source .venv/bin/activate

if [ ! -f ".venv/.deps_installed" ]; then
  echo "Installing dependencies (one-time)…"
  pip install --upgrade pip >/dev/null
  pip install -r requirements.txt
  touch .venv/.deps_installed
fi

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo "  Created .env — open it and add your API keys, then re-run ./start.sh"
  echo ""
  exit 0
fi

echo ""
echo "  Server starting at http://127.0.0.1:8000"
echo "  Press Ctrl+C to stop."
echo ""
exec python backend.py
