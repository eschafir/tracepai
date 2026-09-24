# TracepAI

Track income and expenses, set budgets, and scan receipts. Runs locally in Docker.

## Run

Requires Docker.

```sh
scripts/start-mac.sh      # or start-linux.sh, or start-windows.ps1
scripts/stop-mac.sh       # or stop-linux.sh, or stop-windows.ps1
```

Open http://localhost:8000 and log in with `user` / `password`. Set `PORT` to use another port, e.g. `PORT=8001 scripts/start-mac.sh`.

Data is stored in the `tracepai-data` Docker volume. Mock data is created on first start.

To scan receipts from a phone, open `http://<your-computer-ip>:8000` on the same Wi-Fi.

## Develop

```sh
cd backend && uv run pytest
cd frontend && npm run build
```
