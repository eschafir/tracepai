# Changes

## 2026-09-28 08:32 EDT - Review

Fifth full code review, written to `docs/code_review.md`. The earlier reports are in `docs/code_review_1.md` and `docs/code_review_2.md`. No application code was changed.

- **Checks:** all 115 backend tests pass, and the frontend type-checks cleanly.
- **New findings (medium, all reproduced against a temporary database):**
  - **M1:** category suggestions learn from expenses in other people's shared wallets. As a result, a CSV import saves the owner's category on a member's own transaction, that transaction can't be edited, and the member's profile export can't be imported again.
  - **M2:** the per-username login limit lets anyone lock any account out with 50 wrong guesses every 15 minutes.
  - **M3:** the share of someone who hasn't accepted, or declined, counts as no one's spending, although it left the payer's wallet.
  - **M4:** leaving a shared wallet removes your share of its past expenses from your history.
  - **M5:** a Decline (or Accept) of a person can't be changed in the app.
- **New low findings:**
  - profile backups older than a year fail on their recurring items
  - share requests can be used for spam
  - deleting a shared expense deletes the other person's pay-back record
- **Earlier findings:** most earlier low findings are still open and are listed again.
- **Action plan:** 14 prioritized actions at the end of the report, starting with committing the uncommitted fixes.

## 2026-09-28 08:25 EDT - Fix

Fixed the high and medium findings (H1, M1-M4) from the fourth review in `docs/code_review.md`.

- **Sharing needs consent (H1):**
  - **Shared wallets:** adding someone to a shared wallet now sends an invitation (`SharedMember.pending`). Until they accept, they aren't a member: they can't see or add to the shared wallet, and no one can give them a share.
    - New endpoints: `POST /api/shared/{id}/accept` and `/decline`.
    - The owner can take an invitation back with the existing remove-member endpoint.
    - Shared wallet responses list `invited` people.
  - **Direct shares:** expenses someone shares with you directly count only after you accept that person (new `ShareConsent` table).
    - New endpoints: `POST /api/shared-expenses/people/{id}/accept` and `/decline`. Declining hides their expenses.
    - Each share now has a `status` (accepted, pending or declined), which the payer sees.
  - **Requests:** `GET /api/shared/requests` lists both kinds of request. A new `ShareRequests` banner at the top of every page offers Accept and Decline.
  - **Where invitations show:** invited people appear on the shared wallet page, and are kept when the owner edits the wallet.
  - **Existing data:** existing members stay members. The column migration in `backend/app/db.py` now also gives new boolean columns their default. Existing direct shares wait for one acceptance.
- **Repeating items start at most a year ago (M1):**
  - `check_start` in `backend/app/models.py` rejects, with a 422, a recurring item, a repeating transaction or a repeating goal contribution that starts more than 365 days ago.
  - The recurring form's date field has the same `min`.
- **Login limit (M2):** besides 5 failures per username and client, `backend/app/auth.py` allows at most 50 failed logins per username per 15 minutes from all clients together. The README says to set `FORWARDED_ALLOW_IPS` to the proxy's address range instead of `*`.
- **Former members (M3):**
  - `apply` in `backend/app/routers/transactions.py` lets someone who left a shared wallet edit their expense in it, keeping its split. A change to the amount, date, wallet or shared wallet returns 409. Deleting it also returns 409, since the others' balances count it.
  - The transaction form keeps the shared wallet and explains what can change.
- **Payments and Undo (M4):** on the Transactions page, settle-up and pay-back transactions are deleted after a confirmation and have no Undo. Errors from a delete are shown in a toast.
- **Tests:**
  - 5 new tests in `backend/tests/test_consent_and_limits.py`.
  - Sharing tests updated to accept invitations and shares.
  - A recurring test now starts 100 days ago.
  - The migration was checked on a database without the new column: the existing member stayed a member.
  - All 115 backend tests pass, and the frontend type-checks and builds.
  - The new screens were not checked in a browser.

## 2026-09-27 20:24 EDT - Review

Fourth full code review, written to `docs/code_review.md`. The first review's report stays in `docs/code_review_1.md`. No application code was changed.

- **Checks:** all 110 backend tests pass, and the frontend type-checks cleanly.
- **New findings:**
  - **H1 (high):** anyone can add any user to a shared expense or shared wallet without their consent, and the amounts count in that user's spending, budgets and alerts.
  - **M1 (medium):** a recurring item dated far in the past posts every missed occurrence at once.
  - **M2 (medium):** with `FORWARDED_ALLOW_IPS=*`, a client-set `X-Forwarded-For` bypasses the login attempt limit.
  - **M3 (medium):** a member who left a shared wallet can't edit their own old expenses.
  - **Low:**
    - 500s on malformed parameters
    - receipt files are never deleted
    - no category-kind check and duplicate budgets
    - repeat drops `goal_id`
    - settle-up transactions can be edited
    - profile import trusts ids from another database
    - dashboard error handling

  H1, M1, M3 and most of the low findings were reproduced against a temporary database.
- **Earlier findings:** the Undo issue (now M4) and most earlier low findings are still open, and are listed again.
- **Action plan:** 12 prioritized actions at the end of the report, starting with committing the uncommitted fixes.

## 2026-09-27 17:50 EDT - Review

Third full code review, written to `docs/code_review.md`, replacing the second report. No application code was changed.

- **Earlier findings:** all 20 high and medium findings from the first two reviews are fixed. The report lists their status and the 14 earlier low findings that are still open.
- **New findings:**
  - **R1 (medium):** Undo after a delete on the Transactions page brings back a settle-up or pay-back payment as ordinary spending. It also can't bring back a directly shared expense's pay-back records.
  - **4 low:** spreadsheet formulas in the CSV export, several budgets for one category, an unbounded `days` on `/recurring/upcoming`, and case-sensitive usernames.

  Every new finding was reproduced against a temporary database.
