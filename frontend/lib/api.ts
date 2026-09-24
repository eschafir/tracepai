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
  merchant: string;
  date: string | null;
  amount: number | null;
  receipt_path: string;
  raw_text: string;
};

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
