# TracepAI Code Review

Date: 2026-09-28
Scope: the whole repository as it is in the working tree (commit `3b25d1a` plus the uncommitted fixes from the second review in `docs/code_review_2.md`): `backend/app`, `frontend/`, Dockerfile, scripts, docs and tests.

## Summary

The code is in good shape. Routers are thin, helpers are small and well named, and docstrings explain intent. The fixes from the last review work: sharing now needs consent, repeating items can't start long ago, and a member who left a shared wallet can edit their old expenses. All 115 backend tests pass (`uv run pytest`, 6.3 s), and the frontend type-checks cleanly (`npx tsc --noEmit`).

What remains falls into three groups:

1. **Shared money that counts in the wrong place (medium).** Categories from a shared wallet's owner leak into a member's own records, declined or pending shares disappear from everyone's spending, and leaving a shared wallet erases your share of its past expenses.
2. **The new login limit (medium).** The per-username limit added in the last round lets anyone lock any account out.
3. **Earlier low findings (low).** Most are still open: 500s on malformed input, receipt files that are never deleted, category and budget consistency, build pinning and hygiene.

About 45 files are modified or new and not committed yet, including `backend/tests/test_access_and_integrity.py`, `backend/tests/test_consent_and_limits.py` and `frontend/components/ShareRequests.tsx`. Commit them before starting on this list.

Findings marked **Confirmed** were reproduced with a TestClient script against a temporary database. The others were found by reading the code.

## Findings

Severity: **High** means a security or data-loss issue to fix before any public deployment. **Medium** is a real bug or a risk under normal use. **Low** is cleanup, performance or hygiene. No high findings are open.

### Medium

#### M1. A shared wallet's categories leak into a member's own records (Confirmed)

- **Where:**
  - `backend/app/categorize.py:29-36`: `suggest_category` looks through all of the user's transactions, including the expenses they added to someone else's shared wallet. Those use the owner's categories.
  - `backend/app/routers/imports.py:144-157`: `save_rows` saves the suggested category without checking who owns it.
  - `frontend/components/TransactionModal.tsx:165-171`: the form pre-fills the suggested category.
- **Problem:** after a member adds "Corner Deli" to a shared wallet, the suggestion for "Corner Deli" is the owner's Groceries category. This causes three problems:
  - A CSV import saves the member's own transaction with the owner's category. It shows as "Uncategorized" in the member's charts and budgets.
  - That transaction can't be edited: every save returns 422 "Category not found".
  - The member's profile export can no longer be imported: "it refers to a category that isn't in the file".

  In the add form, the suggestion picks a category that isn't in the member's list, and saving fails.
- **Evidence:** the suggestion returned category 4 (the owner's Groceries) instead of 14 (the member's). The CSV row was imported with category 4. The edit returned 422, and re-importing the member's own profile export returned 400.
- **Action:**
  - In `suggest_category`, only learn from transactions with `shared_wallet_id` set to `None`.
  - In `save_rows`, check that the category belongs to the user.
  - Clear the category on existing rows where it doesn't belong to the user and the row isn't in a shared wallet. This can be a one-off step in `init_db`.

#### M2. The per-username login limit lets anyone lock an account out (Confirmed)

- **Where:** `backend/app/auth.py:26-28` and `:94-98`
- **Problem:** after 50 failed logins for a username from any clients, `login` returns 429 before it checks the password. The real owner is then locked out too, even with the correct password and from a new address. Anyone can keep this up with 50 requests every 15 minutes. Signup is open and `/api/auth/users/{username}` confirms which usernames exist, so every account on the public deployment can be targeted. This undoes the goal stated on line 26: "so no one can lock the owner out with a few wrong guesses".
- **Evidence:** after 5 failures from one client and 50 from 50 other addresses, a login with the correct password from a new address returned 429.
- **Action:** the limit was added because a client can fake its address when `FORWARDED_ALLOW_IPS=*`. Fix that instead:
  - Set `FORWARDED_ALLOW_IPS` to the proxy's range. If Render doesn't publish one, key the per-client counter on the rightmost `X-Forwarded-For` entry, which Render appends.
  - Then remove the per-username lockout. If a global guard is still wanted, slow down failed attempts (for example, a one-second delay after the 50th) instead of blocking the username.

