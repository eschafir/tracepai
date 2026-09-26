# TracepAI MVP Plan

## Context
The project folder is empty apart from CLAUDE.md and a placeholder docs/PLAN.md. The goal is a local, Docker-packaged personal finance app:
- Next.js frontend served by a FastAPI backend, with a SQLite database.
- Login is hardcoded to `user` / `password`.
- The app starts with mock data.
- You can add, edit and delete transactions, set budgets, and see six analytics charts.

Decisions made while planning:
- **Receipts:** you photograph a receipt inside the app. Open-source OCR (Tesseract) reads it and fills in the add-transaction form. No WhatsApp, no Claude vision.
- **Google Sheet:** dropped. All data lives in SQLite.
- **Phase 1 scope:** login, transactions (fast entry, notes, tags, splits, receipt attachment), categories, budgets, mock data, receipt scanning, all 6 charts, and CSV/JSON export.
- **Later phases:** Open Banking sync, smart categorization, recurring detection, FX, shared wallets, push alerts, encryption and biometrics.

## Layout
```
backend/                 FastAPI app, managed with uv (pyproject.toml, uv.lock)
  app/main.py            app, routers, static mount of frontend build at /
  app/db.py              SQLModel engine, create_all, seed on first run
  app/models.py          User, Session, Category, Transaction, Split, Budget
  app/auth.py            login/logout, session cookie dependency
  app/routers/           transactions.py, categories.py, budgets.py, analytics.py, receipts.py, export.py
  app/ocr.py             pytesseract call + receipt text parsing
  app/seed.py            deterministic mock data (~6 months)
  tests/                 pytest: auth, CRUD, analytics, receipt parser
frontend/                Next.js (App Router, static export), TypeScript, Tailwind, Recharts
  app/login, app/(dashboard)/page.tsx, app/transactions, app/budgets
Dockerfile               stage 1 node build -> stage 2 python + uv + tesseract-ocr
scripts/                 start-mac.sh, stop-mac.sh, start-linux.sh, stop-linux.sh, start-windows.ps1, stop-windows.ps1
docs/PLAN.md             copy of this plan, updated as phases complete
```

## Data model (SQLModel, SQLite at /data/tracepai.db, Docker volume)
- **User:** id, username, password_hash. Seeded with `user` / `password` (hashed with argon2 or bcrypt). The table supports multiple users later.
- **Session:** token, user_id, created_at. The token is stored in an HTTP-only cookie.
- **Category:** id, user_id, name, color, kind (`income` or `expense`).
- **Transaction:** id, user_id, date, amount (always positive), kind, merchant, payment_method, category_id (nullable when there are splits), notes, tags (comma-separated text), receipt_path.
- **Split:** id, transaction_id, category_id, amount. A transaction with splits is counted per split in category analytics.
- **Budget:** id, user_id, category_id, monthly_limit.

The database is created with `create_all` if it doesn't exist. `seed.py` fills it on first run only:
- Categories.
- Six months of transactions: salary, rent, groceries, dining, transport, subscriptions, a few large outliers, and some split purchases.
- Budgets.

## API (all under /api, all except login require the session cookie)
- **Login:** `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`.
- **Transactions:** full create/read/update/delete on `/transactions`. The list takes `start`, `end`, `category`, `tag` and `q` filters. Splits are sent inline with the transaction.
- **Categories and budgets:** create/read/update/delete on `/categories` and `/budgets`.
- **Analytics** (each takes a date range):
  - `/analytics/categories`: donut chart.
  - `/analytics/cashflow?bucket=day|month`: income vs expenses and net.
  - `/analytics/budgets?month=`: spent vs limit, percent, days remaining.
  - `/analytics/merchants`: top single transactions, and merchants ranked by count and total.
  - `/analytics/comparison?month=`: cumulative daily spend this month vs last month.
  - `/analytics/balance`: running balance over time.
- **Receipts:**
  - `POST /receipts/scan` (image upload): saves the image to /data/receipts, runs Tesseract, and returns `{merchant, date, amount, receipt_path, raw_text}`.
  - `GET /receipts/{name}`: serves the image.
- **Export:** `GET /export?format=csv|json`.

## Receipt OCR
- The Docker image installs `tesseract-ocr` with apt; Python calls it through `pytesseract` and Pillow.
- The parser in `ocr.py` uses simple rules:
  - **Merchant:** the first non-empty line.
  - **Date:** the first match against common date formats.
  - **Amount:** the number on a line with TOTAL, IMPORTE or AMOUNT; if there is none, the largest money value.
- The results are a suggestion. The form opens pre-filled and you correct it before saving.
- Unit tests run the parser on sample receipt text.
- Accuracy will be moderate. A later upgrade is a local vision model through Ollama (e.g. Qwen2.5-VL) behind the same endpoint.

## Frontend
- Built with `output: 'export'`. FastAPI serves the files at `/`, and the frontend calls `/api` on the same origin, so no CORS setup is needed.
- **Login page.** Redirects to the dashboard once you're logged in.
- **Dashboard:**
  - KPI row: balance, this month's income, expenses and net.
  - The six charts: category donut, cash flow bars, budget progress bars, merchant outliers (ranked bars), period comparison line, and live balance line.
  - A period picker: week, month or year.
- **Transactions page:**
  - A table with filters and edit/delete actions.
  - A fast-entry modal: amount, category and payment method up front, with notes, tags and splits in an expandable section.
  - A "Scan receipt" button (`<input type="file" accept="image/*" capture>`) that pre-fills the modal.
  - Export buttons.
- **Budgets page:** create/read/update/delete on monthly limits per category.
- Implementation loads the `frontend-design` and `dataviz` skills before building the UI and charts.

## Docker and scripts
- **Dockerfile:**
  - Stage 1: `node:lts` runs `npm ci && npm run build`.
  - Stage 2: `python:3.13-slim` plus the uv binary and tesseract-ocr. It runs `uv sync --frozen`, copies `frontend/out` to `backend/static`, and starts `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- **Start scripts:** build the image and run the container detached, named `tracepai`, publishing port 8000, with the `tracepai-data` volume mounted at /data.
- **Stop scripts:** stop and remove the container.
- **Phone access:** open `http://<laptop-ip>:8000` from a phone on the same Wi-Fi.

## Housekeeping
- Write this plan into `docs/PLAN.md`.
- Replace the WhatsApp/Google Sheet "Aditional implementation" section in CLAUDE.md with the in-app OCR decision.
- Write a short README: prerequisites (Docker), start/stop commands, login details.

## Build order
1. Backend skeleton, models, database creation and seed, auth, and tests.
2. Transactions, categories, budgets and export endpoints, with tests.
3. Analytics endpoints, with tests.
4. OCR endpoint and parser, with tests.
5. Frontend: login, transactions page and modal, budgets page, dashboard charts.
6. Dockerfile and scripts, then the README and docs/PLAN.md.

## Verification
- `uv run pytest` in backend/ passes.
- `scripts/start-mac.sh` brings the container up.
- Then, at http://localhost:8000:
  - Log in with `user` / `password` and see the dashboard with mock data in all six charts.
  - Add, edit and delete a transaction, including a split, and see the charts update.
  - Upload a receipt photo and see the fields pre-filled.
  - Export CSV and JSON.
- Restart the container and confirm the data persists.
- Use the browser tools (claude-in-chrome) to click through the flow and check the console for errors.
- `scripts/stop-mac.sh` stops the container cleanly.

## Status (2026-09-24)

Phase 1 complete. All build-order steps are done and verified: 12 backend tests pass, the Docker image builds and runs, receipt OCR works in the container, the end-to-end UI flow (login, scan, split, search, edit, delete, export, logout) passes in headless Chrome, and data persists across restarts.

