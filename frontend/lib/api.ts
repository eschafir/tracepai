export type Kind = "income" | "expense" | "transfer";

export type Frequency = "weekly" | "monthly" | "yearly";

export type Category = { id: number; name: string; color_slot: number; kind: "income" | "expense" };

export type WalletKind = "bank" | "card" | "cash" | "savings";

export type Wallet = { id: number; name: string; kind: WalletKind; color_slot: number; opening_balance: number; balance: number };

export type Split = { category_id: number; amount: number };

export type TransactionInput = {
  date: string;
  amount: number;
  kind: Kind;
  merchant: string;
  wallet_id: number;
  to_wallet_id: number | null;
  category_id: number | null;
  notes: string;
  tags: string;
  receipt_path: string | null;
  place: string | null;
  lat: number | null;
  lng: number | null;
  splits: Split[];
  repeat?: Frequency | null;
};

export type Transaction = TransactionInput & { id: number; recurring_id: number | null };

export type RecurringInput = {
  kind: Kind;
  amount: number;
  merchant: string;
  wallet_id: number;
  to_wallet_id: number | null;
  category_id: number | null;
  frequency: Frequency;
  next_date: string;
};

export type RecurringRule = RecurringInput & { id: number; notes: string; tags: string };

export type RecurringSuggestion = RecurringInput & { occurrences: number };

export type Upcoming = { rule_id: number; date: string; merchant: string; amount: number; kind: Kind; wallet_id: number; to_wallet_id: number | null };

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
  if (res.status === 401 && !path.startsWith("/auth/login")) {
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

export type GoalInput = { name: string; target_amount: number; target_date: string | null; color_slot: number };

export type Goal = GoalInput & {
  id: number;
  saved: number;
  percent: number;
  remaining: number;
  months_left: number | null;
  monthly_needed: number | null;
};

export type Contribution = { id: number; goal_id: number; date: string; amount: number; note: string };

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
