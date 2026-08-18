#!/usr/bin/env bash
# Killer demo: start fixtures, reduce a >15 KB request, print the scoreboard.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

PORT="${PORT:-18765}"
python3 -m crashmin.fixtures --host 127.0.0.1 --port "$PORT" &
PID=$!
cleanup() { kill "$PID" 2>/dev/null || true; }
trap cleanup EXIT

for _ in $(seq 1 50); do
  if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT}/health')" 2>/dev/null; then
    break
  fi
  sleep 0.05
done

python3 - <<PY
from pathlib import Path
from crashmin.demo import killer_curl
Path("${ROOT}/examples/killer.curl").write_text(killer_curl("http://127.0.0.1:${PORT}"))
print("wrote examples/killer.curl")
PY

python3 -m crashmin \
  "$ROOT/examples/killer.curl" \
  --status 500 \
  --body-regex 'panic: nil pointer' \
  --final-confirm 20 \
  --compact