Deviations from the plan:
- Category colors are stored as `color_slot` (1-8), an index into the validated chart palette, so light and dark mode each use their own colors.
- The start scripts read `PORT` (default 8000).

Next phases: smart categorization, recurring detection, Open Banking sync, FX, shared wallets, pacing alerts, local vision model for receipts.

---

# TracepAI Phase 2: Wallets, Transfers, Recurring, Smart Categories, CSV Import

## Context
Phase 1 works end to end, but the app has only one balance for everything. It also can't:
- tell a transfer apart from spending,
- handle fixed monthly charges,
- guess categories,
- load bank statements.

These four features close the biggest gaps against Spendee, and none of them needs an outside service.

Decisions made:
- **Data reset:** the database is reset once, and the new mock data includes wallets, transfers and recurring items. There is no migration code.
- **Wallets replace "Paid with":** the `payment_method` field is removed, and the wallet picker takes its place in the add form.

## Data model changes (`backend/app/models.py`)
- **New `Wallet`:** id, user_id, name, kind (`bank` | `card` | `cash` | `savings`), color_slot (1-8, same palette as categories), opening_balance.
- **`Kind` gains `transfer`.**
- **`Transaction`:**
  - Adds `wallet_id` (required) and `to_wallet_id` (set only for transfers).
  - Adds `recurring_id` (nullable), pointing to the rule that created it.
  - Drops `payment_method`.
  - A transfer has no category and no splits.
- **New `RecurringRule`:** id, user_id, wallet_id, to_wallet_id, kind, amount, merchant, category_id, notes, tags, frequency (`weekly` | `monthly` | `yearly`), next_date.
- **Wallet balance:** opening_balance + income − expenses − transfers out + transfers in. It is computed, not stored.

## Backend

### Wallets: `app/routers/wallets.py`
- Create/read/update/delete, following the same pattern as `app/routers/categories.py`.
- `GET /wallets` returns each wallet with its current balance.
- Deleting a wallet that still has transactions returns 409, with the message "Move or delete this wallet's transactions first."

### Transactions: `app/routers/transactions.py`
- `query_transactions` gains a `wallet` filter that matches `wallet_id` or `to_wallet_id`.
- Validation:
  - A transfer needs a `to_wallet_id` different from `wallet_id`.
  - A transfer can't have a category or splits.
- The `TransactionIn` schema gains a `repeat` field (`none` | `weekly` | `monthly` | `yearly`). If it's set, the same request also creates a `RecurringRule`, with `next_date` = date + one period.

### Analytics: `app/routers/analytics.py`
- Every endpoint takes an optional `wallet` parameter, passed through to `query_transactions`.
- Transfers are left out of income, expenses, categories, merchants and comparison. They already are in practice, because those use `kind == income/expense`; the change is to make sure cashflow does the same.
- `/analytics/balance` becomes:
  - opening balances plus the running total for "all wallets",
  - or the single wallet's balance when `wallet` is given, where transfers count as in or out.

### Recurring: `app/recurring.py` and `app/routers/recurring.py`
- **`post_due(db, user_id, today)`** creates a transaction for every rule whose `next_date <= today` and advances `next_date`, looping to catch up on missed periods.
  - It is called at the top of `query_transactions`. That one function feeds the transaction list, analytics and export, so due items always appear without a scheduler.
- **Rule management:** create/read/update/delete on `/recurring`. Deleting a rule keeps the transactions it already posted.
- **`GET /recurring/upcoming?days=14`** lists the charges due soon, as reminders.
- **`GET /recurring/suggestions`** detects likely subscriptions from history:
  - same wallet and same merchant (after normalizing the name),
  - 3 or more occurrences,
  - amounts within 10% of each other,
  - gaps between them of 25-35 days (monthly) or 6-8 days (weekly),
  - and no existing rule for that merchant.
  - It returns merchant, typical amount, frequency and the suggested next date.

### Smart categorization: `app/categorize.py`
- **`normalize(merchant)`:** lowercase, strip digits, punctuation and store numbers. For example, "UBER *TRIP 8821" becomes "uber trip".
- **`suggest_category(db, user_id, merchant)`:**
  - First choice: the category you last used for the same normalized merchant. Your latest manual choice wins, which is the "learning" part.
  - Fallback: a small built-in keyword map to category names, such as uber/lyft/shell → Transport, netflix/spotify → Subscriptions, and safeway/whole foods/trader → Groceries. It only matches categories you actually have.
- **`GET /categories/suggest?merchant=`** returns `{category_id, source: "history" | "keyword"}` or null.
- CSV import uses it too.

### CSV import: `app/routers/imports.py`
- **`POST /import/preview`** (file upload) returns:
  - the headers and the first 5 rows,
  - a guessed column mapping, from header names like date, description/payee/merchant, amount, debit/credit,
  - a guessed date format: the first of ISO, MM/DD/YYYY or DD/MM/YYYY that parses every row.
- **`POST /import`** (file, mapping, wallet_id, date format, expenses-are-negative flag):
  - parses each row,
  - skips duplicates, meaning the same wallet, date, amount and merchant already exists,
  - categorizes each row with `suggest_category`,
  - tags the rows `imported`,
  - returns `{imported, duplicates, errors: [row, message]}`.
- Amount parsing handles signs, currency symbols, thousands separators and both decimal styles. It is a new helper, because `ocr.parse_money` assumes exactly 2 decimals.

### Mock data: `app/seed.py`
- **Wallets:** Checking (bank, $2,500 opening), Credit card, Cash, Savings.
- **Assignment:** salary and rent go to Checking, most spending to Credit card, and some small purchases to Cash.
- **Monthly transfers:** $500 from Checking to Savings, and a credit card payment from Checking to Credit card.
- **Recurring rules:** Salary and Rent, which post automatically each month.
- **Subscriptions left for detection:** Netflix, Spotify and iCloud at fixed amounts on fixed days, with no rule. They show up as suggestions for the demo.

### Tests: `backend/tests/`
The existing tests are updated for wallets. New tests cover:
- wallet balances with transfers, and the 409 when deleting a wallet that has transactions,
- transfers left out of analytics,
- `post_due` catching up on missed periods,
- `repeat` on create,
- suggestions finding the seeded subscriptions,
- `normalize` and `suggest_category`, with history taking priority over keywords,
- CSV preview guesses and import: duplicates skipped, debit/credit columns, DD/MM dates, comma decimals.

## Frontend

### Add form: `components/TransactionModal.tsx`
- The toggle becomes Expense / Income / Transfer.
- "Paid with" becomes a wallet picker, and Transfer shows "From" and "To" wallets.
- A "Repeat" select (Never / Weekly / Monthly / Yearly) sits under the extra details.
- When the merchant field loses focus, or after a receipt scan, and you haven't picked a category yet, the form calls `/categories/suggest`. It fills in the category and shows a short hint, "Category from your past transactions".

### Wallets page: new `app/wallets/page.tsx`
- A list of wallets with their balances.
- Add/edit wallet: name, type, color and opening balance.
- Clicking a wallet opens the transactions list filtered to it.

### Recurring page: new `app/recurring/page.tsx`
- Your rules, each with the next date, amount, wallet and frequency, plus edit and delete.
- A "Suggested" section with a "Make recurring" button for each detected subscription.

### Dashboard: `app/page.tsx`
- A wallet picker (All wallets, or one wallet) next to the period picker; every analytics call passes it.
- A row of wallet balances under the headline number.
- An "Upcoming" panel listing the next 14 days of recurring charges.

