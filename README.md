# TracepAI

Track income and expenses, set budgets, and scan receipts. Runs locally in Docker.

## Run

Requires Docker.

```sh
scripts/start-mac.sh      # or start-linux.sh, or start-windows.ps1
scripts/stop-mac.sh       # or stop-linux.sh, or stop-windows.ps1
```

Open http://localhost:8000 and log in with `user` / `password`. Set `PORT` to use another port, e.g. `PORT=8001 scripts/start-mac.sh`.

Data is stored in the `tracepai-data` Docker volume. Mock data is created on first start, because the start scripts set `TRACEPAI_SEED_DEMO=1`. Leave it unset on a public deployment. There, also set:
- `TRACEPAI_SECURE_COOKIES=1` when the app is served over HTTPS
- `FORWARDED_ALLOW_IPS` to the address range of the proxy in front of the app, such as Render's, so failed logins are counted per real client. Don't use `*`: it lets a client choose its own address. Each username also allows at most 50 failed logins per 15 minutes from all clients together.
- `TZ` to the users' time zone, for example `America/New_York` (the start scripts pass your computer's)

Receipts, tickets and invoices (photos, images or PDFs) are read with Tesseract OCR inside the container, in English and Spanish. Bank statements are imported as CSV.

To scan receipts from a phone, open `http://<your-computer-ip>:8000` on the same Wi-Fi.

## Develop

```sh
cd backend && uv run pytest              # fast tests
cd backend && uv run pytest -m model -s  # reads generated documents with the real model (a few minutes)
cd frontend && npm run build
```