- **Performance:** measured and not a concern at this scale. A 2,000-row CSV import takes 1.2 s, and analytics respond in under 0.1 s with 2,240 transactions.
- **Action plan:** 12 prioritized actions at the end of the report.
- **Time:** estimated. The clock couldn't be read directly.

## 2026-09-27 17:25 EDT - Fix

Fixed the medium findings N1-N5 from the second review in `docs/code_review.md`.

- **Login limit (N1):** `backend/app/auth.py` counts failed logins per username and client IP, so someone guessing a password no longer locks the real owner out. Entries older than 15 minutes are dropped. The README says to set `FORWARDED_ALLOW_IPS=*` behind Render's proxy.
- **Split totals (N2):** `TransactionIn` in `backend/app/models.py` rejects splits that don't add up to the transaction amount (422, "The split amounts must add up to the total"). A profile file with such a transaction is rejected too.
- **Profile merge (N3):** `backend/app/routers/imports.py` stops with a 400 when a wallet in the file has the same name as one in the account but a different currency. Before, its amounts were added in the wrong currency.
- **Exchange rates (N4):**
  - `backend/app/fx.py` writes fetched rates in its own session, so fetching rates no longer commits the request's unfinished changes.
  - `update_shared` in `backend/app/routers/shared.py` now updates members, which can fetch rates, before it changes the ledger. A refused edit (for example removing someone who is still owed money) no longer saves the rename.
- **Time zone (N5):**
  - The start scripts pass the host's time zone into the container as `TZ`: from `/etc/localtime` on Mac and Linux, and through .NET on Windows (PowerShell 7; Windows PowerShell 5.1 keeps UTC). Recurring items then post on the user's date, not UTC's.
  - The dashboard and the Budgets page send the browser's month to the budgets, budget-plan and comparison analytics. The new helper is `thisMonth()` in `frontend/lib/format.ts`.
- **Tests:** 4 new tests in `backend/tests/test_access_and_integrity.py`. The shared-wallet test was checked to fail on the old code. All 110 backend tests pass, and the frontend builds.
- **Note:** the two entries before this one (11:15 and 11:45) have estimated times that are too early, because the clock couldn't be read then.

## 2026-09-27 11:45 EDT - Review

Second full code review, written to `docs/code_review.md`, replacing the first report. No application code was changed.

- **Earlier findings:** all 15 high and medium findings from the first review are fixed. The report keeps a status table for them.
- **New findings:** no high-severity issues. 5 new medium issues:
  - anyone can lock another user out with failed logins
  - split amounts aren't checked against the total
  - profile merge matches wallets by name and ignores their currency
  - an exchange-rate fetch commits the request's unfinished changes
  - the server's date is UTC while the browser's is local

  There are also 3 new low issues, and 11 low issues from the first review are still open. The first three medium issues were reproduced.
- **Action plan:** 12 prioritized actions at the end of the report.

## 2026-09-27 11:15 EDT - Fix

Fixed the high and medium findings from `docs/code_review.md` (H1-H5, M1-M10).

- **Receipts (H1, H2, M10):**
  - A scanned file's extension now comes from its content, never from the uploaded filename.
  - Receipts are saved as `<user id>-<random>.<ext>`. Only images and PDFs are served as their own type (anything else as `application/octet-stream`), always with `X-Content-Type-Options: nosniff`.
  - A receipt is served only to its owner: the name must carry the user's id, or be attached to one of their transactions. A transaction can only point to the user's own receipts.
  - The file is saved after OCR succeeds.
  - Uploads (receipts, CSV statements, profile files) are limited to 15 MB, and larger ones get a 413.
- **Ownership checks (H3):**
  - New `check_owned()` in `app/auth.py`, used for every wallet, category and split id on transactions, recurring items, budgets, goals and goal contributions. Ids that don't exist now return 422 instead of 500.
  - Expenses in a shared wallet must use the owner's categories.
- **Profile import (H4, M1, M2, M3):** `POST /api/import/profile` was rewritten.
  - **Validation:** every record is checked with the model the API uses for it and through the same code paths (`apply`, `check_rule`). A bad record returns a 400 that names it (for example "Transaction 3 in the file is invalid ..."), and nothing is saved unless the whole file is valid.
  - **Merge (the default now):** adds only what isn't in the account yet. Goals are matched by name, recurring items by wallet, merchant, kind and frequency, and transactions by wallet, date, amount, merchant and kind.
  - **Sharing:** the export now includes each transaction's shared wallet, shares, settle-up link and pay-back link. On import they're kept only if they still hold for the user, so restored settle-up payments stay out of spending.
  - **Replace:** refused (409) while the user shares wallets or expenses. It deletes in foreign-key order.
  - **Dialog:** the import dialog defaults to merge, and replace needs a confirmation checkbox.
- **Mock account (H5):** `user` / `password` is only created when `TRACEPAI_SEED_DEMO=1`. The three start scripts set it, and a cloud deployment doesn't.
- **Currency (M4):** wallet and shared-wallet currencies are uppercased by a model validator, so `"usd"` no longer breaks the wallets list and analytics.
- **Deletes (M5, M6):**
  - SQLite now enforces foreign keys, like Postgres.
  - A wallet used by recurring items or goals can't be deleted.
  - A category used by transactions, splits or recurring items can't be deleted, and deleting an unused one also removes its budget.
  - Enforcing foreign keys showed that deleting a recurring item, a goal, a settlement or a shared wallet failed whenever other rows pointed at it. These deletes now remove or detach those rows first.
  - Transactions a recurring item already posted now stay when the item is deleted and only lose the link (new `delete_rule()` in `app/recurring.py`).