### Transactions page: `app/transactions/page.tsx`
- A wallet filter.
- Transfers display as "Checking to Savings", in neutral ink with no sign.
- The Paid-with column shows the wallet instead.
- A new "Import CSV" button opens an import dialog (new `components/ImportDialog.tsx`):
  - pick a file and a wallet,
  - check the preview and the guessed mapping, adjusting the columns and date format if needed,
  - import, then see the result counts.

### Shared pieces
- `components/Shell.tsx`: the nav adds Wallets and Recurring.
- `lib/api.ts`: types added for Wallet, RecurringRule and the import preview.

## Data reset
During implementation, I'll remove the `tracepai-data` Docker volume once, so the new schema and mock data are created. The start/stop scripts don't change.

## Status (2026-09-24)

Phase 2 complete. 34 backend tests pass. The end-to-end browser flows for Phase 1 and Phase 2 pass in the container.

Deviations from the plan:
- Budgets stay across all wallets. The dashboard labels them "Across all wallets" when you pick one wallet.
- Choosing a date format during import uses the format that parses the most rows. When dates are ambiguous (01/09), MM/DD wins the tie and you can change it in the preview.

---

# TracepAI: Read receipts, invoices and bank statements with qwen3-vl (Ollama)

**Superseded on 2026-09-26:** the vision model was too slow on the Mac and tied deployments to a machine that can run it. Receipts are read with Tesseract again (see the last section), and bank statements come in as CSV only.

## Context
Today, receipt photos are read with Tesseract plus hand-written rules. That only finds one total, and bank statements can only come in as CSV. You want every document read by the local vision model `qwen3-vl:8b`, which you've downloaded with Ollama:
- a photo taken in the app,
- an uploaded receipt, ticket or invoice (image or PDF),
- an uploaded bank statement (PDF or image) with many transactions.

Tesseract is removed (your decision).

### What I measured on this Mac
- **Setup:** Ollama 0.34.4 has `qwen3-vl:8b` (8.8B parameters, vision support, thinking on by default).
- **Receipt** (generated image): correct merchant, date and total, in about 9 seconds once the model is loaded. The first call adds a 5-second model load.
- **12-row bank statement:**
  - All 11 transactions correct: dates, amounts, and money in vs out. The opening and closing balance rows were skipped.
  - It took about 92 seconds with `format:"json"` and `think:false`.
  - With the strict JSON schema it took 149 seconds, because the model pads its output with whitespace. So the plan uses plain JSON mode and validates the result in code.
- **Prompt wording matters.** Early prompts labeled a receipt as income. The model now returns `direction: money_out | money_in`, the prompt spells out the rules, and code converts that to expense or income.
- **Docker:** the container reaches Ollama on the Mac at `http://host.docker.internal:11434` (verified with `docker exec`).

## Backend

### `app/vision.py` (new): the Ollama client
- **Settings:** `TRACEPAI_OLLAMA_URL` (default `http://localhost:11434`; the Dockerfile sets `http://host.docker.internal:11434`) and `TRACEPAI_VISION_MODEL` (default `qwen3-vl:8b`).
- **`read_pages(images: list[bytes]) -> Extraction`:** one `/api/chat` call per page, using the standard library (`urllib`), so no new HTTP dependency.
  - Request options: `think:false`, `format:"json"`, `temperature:0`, `keep_alive:"10m"`, and a 600-second timeout per page.
  - Uses the prompt I tested above.
- **Validating the model's answer.** A Pydantic model checks each page:
  - `document_type` must be one of receipt, invoice, bank_statement or other.
  - Each transaction gets `kind` from `direction`, and `amount` becomes `abs(amount)`.
  - A date that isn't valid YYYY-MM-DD becomes null.
  - The merchant is trimmed and cut to 80 characters.
  - Rows with no amount or a zero amount are dropped.
  - Pages are combined in order. The document type comes from the first page, but becomes bank_statement if any page is one.
- **Errors, each turned into a message that says how to fix it:**
  - Ollama can't be reached → 503, "Can't reach Ollama at <url>. Open the Ollama app and try again."
  - The model isn't installed → 503, "Run `ollama pull qwen3-vl:8b`, then try again."
  - The model returns JSON that doesn't parse, twice in a row (one retry) → 502, "The document could not be read. Try a sharper photo."

### `app/documents.py` (new): files to page images
- **Images** (JPEG, PNG, HEIC is not supported, WebP):
  - apply the phone's rotation (`ImageOps.exif_transpose`),
  - convert to RGB,
  - shrink so the longest side is at most 1600px (keeps prompt time down),
  - encode as PNG.
- **PDFs:** render each page with `pypdfium2` (a new dependency; a pure wheel, no system packages) at about 144 dpi, up to 8 pages. More than 8 pages → 400, "Split statements longer than 8 pages."
- **Anything else** → 400, "Upload a photo, an image or a PDF."

### Receipt scan: `app/routers/receipts.py`
- `POST /receipts/scan` keeps its path and response fields (`merchant`, `date`, `amount`, `receipt_path`), and now also returns `kind`, `document_type` and `count`.
- It saves the upload as the attachment (PDFs included), reads it with `vision`, and returns the first transaction.
- If there are several (a statement), `count > 1` lets the form point you to Import.
- `raw_text` is dropped.
- `GET /receipts/{name}` is unchanged.

### Import: `app/routers/imports.py`
- **Shared saving.** The saving step of the CSV import (duplicate check by wallet, date, amount and merchant, the `suggest_category` call, the `imported` tag) moves into `save_rows(db, user, wallet_id, rows)`. The CSV import and the new document import both use it. The CSV behaviour and its tests stay the same.
- **`POST /import/document/preview`** (file) → `{document_type, transactions: [{date, merchant, amount, kind, category_id}]}`. The category is pre-filled with `suggest_category` (`app/categorize.py`).
- **`POST /import/document`** (JSON: `wallet_id`, plus the reviewed `transactions` list) → `save_rows` → `{imported, duplicates, errors}`. A row without a date is reported as an error for that row.

### Cleanup
- Delete `app/ocr.py` and `tests/test_ocr.py`.
- Remove `pytesseract` from `pyproject.toml`, and `tesseract-ocr` from the Dockerfile.
- Add `pypdfium2`.

### Scripts
- `start-linux.sh` gains `--add-host=host.docker.internal:host-gateway`. Docker Desktop provides that name on Mac and Windows but plain Linux Docker doesn't.
- The README notes that the container needs Ollama running with `qwen3-vl:8b`, and that on Linux Ollama must listen beyond localhost (`OLLAMA_HOST=0.0.0.0`).

## Frontend

### Add form: `components/TransactionModal.tsx`
- "Scan receipt" becomes two buttons:
  - **Take photo** (`accept="image/*" capture="environment"`), which opens the iPhone camera,
  - **Upload file** (`accept="image/*,application/pdf"`, no `capture`), which opens Files or Photos.
- **While reading:** "Reading with qwen3-vl, 12s", with a live seconds counter. Both buttons are disabled.
- **When done:**
  - It fills in amount, date, merchant and kind.
  - It runs the existing category suggestion.
  - It shows "Check the details before saving."
  - If `count > 1`, it also shows: "This looks like a bank statement with N transactions. Use Import on the Transactions page to add them all."
- Errors show the server's message.

