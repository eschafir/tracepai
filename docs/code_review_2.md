# TracepAI Code Review

Date: 2026-09-27
Scope: the whole repository as it is in the working tree (commit `3b25d1a` plus the uncommitted fixes from earlier reviews): `backend/app`, `frontend/`, Dockerfile, scripts, docs and tests.

## Summary

The code is in good shape. Routers are thin, helpers are small and well named, and docstrings explain intent. Ownership checks (`check_owned`), receipt handling, profile import validation, session expiry and SQLite foreign keys are now in place. All 110 backend tests pass (`uv run pytest`, 4.2 s), and the frontend type-checks cleanly (`npx tsc --noEmit`).

What remains falls into three groups:

1. **Consent in sharing (new, high).** Any signed-in user can add any other user to a shared expense or a shared wallet. The other person never has to accept, and the amounts count in their spending, budgets and alerts.
2. **Input limits (medium).** Several inputs are accepted without bounds. A recurring item dated in 1990 posts about 1,900 transactions at once, and a few malformed parameters return 500 instead of 4xx.
3. **Hygiene carried over from earlier reviews (low).** Build pinning, a root container, the wrong test dependency (`httpx2`), README drift, verbose export code and repeated work in analytics.

The fixes from the earlier reviews are not committed yet: 33 files are modified and `backend/tests/test_access_and_integrity.py` is untracked. Commit them before starting on this list.

Findings marked **Confirmed** were reproduced with a TestClient script against a temporary database. The others were found by reading the code.

## Status

The high and medium findings (H1, M1-M4) were fixed on 2026-09-28. `backend/tests/test_consent_and_limits.py` covers them, and 115 backend tests pass. The low findings (L1-L9) are still open.

How they were resolved, where it differs from the suggested action:

- **H1:**
  - Shared wallets: people added to a shared wallet are invited, and become members only when they accept.
  - Direct shares: each person accepts or declines once per sender, not per expense.
  - Existing members stay members. Existing direct shares wait for the other person to accept once.
- **M2:** each username now also allows at most 50 failed logins per 15 minutes from all clients together. That keeps the limit even if a client fakes its address. The README no longer suggests `FORWARDED_ALLOW_IPS=*`.
- **M3:** a former member can edit the merchant, category, notes, tags and place of their expense, but not its amount, date, wallet or shared wallet. They can't delete it either, because the remaining members' balances still count it.
- **M4:** settle-up and pay-back transactions are deleted after a confirmation, without Undo.

## Findings

Severity: **High** means a security or data-integrity issue to fix before any public deployment. **Medium** is a real bug or a risk under normal use. **Low** is cleanup, performance or hygiene.

### High

#### H1. Anyone can put expenses into another user's account (Confirmed)

- **Where:**
  - `backend/app/routers/transactions.py:78-85`: a direct share accepts any existing user id.
  - `backend/app/routers/shared.py:66-76` and `:166-176`: the owner of a shared wallet can add any username as a member.
  - `backend/app/routers/analytics.py:48-52`: `spending()` includes the user's share of other people's expenses.
- **Problem:** sharing needs no consent from the other person. A stranger can:
  - create an expense and give another user a 99% share;
  - or add them to a shared wallet and record expenses split with them.

  The victim's dashboard, budgets, pace alerts, year review and Shared page then show that spending. User ids are sequential, and `/api/auth/users/{username}` confirms which usernames exist, so every account can be targeted. This is harmless on a single-user local install. On the public Render deployment, it lets anyone falsify another user's numbers and fill their Shared page with spam.
- **Evidence:** user `stranger` created a 10,000 USD expense shared 1% / 99% with user `victim`. The victim's `/api/analytics/summary` went from 0 to 9,900 USD in expenses, and the expense appeared on their Shared page.
- **Action:** add an `accepted` flag to `SharedMember`, and a per-person accepted state to direct shares. Count a share, or show a ledger, only after the person accepts it. Show pending invitations on the Shared page with Accept and Decline buttons. A simpler interim option: only allow sharing with people who already share a wallet with you, or with people you've added as contacts who confirmed.

