# Changes

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