### Import dialog: `components/ImportDialog.tsx`
- The file picker accepts CSV, PDF and images.
- **CSV:** the current flow, unchanged.
- **PDF or image:**
  - It calls `/import/document/preview` and shows "Reading N-page document with qwen3-vl, 45s" with the counter, plus a note that statements can take a minute or two per page.
  - Then a review table, one row per transaction: include checkbox, date, description, amount, In/Out, and a category select (pre-filled). Every cell can be edited.
  - "Import N transactions" sends the checked rows.
  - The result screen is the same as for CSV.

### Types: `lib/api.ts`
Adds `DocumentPreview`, `DocumentRow`, and the new receipt scan fields.

## Tests

### 1. Fast unit and API tests (always run, no model; `uv run pytest`)
`tests/test_vision.py` replaces `vision._chat` with a fake that returns canned JSON. It covers:
- **Checking the model's answer:** direction to kind, negative amounts made positive, bad dates becoming null, zero or missing amounts dropped, merchant trimming, an unknown document type becoming "other", and pages combined in order.
- **Retry and failure:** one retry on JSON that doesn't parse, then 502. Ollama unreachable gives 503 with the message; a missing model (404 from Ollama) gives 503 with the pull instruction.
- **Request contents:** `think:false`, `format:"json"`, temperature 0 and the model name, as seen by the fake.
- **`documents.py`:**
  - A rotated JPEG (set through its rotation metadata) comes out upright.
  - A 3000px image is shrunk to 1600px.
  - A 3-page PDF (built with Pillow) gives 3 images.
  - A 9-page PDF gives 400, and a text file gives 400.
- **Receipt scan:**
  - Returns the first transaction and saves the attachment; a PDF upload works.
  - A statement-shaped answer returns `count > 1`.
- **Document import:**
  - The preview pre-fills categories (UBER → Transport).
  - Import saves the rows tagged `imported`, a second import counts them all as duplicates, and a row without a date is an error.
  - The existing CSV import tests still pass through `save_rows`.

### 2. Real-model tests (opt-in: `uv run pytest -m model`)
These are skipped automatically when Ollama or the model isn't available. The test documents are generated in code, so they're reproducible and nothing binary is added to the repo:
- a clean receipt PNG,
- a "phone photo" receipt: rotated 4 degrees, gray background, JPEG compression, slight blur,
- a Spanish ticket with comma decimals (`TOTAL 23,45 EUR`, date `21/09/2026`),
- an invoice PDF with line items, subtotal, tax and total due, where the total is the expected amount,
- a 2-page bank statement PDF with 16 rows, including a deposit and opening/closing balance rows,
- an image that isn't a financial document.

The checks:
- exact amount and date for each receipt and invoice,
- the merchant contains the expected word,
- `document_type` is correct,
- the statement has exactly 16 transactions with the right amounts, money in vs out and dates, with the balance rows excluded,
- the non-financial image returns "other" or no transactions.

Each test prints its time, so slow runs are visible.

### 3. End-to-end in the container
Headless Chrome, using the puppeteer-core scripts in the scratchpad, against the real Ollama:
- **Add form, Upload file** with the phone-style receipt JPEG: the fields fill correctly, the category is suggested, and saving puts the attachment on the transaction.
- **Add form with a statement PDF:** shows the "use Import" hint.
- **Import dialog with the 2-page statement PDF:**
  - The review table shows 16 rows.
  - Edit one amount, untick one row, and import.
  - The counts match (15 imported).
  - The edited amount is saved.
  - Importing again counts every row as a duplicate.
- **Earlier flows** (the Phase 1 and Phase 2 scripts, and the recurring-item script) all still pass.
- **Ollama unreachable:** run a second container with `TRACEPAI_OLLAMA_URL` pointing at a closed port, and check that the form shows the "Open the Ollama app" message.
- **Screenshots** of the scan states and the review table, on desktop and at iPhone width, in light and dark mode.

### 4. On your iPhone (manual, after I report back)
Open `http://<mac-ip>:8001` on the same Wi-Fi. Use Take photo on a real receipt, and Import on a real statement PDF.

## Status (2026-09-24)

Done. 49 fast tests and 6 real-model tests pass (`uv run pytest`, `uv run pytest -m model -s`). The browser flows pass in a separate test container against the real Ollama:
- phone-style receipt read in about 10 seconds,
- 2-page, 16-row statement read in about 72 seconds, with every row exact,
- the Ollama-unreachable message shows correctly.

Changes from the plan:
- The review table is a responsive list rather than an HTML table: one line per row on desktop, two columns on phones.
- The Transactions button is now "Import", since it takes statements, receipts and CSV.
- Browser tests run in a separate container (port 8002, its own volume), never against the user's instance on 8001.

---

# TracepAI: Savings goals, locations and map, monthly summary, undo delete

## Context
These are the next features from the Spendee comparison. CSV import is already built, so this batch skips it (your decision). Decisions made:
- **Location:** search a place or address (looked up on OpenStreetMap), plus the GPS position inside a receipt photo when the phone includes it. "Use my location" only works on the Mac (localhost), because Safari blocks it on plain-http pages like `http://<mac-ip>:8001`. No HTTPS setup.
- **Goals:** each goal keeps its own contributions ("Add $200"), with a progress bar and the monthly amount needed to reach the date. Adding to a goal doesn't move money between wallets.

**Your real data is on port 8001, so the database is not reset this time.**
- New tables are created automatically on start-up.
- New columns on existing tables are added by a small start-up step. There's no reset and no manual migration.
- Before I deploy to 8001, I back up `/data/tracepai.db` to the scratchpad.
- All testing runs in a separate container (port 8002, its own volume), per the saved rule.

## Backend

### Adding new columns: `app/db.py`
- After `create_all`, `add_missing_columns()` compares each table's model with SQLite's `PRAGMA table_info`.
- For each column the database lacks, it runs `ALTER TABLE ... ADD COLUMN`. Every new column is nullable, so existing rows stay valid.
- It is generic, so future nullable columns need no new code.

### Savings goals
- **Tables (`app/models.py`):**
  - `Goal`: id, user_id, name, target_amount (> 0), target_date (optional), color_slot (1-8).
  - `GoalContribution`: id, goal_id, date, amount, note. The amount can be negative, which means taking money out of the goal.
- **API (`app/routers/goals.py`):**
  - `GET /goals` returns each goal with `saved`, `percent`, `remaining`, `months_left` and `monthly_needed`. `monthly_needed` is remaining divided by the whole months until target_date (at least 1); it's null when there's no date or the goal is reached.
  - Create, update and delete goals.
  - `GET /goals/{id}/contributions` lists the history.
  - `POST /goals/{id}/contributions` records an add or a take-out, and `DELETE /goals/contributions/{id}` removes one.
  - Deleting a goal deletes its contributions.

### Locations
- **New Transaction columns:** `place` (text), `lat` and `lng` (numbers). All three are optional and can be edited like any other field.
- **Place search (`app/routers/places.py`):**
  - `GET /places/search?q=` is passed on to OpenStreetMap's lookup service (Nominatim) and returns up to 5 results: `{name, address, lat, lng}`.
  - `GET /places/reverse?lat=&lng=` returns a place name for a position.
  - Requests go out from the backend with a `User-Agent: TracepAI` header, as Nominatim's usage policy requires. Searches happen only when you press Search, never while you type, to respect its one-request-per-second limit.
  - If the lookup service can't be reached, you get a clear 503 message; nothing else breaks.
- **Photo GPS (`app/documents.py`):**
  - `gps_from_image(content)` reads the photo's GPS data with Pillow, `getexif().get_ifd(0x8825)`, converting degrees/minutes/seconds and the N/S/E/W reference into a latitude and longitude.
  - `POST /receipts/scan` also returns `lat` and `lng` when the photo has them.
  - Many iPhone uploads strip GPS, so this is a bonus, not the main way to add a location.