### Medium

#### M1. Recurring items accept any start date and can post thousands of transactions (Confirmed)

- **Where:** `backend/app/models.py:229-236` (`RecurringBase.next_date`), `backend/app/recurring.py:29-40`
- **Problem:** `next_date` has no lower bound. On the next GET, `post_due` fills in every missed occurrence in a single request. A typo in the year, or an API call, creates a large number of real transactions. The same applies to `PUT /api/recurring/{id}` and to rules in an imported profile.
- **Evidence:** a weekly rule with `next_date` 1990-01-01 posted 1,917 transactions on the next request.
- **Action:** reject a `next_date` more than one year before today in `RecurringBase`, with a clear message. The frontend's date field can use the same `min`.

#### M2. The login attempt limit can be bypassed behind a proxy

- **Where:** `backend/app/auth.py:91`, `README.md` ("set `FORWARDED_ALLOW_IPS=*`")
- **Problem:** with `FORWARDED_ALLOW_IPS=*`, uvicorn trusts every hop. It then takes the client address from the leftmost `X-Forwarded-For` entry (`uvicorn/middleware/proxy_headers.py:176-177`, version 0.53.0), and the client sets that value. An attacker can send a different `X-Forwarded-For` on each attempt, so every guess is counted for a new "client" and the 5-attempt limit never triggers.
- **Action:** set `FORWARDED_ALLOW_IPS` to the proxy's address range instead of `*`. If Render doesn't publish one, use the rightmost `X-Forwarded-For` entry for the lockout key, since Render appends the real client address. Update the README line to match.

#### M3. A member who left a shared wallet can't edit their old expenses (Confirmed)

- **Where:** `backend/app/routers/transactions.py:60`
- **Problem:** `apply` calls `get_member_ledger` for the transaction's `shared_wallet_id`. After the user leaves the shared wallet, that call returns 404, so every edit of their own past expense fails with "Shared wallet not found". The expense stays in their wallet and in their balance, but they can't change its date, amount or notes. Only deleting it works.
- **Evidence:** after settling up and leaving, `PUT /api/transactions/{id}` on the member's own expense returned 404.
- **Action:** when the transaction already belongs to a ledger the user has left, and `shared_wallet_id` doesn't change, skip the membership check and keep the saved split. Alternatively, when someone leaves, detach their expenses (`shared_wallet_id = None`, `shared_members = None`), since their balance is already zero.

#### M4. Undo after a delete turns payments into spending (carried over, still open)

- **Where:** `frontend/app/transactions/page.tsx:100-106`
- **Problem:** Undo re-creates the deleted transaction with `POST /api/transactions`. `TransactionIn` has no `settlement_id` or `share_payment_id`, so a restored "Settle up with ..." or "Paid ... back" transaction becomes an ordinary expense or income, and analytics counts it as spending. The pay-back records that the delete removed (`delete_payment`) don't come back, and the recurring link is lost too.
- **Action:** don't offer Undo for transactions with `settlement_id` or `share_payment_id`, and ask for confirmation instead. For other transactions the current undo is fine.

### Low

#### L1. Malformed input returns 500 (Confirmed)
- `POST /api/import` with a `mapping` that isn't JSON (`imports.py:90`), or an unknown `date_format` (`importer.py:37`, `KeyError`).
- `/api/analytics/year?year=1`, `/api/analytics/summary?month=bad` (`analytics.py:97-99`), `/api/recurring/upcoming?days=99999999` (`routers/recurring.py:29-38`), and a `cashflow` range that runs past year 9999.

Use `Literal[...]` for `date_format`, validate `mapping` with `Mapping.model_validate_json` and turn failures into a 400. Add `Query(pattern=r"^\d{4}-\d{2}$")` for `month`, `Query(ge=2000, le=2100)` for `year`, `Query(ge=1, le=366)` for `days`, and cap `cashflow` ranges at a few years.