#### M3. Pending and declined direct shares disappear from everyone's spending (Confirmed)

- **Where:** `backend/app/routers/analytics.py:66-80` (`spending`)
- **Problem:** the payer's own shared expense counts only their percent. The other person's percent counts only once they accept. Until then, and forever after a decline, that part of the money counts for no one. The payer's wallet still drops by the whole amount, so their spending, budgets and savings rate are too low.
- **Evidence:** a 100 USD dinner shared 50/50 with someone who declined added 50 USD to the payer's spending and nothing to the other person's.
- **Action:** in `spending`, add the percent of everyone who hasn't accepted to the payer's share. `status()` in `routers/shared_expenses.py` already works out who has accepted. The Shared page can then say "counts as yours until they accept".

#### M4. Leaving a shared wallet erases your share of its past expenses (Confirmed)

- **Where:** `backend/app/routers/analytics.py:48-52`
- **Problem:** `spending` includes other people's expenses only from the shared wallets the user is in now (`my_ledgers`). After someone settles up and leaves, their share of expenses others paid disappears from past months. Their charts, budgets and year review change after the fact. Their own expenses in that shared wallet still count, so the history becomes inconsistent.
- **Evidence:** a member's September spending was 50 USD (half of a 100 USD hotel). After they settled up and left, it was 0.
- **Action:** select shared-wallet expenses by whether the user has a share in `shared_members`, not by current membership. They accepted the invitation when they joined, so no new consent is needed.

#### M5. A decline can't be undone

- **Where:** `backend/app/shared.py:134-136` and `frontend/components/ShareRequests.tsx`
- **Problem:** after someone clicks Decline for a person, that person's shared expenses are hidden for good. `/api/shared/requests` lists only people who haven't been answered yet, and no page lists declined people. `POST /api/shared-expenses/people/{id}/accept` would fix it, but nothing in the UI calls it. It also works the other way: once you accept someone, there's no way to stop counting what they share. A single mis-click on Decline or Accept is permanent.
- **Evidence:** after a decline, `/api/shared/requests` returned `{"wallets": [], "people": []}`.
- **Action:** add a short "People" list to the Shared page. It lists everyone you have answered (from `ShareConsent`), with Accept or Stop counting next to each. The endpoints already exist.

### Low

#### L1. Old backups with a recurring item can't be restored (Confirmed)

- **Where:** `backend/app/routers/imports.py:256` and `:329-340`, `backend/app/models.py:127-130`
- **Problem:** the M1 fix from the last review (`check_start`) applies to imported profiles. A profile exported more than a year ago usually has a recurring item whose next date is now over a year old, so the whole import fails. The error also reads badly: `record()` prints an empty location for model-level errors, which gives "(: Value error, A repeating item ...)".
- **Action:**
  - On import, move an old `next_date` forward with `advance` to the first date that is today or later. Say so in the import result. Posting a year or more of missed items isn't what a restore should do.
  - In `record()`, leave out the location when it's empty, and remove the "Value error, " prefix the same way `lib/api.ts` does.

#### L2. Malformed input returns 500 (Confirmed, carried over)

The following requests still return 500:
- `/api/analytics/summary?month=bad` (`analytics.py:97-99`)
- `/api/analytics/year?year=1`
- `/api/recurring/upcoming?days=99999999` (`routers/recurring.py:29-38`)
- `POST /api/import` with a `mapping` that isn't JSON (`imports.py:90`) or an unknown `date_format` (`importer.py:37`)

A `cashflow` range that runs past year 9999 does too.

Use `Query(pattern=r"^\d{4}-\d{2}$")` for `month`, `Query(ge=2000, le=2100)` for `year` and `Query(ge=1, le=366)` for `days`. Use `Literal[...]` for `date_format`, and validate `mapping` with `Mapping.model_validate_json`. Cap `cashflow` ranges at a few years.

