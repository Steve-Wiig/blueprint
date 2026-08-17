#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
echo "Starting Overnight Loop..."
if [ -z "${GEMINI_API_KEY:-}" ]; then echo "ERROR: export GEMINI_API_KEY first"; exit 1; fi
python3 "$DIR/loop.py"
python3 "$DIR/report.py"
