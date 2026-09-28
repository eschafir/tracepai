"use client";

import { useState } from "react";
import { api, ApiError, SharedExpense, Wallet } from "@/lib/api";
import { iso, money, shortDate } from "@/lib/format";

type Share = SharedExpense["shares"][number];

/**
 * Whether one person paid back their share of a shared expense, as the payer or that person sees it. Either of them
 * can mark it paid, optionally recording the money in one of their wallets, record it later, or undo it.
 */
export default function ShareStatus({
  expense,
  share,
  myId,
  wallets,
  onChange,
}: {
  expense: SharedExpense;
  share: Share;
  myId: number;
  wallets: Wallet[];
  onChange: (updated: SharedExpense) => void;
}) {
  const [form, setForm] = useState<{ date: string; wallet: string; recordOnly: boolean } | null>(null);
  const [error, setError] = useState("");
  const mine = share.user_id === myId;
  const payer = expense.paid_by.username;
  const amount = money(share.amount, expense.currency);
  const sameCurrency = wallets.filter((w) => w.currency === expense.currency);
  const payment = share.payment;

  async function run(path: string, method: string, json?: object) {
    setError("");
    try {
      onChange(await api<SharedExpense>(path, { method, json }));
      setForm(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "That didn't work. Check that TracepAI is running.");
    }
  }

  return (
    <div className="text-xs">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        {payment ? (
          <span className="text-up">
            {mine ? `You paid ${payer} back ${amount}` : `${share.username} paid you back ${amount}`}, {shortDate(payment.date)}
          </span>
        ) : (
          <span className={mine ? "text-critical" : "text-ink"}>{mine ? `You owe ${payer} ${amount}` : `${share.username} owes you ${amount}`}</span>
        )}
        {share.status !== "accepted" && (
          <span className="text-ink-2">{share.status === "pending" ? `${share.username} hasn't accepted your shared expenses yet` : `${share.username} declined your shared expenses`}</span>
        )}
        {!form && !payment && (
          <button type="button" className="text-accent" onClick={() => setForm({ date: iso(new Date()), wallet: "", recordOnly: false })}>
            Mark paid
          </button>
        )}
        {!form && payment && !payment.recorded_by.includes(myId) && (
          <button type="button" className="text-accent" onClick={() => setForm({ date: payment.date, wallet: String(sameCurrency[0]?.id ?? ""), recordOnly: true })}>
            Record in my wallet
          </button>
        )}
        {!form && payment && (
          <button
            type="button"
            className="text-ink-2 hover:text-critical"
            title="Also removes it from any wallet it was recorded in"
            onClick={() => run(`/shared-expenses/payments/${payment.id}`, "DELETE")}
          >
            Undo
          </button>
        )}
      </div>
      {form && (
        <form
          className="mt-2 flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (form.recordOnly && payment) run(`/shared-expenses/payments/${payment.id}/record`, "POST", { wallet_id: Number(form.wallet) });
            else
              run(`/shared-expenses/${expense.id}/payments`, "POST", {
                user_id: share.user_id,
                date: form.date,
                wallet_id: form.wallet ? Number(form.wallet) : null,
              });
          }}
        >
          {!form.recordOnly && (
            <label className="font-medium">
              Date
              <input className="field mt-1 block py-1" type="date" required value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
            </label>
          )}
          <label className="font-medium">
            {mine ? "Paid from" : "Received in"}
            <select className="field mt-1 block py-1" required={form.recordOnly} value={form.wallet} onChange={(e) => setForm({ ...form, wallet: e.target.value })}>
              {!form.recordOnly && <option value="">Don&apos;t record in a wallet</option>}
              {sameCurrency.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="btn py-1" onClick={() => setForm(null)}>
            Cancel
          </button>
          <button className="btn btn-primary py-1" disabled={form.recordOnly && !sameCurrency.length}>
            {form.recordOnly ? "Record" : "Mark paid"}
          </button>
        </form>
      )}
      {error && (
        <p role="alert" className="mt-1 text-critical">
          {error}
        </p>
      )}
    </div>
  );
}
