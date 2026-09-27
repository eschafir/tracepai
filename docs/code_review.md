# TracepAI Code Review

Date: 2026-09-27
Scope: the whole repository at commit `31b49ba` (backend `backend/app`, frontend `frontend/`, Dockerfile, scripts, docs, tests).

## Summary

The codebase is small, readable and consistent. Routers are thin, helpers are well named, docstrings explain intent, and the 92 backend tests pass (`uv run pytest`, 2.5 s). The frontend type-checks cleanly (`npx tsc --noEmit`).

The main problems are in three areas:

1. **Authorization and input trust.** Several endpoints accept ids of other users' wallets and categories, any signed-in user can read any receipt, and an uploaded receipt can be served as HTML (stored XSS). The profile import writes file contents straight into table models without validation.
2. **Cloud deployment (the new Render/Supabase/Postgres path).** The mock account with a published password is created on any empty database, sessions never expire, and several behaviours differ between SQLite and Postgres because SQLite foreign keys are not enforced.
3. **Profile export/import (latest commit).** Merge duplicates data, settle-up payments become ordinary spending after a restore, and "replace" (the default) can fail or damage shared data.

Findings marked **Confirmed** were reproduced with a TestClient script against a temporary database. The others were found by reading the code.

## Findings

Severity: **High** means a security or data-loss issue to fix before deploying publicly. **Medium** is a real bug or a risk under normal use. **Low** is cleanup, performance or hygiene.

### High

#### H1. Stored XSS through receipt uploads (Confirmed)

- **Where:** `backend/app/routers/receipts.py:18` and `:42`
- **Problem:** the stored file's extension comes from the uploaded filename, and `FileResponse` picks the content type from that extension. A valid image (for example a GIF with HTML appended) uploaded as `x.html` passes `to_images`, gets saved as `<uuid>.html`, and is served as `text/html` from the app's own origin. Anyone who opens that link while signed in runs the attacker's script, which can call every API endpoint with the victim's cookie.
- **Evidence:** a GIF uploaded as `x.html` was served back with `content-type: text/html; charset=utf-8`.
- **Action:** take the suffix from the detected format (`.pdf` when `is_pdf`, otherwise `Image.open(...).format`), never from the filename. Serve receipts with an explicit `media_type` and the header `X-Content-Type-Options: nosniff`.

#### H2. Any signed-in user can read any receipt

- **Where:** `backend/app/routers/receipts.py:32-42`, `backend/app/storage.py`
- **Problem:** `GET /api/receipts/{name}` checks that someone is signed in, but not that the receipt belongs to them. Names are random UUIDs, so this is hard to exploit today, but receipts are personal documents and the check costs one query. The profile import also lets a user set `receipt_path` to any name.
- **Action:** store receipts as `<user_id>/<uuid>.<ext>`, and only serve a name with the caller's prefix. This also covers a freshly scanned receipt that isn't attached to a transaction yet.

#### H3. Missing ownership checks on referenced ids (Confirmed)

- **Where:**
  - `backend/app/routers/transactions.py:56` (`apply`): `wallet_id`, `to_wallet_id`, `category_id`, split `category_id`
  - `backend/app/routers/recurring.py:66,78`: `wallet_id`, `to_wallet_id`, `category_id`
  - `backend/app/routers/budgets.py:23,32`: `category_id`
  - `backend/app/routers/goals.py:78,87`: `wallet_id`
- **Problem:** only the goal link is checked (`check_linked`). A user can create transactions, rules and budgets that point at another user's wallet or category. Ids that don't exist are accepted too. On SQLite this leaves orphan rows. `check_received` then raises `AttributeError` (500) on a missing wallet, and `export` raises `KeyError` on a foreign wallet.
- **Evidence:** a second account created an expense on the mock user's Checking wallet (200) and a budget on the mock user's category (200).
- **Action:** add one helper, for example `owned(db, Model, id, user) -> Model` that raises 422, next to the existing `get_owned` functions. Call it for every referenced id in `apply`, `create_rule`/`update_rule`, `create_budget`/`update_budget` and `create_goal`/`update_goal`. The six copies of `get_owned` can be folded into the same helper.

#### H4. Profile import writes unvalidated data and can break an account (Confirmed)

- **Where:** `backend/app/routers/imports.py:143-345`
- **Problem:** the import builds `Wallet`, `Category`, `Transaction` and other table models directly from the JSON. SQLModel table models skip validation, so negative amounts, out-of-range `color_slot`, unknown `kind` values and malformed dates go straight into the database. Missing keys (`w["name"]`, `t["amount"]`) raise `KeyError` and return a 500 instead of a 400. Transfers are never checked with `check_transfer` or `check_received`.
- **Evidence:** importing one transaction with `"kind": "bogus"` succeeded. After that, every request that lists the account's transactions failed with `LookupError: 'bogus' is not among the defined enum values`, and the account could not be used.
- **Action:** validate each record with the input models that already exist (`WalletBase`, `CategoryBase`, `BudgetBase`, `GoalBase`, `RecurringBase`, `TransactionIn`) before remapping ids, and turn `ValidationError`/`KeyError` into one 400 that names the bad record. Run the same ownership and transfer checks as the normal endpoints.