#### L2. Receipt files are never deleted
`backend/app/storage.py` has no delete function. Files stay behind after a transaction is deleted, after its receipt is replaced, after a profile "replace" (`imports.py:207-212`), and after a scan the user cancels. They are only reachable by their owner, but they accumulate forever, locally and in Supabase Storage. Add `storage.delete_receipt(name)` and call it when a transaction is deleted or its `receipt_path` changes. Leftover scans can be cleaned up at startup: files older than a day that no transaction references.

#### L3. Categories and budgets are not checked for consistency (Confirmed)
- An income transaction can use an expense category (`transactions.py:63` only checks the owner). The category then appears in expense breakdowns with income amounts mixed in.
- Several budgets can exist for one category (`budgets.py:22-29`). Budget views list the category twice, and `budget_plan` counts both limits in "assigned".

Check `category.kind` against the transaction kind in `apply` and `check_rule`. Return 409 when a budget for that category already exists, or add a unique constraint on `(user_id, category_id)`.

#### L4. "Repeat" on a new transaction drops the goal and the sharing (Confirmed)
`transactions.py:126-131` copies a fixed list of fields into the new recurring item. `goal_id` isn't in the list, and neither are `shared_wallet_id` and the shares, so later occurrences are no longer goal transfers or shared expenses. The UI doesn't offer this combination today, but the API does. Add `goal_id` to the list, and reject `repeat` together with sharing until recurring shared expenses are supported.

#### L5. Settle-up and pay-back transactions can be edited freely
`PUT /api/transactions/{id}` changes the amount and date of a transaction that has a `settlement_id` or `share_payment_id`. Its `Settlement` or `SharePayment` stays as it was, so the wallet balance and the ledger no longer agree. Return 409 for these transactions, with a message saying to change the payment on the Shared page instead.

#### L6. Profile import trusts ids from another database
`imports.py:215-233` keeps a `shared_wallet_id`, `settlement_id` or `share_payment_id` from the file if a row with that id exists in this database and involves the user. For a file exported from another instance, the id can point to an unrelated ledger or payment that happens to involve the user. Keep these links only when the file was exported from this instance, for example by writing an instance id into the export and checking it on import. Otherwise import these rows as plain transactions tagged `settle-up`.

#### L7. Dashboard failures leave a blank page
`frontend/app/page.tsx:66-93` loads 14 endpoints with `Promise.all` and has no `catch`. If one of them fails (for example a 503 from the exchange rates), nothing renders and no error is shown. A slow response from an earlier filter can also overwrite a newer one. Catch the error and show a toast. Ignore results from a `load` call that a newer one has replaced, using a counter or an `AbortController`.

#### L8. Earlier low findings still open
- **Shared wallet delete** (`shared.py:110-127`): deleting a shared wallet deletes other members' expenses from their own wallets. Detach them instead.
- **Legacy share format** (`app/shared.py:117`): `shared_with` misses rows in the old `"1,4"` format. Migrate them once, or drop the legacy branch.
- **Tag filter** (`transactions.py:44`): tags match substrings, so `food` matches `seafood`.
- **Repeated work in analytics:**
  - `summary` builds `spending()` three times, plus a fourth time through `budgets()`, and `year_review` about six times. Each build runs `post_due` and a full query.
  - `shared.summary` calls `expenses()` twice.
  - `ledger_detail`, `in_ledger_currency` and `shared_expenses.item` fetch wallets one row at a time.
  - `save_rows` calls `suggest_category` for each imported row, and each call scans the user's whole history.

  None of this matters at current data sizes. Compute once and pass the results down when it does.