- **Analytics:** `GET /analytics/places?start&end&wallet` returns the transactions that have a location, for the map.

### Monthly summary (`app/routers/analytics.py`)
`GET /analytics/summary?month=YYYY-MM&wallet=` returns, reusing `expense_by_category`, `month_bounds` and `query_transactions`:
- income, expenses, net, and the savings rate (net divided by income),
- spending vs the same number of days last month: amount and percent change,
- the top category (name, total, share),
- the biggest purchase (merchant, amount, date),
- the most visited merchant (name, count),
- budgets over their limit (names),
- whether the month is still in progress.

### Undo delete
No new endpoint. Undo sends the deleted transaction back through the existing `POST /transactions` (splits, receipt, location and tags included). It gets a new id; the only thing it doesn't keep is its link to a recurring rule.

### Mock data (`app/seed.py`; fresh installs and the test container only)
- Coordinates for the seeded San Francisco merchants.
- A "Lisbon trip" goal ($2,000 by next spring) with a few contributions.
- An "Emergency fund" goal with no date.

## Frontend

### Goals page: new `app/goals/page.tsx`, plus a Goals link in the nav
- **Goal cards:** name and color, then "$1,200 of $2,000", a progress bar in the goal's color, and "Save $200 a month to reach it by Mar 2027" (or "Reached"). Also Add money and Take out (amount plus an optional note), history, edit and delete.
- **New goal form:** name, target, optional date, color.
- **Dashboard:** a small "Goals" panel with each goal's progress bar and a link to the page.

### Location in the add form: `components/TransactionModal.tsx`
- **Place field,** under "Add notes, tags, splits or repeat":
  - a text box with a Search button; pick one of up to 5 results,
  - or "Use my location" (shown only where the browser allows it: `window.isSecureContext && navigator.geolocation`), which then looks up the place name,
  - or the photo GPS after a scan, labeled "Location from the photo",
  - with Remove to clear it.
- The chosen place shows as a pin icon, then the name.

### Map on Transactions: `app/transactions/page.tsx` and a new `components/SpendingMap.tsx`
- **List | Map switch.** The map uses Leaflet and `react-leaflet` with OpenStreetMap tiles. It's loaded only in the browser (`next/dynamic`, `ssr:false`), because Leaflet needs `window`.
- **Markers:** one circle per transaction that has a location, colored by category, with a hover or click popup showing merchant, amount, date and category. The map zooms to fit all markers, and the wallet and date filters also apply to the map.
- **Empty map:** "No transactions with a location in this period. Add a place when you add or edit a transaction."
- **In the list,** transactions with a place show a small pin and the place name under the merchant.

### Monthly summary on the dashboard: `app/page.tsx`
- A "September so far" panel (just "August" for a finished month), with previous and next month arrows. It shows:
  - Spent $3,004, 12% more than by this point last month.
  - Top category: Rent, $1,450 (48%).
  - Biggest purchase: IKEA, $210 on Aug 29.
  - Most visited: Blue Bottle, 6 times.
  - Over budget: Groceries, Dining.
  - Kept 31% of income.
- These are sentences, not charts. Colors mean something only with a label (green for less spending, red for more). The panel respects the dashboard's wallet picker.

### Undo instead of confirming a delete: `app/transactions/page.tsx`, plus a new `components/Toast.tsx`
- Delete removes the row at once and shows "Transaction deleted." with an Undo button, for 6 seconds, at the bottom center of the page, readable by screen readers.
- Undo sends the saved copy back and reloads the list. The two-step "Delete / Keep" confirmation goes away.
- A second delete while a toast is showing replaces it, and that one gets its own Undo.

## Tests

### Backend (`uv run pytest`)
- **Adding columns:** build a database with the old transaction table (no place, lat or lng) plus rows, run `init_db`, and check that the columns exist and the rows are unchanged.
- **Goals:**
  - create a goal, then add and take out money; saved and percent are correct,
  - `monthly_needed`: 3 months left and $600 remaining gives $200; a reached goal and a goal with no date give null,
  - deleting a goal removes its contributions,
  - validation: a zero target or a slot of 9 is rejected.
- **Places:**
  - The search and reverse endpoints are tested with a fake network call: the results are reshaped, the User-Agent header is sent, and an unreachable lookup service gives 503.
- **Photo GPS:**
  - A JPEG with a known position (a fixture built with Pillow) reads back to within 1e-5 degrees, and a photo without GPS gives None.
  - The scan endpoint returns lat and lng (with a fake model).
- **Transactions:** place, lat and lng are saved and edited; `analytics/places` returns only rows that have a location and follows the date and wallet filters.
- **Summary:**
  - For a controlled month in the test data: expenses and income match the transaction list, the top category and biggest purchase are right, the percent change matches, and the over-budget list matches `analytics/budgets`.
  - A month with no data returns zeros and nulls, not errors.
- **Undo:** re-posting a deleted split transaction recreates the same fields and splits.

### Browser, in the test container on 8002 (puppeteer scripts in the scratchpad)
- **Goals:** create "Laptop", $1,500 by a date 3 months out; add $300; the bar shows 20% and "Save $400 a month"; take out $100; delete a contribution; delete the goal. The dashboard panel matches.
- **Location:**
  - search "Ferry Building San Francisco" (one real Nominatim call), pick the first result, save; the list shows the pin and place,
  - edit the transaction and remove the place,
  - scan a receipt photo with GPS in its data (real qwen3-vl): "Location from the photo" appears.
- **Map:** switch to Map; the number of markers equals the transactions with a location in the period; clicking a marker shows its popup; changing the period changes the markers.
- **Summary:** the panel's numbers equal `/api/analytics/summary`; the previous-month arrow shows August.
- **Undo:** delete a split transaction and press Undo; the row and its splits come back. Delete another and let the toast expire; it stays deleted.
- **Earlier flows:** the earlier scripts (Phase 1 and 2, recurring, document import, receipt viewer) still pass.
- **Screenshots** on desktop and at iPhone width, in light and dark mode.

### Deploying to your app on 8001
1. Back up `tracepai.db`.
2. Rebuild and restart, keeping the volume.
3. Check that the transaction count is unchanged and the new columns exist.
4. Open the dashboard and make sure it loads.

## Status (2026-09-24)

Built and tested: 64 backend tests pass, and the browser flows pass in the test container on port 8002.

Changes from the plan:
- The map uses the transaction list the page already loads, so every list filter also applies to the map. The separate `/analytics/places` endpoint was dropped.
- Undo shows "Deleted <merchant>." with Undo, rather than "Transaction deleted."

---

# TracepAI: Goal money moves between wallets

## Context
Today, "Add money" on a goal only records a number. No wallet changes, so the same money counts both in a wallet balance and as "saved" in the goal, and the app can't tell where the goal's money actually is.

After this change, every goal is kept in one wallet (for example Savings).
- **Add money** picks a source wallet and records a real transfer from that wallet to the goal's wallet.
- **Take out** records a transfer from the goal's wallet back to a wallet you pick.
- **The goal's saved amount** is the sum of those transfers: money in minus money out.

Balances, the goal and the Transactions list always agree, because they all read the same transfers.

Your data on port 8001 (checked read-only on 2026-09-25): one goal ("My Monthly Intended Savings"), no contributions, and the wallets Wells Fargo Checking, BOFA Credit card and Galicia USD. There's no savings wallet yet, so you'd create one on the Wallets page, or keep the goal in any existing wallet. **No money is moved and no balance changes on deploy.**