#### H5. Mock account with a published password on cloud deployments

- **Where:** `backend/app/db.py:64-66`, `backend/app/seed.py:72`, `README.md`, `scripts/start-*.sh`
- **Problem:** `init_db` seeds `user` / `password` whenever the user table is empty, including on the new Postgres/Render path. On a public URL anyone can sign in to that account. It also receives shares: other users can add it to shared wallets and expenses.
- **Action:** seed only when explicitly enabled, for example `TRACEPAI_SEED_DEMO=1`, set by the local start scripts and not by the Render deploy. This keeps the local mock-data requirement in CLAUDE.md.

### Medium

#### M1. Profile import "merge" duplicates everything (Confirmed)

- **Where:** `backend/app/routers/imports.py:237-323`
- **Problem:** merge reuses wallets and categories by name, but always inserts new goals, recurring rules and transactions. Importing your own export once doubles the account.
- **Evidence:** merging the mock user's own export changed the transaction count from 240 to 480. Duplicated recurring rules will also post each charge twice from now on.
- **Action:** in merge mode, skip transactions that already exist, using the `(date, amount, merchant)` key that `save_rows` uses per wallet. Skip goals and rules with the same name/merchant and wallet. Otherwise, remove merge and keep replace only (simpler).

#### M2. Export/import turns settle-up and pay-back payments into spending

- **Where:** `backend/app/routers/export.py:106-126`, `backend/app/routers/imports.py:286-323`
- **Problem:** the profile export leaves out `settlement_id`, `share_payment_id`, `shared_wallet_id` and `shared_members`. After a restore, "Settle up with ..." and "Paid ... back" transactions become ordinary expenses and income. Analytics then counts them as spending (`analytics.spending` only excludes them by those ids), and shared expenses count at 100% instead of your share.
- **Action:** export these fields. On import, keep them only if the referenced settlement, payment or shared wallet still exists and involves the user. Otherwise, import the row with a tag (for example `settle-up`) and keep it out of spending the same way. At minimum, document the limitation in the import dialog.

#### M3. "Replace" import is the default and is unsafe with shared data

- **Where:** `backend/app/routers/imports.py:159-177`, `frontend/components/ProfileImportModal.tsx:15`
- **Problem:** replace deletes every transaction, wallet and category of the user without the cleanup that `delete_transaction` does:
  - `SharePayment` rows and the other person's recorded payment are left behind.
  - The user's expenses in shared wallets disappear, which silently changes the balances other members see.
  - Categories used by other members' expenses in a shared wallet the user owns are deleted.
  - On Postgres the deletes hit foreign keys (`sharepayment.transaction_id`, `settlement`), so the import fails with a 500.
  - The dialog preselects replace with no confirmation step.
- **Action:** default the dialog to merge (after M1), and ask for a typed confirmation before replace. In replace, delete through the same path as `delete_transaction`, or refuse replace while the user owns or belongs to a shared wallet.

#### M4. Lowercase currency breaks wallets and analytics (Confirmed)

- **Where:** `backend/app/routers/wallets.py:65-69`, `backend/app/routers/shared.py:100-104`
- **Problem:** the code compares `data.currency.upper()` with the stored currency, but only uppercases the value inside `check_currency`, which runs only when the currency changes. Saving a USD wallet with `"usd"` stores `usd`. `Rates.per_usd("usd")` then finds no rates and `values[max(i, 0)]` raises `IndexError`.
- **Evidence:** after `PUT /api/wallets/{id}` with `"currency": "usd"`, both `GET /api/wallets` and `GET /api/analytics/summary` returned 500.
- **Action:** uppercase in the model with a field validator on `WalletBase.currency` and `SharedWalletBase.currency`, and remove the manual `.upper()` calls.

#### M5. Deleting a wallet or category leaves dangling references

- **Where:** `backend/app/routers/wallets.py:39-41,76-82`, `backend/app/routers/categories.py:46-50`
- **Problem:**
  - `used()` only looks at transactions. A wallet that has recurring rules or goals but no transactions yet can be deleted. The rule then posts transactions into a wallet that no longer exists, and `analytics.converter` fails on `db.get(Wallet, ...).currency` (500 on the dashboard). `analytics.budgets` fails with a `KeyError` on `currency_of[rule.wallet_id]`.
  - Deleting a category leaves budgets, transactions, splits and rules pointing at it. On SQLite they become "Uncategorized". On Postgres the delete itself raises an `IntegrityError` (500).