- **Sessions (M7):**
  - Sessions expire after 30 days on the server too.
  - Changing the password signs out the user's other sessions.
  - `TRACEPAI_SECURE_COOKIES=1` marks the cookie secure.
  - Five failed logins for a username block it for 15 minutes (429).
- **Recurring posting (M8):** due rules are locked with `SELECT ... FOR UPDATE`, so several processes on Postgres can't post the same date twice. SQLite keeps the thread lock.
- **Exchange rates (M9):**
  - A failed fetch waits an hour before trying again, instead of retrying on every request.
  - A currency with no stored rates returns a clear 503 instead of an `IndexError`.
  - `/api/fx/convert` only accepts 3-letter uppercase codes.
  - The currency list is fetched once a day.
- **Tests:**
  - New `backend/tests/test_access_and_integrity.py` (14 tests) covers each fix. All 106 backend tests pass, and the frontend builds.
  - Test cleanup was adjusted for enforced foreign keys (`test_wallets_recurring.py`) and for the new receipt names (`test_storage.py`).
- **README:** documents `TRACEPAI_SEED_DEMO` and `TRACEPAI_SECURE_COOKIES`.

## 2026-09-27 10:26 EDT - Review

Full code review of the repository, written to `docs/code_review.md`. No application code was changed.

- **Findings:** 5 high, 10 medium and 11 low, each with its location, the problem and an action. The high ones:
  - stored XSS through receipt uploads
  - receipts readable by any signed-in user
  - missing ownership checks on wallet and category ids
  - unvalidated profile import
  - the published mock-account password on cloud deployments
- **Evidence:** 5 of the findings were reproduced with a TestClient script against a temporary database, and the report marks them as Confirmed. The existing 92 backend tests pass and the frontend type-checks.
- **Action plan:** a prioritized table of 14 actions at the end of the report.

## 2026-09-27 09:58 EDT - Feature

User menu dropdown with Profile settings, nested Export and Import options, and simplified toolbar.

- **User Profile Management:**
  - Added `display_name` to `User` model.
  - Added `PUT /api/auth/profile` allowing users to update their display name and change password (verifying current password and minimum 8 characters).
  - Updated `/api/auth/me` to include `display_name`.
- **Navigation & User Dropdown:**
  - In `frontend/components/Shell.tsx`, the user's name is now a clickable dropdown button.
  - Dropdown options:
    - **Profile**: Opens `ProfileModal` to edit display name and password.
    - **Export**: Expands two options: **CSV** (direct bank transactions export) and **Profile** (full backup).
    - **Import**: Expands two options: **CSV** (opens bank statement import) and **Profile** (opens profile restore dialog).
    - **Log out**: Logs out the user.
- **Transactions Page Cleanup:**
  - Removed cluttered import and export buttons from `frontend/app/transactions/page.tsx`, keeping the action bar clean and focused.
- **Tests:**
  - Added profile update tests in `backend/tests/test_dual_auth.py`. All 92 backend tests pass.

## 2026-09-27 09:45 EDT - Feature

Full Account Profile Export and Import (Backup & Restore).

- **Export Profile:**
  - Added `GET /api/export/profile` generating a complete JSON backup containing user layout preferences, wallets, categories, budgets, goals, recurring rules, transactions, and split breakdowns.
- **Import Profile:**
  - Added `POST /api/import/profile` supporting both `replace` (clean 1:1 replica) and `merge` modes.
  - Automatically remaps internal foreign keys (`wallet_id`, `category_id`, `goal_id`, `recurring_id`) to ensure atomic and relational integrity on restore.
- **Frontend UI:**
  - Added "Export Profile" link and "Import Profile" button to the Transactions page action toolbar.
  - Created `ProfileImportModal` component with file preview and restore mode options.
- **Tests:**
  - Added `backend/tests/test_profile_export_import.py` covering profile structure, full clone with replace mode, merge mode, and invalid file validation. All 91 backend tests pass.

## 2026-09-27 08:33 EDT - Feature

Cloud database (Supabase PostgreSQL), cloud object storage (Supabase Storage), and mobile-ready dual authentication for deployment to Render.

- **Database:**
  - Added support for PostgreSQL via `DATABASE_URL` with connection pooling and `psycopg` driver.
  - Made schema column inspection in `add_missing_columns()` dialect-agnostic via SQLAlchemy `inspect` (supporting both SQLite and PostgreSQL).
  - Added dialect-aware upsert logic in `backend/app/fx.py` to use `sqlalchemy.dialects.postgresql.insert` when running on PostgreSQL.
