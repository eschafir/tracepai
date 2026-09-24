#!/bin/sh
set -e
cd "$(dirname "$0")/.."
PORT="${PORT:-8000}"
docker build -t tracepai .
docker rm -f tracepai >/dev/null 2>&1 || true
docker run -d --name tracepai --add-host=host.docker.internal:host-gateway -p "$PORT:8000" -v tracepai-data:/data tracepai >/dev/null
echo "TracepAI is running at http://localhost:$PORT (login: user / password)"
