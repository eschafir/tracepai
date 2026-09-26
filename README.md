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

Receipts, tickets and invoices (photos, images or PDFs) are read with Tesseract OCR inside the container, in English and Spanish. Bank statements are imported as CSV.

To scan receipts from a phone, open `http://<your-computer-ip>:8000` on the same Wi-Fi.

## Develop

```sh
cd backend && uv run pytest              # fast tests
cd backend && uv run pytest -m model -s  # reads generated documents with the real model (a few minutes)
cd frontend && npm run build
```