## Decisions
- **A goal is a label on transfers, not a separate ledger.**
  - A goal contribution is an ordinary `Transaction` of kind `transfer` with a new `goal_id`.
  - The `GoalContribution` table goes away. Your database has no rows in it; the empty table is left in place and unused.
- **Direction:** a linked transfer *into* the goal's wallet adds to the goal, and one *out of* it takes away.
- **Locked wallet:** once a goal has transfers, its wallet can't be changed; changing it would flip the meaning of old transfers. Trying to change it returns a clear 422.
- **Existing goal:** it has no wallet yet. Its card says "Choose where this goal's money is kept" and opens the edit form; Add money is unavailable until a wallet is chosen.
- **Deleting a goal** keeps its transfers, because the money really moved. They just lose the goal label.
- **Removing a contribution** from the goal's history deletes that transfer, so the wallet balances go back.
- **Transactions page:** editing or deleting a linked transfer there updates the goal automatically. An edit that no longer touches the goal's wallet is rejected with a message naming the goal and wallet.

## Backend
- **`app/models.py`:**
  - `Goal` gains a nullable `wallet_id`.
  - `TransactionBase` gains a nullable `goal_id` (`foreign_key="goal.id"`).
  - `add_missing_columns()` adds both columns on start-up; no migration.
  - `GoalContribution` and `ContributionBase` are removed.
  - The new `ContributionIn` has date, amount (> 0), direction (`in` / `out`), `other_wallet_id` and note.
- **`app/routers/goals.py`:**
  - `progress()` sums linked transfers: + when `to_wallet_id == goal.wallet_id`, − when `wallet_id == goal.wallet_id`.
  - `POST /goals/{id}/contributions` creates the transfer. The merchant is the goal name, notes hold the note, and the wallets are `other -> goal wallet` for `in` and `goal wallet -> other` for `out`. It's rejected when the goal has no wallet or when the other wallet is the goal's wallet.
  - `GET /goals/{id}/contributions` lists the linked transfers as `{id, date, amount (signed), note, wallet_id}`, where `id` is the transaction id.
  - `DELETE /goals/contributions/{id}` deletes the transaction.
  - `PUT /goals/{id}` rejects a wallet change once transfers exist.
  - `DELETE /goals/{id}` sets `goal_id = null` on its transfers, then deletes the goal.
- **`app/routers/transactions.py`:** on create and update, if `goal_id` is set it must be the user's goal, the transaction must be a transfer, and one side must be the goal's wallet (422 otherwise).
- **`app/seed.py`** (fresh installs and the test container only):
  - The two goals are kept in Savings.
  - Their contributions become Checking -> Savings transfers.
  - The Savings opening balance is lowered by the same total, so the seeded balances stay the same.

## Frontend
- **`lib/api.ts`:**
  - `GoalInput` gains `wallet_id`.
  - `Contribution` changes to the shape above.
  - `TransactionInput` gains `goal_id`.
