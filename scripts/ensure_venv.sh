#!/usr/bin/env bash
# Ensure the project virtualenv is usable before the service starts.
#
# Why this exists: a venv's interpreter is just a symlink to a system Python.
# When the OS upgrades Python (e.g. 3.13 -> 3.14), the venv's site-packages
# directory (lib/pythonX.Y/site-packages) no longer matches the interpreter,
# so every import fails ("No module named 'uvicorn'") and the service
# crash-loops -> 502 at the proxy. This script detects that and rebuilds.
#
# Idempotent and fast on the happy path: if uvicorn imports, it does nothing.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"
REQ="$ROOT/requirements.txt"

# Prefer a versioned interpreter so a future `python3` bump doesn't move us
# again; fall back to whatever python3 is available.
pick_python() {
    for p in python3.14 python3.13 python3.12 python3; do
        if command -v "$p" >/dev/null 2>&1; then
            command -v "$p"
            return 0
        fi
    done
    echo "ensure_venv: no python3 interpreter found" >&2
    exit 1
}

rebuild() {
    local base; base="$(pick_python)"
    echo "ensure_venv: rebuilding venv with $base"
    rm -rf "$VENV"
    "$base" -m venv "$VENV"
    "$PY" -m pip install --upgrade pip
    "$PY" -m pip install -r "$REQ"
}

if [ ! -x "$PY" ] || ! "$PY" -c "import uvicorn" >/dev/null 2>&1; then
    echo "ensure_venv: venv missing or broken — rebuilding"
    rebuild
else
    echo "ensure_venv: venv OK"
fi
