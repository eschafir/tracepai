# Changes

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
