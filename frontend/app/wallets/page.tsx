"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, ApiError, Wallet, WalletKind } from "@/lib/api";
import { money, slotColor } from "@/lib/format";

const KINDS: { value: WalletKind; label: string }[] = [
  { value: "bank", label: "Bank account" },
  { value: "card", label: "Credit card" },
  { value: "cash", label: "Cash" },
  { value: "savings", label: "Savings" },
];

type Draft = { name: string; kind: WalletKind; color_slot: number; opening_balance: string };

const empty: Draft = { name: "", kind: "bank", color_slot: 1, opening_balance: "0" };

function WalletForm({ initial, submitLabel, onSubmit, onCancel }: {
  initial: Draft;
  submitLabel: string;
  onSubmit: (draft: Draft) => Promise<void>;
  onCancel?: () => void;
}) {
  const [draft, setDraft] = useState(initial);
  return (
    <form
      className="grid gap-3 sm:grid-cols-[1fr_auto_auto]"
      onSubmit={async (e) => {
        e.preventDefault();
        await onSubmit(draft);
      }}
    >
      <label className="text-sm font-medium">
        Name
        <input className="field mt-1" required value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
      </label>
      <label className="text-sm font-medium">
        Type
        <select className="field mt-1" value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value as WalletKind })}>
          {KINDS.map((k) => (
            <option key={k.value} value={k.value}>
              {k.label}
            </option>
          ))}
        </select>
      </label>
      <label className="text-sm font-medium">
        Starting balance
        <input
          className="field mt-1 block tnum sm:w-36"
          type="number"
          step="0.01"
          required
          value={draft.opening_balance}
          onChange={(e) => setDraft({ ...draft, opening_balance: e.target.value })}
        />
      </label>
      <div className="flex flex-wrap items-center gap-3 sm:col-span-3">
        <fieldset className="flex gap-1" aria-label="Color">
          {[1, 2, 3, 4, 5, 6, 7, 8].map((slot) => (
            <button
              key={slot}
              type="button"
              aria-label={`Color ${slot}`}
              aria-pressed={draft.color_slot === slot}
              onClick={() => setDraft({ ...draft, color_slot: slot })}
              className={`h-6 w-6 rounded-full ${draft.color_slot === slot ? "ring-2 ring-ink ring-offset-2 ring-offset-panel" : ""}`}
              style={{ background: slotColor(slot) }}
            />
          ))}
        </fieldset>
        <span className="ml-auto flex gap-2">
          {onCancel && (
            <button type="button" className="btn" onClick={onCancel}>
              Cancel
            </button>
          )}
          <button className="btn btn-primary">{submitLabel}</button>
        </span>
      </div>
    </form>
  );
}

export default function WalletsPage() {
  const [wallets, setWallets] = useState<Wallet[] | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => setWallets(await api<Wallet[]>("/wallets")), []);

  useEffect(() => {
    load();
  }, [load]);

  async function run(action: () => Promise<unknown>) {
    setError("");
    try {
      await action();
      setEditing(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The change was not saved. Check that TracepAI is running.");
    }
  }

  const body = (d: Draft) => ({ ...d, opening_balance: Number(d.opening_balance) });
  const total = wallets?.reduce((s, w) => s + w.balance, 0) ?? 0;

  return (
    <Shell>
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="font-display text-3xl font-bold tracking-tight">Wallets</h1>
        {wallets && <p className="text-ink-2">Total {money(total)}</p>}
      </div>
      {error && (
        <p role="alert" className="mb-4 text-sm text-critical">
          {error}
        </p>
      )}
      {wallets && (
        <ul className="mb-4 divide-y divide-line rounded-2xl bg-panel">
          {wallets.map((w) =>
            editing === w.id ? (
              <li key={w.id} className="p-5">
                <WalletForm
                  initial={{ ...w, opening_balance: String(w.opening_balance) }}
                  submitLabel="Save changes"
                  onCancel={() => setEditing(null)}
                  onSubmit={(d) => run(() => api(`/wallets/${w.id}`, { method: "PUT", json: body(d) }))}
                />
              </li>
            ) : (
              <li key={w.id} className="grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-1 px-5 py-4 sm:grid-cols-[auto_1fr_auto_auto] sm:gap-x-5">
                <span className="h-3 w-3 rounded-full" style={{ background: slotColor(w.color_slot) }} />
                <Link href={`/transactions/?wallet=${w.id}`} className="hover:underline">
                  <span className="block font-medium">{w.name}</span>
                  <span className="block text-sm text-ink-2">{KINDS.find((k) => k.value === w.kind)?.label}</span>
                </Link>
                <span className={`text-right font-display text-xl font-semibold tnum ${w.balance < 0 ? "text-critical" : ""}`}>
                  {money(w.balance)}
                </span>
                <span className="col-start-2 flex gap-3 text-sm sm:col-start-auto">
                  <button className="text-accent" onClick={() => setEditing(w.id)}>
                    Edit
                  </button>
                  <button
                    className="text-ink-2 hover:text-critical"
                    onClick={() => run(() => api(`/wallets/${w.id}`, { method: "DELETE" }))}
                  >
                    Delete
                  </button>
                </span>
              </li>
            ),
          )}
        </ul>
      )}
      <section className="rounded-2xl bg-panel p-5">
        <h2 className="mb-4 font-display text-lg font-semibold">Add a wallet</h2>
        <WalletForm
          key={wallets?.length}
          initial={empty}
          submitLabel="Add wallet"
          onSubmit={(d) => run(() => api("/wallets", { method: "POST", json: body(d) }))}
        />
      </section>
    </Shell>
  );
}
