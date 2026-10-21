#!/bin/sh
# Raval Trips - macOS: double-click this file. First run installs, later runs just start the app.
cd "$(dirname "$0")" || exit 1
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10 or newer is required. Install it from https://www.python.org/downloads/ and run this again."
  read -r -p "Press Enter to close…" _; exit 1
fi
if [ ! -x .venv/bin/raval-trips ]; then
  echo "Installing Raval Trips (one time, about a minute)…"
  "$PY" -m venv .venv && .venv/bin/python -m pip install --quiet --upgrade pip && .venv/bin/python -m pip install --quiet . || {
    echo "Installation failed."; read -r -p "Press Enter to close…" _; exit 1; }
fi
exec .venv/bin/raval-trips serve