- **`app/goals/page.tsx`:**
  - The goal form gets a "Kept in" wallet select, required and preselecting the first savings wallet. It's disabled with a short note once the goal has transfers.
  - The card shows "Kept in Savings".
  - Add money adds a "From" wallet select (the goal's wallet excluded, defaulting to the first bank wallet), and Take out adds a "To" select.
  - History rows show the other wallet ("from Checking" / "to Checking").
  - The delete confirmation reads "Delete goal (its transfers stay in Transactions)".
  - Removing a history row says it also removes the transfer.
- **`components/TransactionModal.tsx`:** keeps the transaction's `goal_id` when editing, so saving a linked transfer doesn't unlink it.
- **`app/transactions/page.tsx`:** linked transfers show the goal name under the merchant ("Goal: Lisbon trip"). Undo already re-posts the whole transaction, `goal_id` included.

## Tests
- **Backend:** rewrite the goal tests in `test_goals_places_summary.py`:
  - Adding $300 from Checking raises Savings by $300, lowers Checking by $300, and makes the goal's saved $300.
  - Taking out $100 reverses it.
  - Removing a history row deletes the transfer and restores the balances.
  - Editing the transfer amount on `/transactions` changes the goal.
  - Deleting the transfer on `/transactions` removes it from the goal.
  - Deleting the goal keeps the transfers with `goal_id` null.
  - A wallet change with transfers present is rejected; without transfers it's allowed.
  - Validation: no goal wallet, the same wallet on both sides, a zero amount, `goal_id` on an expense, and a transfer that doesn't touch the goal's wallet are all rejected.
  - The seeded balances are unchanged from before.
  - `add_missing_columns` adds `goal.wallet_id` and `transaction.goal_id` to an old database.
- **Browser, in the test container on 8002:**
  - Create a goal kept in Savings, add $300 from Checking, and check the goal, the Wallets balances and the Transactions list.
  - Take out, remove a history row, and edit the transfer on Transactions.
  - Delete the goal.
  - Check the existing-goal prompt on a goal with no wallet.
  - Screenshots on desktop and at phone width, in light and dark mode.

## Deploying to your app on 8001
1. Back up `tracepai.db`.
2. Rebuild and restart, keeping the volume.
3. Check that the transaction count and all wallet balances are unchanged, and that the new columns exist.

## Status (2026-09-25)

Built and tested: 66 backend tests pass, the browser flows pass on port 8002, and the migration was checked on a copy of the real database. Not yet deployed to 8001.

Changes from the plan:
- Goals also return `transfer_count`, so the edit form knows when to lock the wallet.
- The seeded balances stay the same because the Checking and Savings opening balances were adjusted.

---

# TracepAI: currencies, net worth, budget pace, goal auto-transfers, price changes, budget styles, year in review, shared wallets

## Context
You picked 8 of the suggested features. Your decisions:
- **Currencies:** totals and charts in USD, and wallets in any currency.
- **ARS rate:** the official BNA rate.
- **Shared wallets:** a real sign-up page, so each person has their own login.
- **Delivery:** three batches, deployed one at a time.

Today every amount is treated as USD, so a pesos wallet would be added to the totals as if it were dollars. Batch 1 fixes that first, because the net worth chart and everything in batch 2 depend on correct totals.

**Carried over for every batch:**
- Log every change in `docs/CHANGES.md` and append each batch's plan to `docs/PLAN.md` with a status section, as before.
- Your real data on 8001 is never reset. New columns are added on start-up. Test in a separate container on 8002.
- Back up `tracepai.db` before each deploy. The last rebuild of 8001 was blocked by a permission check, so each deploy ends with the command for you to run (`! PORT=8001 ./scripts/start-mac.sh`) unless you allow it.

---

## Batch 1: Multi-currency wallets and net worth

### Exchange rates: new `backend/app/fx.py`
- **New table `FxRate`:** `currency`, `date` and `per_usd` (units of the currency per 1 USD). `currency` and `date` together are the primary key.
- **Sources** (all checked; free, no API key):
  - **ARS:** `api.argentinadatos.com/v1/cotizaciones/dolares/oficial`. It has the full daily BNA history since 2011; use `venta`.
  - **The ~30 ECB currencies** (EUR, BRL, GBP, MXN, JPY, ...): `api.frankfurter.dev/v1/{start}..?base=USD&symbols=X`. It has daily history.
  - **Any other currency** (CLP, UYU, COP, ...): `open.er-api.com/v6/latest/USD` has 166 currencies but only today's rate. History builds up from the day the wallet is created.
- **`refresh(db, currency)`:**
  - Fetches from the right source and stores the rates.
  - Runs at most once a day per currency, serialized with a lock, like `post_due` in `app/recurring.py`.
  - Uses a 5-second timeout. If the fetch fails, it logs the error and keeps using the stored rates.
- **`Rates`:** loaded once per request. `usd(amount, currency, date)` uses the nearest rate on or before that date (weekends and holidays have no rate); for dates before the first stored rate, it uses the earliest one. USD is passed through unchanged.
- **Endpoints:**
  - `GET /fx/convert?amount&from&to&date` gives the estimate used to pre-fill "Received" fields.
  - `GET /fx/currencies` lists the supported codes for the currency picker.

### Model changes: `backend/app/models.py`
- **`WalletBase.currency: str = "USD"`** (a 3-letter code).
  - `add_missing_columns()` in `app/db.py` is extended to add a column's scalar default (`DEFAULT 'USD'`), so your 3 existing wallets become USD. This is a small generic change.
  - Creating a wallet, or changing its currency, runs `refresh` first. It returns 422 if no rate can be found.
  - The currency is locked once the wallet has transactions (409), the same rule as a goal's wallet.
- **`Entry.to_amount: float | None`:** the amount received in the destination wallet's currency.
  - It's required for a transfer between two wallets in different currencies, and must be null otherwise.
  - It's checked in the transactions and recurring routers and in the goal contributions endpoint.
  - Being on `Entry`, recurring transfers carry it too, and `post_due` copies it automatically.

### Where the conversion applies
- **`app/wallets.py`:**
  - `wallet_deltas` stays in each wallet's own currency. The destination side uses `to_amount or amount`.
  - `WalletOut` gains `currency` and `balance_usd`, the balance at the latest rate.
- **`app/routers/analytics.py`:** every endpoint reports in USD.
  - A helper converts each transaction by its wallet's currency and its date, and scales splits by the same ratio.
  - This affects `categories`, `cashflow`, `budgets`, `merchants`, `comparison` and `summary`.
  - `balance`, the live budget line, sums each wallet's balance converted at each day's rate.
- **Budgets** are in USD.
- **Goals** are counted in the currency of the wallet they're kept in. Money coming in counts `to_amount` when it's set.
- **Export:** gains `currency` and `to_amount` columns.
- **Import:** amounts are taken in the chosen wallet's currency.
- **Receipt scans** fill the amount in the selected wallet's currency. The vision model doesn't detect currency, which is out of scope.

### Net worth (feature 6)
- **`GET /analytics/networth?months=24`:** a point at each month end plus today, each with `assets` (positive wallet balances), `debts` (negative ones, like cards) and `net`, all in USD at that date's rate. It also returns the current breakdown for each wallet.
- **Dashboard:** a new "Net worth" panel shows the net line and the assets and debts series, built like `BalanceChart` in `frontend/components/charts.tsx`, plus a short per-wallet list with native and USD amounts.

### Frontend
- **`frontend/lib/format.ts`:** `money(value, currency = "USD")`, with the Intl formatters cached per currency.
- **`app/wallets/page.tsx`:**
  - A currency picker (text input with the supported codes as suggestions), locked with a note once the wallet has transactions.
  - Each balance is shown in its own currency, with the USD equivalent under non-USD balances.
- **`components/TransactionModal.tsx`:**
  - The amount label shows the wallet's currency.
  - A transfer between different currencies shows a required "Received (ARS)" field, pre-filled from `/fx/convert`.
- **`components/RecurringForm.tsx`:** the same "Received" field for transfers.
- **Goals page:** the Add money / Take out form shows "Received" when the two wallets' currencies differ.
- **`app/transactions/page.tsx`:** amounts are shown in the wallet's currency.
- **`app/page.tsx`:** the "All wallets" total uses `balance_usd`; today it adds native balances together. Chart totals are labeled USD.

### Tests
- **Backend:**
  - `fx` with fake fetchers, following the pattern of the places tests: parsing each source, nearest-earlier lookup, once-a-day refresh, and a failed fetch keeping the stored rates.
  - An EUR wallet: an expense shows converted in `categories`, `summary` and `budgets`.
  - Cross-currency transfers: `to_amount` is required when currencies differ and rejected when they match; balances stay native; a recurring transfer posts `to_amount`.
  - `networth` totals.
  - The currency lock.
  - `add_missing_columns` fills `USD` on an old wallet table.
  - Rewriting the seed isn't needed: all its wallets are USD.
- **Browser (8002):**
  - Create a "Galicia ARS" wallet (a real rate call).
  - Add an ARS 15,000 expense; the dashboard category total equals 15000 / the stored rate.
  - Transfer USD to ARS with a Received amount; both balances are right.
  - The net worth panel.
  - Currency lock.
  - Phone width in dark mode.
- **Migration on a copy of your real database:** the transaction count and balances are unchanged, and all wallets are USD.

---

## Batch 2: Pace alerts, goal auto-transfers, price changes, budget styles, year in review

### Budget pace alerts (feature 2)
- **`/analytics/budgets`:** each row gains `projected` and `alert`.
  - `projected` = spent + upcoming recurring charges in that category before the month ends + (spending not from recurring items / days elapsed x days left).
  - Separating recurring charges keeps rent paid on day 1 from projecting 30x.
- **When it alerts:**
  - Only while the month is in progress and at least 5 days have passed.
  - "On pace to go over by $X" when the projection is over the limit.
  - "Over by $X" when the spending already is.
- **Where it shows:** a banner at the top of the dashboard (the top 3 alerts, linking to Budgets) and a note on each budget row.
- **In-app only:** real push notifications need HTTPS and a service worker, which this local setup doesn't have.

### Monthly goal transfers (feature 3)
- **`goal_id` moves from `TransactionBase` to `Entry`,** so recurring rules can carry it.
  - `post_due` copies it.
  - `check_linked` in `app/routers/goals.py` is also used when creating or editing recurring items.
- **`POST /goals/{id}/contributions`** accepts `repeat: "monthly"` (for adding money only). It records today's transfer and creates a rule for next month.
- **Goals page:**
  - A "Repeat monthly" checkbox on Add money.
  - The card shows "Adds $200 monthly from Checking" with a Stop button.
  - The "Save $X a month" hint gets a "Set up" button that opens Add money with that amount filled in and Repeat checked.
- **Recurring page:** shows "Goal: <name>".

### Subscription price changes (feature 5)
- **Detection, `price_changes()` in `app/recurring.py`:** for each expense rule, take the latest expense from the last 45 days in the same wallet with the same normalized merchant (`normalize` from `app/categorize.py`). Flag it if its amount differs from the rule's by more than 1% and more than $0.50.
- **New nullable column `RecurringRule.price_seen`:** "Keep $15.49" stores the amount you dismissed, so the alert doesn't come back.
- **Endpoint:** `GET /recurring/price-changes`.
- **Recurring page:** "Netflix charged $17.99; this item says $15.49", with "Update to $17.99" and "Keep $15.49".
- **Dashboard:** the same alerts appear in the alert banner.

### Budget styles (feature 4)
- **New columns:**
  - `User.budget_style`: `limits` (the default), `zero_based` or `50_30_20`.
  - `Category.group`: `need`, `want`, `savings` or null.
- **Endpoints:** `GET` and `PUT /settings` for the budget style.
- **Budgets page:** a style switch with three options:
  - **Limits:** today's view.
  - **Zero-based:** "This month's income $X, assigned $Y, left to assign $Z" (or "assigned $Z more than you earned"). Categories without a budget are listed with an Assign box. Unspent money doesn't roll over.
  - **50/30/20:** targets are 50%, 30% and 20% of the month's income. Actual needs and wants come from the category groups; savings = income - needs - wants. It shows three bars, a group picker for each category, and a warning listing categories without a group.
- **Seeded groups** (fresh installs only): Rent, Groceries, Utilities, Transport and Household are needs; Dining, Shopping and Subscriptions are wants.
- **Dashboard:** the "Budgets this month" panel follows the chosen style. Pace alerts apply wherever category limits exist.

### Year in review (feature 7)
- **`GET /analytics/year?year=YYYY`** (USD):
  - income, expenses, net and savings rate
  - income and expenses by month
  - the top 5 categories with their share
  - the 5 biggest purchases and the 5 most visited merchants
  - the busiest month
  - spending compared with the previous year
  - how much each goal gained during the year
  - net worth at the start and end of the year (from batch 1)
- **New page `app/review/page.tsx`:** a "Year" link in `Shell.tsx`, arrows to change year, `CashflowChart` with monthly buckets, `CategoryDonut`, `RankedBars`, and sentences in the style of `MonthSummary`.

### Tests
- **Backend:**
  - Pace projection: a fixed rent doesn't trigger an alert, a fast dining pace does, and nothing alerts before day 5.
  - A goal repeat rule posts a linked transfer next month.
  - Price change detection and "Keep".
  - Each budget style's numbers.
  - Year totals match the transaction list for a controlled year.
- **Browser (8002):** every new control, plus phone width and dark mode.

---

## Batch 3: Sign-up and shared wallets (feature 9); detailed plan before building

**Proposed shape:**
- **Sign-up page:**
  - A new `POST /auth/signup` (username, password of at least 8 characters). New accounts start with default categories and one Cash wallet, not mock data.
  - The login page links to it.
  - `CLAUDE.md` "Limitations" is updated, since logins are no longer hardcoded.
- **Sharing a wallet:**
  - A new `WalletMember` table (wallet, user). The wallet's owner shares it by username.
  - Every query that filters by `user_id` changes to "wallets I own or am a member of". This is the risky part; it touches every router and gets its own tests.
- **Shared wallet page:**
  - A ledger where each member adds expenses marked "paid by".
  - Each expense is split equally among the members.
  - A "who owes whom" balance, and Settle up, which records a settlement.
- **Personal analytics** count only your share of shared expenses.

**Open questions to settle before batch 3:**
- Categories are per user, so which categories do shared expenses use?
- When you pay a shared expense with your own card, should the app also record it in that card wallet?

---

## Critical files
- **Backend:**
  - `backend/app/models.py`, `db.py`, `wallets.py`, a new `fx.py`, `recurring.py`
  - `backend/app/routers/analytics.py`, `transactions.py`, `recurring.py`, `goals.py`, `wallets.py`, `export.py`, a new `fx.py`, a new `settings.py`
  - `main.py`, to register the new routers
- **Frontend:**
  - `frontend/lib/format.ts`, `lib/api.ts`
  - `app/page.tsx`, `wallets/page.tsx`, `transactions/page.tsx`, `budgets/page.tsx`, `goals/page.tsx`, `recurring/page.tsx`, a new `review/page.tsx`
  - `components/TransactionModal.tsx`, `RecurringForm.tsx`, `charts.tsx`, `Shell.tsx`

## Verification for each batch
1. `cd backend && uv run pytest -q`: all tests pass.
2. `npx tsc --noEmit` in `frontend`.
3. Build `tracepai:<batch>-test`, run it on 8002 with its own volume, and run the Puppeteer flows (scripts in the scratchpad, reusing the earlier install). Take screenshots on desktop in light mode and at phone width in dark mode.
4. Run the new image on a copy of the real database on 8003: the transaction count and wallet balances are unchanged, and the new columns exist.
5. Back up `tracepai.db`, deploy to 8001 (or hand you the command), check the dashboard loads, and log everything in `docs/CHANGES.md`.

## Status: batch 1 (2026-09-25)

Batch 1 (multi-currency wallets and net worth) is built and tested:
- 74 backend tests pass.
- 14 browser checks pass in the test container on 8002.
- The new version was run on a copy of the real database: its 6 transactions and every wallet balance are unchanged, and all its wallets became USD.

Changes from the plan:
- `/fx/convert` takes `source` and `to` (not `from`).
- Wallets also return `in_use`, which the Wallets page uses to lock the currency field.
- Goals return their `currency`, so goal amounts show in the goal wallet's currency.

Batches 2 and 3 have not started.

## Status: batch 2 (2026-09-25)

Batch 2 (pace alerts, monthly goal transfers, price changes, budget styles, year in review) is built and tested:
- 82 backend tests pass.
- 28 browser checks pass in the test container on 8002.
- The new version was run on a copy of the real database: its wallets, balances and 6 transactions are unchanged, and every new endpoint responds.

Changes from the plan:
- The category group column is `budget_group`, stored as an enum, because SQLModel can't store a `Literal`.
- `GET /goals` now adds due recurring transactions first, like the other list endpoints, so a monthly goal transfer counts as soon as it's due.
- The year review returns every category, not only the top 5, so the donut's shares are true.
- Deleting a goal also stops its monthly transfers.

Batch 3 (sign-up and shared wallets) has not started; its open questions are listed above.

## Batch 3 as built: sign-up and shared wallets (2026-09-25)

Decisions (my recommendations, which you accepted):
- **Categories:** a shared wallet uses its owner's categories. In another member's own charts, a shared expense counts under their category with the same name, or "Shared".
- **Paying with your own card:** the whole amount is recorded in the card wallet you paid from, so its balance stays right, and the expense is also added to the shared ledger.

Design:
- **A shared wallet is a ledger, not a place money sits.**
  - New tables: `SharedWallet` (owner, name, currency), `SharedMember` and `Settlement`.
  - A shared expense is an ordinary expense in the payer's own wallet, with `shared_wallet_id` set.
- **Who shares an expense is fixed when it's added** (`Transaction.shared_members`), so people who join later don't share earlier expenses.
- **Personal pages only ever read your own data.** Two exceptions:
  - The shared wallet page, for its members.
  - The spending view in analytics, which adds your share of what other members paid and cuts your own shared expenses to your share.
- **Balances and net worth still use whole amounts,** because the whole payment left the payer's wallet.
- **Settling up** records a `Settlement` in the ledger's currency. Each side can also record it in one of their own wallets; that transaction has `settlement_id` set, which moves the wallet's balance but is left out of spending and income.
- **Member rules:**
  - Only the owner adds or removes people.
  - A member can leave, but only once settled up.
  - A shared wallet can only be deleted while it has no expenses or payments.
- **Sign-up** (`POST /api/auth/signup`):
  - username of 3 to 32 letters, numbers, dots, dashes or underscores; password of at least 8 characters
  - new accounts get the default categories and a Cash wallet
  - the mock-data `user` account is unchanged

## Status: batch 3 (2026-09-25)

Built and tested:
- 85 backend tests pass.
- 26 two-person browser checks pass in the test container on 8002, and the batch 2 browser suite still passes.
- On a copy of the real database, the wallets, balances, transactions and monthly spending are unchanged, and sign-up works.

All three batches of the plan are now built.

---

# TracepAI: Receipts with Tesseract again

## Context
The Ollama vision model was slow on the Mac and would limit deployments. Decisions (2026-09-26): read receipts, tickets and invoices with Tesseract (English and Spanish); drop reading bank statements from photos or PDFs, so statements come in as CSV only.

## Status
Done. `app/ocr.py` OCRs each page from `documents.to_images` and applies the rules for merchant, date and total. `/receipts/scan` returns merchant, date, amount, the attachment and the photo location. `app/vision.py`, the document import endpoints and the Import review table are removed. The Docker image installs `tesseract-ocr` with the English and Spanish packs.