#### L3. Categories and budgets are not checked for consistency (Confirmed, carried over)

- An income transaction can use an expense category (`transactions.py:75` only checks the owner). The same is true for recurring items (`routers/recurring.py:67`).
- Several budgets can exist for one category (`budgets.py:22-29`): two POSTs both returned 200. Budget views then list the category twice, and `budget_plan` counts both limits.

Check `category.kind` against the transaction kind in `apply` and `check_rule`. Return 409 when a budget for that category already exists.

#### L4. Usernames are case-sensitive (Confirmed, carried over)

`auth.py:112` and `:99`: `backup5` and `Backup5` both signed up. Two accounts that look the same make sharing by username error-prone. Store and look up usernames in lowercase, and apply the same rule in `find_user` and `find_users`.

#### L5. Share requests can be used for spam

- A direct share is a request, and anyone can send one to any user id. Ids are sequential, so one account can put a banner on every user's pages.
- A declined shared wallet invitation deletes the `SharedMember` row, so the owner can invite the same person again right away, as often as they like.

This is annoying rather than harmful now that nothing counts without consent. Keep declined wallet invitations as a declined row, and don't invite that person again. For direct shares, M5's People list already makes a decline stick.

#### L6. Deleting a shared expense removes the other person's pay-back record

`transactions.py:169-170` calls `delete_payment`, which also deletes the "Paid ... back" transaction in the other person's wallet (`shared.py:143-147`). Their wallet balance changes without them doing anything. Undo on the Transactions page then re-creates the expense without its payments. Detach the other person's recorded transaction instead (`share_payment_id = None`, tagged `settle-up`). Also ask for confirmation instead of offering Undo when a shared expense has payments.

#### L7. Earlier low findings still open

- **Receipt files are never deleted** (`storage.py` has no delete). Files stay after a transaction is deleted, a receipt is replaced, a profile is replaced, or a scan is cancelled. Every scan uploads the file before the user saves anything.
- **"Repeat" drops the goal** (`transactions.py:141`): `goal_id` isn't copied into the new recurring item.
- **Settle-up and pay-back transactions can be edited** (`transactions.py:63`). The `Settlement` or `SharePayment` then no longer matches the wallet. Return 409 for them.
- **Profile import trusts ids from another database** (`imports.py:215-233`). Keep links to shared wallets and payments only when the file was exported from this instance.
- **Dashboard failures leave a blank page** (`frontend/app/page.tsx:66-93`): 14 requests in `Promise.all` with no `catch`, and no guard against a slower, older response overwriting a newer one.
- **Deleting a shared wallet** deletes other members' expenses from their own wallets (`routers/shared.py:150-167`). Detach them instead.
- **Legacy share format** (`shared.py:47-48`): the `"1,4"` branch in `parse_shares` is never matched by `shared_with`'s `"{uid}:"` filter. Migrate old rows once, or drop the branch.
- **Tag filter matches substrings** (`transactions.py:44`): `food` matches `seafood`.
- **Repeated work:**
  - `analytics.summary` builds `spending()` four times, and `year_review` about six times. Each build runs `post_due` and a full query.
  - `routers/shared.py` `summary` calls `expenses()` twice.
  - `ledger_detail`, `in_ledger_currency` and `shared_expenses.item` fetch wallets one row at a time.
  - `shared_expenses.status` reads all of the other person's consents once per share.
  - `save_rows` scans the whole history for every imported row.

  None of this matters at current data sizes.
