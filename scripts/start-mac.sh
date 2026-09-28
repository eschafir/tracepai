#!/bin/sh
set -e
cd "$(dirname "$0")/.."
PORT="${PORT:-8000}"
# The host's time zone (e.g. America/New_York), so "today" in the app is the same day as on your computer
TZ_NAME="$(readlink /etc/localtime | sed 's#.*/zoneinfo/##')"
docker build -t tracepai .
docker rm -f tracepai >/dev/null 2>&1 || true
docker run -d --name tracepai -p "$PORT:8000" -e TRACEPAI_SEED_DEMO=1 -e TZ="${TZ_NAME:-UTC}" -v tracepai-data:/data tracepai >/dev/null
echo "TracepAI is running at http://localhost:$PORT (login: user / password)"
