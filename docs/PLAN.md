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