- **Action:** make `used()` also check `RecurringRule` and `Goal`. For categories, either block the delete while in use (like wallets) or null out `category_id` and delete the budget in the same request.

#### M6. SQLite does not enforce foreign keys

- **Where:** `backend/app/db.py:25`
- **Problem:** there is no `PRAGMA foreign_keys=ON`, so every FK and the `ondelete="CASCADE"` on `Split` does nothing in SQLite. Postgres enforces them. The local app, the tests and the cloud deployment therefore behave differently (see M3 and M5), and the tests can't catch these bugs.
- **Action:** add a SQLAlchemy `connect` event listener that runs `PRAGMA foreign_keys=ON` for SQLite, then fix whatever the tests show.

#### M7. Sessions never expire and cookies aren't marked secure

- **Where:** `backend/app/auth.py:22-34,50-55`, `backend/app/models.py:55-58`
- **Problem:** the cookie lasts 30 days, but the token row is valid forever, and a bearer token (returned to mobile clients) never expires. Changing the password doesn't sign out other sessions. The cookie has no `secure` flag, which matters now that the app is deployed over HTTPS. Login has no attempt limit.
- **Action:** reject sessions older than 30 days in `current_user` (the `created_at` column already exists). Delete the user's other sessions on password change. Set `secure=True` when an env var such as `TRACEPAI_SECURE_COOKIES` is set. A simple per-username failure counter is enough to limit login attempts.

#### M8. Recurring posting is only safe in a single process

- **Where:** `backend/app/recurring.py:23-38`
- **Problem:** `post_due` runs on GET requests and uses a process-local `threading.Lock`. The comment says "the app runs as a single process", but the Postgres/Render deployment can run several workers or instances. Two of them can post the same due date twice.
- **Action:** add a unique constraint on `(recurring_id, date)` for `Transaction` and ignore conflicts, or lock the rule rows with `SELECT ... FOR UPDATE` on Postgres. The constraint is simpler and works on both databases.

#### M9. Exchange rates hang the app when offline

- **Where:** `backend/app/fx.py:67-87,104-111`, `backend/app/routers/fx.py:11-23`
- **Problem:**
  - `_checked` is only set after a successful fetch. When the network is down, every request tries again (5 s timeout per source) while holding the global `_lock`. The dashboard sends 14 requests in parallel (`frontend/app/page.tsx:70-83`), so they queue behind each other and the page hangs for a long time.
  - A currency with no stored rates makes `per_usd` raise `IndexError` (500).
  - `/api/fx/convert` accepts any string for `source` and `to`, and each unknown code causes a new outbound request.
  - `/api/fx/currencies` fetches the full list on every call.
- **Action:** record the attempt in `_checked` even when it fails, with a shorter retry (for example once an hour). Have `per_usd` raise a clear `ValueError` when there are no rates. Restrict `/fx/convert` to 3-letter uppercase codes. Cache `currencies()` for the day.

#### M10. No upload size limits

- **Where:** `backend/app/routers/receipts.py:16`, `backend/app/routers/imports.py:28,151`
- **Problem:** receipts, CSV statements and profile JSON are read into memory in full. A large upload can exhaust memory on a small Render instance. A failed scan also leaves the stored file behind, because it is saved before OCR runs.
- **Action:** reject files over a fixed size (for example 15 MB) using `UploadFile.size`. Save the receipt after OCR succeeds.

### Low

#### L1. Deleting a shared wallet deletes other members' transactions
`backend/app/routers/shared.py:112-126`. The owner's delete removes expenses that each member recorded in their own wallets. The docstring says this is intended, but members lose records of money that really left their wallets. Consider detaching them instead (`shared_wallet_id = None`, `shared_members = None`), the same way `delete_goal` detaches transfers.

#### L2. Legacy share format is missed by `shared_with`
`backend/app/shared.py:113`. The SQL filter looks for `"{uid}:"`, so expenses stored in the older `"1,4"` format never reach the other members. Either migrate old rows to the percent format once at startup, or drop the legacy branch in `shares()` if no such rows exist.

#### L3. Tag filter matches substrings
`backend/app/routers/transactions.py:43`. `tags.contains("vac")` matches `vacation`, and `"food"` matches `seafood`. Match whole comma-separated tags instead.

#### L4. Unbounded or unvalidated query parameters cause 500s or heavy work
- `analytics.cashflow` loops day by day over any `start`/`end` range: `start=0001-01-01` builds millions of entries.
- `month_bounds` raises `ValueError` (500) for a malformed `month`.
- `year_review` accepts any year.

Constrain `month` with a `YYYY-MM` pattern and cap the range.

#### L5. Repeated work in analytics and shared wallets
- `year_review` rebuilds `spending()` about six times, and each call runs `post_due` and a full query.
- `shared.summary` calls `expenses()` three times, and `list_shared` does this for every ledger.
- `ledger_detail` fetches the wallet and the recorders once per row (N+1 queries).

