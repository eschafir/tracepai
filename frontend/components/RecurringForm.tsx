"use client";

import { useState } from "react";
import { api, Category, Frequency, Kind, RecurringInput, Wallet } from "@/lib/api";
import { iso } from "@/lib/format";

const KINDS: { value: Kind; label: string }[] = [
  { value: "expense", label: "Expense" },
  { value: "income", label: "Income" },
  { value: "transfer", label: "Transfer" },
];

export default function RecurringForm({
  wallets,
  categories,
  onSubmit,
}: {
  wallets: Wallet[];
  categories: Category[];
  onSubmit: (rule: RecurringInput) => Promise<void>;
}) {
  const [kind, setKind] = useState<Kind>("expense");
  const [amount, setAmount] = useState("");
  const [merchant, setMerchant] = useState("");
  const [walletId, setWalletId] = useState("");
  const [toWalletId, setToWalletId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [frequency, setFrequency] = useState<Frequency>("monthly");
  const [nextDate, setNextDate] = useState(iso(new Date()));

  const isTransfer = kind === "transfer";
  const fromWallet = walletId || String(wallets[0]?.id ?? "");
  const startsNow = nextDate <= iso(new Date());

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
          category_id: !isTransfer && categoryId ? Number(categoryId) : null,
          frequency,
          next_date: nextDate,
        });
        setAmount("");
        setMerchant("");
        setCategoryId("");
        setToWalletId("");
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
              setKind(k.value);
              setCategoryId("");
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
          Amount
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
        <label className="text-sm font-medium">
          Repeats
          <select className="field mt-1" value={frequency} onChange={(e) => setFrequency(e.target.value as Frequency)}>
            <option value="weekly">Every week</option>
            <option value="monthly">Every month</option>
            <option value="yearly">Every year</option>
          </select>
        </label>
        <label className="text-sm font-medium">
          First date
          <input className="field mt-1" type="date" required value={nextDate} onChange={(e) => setNextDate(e.target.value)} />
        </label>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-2">
          {startsNow
            ? "The first date is today or earlier, so it is added to your transactions right away."
            : "It is added to your transactions on the first date, then keeps repeating."}
        </p>
        <button className="btn btn-primary">Add recurring</button>
      </div>
    </form>
  );
}
