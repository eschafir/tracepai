# TracepAI Profile Export & Import Implementation Plan

## Goal Description

Currently, the export functionality provides flat CSV and transaction-only JSON exports. When a user exports this CSV and attempts to import it into a new account:
1. All amounts are imported into a single wallet as flat transactions without preserving kind (`expense`, `income`, `transfer`).
2. Custom wallets, categories, budgets, savings goals, recurring rules, and split transactions are not recreated.
3. The new account ends up with messy data and unassigned categories.

This plan implements **Full Profile Export and Import** (Backup & Restore):
- **Export Profile (`GET /api/export/profile`)**: Generates a single, comprehensive `tracepai-profile-[username].json` file containing all account configuration and records (user layout settings, wallets, categories, budgets, goals, recurring rules, transactions, and splits).
- **Import Profile (`POST /api/import/profile`)**: Recreates the entire account state in another user account with 1:1 fidelity, correctly re-mapping all internal foreign keys (`wallet_id`, `category_id`, `goal_id`, `recurring_id`) and preserving transfers and splits.
- **Frontend UI Integration**: Adds "Export Profile" and "Import Profile" buttons with an interactive dialog on the Transactions page.

---

## User Review Required

> [!IMPORTANT]
> **Restore Modes (Replace vs Merge)**:
> - **Replace Mode (Default & Recommended for New Users)**: Removes initial placeholder data (e.g. the default Cash wallet and placeholder categories created at signup) and installs the exact configuration and transactions from the backup.
> - **Merge Mode**: Preserves existing wallets and categories, matching by name/kind, and appends the imported records.

---

## Open Questions

None. The schema structure and foreign key relationships are well-defined in [`backend/app/models.py`](file:///Users/eschafir/Research/tracepai/backend/app/models.py).

---

## Proposed Changes

### Backend API Layer

#### [MODIFY] backend/app/routers/export.py
Add `GET /api/export/profile`:
- Queries the authenticated user's `User` preferences (`budget_style`, `overview_layout`, `year_layout`).
- Queries all `Wallet`, `Category`, `Budget`, `Goal`, `RecurringRule`, and `Transaction` records (including child `Split` records).
- Generates a downloadable JSON payload with headers:
  `Content-Disposition: attachment; filename=tracepai-profile-{username}.json`.

```python
@router.get("/profile")
def export_profile(db: DbSession, user: CurrentUser):
    # Returns comprehensive profile JSON bundle
    ...
```

#### [MODIFY] backend/app/routers/imports.py
Add `POST /api/import/profile`:
- Accepts an uploaded profile JSON file and a `mode` parameter (`replace` or `merge`).
- If `replace`: Deletes current user's existing transactions, recurring rules, budgets, goals, categories, and wallets.
- Inserts new wallets and maps `old_wallet_id -> new_wallet_id`.
- Inserts new categories and maps `old_category_id -> new_category_id`.
- Inserts budgets linking to the mapped `category_id`.
- Inserts goals linking to the mapped `wallet_id` and maps `old_goal_id -> new_goal_id`.
- Inserts recurring rules linking to mapped wallets, categories, and goals.
- Inserts transactions linking to mapped wallets, categories, goals, and recurring rules, creating nested `Split` records with mapped categories.
- Updates user settings (`budget_style`, `overview_layout`, `year_layout`).
- Commits atomically in a single database transaction.

---

### Frontend UI Layer

#### [MODIFY] frontend/lib/api.ts
Add TypeScript types for profile import responses and API helpers:
```typescript
export type ProfileImportResult = {
  ok: boolean;
  imported: {
    wallets: number;
    categories: number;
    budgets: number;
    goals: number;
    recurring_rules: number;
    transactions: number;
  };
};
```

#### [NEW] frontend/components/ProfileImportModal.tsx
A modal dialog that:
- Allows selecting or dragging a `tracepai-profile-*.json` file.
- Shows file summary and a toggle between "Replace existing setup" and "Merge with existing setup".
- Submits `POST /api/import/profile` with FormData.
- Displays the import result summary and reloads page data.

#### [MODIFY] frontend/app/transactions/page.tsx
- Add "Export Profile" and "Import Profile" buttons in the top action toolbar alongside existing CSV and JSON options.
- Wire "Import Profile" button to open `ProfileImportModal`.

---

## Verification Plan

### Automated Tests

#### [NEW] backend/tests/test_profile_export_import.py
1. **`test_export_profile_structure`**:
   - Call `GET /api/export/profile` for seeded user.
   - Assert all expected top-level keys exist: `user`, `wallets`, `categories`, `budgets`, `goals`, `recurring_rules`, `transactions`.
   - Assert splits, transfers, and metadata are intact.
2. **`test_import_profile_full_restore_replace`**:
   - Sign up a fresh user.
   - Export profile from original user.
   - Import the profile into the fresh user with `mode=replace`.
   - Assert the fresh user has:
     - Identical wallet count, names, currencies, and balances.
     - Identical categories and budget limits.
     - Identical savings goals.
     - Identical recurring rules.
     - Identical transaction count, transfers, and split amounts.
3. **`test_import_profile_merge_mode`**:
   - Import with `mode=merge` into an account with existing transactions and verify non-destructive addition.
4. **`test_import_profile_validation`**:
   - Verify that invalid JSON or non-profile files return a clear 400 Bad Request error.

Run test command:
```bash
cd backend
uv run pytest tests/test_profile_export_import.py
```

### Manual Verification
1. Export profile from user `user`.
2. Register a new account `clone_user`.
3. Open Transactions page on `clone_user` and click "Import Profile".
4. Upload the exported file and click "Restore Profile".
5. Verify that Wallets, Categories, Budgets, Goals, and Dashboard Analytics match the source account.
