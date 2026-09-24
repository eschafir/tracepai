"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError, Category, Frequency, Kind, ReceiptScan, Transaction, TransactionInput, Wallet } from "@/lib/api";
import { iso, money } from "@/lib/format";

const KINDS: { value: Kind; label: string }[] = [
  { value: "expense", label: "Expense" },
  { value: "income", label: "Income" },
  { value: "transfer", label: "Transfer" },
];

type SplitRow = { category_id: string; amount: string };

export default function TransactionModal({
  categories,
  wallets,
  initial,
  onClose,
  onSaved,
}: {
  categories: Category[];
  wallets: Wallet[];
  initial?: Transaction;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [kind, setKind] = useState<Kind>(initial?.kind ?? "expense");
  const [amount, setAmount] = useState(initial ? String(initial.amount) : "");
  const [categoryId, setCategoryId] = useState(initial?.category_id ? String(initial.category_id) : "");
  const [walletId, setWalletId] = useState(String(initial?.wallet_id ?? wallets[0]?.id ?? ""));
  const [toWalletId, setToWalletId] = useState(initial?.to_wallet_id ? String(initial.to_wallet_id) : "");
  const [repeat, setRepeat] = useState<Frequency | "">("");
  const [hint, setHint] = useState("");
  const [date, setDate] = useState(initial?.date ?? iso(new Date()));
  const [merchant, setMerchant] = useState(initial?.merchant ?? "");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [tags, setTags] = useState(initial?.tags ?? "");
  const [receiptPath, setReceiptPath] = useState(initial?.receipt_path ?? null);
  const [splits, setSplits] = useState<SplitRow[]>(
    initial?.splits.map((s) => ({ category_id: String(s.category_id), amount: String(s.amount) })) ?? [],
  );
  const [showDetails, setShowDetails] = useState(Boolean(initial && (initial.notes || initial.tags || initial.splits.length)));
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const options = categories.filter((c) => c.kind === kind);
  const isTransfer = kind === "transfer";

  async function suggestCategory(name: string) {
    if (isTransfer || categoryId || splits.length || !name.trim()) return;
    const params = new URLSearchParams({ merchant: name, kind });
    const suggestion = await api<{ category_id: number; source: string } | null>(`/categories/suggest?${params}`);
    if (suggestion) {
      setCategoryId(String(suggestion.category_id));
      setHint(suggestion.source === "history" ? "Category from your past transactions" : "Category guessed from the name");
    }
  }
  const splitTotal = splits.reduce((s, r) => s + (Number(r.amount) || 0), 0);
  const splitMismatch = splits.length > 0 && Math.abs(splitTotal - Number(amount)) > 0.005;

  async function scanReceipt(file: File) {
    setBusy(true);
    setError("");
    setStatus("Reading receipt");
    const form = new FormData();
    form.append("file", file);
    try {
      const scan = await api<ReceiptScan>("/receipts/scan", { method: "POST", body: form });
      setReceiptPath(scan.receipt_path);
      if (scan.amount) setAmount(String(scan.amount));
      if (scan.date) setDate(scan.date);
      if (scan.merchant) {
        setMerchant(scan.merchant);
        suggestCategory(scan.merchant);
      }
      setKind("expense");
      setStatus(
        scan.amount
          ? "Receipt read. Check the amount, date and merchant before saving."
          : "Receipt attached, but no total was found. Enter the amount yourself.",
      );
    } catch (err) {
      setStatus("");
      setError(err instanceof ApiError ? err.message : "The receipt could not be read. Try a sharper photo.");
    } finally {
      setBusy(false);
    }
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const body: TransactionInput = {
      date,
      amount: Number(amount),
      kind,
      merchant,
      wallet_id: Number(walletId),
      to_wallet_id: isTransfer ? Number(toWalletId) : null,
      category_id: isTransfer || splits.length ? null : categoryId ? Number(categoryId) : null,
      notes,
      tags: tags
        .split(/[\s,]+/)
        .map((t) => t.replace(/^#/, ""))
        .filter(Boolean)
        .join(","),
      receipt_path: receiptPath,
      splits: isTransfer ? [] : splits.map((s) => ({ category_id: Number(s.category_id), amount: Number(s.amount) })),
      repeat: repeat || null,
    };
    try {
      await api(initial ? `/transactions/${initial.id}` : "/transactions", {
        method: initial ? "PUT" : "POST",
        json: body,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Saving failed. Check that TracepAI is running.");
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center" onClick={onClose}>
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="txn-title"
        onSubmit={save}
        onClick={(e) => e.stopPropagation()}
        className="max-h-[92vh] w-full overflow-y-auto rounded-t-3xl bg-panel p-6 sm:max-w-md sm:rounded-3xl"
      >
        <div className="mb-5 flex items-center justify-between">
          <h2 id="txn-title" className="font-display text-xl font-semibold">
            {initial ? "Edit transaction" : "Add transaction"}
          </h2>
          <button type="button" onClick={onClose} className="text-sm text-ink-2 hover:text-ink">
            Cancel
          </button>
        </div>

        <div className="mb-4 grid grid-cols-3 rounded-full bg-panel-sunk p-1 text-sm font-medium">
          {KINDS.map((k) => (
            <button
              key={k.value}
              type="button"
              aria-pressed={kind === k.value}
              onClick={() => {
                setKind(k.value);
                setCategoryId("");
                setSplits([]);
                setHint("");
              }}
              className={`rounded-full py-1.5 ${kind === k.value ? "bg-panel shadow-sm" : "text-ink-2"}`}
            >
              {k.label}
            </button>
          ))}
        </div>

        <label className="block text-sm font-medium">
          Amount
          <div className="mt-1.5 flex items-center gap-2 border-b-2 border-accent pb-1">
            <span className="font-display text-3xl text-ink-2">$</span>
            <input
              className="w-full bg-transparent font-display text-4xl font-semibold tnum outline-none"
              inputMode="decimal"
              type="number"
              step="0.01"
              min="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
              autoFocus
              placeholder="0.00"
            />
          </div>
        </label>

        <div className="mt-4 grid grid-cols-2 gap-3">
          {isTransfer ? (
            <label className="block text-sm font-medium">
              To
              <select className="field mt-1.5" value={toWalletId} onChange={(e) => setToWalletId(e.target.value)} required>
                <option value="">Choose</option>
                {wallets
                  .filter((w) => String(w.id) !== walletId)
                  .map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
              </select>
            </label>
          ) : (
            <label className="block text-sm font-medium">
              Category
              <select
                className="field mt-1.5"
                value={categoryId}
                onChange={(e) => {
                  setCategoryId(e.target.value);
                  setHint("");
                }}
                disabled={splits.length > 0}
              >
                <option value="">{splits.length ? "Split" : "Uncategorized"}</option>
                {options.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="block text-sm font-medium">
            {isTransfer ? "From" : kind === "income" ? "Into" : "Paid with"}
            <select className="field mt-1.5" value={walletId} onChange={(e) => setWalletId(e.target.value)} required>
              {wallets.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </label>
          {hint && <p className="col-span-2 -mt-1 text-xs text-ink-2">{hint}</p>}
          <label className="block text-sm font-medium">
            Date
            <input className="field mt-1.5" type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
          </label>
          <label className="block text-sm font-medium">
            {kind === "expense" ? "Merchant" : kind === "income" ? "From" : "Description"}
            <input
              className="field mt-1.5"
              value={merchant}
              onChange={(e) => setMerchant(e.target.value)}
              onBlur={(e) => suggestCategory(e.target.value)}
            />
          </label>
        </div>

        {kind === "expense" && (
          <div className="mt-4">
            <input
              ref={fileInput}
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && scanReceipt(e.target.files[0])}
            />
            <button type="button" className="btn w-full" onClick={() => fileInput.current?.click()} disabled={busy}>
              {receiptPath ? "Scan a different receipt" : "Scan receipt"}
            </button>
            {receiptPath && (
              <a
                href={`/api/receipts/${receiptPath}`}
                target="_blank"
                rel="noreferrer"
                className="mt-2 block text-center text-sm text-accent underline"
              >
                View attached receipt
              </a>
            )}
          </div>
        )}
        {status && (
          <p role="status" className="mt-3 text-sm text-ink-2">
            {status}
          </p>
        )}

        <button
          type="button"
          className="mt-5 text-sm font-medium text-accent"
          aria-expanded={showDetails}
          onClick={() => setShowDetails(!showDetails)}
        >
          {showDetails ? "Hide notes, tags and more" : "Add notes, tags, splits or repeat"}
        </button>

        {showDetails && (
          <div className="mt-3 space-y-3">
            <label className="block text-sm font-medium">
              Notes
              <textarea className="field mt-1.5" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
            </label>
            <label className="block text-sm font-medium">
              Tags
              <input
                className="field mt-1.5"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="vacation, workReimbursable"
              />
            </label>
            {!initial && (
              <label className="block text-sm font-medium">
                Repeat
                <select className="field mt-1.5" value={repeat} onChange={(e) => setRepeat(e.target.value as Frequency | "")}>
                  <option value="">Never</option>
                  <option value="weekly">Every week</option>
                  <option value="monthly">Every month</option>
                  <option value="yearly">Every year</option>
                </select>
              </label>
            )}
            {kind === "expense" && (
              <fieldset>
                <legend className="text-sm font-medium">Split across categories</legend>
                {splits.map((s, i) => (
                  <div key={i} className="mt-2 flex gap-2">
                    <select
                      className="field"
                      aria-label={`Split ${i + 1} category`}
                      value={s.category_id}
                      required
                      onChange={(e) => setSplits(splits.map((r, j) => (j === i ? { ...r, category_id: e.target.value } : r)))}
                    >
                      <option value="">Choose</option>
                      {options.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                    <input
                      className="field w-28 tnum"
                      aria-label={`Split ${i + 1} amount`}
                      type="number"
                      step="0.01"
                      min="0.01"
                      required
                      value={s.amount}
                      onChange={(e) => setSplits(splits.map((r, j) => (j === i ? { ...r, amount: e.target.value } : r)))}
                    />
                    <button
                      type="button"
                      aria-label={`Remove split ${i + 1}`}
                      className="px-2 text-ink-2 hover:text-critical"
                      onClick={() => setSplits(splits.filter((_, j) => j !== i))}
                    >
                      &times;
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  className="mt-2 text-sm text-accent"
                  onClick={() =>
                    setSplits([
                      ...splits,
                      { category_id: splits.length ? "" : categoryId, amount: splits.length ? "" : amount },
                    ])
                  }
                >
                  Add a split
                </button>
                {splitMismatch && (
                  <p className="mt-1 text-sm text-critical">
                    Splits add up to {money(splitTotal)}. They need to match the amount, {money(Number(amount) || 0)}.
                  </p>
                )}
              </fieldset>
            )}
          </div>
        )}

        {error && (
          <p role="alert" className="mt-4 text-sm text-critical">
            {error}
          </p>
        )}
        <button className="btn btn-primary mt-6 w-full py-2.5" disabled={busy || splitMismatch}>
          {initial ? "Save changes" : "Add transaction"}
        </button>
      </form>
    </div>
  );
}
