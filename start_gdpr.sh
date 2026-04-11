#!/usr/bin/env bash
# GDPRScanner — launch script (uses ./venv)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/venv/bin/activate"
exec python3 "$SCRIPT_DIR/gdpr_scanner.py" "${@}"
