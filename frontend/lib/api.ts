export type Kind = "income" | "expense" | "transfer";

export type Frequency = "weekly" | "monthly" | "yearly";

export type BudgetGroup = "need" | "want" | "savings";

export type Category = { id: number; name: string; color_slot: number; kind: "income" | "expense"; budget_group: BudgetGroup | null };

export type WalletKind = "bank" | "card" | "cash" | "savings";

export type WalletInput = { name: string; kind: WalletKind; color_slot: number; opening_balance: number; currency: string };

export type Wallet = WalletInput & { id: number; balance: number; balance_usd: number; in_use: boolean };

export type Split = { category_id: number; amount: number };

export type TransactionInput = {
  date: string;
  amount: number;
  kind: Kind;
  merchant: string;
  wallet_id: number;
  to_wallet_id: number | null;
  to_amount: number | null;
  category_id: number | null;
  notes: string;
  tags: string;
  receipt_path: string | null;
  place: string | null;
  lat: number | null;
  lng: number | null;
  splits: Split[];
  repeat?: Frequency | null;
  goal_id: number | null;
  shared_wallet_id: number | null;
  shares?: Record<number, number> | null; // shared expenses: percent per user id
};

export type Transaction = TransactionInput & { id: number; recurring_id: number | null; shared_members: string | null; settlement_id: number | null };

export type RecurringInput = {
  kind: Kind;
  amount: number;
  merchant: string;
  wallet_id: number;
  to_wallet_id: number | null;
  to_amount: number | null;
  category_id: number | null;
  frequency: Frequency;
  next_date: string;
};

export type RecurringRule = RecurringInput & { id: number; notes: string; tags: string; goal_id: number | null };

export type PriceChange = { rule_id: number; merchant: string; wallet_id: number; old: number; new: number; date: string };

export type RecurringSuggestion = RecurringInput & { occurrences: number };

export type Upcoming = { rule_id: number; date: string; merchant: string; amount: number; to_amount: number | null; kind: Kind; wallet_id: number; to_wallet_id: number | null };

export type NetWorthPoint = { date: string; assets: number; debts: number; net: number };

export type ImportMapping = { date: string | null; merchant: string | null; amount: string | null; debit: string | null; credit: string | null };

export type ImportPreview = { headers: string[]; rows: string[][]; row_count: number; mapping: ImportMapping; date_format: string };

export type ImportResult = { imported: number; duplicates: number; errors: { row: number; message: string }[] };

export type Budget = { id: number; category_id: number; monthly_limit: number };

export type ReceiptScan = {
  document_type: string;
  count: number;
  merchant: string;
  date: string | null;
  amount: number | null;
  kind: "income" | "expense";
  receipt_path: string;
  lat: number | null;
  lng: number | null;
};

export type DocumentRow = {
  date: string | null;
  merchant: string;
  amount: number;
  kind: "income" | "expense";
  category_id: number | null;
};

export type DocumentPreview = { document_type: string; transactions: DocumentRow[] };

export class ApiError extends Error {}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...rest } = init;
  const res = await fetch(`/api${path}`, {
    ...rest,
    headers: json === undefined ? rest.headers : { "Content-Type": "application/json" },
    body: json === undefined ? rest.body : JSON.stringify(json),
  });
  if (res.status === 401 && !path.startsWith("/auth/login") && !path.startsWith("/auth/signup")) {
    window.location.href = "/login/";
    return new Promise<T>(() => {});
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : (body.detail?.[0]?.msg?.replace(/^Value error, /, "") ?? "Some values are invalid. Check the form and try again.");
    throw new ApiError(detail);
  }
  return res.json();
}

export type Place = { name: string; address: string; lat: number; lng: number };

export type PlacePoint = {
  id: number;
  date: string;
  merchant: string;
  place: string | null;
  lat: number;
  lng: number;
  amount: number;
  kind: Kind;
  category: string;
  color_slot: number | null;
};

export type GoalInput = { name: string; target_amount: number; target_date: string | null; color_slot: number; wallet_id: number | null };

export type Goal = GoalInput & {
  id: number;
  currency: string;
  repeating: { rule_id: number; amount: number; wallet_id: number; next_date: string }[];
  saved: number;
  transfer_count: number;
  percent: number;
  remaining: number;
  months_left: number | null;
  monthly_needed: number | null;
};

// A transfer into (positive amount) or out of a goal's wallet; wallet_id is the other wallet.
export type Contribution = { id: number; date: string; amount: number; note: string; wallet_id: number };

export type MonthSummary = {
  month: string;
  in_progress: boolean;
  income: number;
  expenses: number;
  net: number;
  savings_rate: number | null;
  compared_days: number;
  change: number;
  change_percent: number | null;
  top_category: { name: string; total: number; share: number | null } | null;
  biggest: { merchant: string; amount: number; date: string } | null;
  most_visited: { merchant: string; count: number } | null;
  over_budget: string[];
};

export type BudgetStyle = "limits" | "zero_based" | "50_30_20";

export type BudgetPlan = {
  month: string;
  income: number;
  assigned: number;
  left_to_assign: number;
  groups: { group: BudgetGroup; actual: number; target: number }[];
  ungrouped: string[];
};

export type YearReview = {
  year: number;
  in_progress: boolean;
  income: number;
  expenses: number;
  net: number;
  savings_rate: number | null;
  months: { period: string; income: number; expense: number; net: number }[];
  busiest_month: { month: string; expense: number } | null;
  previous_expenses: number;
  change_percent: number | null;
  categories: { category_id: number | null; name: string; color_slot: number | null; total: number; share: number | null }[];
  largest: { id: number; date: string; merchant: string; amount: number }[];
  frequent: { merchant: string; count: number; total: number }[];
  goals: { name: string; gained: number; currency: string }[];
  net_worth_start: number;
  net_worth_end: number;
};

export type Member = { id: number; username: string };

export type SharedWallet = {
  id: number;
  name: string;
  currency: string;
  color_slot: number;
  owner_id: number;
  members: Member[];
  my_balance: number; // positive: the others owe you
  expense_count: number;
  in_use: boolean; // has expenses or payments, so its currency is locked
  categories: Category[]; // the owner's; shared expenses use these
};

export type Settlement = { id: number; from_user_id: number; to_user_id: number; amount: number; date: string; recorded_by: number[] };

export type SharedDetail = SharedWallet & {
  expenses: {
    id: number;
    date: string;
    merchant: string;
    category_id: number | null;
    splits: Split[];
    amount: number;
    currency: string;
    amount_shared: number;
    paid_by: number;
    shares: { user_id: number; percent: number }[];
  }[];
  settlements: Settlement[];
  balances: Record<string, number>;
  debts: { from_user_id: number; to_user_id: number; amount: number }[];
};

// Percent per user id from a transaction's shared_members: "1:60,4:40", or the older "1,4" for an equal split.
export function parseShares(sharedMembers: string | null): Record<number, number> {
  if (!sharedMembers) return {};
  const parts = sharedMembers.split(",").map((p) => p.split(":"));
  return Object.fromEntries(parts.map(([id, percent]) => [Number(id), percent === undefined ? 100 / parts.length : Number(percent)]));
}

// Percentages that add up to exactly 100; the last person takes the rounding (33.33, 33.33, 33.34).
export function equalShares(ids: number[]): Record<number, number> {
  const each = Math.round(10000 / ids.length) / 100;
  return Object.fromEntries(ids.map((id, i) => [id, i === ids.length - 1 ? Math.round((100 - each * (ids.length - 1)) * 100) / 100 : each]));
}