- **Receipt Storage:**
  - Added `backend/app/storage.py` adapter. When `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are provided, uploads receipts to the Supabase `receipts` bucket and serves them via short-lived signed URLs.
  - Falls back to local filesystem when Supabase is not configured (offline/dev/tests).
- **Authentication:**
  - Updated `backend/app/auth.py` to support `Authorization: Bearer <token>` in addition to session cookies.
  - Returns `token` in login and signup responses for mobile app compatibility.
- **Docker & Deployment:**
  - Updated `Dockerfile` CMD to bind to `${PORT:-8000}` dynamically for Render compatibility.
- **Tests:**
  - 87 backend tests pass (9 new tests covering URL normalization, dialect selection, dual auth, storage upload, and signed URL redirection).

## 2026-09-26 10:12 EDT - Modification

Receipts are read with Tesseract OCR again instead of the qwen3-vl vision model through Ollama. The model was slow on the Mac and tied deployments to a machine that can run it.

- **What reads receipts:**
  - **How:** Tesseract, in English and Spanish, installed in the Docker image (`tesseract-ocr`, `-eng`, `-spa`). Nothing to set up on the host, and the Ollama app and model are no longer needed.
  - **Speed:** a scan takes about 0.3 seconds.
- **What it reads:**
  - Receipts, tickets and invoices, as photos, images or PDFs (every page is read). They pre-fill the amount, date and merchant in Add transaction, and the file is kept as the attachment.
  - The photo's GPS location still fills the place.
  - When no total is found, the form says so, as before.
- **The rules** (`backend/app/ocr.py`, brought back from the first version):
  - **Merchant:** the first line with letters, skipping titles like "Invoice", "Factura", "Ticket" or "Receipt".
  - **Date:** YYYY-MM-DD or DD/MM/YYYY, swapping day and month when the month would be over 12.
  - **Amount:** the last line with total, importe, monto, a pagar or amount (not a subtotal). Otherwise, the largest amount.
  - **Amount formats:** both 1,234.56 and 1.234,56.
- **Before reading:** images are turned to gray, their contrast is stretched, and small ones are enlarged.
- **Removed:**
  - `backend/app/vision.py` and the model tests.
  - Reading bank statements from photos or PDFs, meaning the `/import/document` endpoints and the Import review table. Statements are imported as CSV only, and Import turns other files away with "Export your statement as CSV".
  - `TRACEPAI_OLLAMA_URL` and the Linux `--add-host` flag.
  - `frontend/lib/useElapsed.ts`.
- **Scan response:** `/api/receipts/scan` returns `merchant`, `date`, `amount`, `receipt_path`, `lat` and `lng`. A missing Tesseract gives a 503 with a clear message.
- **Tests:**
  - **Backend:** 78 fast tests pass, and new tests in `backend/tests/test_ocr.py` cover the rules, the scan endpoint and the missing-Tesseract error.
  - **Real OCR:** `uv run pytest -m ocr` reads the generated receipt, phone photo, Spanish ticket and invoice PDF correctly. These 5 tests pass in a container with Tesseract, since it isn't installed on the Mac.
  - **Browser:** on a separate test container:
    - the receipt, invoice PDF and phone photo fill the form
    - a picture without text says no total was found
    - the attachment opens
    - Import takes a CSV and turns away a PDF
    - phone width in dark mode
  - The earlier suites still pass.
  - A copy of the live database starts unchanged, with no schema change.
- **Docs:** README, CLAUDE.md (Receipt capture) and docs/PLAN.md are updated.

## 2026-09-26 08:56 EDT - Feature

A single expense can be shared with other people directly, without a shared wallet, and each person's share is tracked until they pay it back.

- **Adding one:**
  - Add transaction has a **Shared** switch for expenses. Turned on, it shows "People and their share": you plus anyone added by username (Enter or Add), with a percent each, starting at an equal split, and "Split equally".
  - Saving is blocked until at least one person is added and the percentages add up to 100%. An unknown username says "No one is signed up as X."
  - The switch adds the "shared" tag, and turning it off removes it. The backend also adds the tag to every direct shared expense.
  - If you're in shared wallets, a "Shared in" choice appears under the switch: "Just this expense, with people I choose" (the default) or one of your shared wallets, which works as before.
- **What each person sees:**
  - **The payer:** the Transactions row shows "Your share $36.00" and, per person, "dora owes you $54.00" or "dora paid you back $54.00, Sep 26".
  - **Everyone else:** a "Shared with you" section at the top of Transactions: "user paid $90.00. Your share is 60%. You owe user $54.00". Only the payer can edit or delete the expense.
- **Spending:** the whole amount leaves the payer's wallet, but each person's spending counts only their share, in their own category with the same name (or "Shared"), as with shared wallets.
- **Paying back:**
  - Either the payer or that person can "Mark paid", with a date and, optionally, one of their wallets in the expense's currency to record the money moving.
  - The other one can later "Record in my wallet". "Undo" removes the payment and anything it recorded, on both sides.
  - Recorded payments move wallet balances but are not spending or income.
- **Cleanup:** removing someone from the expense, turning Shared off, or deleting the expense removes their payments and what they recorded.
- **Code:**
  - **Backend:**
    - New `SharePayment` table and `Transaction.share_payment_id`, both added to existing databases on start-up.
    - `apply()` in `routers/transactions.py` accepts `shares` without a shared wallet and validates them.
    - New `routers/shared_expenses.py`: list, get, mark paid, record, undo.
    - `GET /api/auth/users/{username}` looks someone up.
    - `shared_with`, `share_payments` and `delete_payment` in `app/shared.py`.
    - `spending()` in `routers/analytics.py` includes shares of direct expenses paid by others, maps categories by the payer's names, and leaves out payback payments.
  - **Frontend:**
    - `components/TransactionModal.tsx` has the switch and people.
    - New `components/ShareStatus.tsx`.
    - `components/Switch.tsx` is extracted from the wallet form and used in both forms.
    - `app/transactions/page.tsx` shows the statuses and the "Shared with you" section.
- **Tests:**
  - New `test_shared_expense_without_a_shared_wallet`. All 87 backend tests pass.
  - A browser run with two accounts on a separate test container covered:
    - the switch, adding people, the unknown user, the 90% block, and the tag
    - each side's spending and view
    - marking paid from a wallet, recording on the other side, and undo
    - editing, then turning Shared off
    - phone width in dark mode
  - The earlier shared-wallet, wallet and layout suites still pass. The batch 3 suite now turns the switch on before choosing a shared wallet.
  - A copy of the live database upgrades with unchanged wallets and transactions.

## 2026-09-25 21:25 EDT - Feature

Panels on Overview and Year can be dragged into any order, and the order is saved to the account.

- **What moves:** every chart panel. The top of each page stays fixed: on Overview the alerts, "Money on hand" with the wallet chips, and the period switch; on Year the title and the year summary.
- **How:**
  - Drag the grip before a panel's title, with the mouse or a finger. Dragging starts only from the grip, so links, buttons and chart tooltips inside panels work as before, and a finger can still scroll.
  - With the grip focused, the arrow keys move the panel one place earlier or later. This replaced dnd-kit's own keyboard sensor, which picks targets by position and moved panels the wrong way when wide and half-width panels are mixed.
  - Panel widths don't change. A half-width panel moved next to a wide one can leave a gap on large screens, which you can fill by dragging.
  - "Where it went" on Overview now notes its period, since it can be moved away from the period switch.
- **Saved:**
  - Per account, so the order follows you to any browser.
  - Panels added in future versions appear in their default place.
- **Code:**
  - Backend: `User.overview_layout` and `User.year_layout` (comma-separated panel ids) are added to existing databases on start-up. `GET /api/settings` returns them as lists. `PUT /api/settings` is now a partial update, applying only the fields sent.
  - New `frontend/components/SortablePanels.tsx`, built on `@dnd-kit/core` and `@dnd-kit/sortable`. `Panel` in `frontend/components/charts.tsx` shows the grip through a `DragHandle` context when it's inside a sortable list. `frontend/app/page.tsx` and `frontend/app/review/page.tsx` pass their panels to it.
- **Tests:**
  - `test_settings` covers the new fields and partial updates. All 86 backend tests pass.
  - A browser run on a separate test container covered:
    - a mouse drag, then a reload
    - the arrow keys, with focus staying on the grip
    - the order saved per account, with another account keeping the default
    - clicks inside panels still working
    - Year dragging
    - a touch drag at phone width in dark mode
  - The earlier wallet and shared-wallet suites still pass.
  - A copy of the live database starts with the new columns, and its wallets and transactions are unchanged.

## 2026-09-25 20:41 EDT - Feature

One wallet form with a Shared switch, percentages per shared expense, editable shared expenses, and deletable shared wallets.

- **One form:** the separate "Shared wallets" section is gone. "Add a wallet" has a Shared switch.
  - **Switched on:** it asks for a name, a currency, a color and People (type a username and press Enter or Add; each person shows as a chip you can remove). Type and starting balance are hidden, because money stays in each person's own wallets.
  - **Editing a shared wallet** opens the same form with the switch on and locked, and its people can be added or removed there. The currency is locked once it has expenses.
  - **On the server:** `POST /api/shared` and `PUT /api/shared/{id}` take `members` (usernames). An unknown username is refused and nothing is created. Someone who still owes or is owed money can't be removed.
- **One list:** shared wallets appear in the same list as your other wallets, as "Shared with ana, cara", with "You're owed $X", "You owe $X" or "Settled up" instead of a balance.
  - They aren't counted in the wallets total.
  - The owner gets Edit and Delete; other members get Open.
- **Percentages:** each shared expense has a share for each person.
  - **In the form:** it starts at an equal split (33.33 / 33.33 / 33.34), shows each person's amount, and has "Split equally". Saving is disabled until the shares add up to 100%.
  - **What uses them:** balances, each person's spending, "your share" on the Transactions page, and the shared wallet page ("You 70%, ana 30%").
  - **Storage:** percentages are saved as `"1:70,4:30"` in `shared_members`. Expenses saved earlier as `"1,4"` still read as an equal split, so nothing was migrated.
  - **Undo** after deleting a shared transaction keeps its percentages.
- **Editing and deleting shared expenses:** the person who paid now has Edit and Delete on their expenses in the shared wallet page. Other members can't change them (the server returns 404). New `GET /api/transactions/{id}` for your own transactions.
- **Deleting a shared wallet:** now allowed with expenses, after a confirm ("Delete Trip and its 1 expense? They are removed from everyone's wallets.").
  - It deletes the shared wallet with its expenses from every member's wallet, its payments, and the payments recorded in wallets.
  - Only the owner can do it.
- **Other:** `/api/auth/me` also returns the user's `id`.
- **Tests:**
  - A new backend test covers percentages (a 70/30 split, rejecting shares that don't total 100 or include someone outside the wallet, reading old rows as equal), payer-only edit and delete, people on create and update, and deleting a shared wallet with its expenses and recorded payments while restoring every balance. All 86 backend tests pass.
  - 20 browser checks with three people in the test container on 8002 all pass. They cover the switch, the list row, editing people, a 70/30 expense, the 90% warning, editing to an equal split, deleting an expense, what another member can see, deleting through the confirm, and phone width in dark mode. The batch 3 suite (updated for the new form) passes too.
  - On a copy of the real database, the existing shared wallet and its old-format expense read the same, and wallets, balances and spending are unchanged. A backup is in the scratchpad (`tracepai-backup-combined.db`).

## 2026-09-25 19:37 EDT - Fix

A shared wallet opened from the Wallets page said "This shared wallet doesn't exist, or you're not a member", so people couldn't be added.

- **Cause:**
  - The shared wallet page read its `?id=` from `window.location` while rendering.
  - After an in-app navigation (clicking a link), Next.js renders the new page before it updates the address, so the page read the previous address, got no id, and requested `/api/shared/`, which is a 404.
  - Opening the page by typing its address worked, which is why the earlier tests (which did that) missed it.
  - Reproduced by creating a shared wallet and clicking its link: the request went to `/api/shared/` and failed.
- **Fix:**
  - The shared wallet page now reads the id with Next's `useSearchParams`, inside a `<Suspense>` boundary as the static export requires.
  - The Transactions page read `?wallet=` the same way, so a wallet link from the Wallets page could open the list unfiltered. It now uses the same approach.
- **Changes you asked for:**
  - The "Shared wallets" section on the Wallets page is now at the bottom, after "Add a wallet".
  - Creating a shared wallet now opens it straight away, so people can be added.
- **Tests** (in the test container on 8002, moving between pages by clicking as a person would, not by typing addresses):
  - The Shared wallets section is last, and creating "Flat" opens its page.
  - Adding "maria" by username works, and going back to Wallets and opening it from the list works.
  - A wallet link opens Transactions filtered to that wallet.
  - The batch 3 browser suite (updated for the new create flow) and all 85 backend tests pass.

## 2026-09-25 18:33 EDT - Feature

Sign-up and shared wallets (batch 3 of the plan in `docs/PLAN.md`).

- **Sign-up:** a new "Create an account" page, linked from the login page.
  - Rules: a username of 3 to 32 letters, numbers, dots, dashes or underscores, and a password of at least 8 characters, typed twice.
  - New accounts start with the default categories and a Cash wallet, and no mock data.
  - The `user` / `password` account is unchanged. `CLAUDE.md` "Limitations" is updated to match.
  - The header now shows who is logged in. Before, the name only appeared as a tooltip on "Log out".
- **Shared wallets** (a new section on the Wallets page, and a page for each shared wallet):
  - Create one with a name and a currency. The owner adds people by username.
  - **Adding expenses:** anyone in it adds expenses with "Add shared expense", or by choosing "Shared in" when adding an expense anywhere. The whole amount comes out of the payer's own wallet, and it's split equally between the people in the shared wallet at that moment.
  - **Categories:** shared expenses use the owner's categories. In each member's own charts, they count under the category with the same name, or "Shared".
  - **Your spending:** budgets, the monthly summary, charts and the Year page count only your share of shared expenses, including your share of what others paid. Wallet balances and net worth still show the whole payment leaving the payer's wallet.
  - **Who owes whom:** the shared wallet page shows it, using the fewest payments, in the shared wallet's currency (expenses in other currencies are converted at their date's rate). Each expense shows who paid, how many ways it's split and your share, and the Transactions list marks shared expenses with your share.
  - **Settle up:** records a payment, optionally in one of your wallets. The other person can record it in theirs with "Record in my wallet". These payments move wallet balances but don't count as spending or income.
  - **Members:** the owner can remove people and members can leave, only once settled up. A shared wallet can only be deleted while it's empty.
- **Backend:**
  - New tables `SharedWallet`, `SharedMember` and `Settlement`.
  - New `Transaction` columns `shared_wallet_id`, `shared_members` and `settlement_id`, added on start-up.
  - New files `app/shared.py` and `app/routers/shared.py`.
  - `POST /api/auth/signup`.
  - Analytics read transactions through a new spending view; balances and net worth are unchanged.
  - Exchange rates now load any currency the first time it's needed, since another member's wallet can be in a currency you don't use.
- **Found and fixed while testing:**
  - SQLModel ignored the username rule written as `regex=`, so a name with a space was accepted. It now uses Pydantic's `StringConstraints`.
  - Recording a settle-up payment returned an empty response, because the object wasn't reloaded after saving.
  - Shared expenses' amounts wrapped onto their own line at phone width; the rows now use a three-column grid.
- **Tests:**
  - 3 new backend tests in `backend/tests/test_shared.py` (sign-up and its rules; users only seeing their own data; the full shared flow with two, then three, people). They cover each person's balances and categories, the "Shared" category, a late joiner, settling up and recording it, leaving, and delete rules. All 85 tests pass.
  - 26 browser checks with two people logged in at once, in the test container on 8002, all pass. The batch 2 browser suite still passes.
  - The new version was run on a copy of the real database: wallets, balances, transactions and this month's spending were unchanged, and sign-up worked. A backup is in the scratchpad (`tracepai-backup-batch3.db`). Not yet deployed.

## 2026-09-25 16:13 EDT - Feature

Pace alerts, monthly goal transfers, subscription price changes, budget styles and a year in review (batch 2 of the plan in `docs/PLAN.md`).

- **Budget pace alerts:**
  - Each budget now has a month-end projection: spending so far, plus recurring charges still due this month, plus the rest of the spending continued at its current daily pace.
  - Recurring charges are kept out of the pace, so rent paid on the 1st doesn't look like runaway spending.
  - It alerts "over budget", or, from day 5 of the month, "on pace to go over by $X".
  - The alerts show in a new banner at the top of the dashboard (up to 3, most urgent first) and on each budget bar.
  - They are in-app only; push notifications would need HTTPS.
- **Monthly goal transfers:**
  - Add money on a goal has a "Repeat monthly" checkbox. It adds today's transfer and creates a recurring transfer for the same day each month.
  - The goal card shows "Adds $X monthly from <wallet>" with a Stop button.
  - When a goal has a target date, a "Set up $X monthly" link fills in the monthly amount needed.
  - Recurring items carry the goal link (`goal_id` moved from transactions to the fields both share), and the Recurring page shows "Goal: <name>".
  - Deleting a goal stops its monthly transfers.
- **Subscription price changes:**
  - An expense recurring item is flagged when its latest charge in the last 45 days (same wallet, same merchant) differs from the saved amount by more than 1% and more than $0.50.
  - The Recurring page offers "Update to <new>" or "Keep <old>". Keep is remembered for that amount, in the new `price_seen` column.
  - Price changes also appear in the dashboard banner.
- **Budget styles:** a Limits / Zero-based / 50/30/20 switch on the Budgets page, saved per user (the new `budget_style` column on users; existing users get "limits").
  - **Zero-based** shows this month's income, the amount assigned to budgets, and what's left to assign.
  - **50/30/20** compares actual needs, wants and savings with 50%, 30% and 20% of income. Each expense category gets a group picker (new `budget_group` column); categories without a group count as wants and are listed.
  - The dashboard's budget panel follows the chosen style.
  - Fresh installs seed groups for the default categories.
- **Year in review:** a new Year page (in the nav) with arrows to change year. It shows:
  - income, spending and the share kept
  - the change against the previous year
  - the busiest month and the top category
  - net worth at the start and end of the year
  - what each goal gained
  - month-by-month income and expenses, where the money went, the biggest purchases and the most visited places
- **New endpoints:**
  - `GET/PUT /api/settings`
  - `GET /api/analytics/budget-plan`
  - `GET /api/analytics/year`
  - `GET /api/recurring/price-changes`
  - `POST /api/recurring/{id}/keep-price`
  - `/api/analytics/budgets` rows gain `projected` and `alert`.
- **Fix:** `GET /api/goals` didn't add due recurring transactions first, unlike the transactions, wallets and recurring endpoints. A monthly goal transfer that was due didn't show as saved until another page triggered posting. Found by the new backend test.
- **Tests:**
  - 7 new backend tests in `backend/tests/test_batch2.py`: the pace projection and alerts, projections on budget rows, monthly goal transfers, price changes, the budget plan and year review on controlled 2014 data, settings, and old users getting "limits". All 82 tests pass.
  - 28 browser checks in the test container on 8002 all pass: the alert banner, the pace note, each budget style, the group picker, updating and keeping a price change, Set up / Repeat monthly / Stop on a goal, the Year page and its year arrows, and no sideways scrolling at phone width in dark mode.
  - The new version was run on a copy of the real database; its data was unchanged. A backup is in the scratchpad (`tracepai-backup-batch2.db`). Not yet deployed.

## 2026-09-25 15:43 EDT - Fix

The wallet currency could not be changed from USD, both when adding a wallet and when editing one.

- **Cause:**
  - The currency field was a text box pre-filled with "USD" and limited to 3 characters, so it was already full: typing "ARS" left it as "USD".
  - Its suggestion list only shows entries that match the text already in the box, so it offered nothing but USD.
  - Reproduced in the browser: clicking the field and typing "ARS" kept "USD", and the only suggestion was "USD".
- **Fix:**
  - The field is now a dropdown with every supported currency, named in full (for example "ARS - Argentine Peso").
  - `GET /api/fx/currencies` now returns every code open.er-api.com has (166) plus the ones with full history. If that site can't be reached, it falls back to USD, ARS and the European Central Bank currencies.
  - When a wallet's currency is locked because it has transactions, the dropdown is now visibly dimmed, not just disabled.
- **Tests:**
  - A new backend test covers the currency list, including when offline. All 75 tests pass.
  - In the test container on port 8002: the dropdown lists 166 currencies, an ARS wallet was created by choosing from it, an unused wallet was changed from ARS to EUR, and a wallet with transactions stayed locked.
  - The batch 1 browser suite passes again (14 checks).
- **Note:** the running app still has the previous build, without currencies. Deploying this build is still pending.

## 2026-09-25 15:33 EDT - Feature

Multi-currency wallets and a net worth chart (batch 1 of the plan in `docs/PLAN.md`).

- **Wallet currencies:** each wallet has a currency (default USD).
  - Your existing wallets become USD automatically.
  - A wallet's currency can't change once it has transactions.
  - The Wallets page shows each balance in its own currency, with the USD value under non-USD balances.
- **Exchange rates** (new `backend/app/fx.py` and `FxRate` table): fetched at most once a day per currency and stored in the database.
  - **ARS:** the official BNA rate, full daily history since 2011, from api.argentinadatos.com.
  - **About 30 major currencies:** daily history from the European Central Bank (api.frankfurter.dev).
  - **Any other currency:** today's rate from open.er-api.com; its history builds up over time.
  - **Lookups:** each amount is converted at the rate for its own date (the nearest earlier rate on weekends).
  - **Failures:** if a fetch fails, the stored rates are used. Creating a wallet in a currency with no rate at all is refused with a clear message.
- **Totals in USD:** every dashboard figure and chart, budgets, the monthly summary and the live balance line convert each transaction at its date's rate. Before this, all amounts were added as if they were dollars.
- **Transfers between currencies:**
  - They need the amount received (`to_amount`), in the add-transaction form, recurring items and goal contributions.
  - The "Received" field is pre-filled from the rate, and you can change it to what you actually got.
  - Transfers within one currency must not have it.
- **Net worth:**
  - A new `GET /api/analytics/networth` returns assets (wallets above zero), debts (below zero) and net worth at each month end and today, in USD.
  - The dashboard shows it as a "Net worth" panel.
- **Lists show each wallet's currency:** Transactions, the map, Recurring, the dashboard's wallet buttons and upcoming list, and goals (in the goal wallet's currency).
- **Export:** gains `currency` and `to_amount` columns.
- **Start-up migration:** `add_missing_columns()` now gives a new text column its default on existing rows (used for `wallet.currency`).
- **Tests:**
  - 8 new backend tests in `backend/tests/test_currency.py`: the source parsers, nearest-rate lookup, once-a-day refresh, failed fetches, conversion in analytics, cross-currency transfers and recurring transfers, the currency lock, goals in another currency, net worth, and old wallets becoming USD. The export test now expects the two new columns. All 74 tests pass.
  - 14 browser checks in a test container on port 8002 all pass: an ARS wallet with the real BNA rate, an ARS expense converted on the dashboard, a USD-to-ARS transfer with a changed received amount, native amounts in the list, the net worth panel, the currency lock, and phone width in dark mode.
- **Real data:** the new version was run on a copy of the real database; its transactions and balances were unchanged. A backup is in the scratchpad (`tracepai-backup-batch1.db`). Not yet deployed.

## 2026-09-25 14:54 EDT - Feature

Money added to or taken from a savings goal now moves between real wallets.

- **Goals are kept in a wallet:**
  - Each goal has a "Kept in" wallet. A new goal preselects the first savings wallet.
  - **Add money** asks for a "From" wallet and records a transfer from it into the goal's wallet.
  - **Take out** asks for a "To" wallet and records a transfer back out.
  - The goal's saved amount is the sum of those transfers (in minus out). The wallet balances, the goal and the Transactions list always agree.
- **Rules:**
  - **Locked wallet:** once money has moved, the goal's wallet can't be changed, because that would flip the meaning of earlier transfers. The edit form shows this.
  - **Removing a history row** deletes its transfer, so the balances go back.
  - **Editing or deleting** one of these transfers on the Transactions page updates the goal. An edit that no longer goes to or from the goal's wallet is rejected with a message naming the goal and wallet.
  - **Deleting a goal** keeps its transfers, because the money really moved. They just lose the goal link.
  - **A goal with no wallet** (like your existing one) shows "Choose where this goal's money is kept" instead of Add money.
- **Backend:**
  - `Goal.wallet_id` and `Transaction.goal_id` are new nullable columns, added on start-up by `add_missing_columns()`.
  - The `GoalContribution` model is removed. Its table stays in existing databases, empty and unused.
  - `app/routers/goals.py` builds the history from linked transfers, creates transfers on `POST /goals/{id}/contributions` (`direction` "in"/"out" plus the other `wallet_id`), and returns `transfer_count` for each goal.
  - `app/routers/transactions.py` checks a transaction's `goal_id` on create and update.
- **Mock data** (fresh installs only): both goals are kept in Savings, and their contributions are Checking-to-Savings transfers. The Checking and Savings opening balances were adjusted by $4,000, so the balances come out the same.
- **Frontend:**
  - `app/goals/page.tsx` adds the Kept in, From and To wallet selects and shows the other wallet in the history.
  - `app/transactions/page.tsx` shows "Goal: <name>" on linked transfers.
  - `components/TransactionModal.tsx` keeps `goal_id` when editing.
- **Fix:** the amount box in the Add/Take out form sat beside its label and overlapped it on phones. `.field` relies on `width: 100%` to wrap below the label, and `w-32` overrode it; the input is now `block`.
- **Tests:**
  - Backend: goal tests rewritten (money moves, take out, removing a row, editing and deleting on Transactions, locked wallet, deleting a goal, validation), and the column test now covers `goal_id`. All 66 tests pass.
  - Browser (21 checks in a test container on 8002): all pass, with screenshots on desktop in light mode and at phone width in dark mode.
  - The migration was run on a copy of the real database: the transaction count (6) and every wallet balance were unchanged.
- **Not yet deployed to 8001.** The rebuild was blocked by a permission check. The database was backed up first.

## 2026-09-25 14:43 EDT - Plan

Planned moving real money when adding to or taking from a savings goal. Nothing is built yet.

- **Problem:** "Add money" on a goal only recorded a number. No wallet changed, so the money counted twice (in a wallet balance and as "saved") and the app didn't know where it was kept.
- **Plan:**
  - Each goal is kept in one wallet.
  - Adding money records a transfer from a chosen wallet into the goal's wallet, and taking out records a transfer back.
  - The goal's saved amount is the sum of those transfers, which carry a new `goal_id`.
  - The `GoalContribution` table is retired; it has no rows in the real database.
- **Existing data:** on deploy, no balances change and no money moves. The existing goal just needs a wallet chosen.
- **Details:** see "TracepAI: Goal money moves between wallets" in `docs/PLAN.md`.

## 2026-09-24 18:30 EDT - Feature

Edit every field of a recurring item from the Recurring page.

- **What you can change:** Edit now opens the full recurring form, pre-filled with the item's current values: type, merchant, amount, Paid with (or From and To for a transfer), Category, Repeats and the date.
- **Date label:** the date reads "Next date" when editing and stays "First date" when adding.
- **When changes apply:** from the next date onward. Transactions already added keep their old values, and the form says so. A next date of today or earlier adds the transaction when you save.
- **Code:**
  - `frontend/components/RecurringForm.tsx` takes an optional `initial` item and an `onCancel`. It only clears the category when the type actually changes.
  - `frontend/app/recurring/page.tsx` replaces the old inline form (amount, repeats, next date only) with `RecurringForm`.
  - The backend is unchanged; `PUT /api/recurring/{id}` already accepted every field.
- **Tests:** two new tests in `backend/tests/test_wallets_recurring.py`:
  - `test_edit_rule_changes_future_transactions_only`
  - `test_edit_rule_validation`: a transfer to the same wallet, a missing destination, an unknown frequency and a zero amount are rejected, and an unknown item returns 404.

  All 66 backend tests pass. A browser run in a separate test container covered the pre-filled values, saving, Cancel, editing a transfer, posting when the date is today, one edit form at a time, and phone width in dark mode.
- **Deployed** to the app on port 8001, after backing up the database.