- **Export code** (`export.py:42-148`): spells out every field and uses `hasattr(x, "value")` on `StrEnum` values. `model_dump(mode="json", exclude={"user_id"})` would cut it to a few lines and keep it in sync with the models.
- **CSV formula injection** (`export.py:19-39`): merchants and notes that start with `=`, `+`, `-` or `@` (possible from bank CSVs and OCR) run as formulas in Excel. Prefix such cells with `'`.
- **Case-sensitive usernames** (`auth.py:110`): `User` and `user` can both sign up. Store and look up usernames in lowercase.
- **Small inconsistencies:**
  - `storage.py:9-11` defines constants it never uses, and reads the environment again in every function.
  - `db.py:38-67` has two near-identical branches. SQLAlchemy's `inspect()` works for SQLite too, so one branch is enough.
  - Imports inside functions without a reason: `db.py:54`, `fx.py:17-24`, `fx.py:98`.
  - `auth.update_profile` checks the password length by hand instead of reusing the `SignUp` constraint. `display_name` has no length limit.
  - `getattr(user, "display_name", "")` is used where `user.display_name` would do.
- **Exchange-rate lock** (`fx.py:89-109`): one global lock is held during the network fetch, so a slow source for one currency blocks every request that needs any rate. A lock per currency is enough.
- **Import error handler** (`imports.py:172-184`): `record()` turns `AttributeError` and `TypeError` into a 400 that names the record. That hides programming errors as bad input. Catch only `ValidationError`, `KeyError`, `ValueError` and `HTTPException`.
- **Sessions table** (`auth.py:41-52`): expired sessions are deleted only when they are used again. Delete expired rows at login.
- **Frontend:**
  - `lib/api.ts:98` drops the caller's `headers` whenever `json` is passed.
  - `Shell.tsx:67` and three other `catch {}` blocks swallow errors silently.
  - There is no ESLint script.
  - `TransactionModal.tsx` (651 lines) would be easier to change if split into smaller components.

#### L9. Build, dependencies and docs (carried over)
- `Dockerfile:1,9` uses the unpinned tags `node:lts-slim` and `ghcr.io/astral-sh/uv:latest`, so builds can't be reproduced. The container also runs as root.
- `pyproject.toml:21` lists `httpx2`. Starlette's `TestClient` needs `httpx`, which is only installed because `supabase` depends on it.
- `supabase` is a large SDK used for two storage calls. The Storage REST API through `httpx` would be enough.
- `README.md:29` says `pytest -m model`, but the marker is `ocr`. The Postgres and Supabase environment variables (`DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_RECEIPTS_BUCKET`, `TRACEPAI_GEOCODER_URL`) aren't documented.
- `.gitignore:45-47` ignores `CLAUDE.md` and `.claude/`, so the project instructions aren't versioned.
- **Tests:**
  - Postgres is only mocked (`test_cloud_db.py`). One CI run against a real Postgres service would cover the foreign-key and locking paths.
  - There are no tests for the H1, M1 and M3 behaviour above.

## Action plan

In priority order. S is under an hour, M is a few hours.

| # | Action | Findings | Effort |
|---|--------|----------|--------|
| 1 | Commit the uncommitted fixes and `test_access_and_integrity.py` | - | S |
| 2 | Require the other person to accept shared wallets and direct shares before they count; tests for pending and declined shares | H1 | M |
| 3 | Lower bound on recurring `next_date` (one year back), in the model and the date field | M1 | S |
| 4 | Stop trusting a client-set `X-Forwarded-For` for the login limit; fix the README line | M2 | S |
| 5 | Let former members edit their own ledger expenses, or detach them on leave | M3 | S |
| 6 | No Undo, and no edit, for settle-up and pay-back transactions | M4, L5 | S |
| 7 | Bound and validate query and form parameters so they return 4xx | L1 | S |
| 8 | Check category kind; one budget per category; carry `goal_id` into repeats | L3, L4 | S |
| 9 | Delete receipt files with their transaction; clean up unattached scans | L2 | S |
| 10 | Dashboard error handling and stale-response guard | L7 | S |
| 11 | Pin Docker images, non-root user, `httpx` instead of `httpx2`, README fixes, version `CLAUDE.md` | L9 | S |
| 12 | Remaining low items as the code is touched | L6, L8 | S each |
