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

Receipts, invoices and bank statements are read by a local vision model through [Ollama](https://ollama.com). Keep the Ollama app running with the model downloaded:

```sh
ollama pull qwen3-vl:2b
```

On Linux, start Ollama with `OLLAMA_HOST=0.0.0.0` so the container can reach it. Set `TRACEPAI_VISION_MODEL` to use another model.

To scan receipts from a phone, open `http://<your-computer-ip>:8000` on the same Wi-Fi.

## Develop

```sh
cd backend && uv run pytest              # fast tests
cd backend && uv run pytest -m model -s  # reads generated documents with the real model (a few minutes)
cd frontend && npm run build
```