- **Export code** (`routers/export.py:42-148`) spells out every field and uses `hasattr(x, "value")` on `StrEnum` values. `model_dump(mode="json", exclude={"user_id"})` would cut it to a few lines.
- **CSV formula injection** (`export.py:35-38`): cells starting with `=`, `+`, `-` or `@` run as formulas in Excel. Prefix them with `'`.
- **Small inconsistencies:**
  - `storage.py:9-11` defines constants it never uses and reads the environment again in each function.
  - `db.py:48-72` has two near-identical branches; `inspect()` works for SQLite too.
  - Imports inside functions: `db.py:61`, `fx.py:16-25`, `fx.py:98`.
  - `fx.py:27` defines `log` after a function; move it up with the other module globals.
  - `routers/fx.py:2` has a stray blank line in the import block.
  - `auth.update_profile` checks the password length by hand, and `display_name` has no length limit.
  - `getattr(user, "display_name", "")` is used where `user.display_name` would do (`auth.py:142`, `:162`).
- **Exchange-rate lock** (`fx.py:73`, `:89`): one global lock is held during the network fetch. A lock per currency is enough.
- **Import error handler** (`imports.py:179`): `record()` turns `AttributeError` and `TypeError` into a 400, which hides programming errors as bad input.
- **Sessions table** (`auth.py:47-50`): expired sessions are deleted only when used again. Delete expired rows at login.
- **Frontend:**
  - `lib/api.ts:98` drops the caller's `headers` whenever `json` is passed.
  - `catch {}` blocks swallow errors silently: `Shell.tsx:68`, `ProfileImportModal.tsx:48`, `app/shared/page.tsx:54` and `LocationField.tsx:57`.
  - `ShareRequests.tsx:12` has no `catch` on its first load.
  - There is no ESLint script, and `TransactionModal.tsx` (658 lines) would be easier to change in smaller parts.

#### L8. Build, dependencies and docs (carried over)

- `Dockerfile:1,9` uses the unpinned tags `node:lts-slim` and `ghcr.io/astral-sh/uv:latest`, and the container runs as root.
- `pyproject.toml:21` lists `httpx2`. Starlette's `TestClient` needs `httpx`, which is only installed because `supabase` pulls it in.
- `supabase` is a large SDK used for two storage calls. The Storage REST API through `httpx` would do.
- `README.md:29` says `pytest -m model`, but the marker is `ocr`.
- `.gitignore:45-47` ignores `CLAUDE.md` and `.claude/`, so the project instructions aren't versioned.

#### L9. Tests

- There are no tests for M1-M5 or L1 above. Each has a short reproduction in this review that can become a test.
- Postgres is only mocked (`test_cloud_db.py`). One CI run against a real Postgres would cover the foreign-key, `FOR UPDATE` and `ADD COLUMN ... DEFAULT` paths.
- The consent screens (the requests banner, invited members) were never checked in a browser (`docs/CHANGES.md`, 2026-09-28 08:25).

## Action plan

In priority order. S is under an hour, M is a few hours.

| # | Action | Findings | Effort |
|---|--------|----------|--------|
| 1 | Commit the uncommitted fixes, new tests and `ShareRequests.tsx` | - | S |
| 2 | Learn categories only from the user's own non-shared transactions; check ownership in CSV import; clear leaked categories once | M1 | S |
| 3 | Replace the per-username lockout with a correct client address (proxy range or rightmost `X-Forwarded-For`) | M2 | S |
| 4 | Count unaccepted shares as the payer's; select shared-wallet expenses by share, not current membership | M3, M4 | S |
| 5 | People list on the Shared page to change an accept or decline; keep declined wallet invitations | M5, L5 | M |
| 6 | Tests for M1-M5, and a browser check of the consent screens | L9 | M |
| 7 | Move old recurring dates forward on profile import; readable model-level errors | L1 | S |
| 8 | Bound and validate query and form parameters so they return 4xx | L2 | S |
| 9 | Check category kind; one budget per category; lowercase usernames | L3, L4 | S |
| 10 | Detach instead of delete: other people's pay-backs, members' expenses on shared wallet delete; no editing of payments | L6, L7 | S |
| 11 | Delete receipt files with their transaction; clean up unattached scans | L7 | S |
| 12 | Dashboard error handling and stale-response guard | L7 | S |
| 13 | Pin Docker images, non-root user, `httpx` instead of `httpx2`, README fix, version `CLAUDE.md` | L8 | S |
| 14 | Remaining low items as the code is touched | L7 | S each |
