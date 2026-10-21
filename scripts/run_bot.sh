#!/usr/bin/env bash
# Start DevTask Bot on macOS/Linux.
# Usage (from repo root): ./scripts/run_bot.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Virtual environment not found. Create it with: python3 -m venv .venv" >&2
  exit 1
fi

exec "$ROOT/.venv/bin/python" -m app.main
