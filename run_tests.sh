#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate venv
if [[ ! -f venv/bin/activate ]]; then
  echo "ERROR: venv not found. Run: python -m venv venv && pip install -r requirements.txt" >&2
  exit 1
fi
source venv/bin/activate

exec python -m pytest "$@"
