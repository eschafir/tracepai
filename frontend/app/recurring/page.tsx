"use client";

import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import RecurringForm from "@/components/RecurringForm";
import { Panel } from "@/components/charts";
import { api, ApiError, Category, Frequency, RecurringRule, RecurringSuggestion, Wallet } from "@/lib/api";
import { money, shortDate } from "@/lib/format";

const FREQUENCIES: Record<Frequency, string> = { weekly: "Every week", monthly: "Every month", yearly: "Every year" };

type Draft = { amount: string; frequency: Frequency; next_date: string };

export default function RecurringPage() {
  const [rules, setRules] = useState<RecurringRule[] | null>(null);
  const [suggestions, setSuggestions] = useState<RecurringSuggestion[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [editing, setEditing] = useState<{ id: number; draft: Draft } | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [r, s, w, c] = await Promise.all([
      api<RecurringRule[]>("/recurring"),
      api<RecurringSuggestion[]>("/recurring/suggestions"),
      api<Wallet[]>("/wallets"),
      api<Category[]>("/categories"),
    ]);
    setRules(r);
    setSuggestions(s);
    setWallets(w);
    setCategories(c);
  }, []);

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

  const walletName = (id: number | null) => wallets.find((w) => w.id === id)?.name ?? "";
  const where = (r: RecurringSuggestion | RecurringRule) =>
    r.kind === "transfer" ? `${walletName(r.wallet_id)} to ${walletName(r.to_wallet_id)}` : walletName(r.wallet_id);
  const signed = (r: RecurringSuggestion | RecurringRule) =>
    `${r.kind === "income" ? "+" : r.kind === "expense" ? "−" : ""}${money(r.amount)}`;

  return (
    <Shell>
      <h1 className="mb-4 font-display text-3xl font-bold tracking-tight">Recurring</h1>
      {error && (
        <p role="alert" className="mb-4 text-sm text-critical">
          {error}
        </p>
      )}
      <div className="space-y-4">
        {suggestions.length > 0 && (
          <Panel title="Looks recurring" note="Found in your history">
            <ul className="divide-y divide-line">
              {suggestions.map((s) => (
                <li key={`${s.wallet_id}-${s.merchant}`} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-3 text-sm">
                  <span className="mr-auto">
                    <span className="font-medium">{s.merchant}</span>
                    <span className="block text-ink-2">
                      {signed(s)} {FREQUENCIES[s.frequency].toLowerCase()}, seen {s.occurrences} times in {where(s)}
                    </span>
                  </span>
                  <button
                    className="btn"
                    onClick={() => run(() => api("/recurring", { method: "POST", json: s }))}
                  >
                    Make recurring
                  </button>
                </li>
              ))}
            </ul>
          </Panel>
        )}

        <Panel title="Scheduled" note="Added automatically on their next date">
          {rules && rules.length === 0 ? (
            <p className="py-6 text-center text-sm text-ink-2">
              Nothing scheduled. Add one below, or accept a suggestion above.
            </p>
          ) : (
            <ul className="divide-y divide-line">
              {rules?.map((r) =>
                editing?.id === r.id ? (
                  <li key={r.id} className="py-3">
                    <form
                      className="flex flex-wrap items-end gap-3 text-sm"
                      onSubmit={(e) => {
                        e.preventDefault();
                        const d = editing.draft;
                        run(() =>
                          api(`/recurring/${r.id}`, {
                            method: "PUT",
                            json: { ...r, amount: Number(d.amount), frequency: d.frequency, next_date: d.next_date },
                          }),
                        );
                      }}
                    >
                      <span className="w-full font-medium">{r.merchant}</span>
                      <label className="font-medium">
                        Amount
                        <input
                          className="field mt-1 w-28 tnum"
                          type="number"
                          step="0.01"
                          min="0.01"
                          required
                          value={editing.draft.amount}
                          onChange={(e) => setEditing({ id: r.id, draft: { ...editing.draft, amount: e.target.value } })}
                        />
                      </label>
                      <label className="font-medium">
                        Repeats
                        <select
                          className="field mt-1"
                          value={editing.draft.frequency}
                          onChange={(e) =>
                            setEditing({ id: r.id, draft: { ...editing.draft, frequency: e.target.value as Frequency } })
                          }
                        >
                          {Object.entries(FREQUENCIES).map(([value, label]) => (
                            <option key={value} value={value}>
                              {label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="font-medium">
                        Next date
                        <input
                          className="field mt-1"
                          type="date"
                          required
                          value={editing.draft.next_date}
                          onChange={(e) => setEditing({ id: r.id, draft: { ...editing.draft, next_date: e.target.value } })}
                        />
                      </label>
                      <span className="ml-auto flex gap-2">
                        <button type="button" className="btn" onClick={() => setEditing(null)}>
                          Cancel
                        </button>
                        <button className="btn btn-primary">Save changes</button>
                      </span>
                    </form>
                  </li>
                ) : (
                  <li key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-3 text-sm">
                    <span className="mr-auto">
                      <span className="font-medium">{r.merchant || "Untitled"}</span>
                      <span className="block text-ink-2">
                        {FREQUENCIES[r.frequency]}, {where(r)}
                      </span>
                    </span>
                    <span className="text-right">
                      <span className={`block font-medium tnum ${r.kind === "income" ? "text-up" : ""}`}>{signed(r)}</span>
                      <span className="block text-ink-2">Next {shortDate(r.next_date)}</span>
                    </span>
                    <span className="flex gap-3">
                      <button
                        className="text-accent"
                        onClick={() =>
                          setEditing({
                            id: r.id,
                            draft: { amount: String(r.amount), frequency: r.frequency, next_date: r.next_date },
                          })
                        }
                      >
                        Edit
                      </button>
                      <button
                        className="text-ink-2 hover:text-critical"
                        title="Stops future entries. Past transactions stay."
                        onClick={() => run(() => api(`/recurring/${r.id}`, { method: "DELETE" }))}
                      >
                        Stop
                      </button>
                    </span>
                  </li>
                ),
              )}
            </ul>
          )}
        </Panel>

        {wallets.length > 0 && (
          <Panel title="Add a recurring item">
            <RecurringForm
              wallets={wallets}
              categories={categories}
              onSubmit={(rule) => run(() => api("/recurring", { method: "POST", json: rule }))}
            />
          </Panel>
        )}
      </div>
    </Shell>
  );
}
