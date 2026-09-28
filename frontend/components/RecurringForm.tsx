"use client";

import { useState } from "react";
import { api, Category, Frequency, Kind, RecurringInput, RecurringRule, Wallet } from "@/lib/api";
import { iso } from "@/lib/format";
import ReceivedField from "@/components/ReceivedField";

const KINDS: { value: Kind; label: string }[] = [
  { value: "expense", label: "Expense" },
  { value: "income", label: "Income" },
  { value: "transfer", label: "Transfer" },
];

/** Adds a recurring item, or edits one when `initial` is given. */
// Every missed date is added when the item is saved, so the server allows starting at most 365 days ago.
const yearAgo = () => {
  const d = new Date();
  d.setDate(d.getDate() - 365);
  return iso(d);
};

export default function RecurringForm({
  wallets,
  categories,
  initial,
  onSubmit,
  onCancel,
}: {
  wallets: Wallet[];
  categories: Category[];
  initial?: RecurringRule;
  onSubmit: (rule: RecurringInput) => Promise<void>;
  onCancel?: () => void;
}) {
  const [kind, setKind] = useState<Kind>(initial?.kind ?? "expense");
  const [amount, setAmount] = useState(initial ? String(initial.amount) : "");
  const [merchant, setMerchant] = useState(initial?.merchant ?? "");
  const [walletId, setWalletId] = useState(initial ? String(initial.wallet_id) : "");
  const [toWalletId, setToWalletId] = useState(initial?.to_wallet_id ? String(initial.to_wallet_id) : "");
  const [received, setReceived] = useState(initial?.to_amount ? String(initial.to_amount) : "");
  const [categoryId, setCategoryId] = useState(initial?.category_id ? String(initial.category_id) : "");
  const [frequency, setFrequency] = useState<Frequency>(initial?.frequency ?? "monthly");
  const [nextDate, setNextDate] = useState(initial?.next_date ?? iso(new Date()));

  const isTransfer = kind === "transfer";
  const fromWallet = walletId || String(wallets[0]?.id ?? "");
  const startsNow = nextDate <= iso(new Date());
  const currencyOf = (id: string) => wallets.find((w) => String(w.id) === id)?.currency;
  const currency = currencyOf(fromWallet) ?? "USD";
  const crossCurrency = isTransfer && !!toWalletId && currencyOf(toWalletId) !== currency;

  async function suggestCategory(name: string) {
    if (isTransfer || categoryId || !name.trim()) return;
    const suggestion = await api<{ category_id: number } | null>(
      `/categories/suggest?${new URLSearchParams({ merchant: name, kind })}`,
    );
    if (suggestion) setCategoryId(String(suggestion.category_id));
  }

  return (
    <form
      className="space-y-3"
      onSubmit={async (e) => {
        e.preventDefault();
        await onSubmit({
          kind,
          amount: Number(amount),
          merchant,
          wallet_id: Number(fromWallet),
          to_wallet_id: isTransfer ? Number(toWalletId) : null,
          to_amount: crossCurrency ? Number(received) : null,
          category_id: !isTransfer && categoryId ? Number(categoryId) : null,
          frequency,
          next_date: nextDate,
        });
        if (initial) return;
        setAmount("");
        setMerchant("");
        setCategoryId("");
        setToWalletId("");
        setReceived("");
        setNextDate(iso(new Date()));
      }}
    >
      <div className="grid w-full grid-cols-3 rounded-full bg-panel-sunk p-1 text-sm font-medium sm:w-80">
        {KINDS.map((k) => (
          <button
            key={k.value}
            type="button"
            aria-pressed={kind === k.value}
            onClick={() => {
              if (k.value !== kind) setCategoryId("");
              setKind(k.value);
            }}
            className={`rounded-full py-1.5 ${kind === k.value ? "bg-panel shadow-sm" : "text-ink-2"}`}
          >
            {k.label}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <label className="col-span-2 text-sm font-medium sm:col-span-1">
          {kind === "expense" ? "Merchant" : kind === "income" ? "From" : "Description"}
          <input
            className="field mt-1"
            required={!isTransfer}
            placeholder={kind === "expense" ? "Gym membership" : ""}
            value={merchant}
            onChange={(e) => setMerchant(e.target.value)}
            onBlur={(e) => suggestCategory(e.target.value)}
          />
        </label>
        <label className="text-sm font-medium">
          Amount{currency !== "USD" && ` (${currency})`}
          <input
            className="field mt-1 tnum"
            type="number"
            inputMode="decimal"
            step="0.01"
            min="0.01"
            required
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </label>
        <label className="text-sm font-medium">
          {isTransfer ? "From" : kind === "income" ? "Into" : "Paid with"}
          <select className="field mt-1" value={fromWallet} onChange={(e) => setWalletId(e.target.value)}>
            {wallets.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </label>
        {isTransfer ? (
          <label className="text-sm font-medium">
            To
            <select className="field mt-1" required value={toWalletId} onChange={(e) => setToWalletId(e.target.value)}>
              <option value="">Choose</option>
              {wallets
                .filter((w) => String(w.id) !== fromWallet)
                .map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
            </select>
          </label>
        ) : (
          <label className="text-sm font-medium">
            Category
            <select className="field mt-1" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
              <option value="">Uncategorized</option>
              {categories
                .filter((c) => c.kind === kind)
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
            </select>
          </label>
        )}
        {crossCurrency && (
          <ReceivedField
            className="field mt-1"
            amount={amount}
            from={currency}
            to={currencyOf(toWalletId)}
            date={nextDate}
            value={received}
            onChange={setReceived}
          />
        )}
        <label className="text-sm font-medium">
          Repeats
          <select className="field mt-1" value={frequency} onChange={(e) => setFrequency(e.target.value as Frequency)}>
            <option value="weekly">Every week</option>
            <option value="monthly">Every month</option>
            <option value="yearly">Every year</option>
          </select>
        </label>
        <label className="text-sm font-medium">
          {initial ? "Next date" : "First date"}
          <input className="field mt-1" type="date" required min={yearAgo()} value={nextDate} onChange={(e) => setNextDate(e.target.value)} />
        </label>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-2">
          {initial
            ? startsNow
              ? "The next date is today or earlier, so it is added to your transactions when you save."
              : "Changes apply from the next date. Transactions already added stay as they are."
            : startsNow
              ? "The first date is today or earlier, so it is added to your transactions right away."
              : "It is added to your transactions on the first date, then keeps repeating."}
        </p>
        <span className="flex gap-2">
          {onCancel && (
            <button type="button" className="btn" onClick={onCancel}>
              Cancel
            </button>
          )}
          <button className="btn btn-primary">{initial ? "Save changes" : "Add recurring"}</button>
        </span>
      </div>
    </form>
  );
}
