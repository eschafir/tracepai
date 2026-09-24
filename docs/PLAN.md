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