This is fine at current data sizes. Compute once and pass the lists down when it starts to matter.

#### L6. Export code is verbose
`backend/app/routers/export.py:42-144` spells out every field and uses `x.value if hasattr(x, "value") else str(x)`, which is unnecessary because the enums are `StrEnum`. `model_dump(mode="json", exclude={"user_id"})` per record would cut the function to about 20 lines and keep export in sync with the models automatically. That also fixes M2 as a side effect.

#### L7. Small inconsistencies
- `backend/app/storage.py:9-11` defines `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` and `RECEIPTS_BUCKET`, then never uses them and reads the environment again in every function.
- `receipts.py:36` and `db.py:44` import inside functions for no reason.
- `auth.update_profile` checks the password length by hand instead of reusing the `SignUp` constraint, `display_name` has no length limit, and `getattr(user, "display_name", "")` is unnecessary because the column always exists.
- `imports.py:3-5` has a stray blank line inside the import block.

#### L8. Frontend
- `frontend/lib/api.ts:96` drops the caller's `headers` whenever `json` is passed.
- Four `catch {}` blocks swallow errors silently (for example `Shell.tsx:67`). Show a toast instead.
- There is no lint script (ESLint isn't configured). `tsc` is clean.
- `components/TransactionModal.tsx` (651 lines) and the larger pages would be easier to change if split into smaller components. Do this only when they're next touched.

#### L9. Build and dependencies
- `Dockerfile` pins neither `ghcr.io/astral-sh/uv:latest` nor `node:lts-slim`, so builds can't be reproduced. Pin versions or digests.
- The container runs as root. Add a non-root user that owns `/data`.
- `pyproject.toml` lists `httpx2` as the dev dependency, but Starlette's `TestClient` imports `httpx`. Tests only work because `supabase` pulls in `httpx` indirectly (`uv tree --invert --package httpx`). Replace `httpx2` with `httpx`.
- The `supabase` SDK is a large dependency used for two storage calls. Consider calling the Storage REST API directly with `httpx`, or making it optional.

#### L10. Documentation drift
- `README.md` says `uv run pytest -m model -s`, but the marker is `ocr`.
- The README and CLAUDE.md describe a local SQLite-only app, while the code now supports Postgres, Supabase Storage and Render. The environment variables (`DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_RECEIPTS_BUCKET`, `PORT`, `TRACEPAI_GEOCODER_URL`) aren't documented.
- `.gitignore` ignores `CLAUDE.md` and `.claude/`, so the project instructions aren't versioned.

#### L11. Test gaps
The tests cover features well, but not these cases:
- **Cross-user access:** one user referencing another user's wallet, category or receipt (H2, H3).
- **Upload handling:** receipt content types (H1) and profile import validation (H4, M1).
- **Currency case:** lowercase currency codes (M4).
- **Deletes with references:** deleting a wallet or category that is still in use (M5).
- **Postgres:** only mocked. One run against a real Postgres (for example a CI service container) would have caught M3 and M5.

## Action plan

In priority order. Each item is small, and none needs new infrastructure.

| # | Action | Findings | Effort |
|---|--------|----------|--------|
| 1 | Derive receipt suffix from content, serve with explicit type and `nosniff`, store under a `user_id/` prefix and check it | H1, H2 | S |
| 2 | One `owned()` helper for every referenced id in transactions, recurring, budgets and goals; add cross-user tests | H3, L11 | S |
| 3 | Validate profile import records with the existing input models; 400 on bad files; tests with malformed files | H4 | M |
| 4 | Seed the mock account only when `TRACEPAI_SEED_DEMO=1` (set in local start scripts) | H5 | S |
| 5 | Uppercase currency in a model validator | M4 | S |
| 6 | Enable SQLite foreign keys; extend `used()` to rules and goals; block or detach category deletes | M5, M6 | S |
| 7 | Fix profile import: dedupe merge, keep settlement/share fields, safe replace with confirmation | M1, M2, M3, L6 | M |
| 8 | Session expiry, revoke other sessions on password change, secure cookie flag, simple login attempt limit | M7 | S |
| 9 | Unique `(recurring_id, date)` constraint for posted transactions | M8 | S |
| 10 | Cache failed FX fetches, clear error for missing rates, validate currency codes, cache the currency list | M9 | S |
| 11 | Upload size limits; save receipt after OCR | M10 | S |
| 12 | Replace `httpx2` with `httpx`; pin Docker base images; non-root container | L9 | S |
| 13 | Update README (test marker, cloud env vars) and version CLAUDE.md | L10 | S |
| 14 | Remaining low items as the code is touched | L1-L8 | S each |

Effort: S is under an hour, M is a few hours.
