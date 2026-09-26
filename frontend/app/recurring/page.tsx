"use client";

import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import RecurringForm from "@/components/RecurringForm";
import { Panel } from "@/components/charts";
import { api, ApiError, Category, Frequency, Goal, PriceChange, RecurringRule, RecurringSuggestion, Wallet } from "@/lib/api";
import { money, shortDate } from "@/lib/format";

const FREQUENCIES: Record<Frequency, string> = { weekly: "Every week", monthly: "Every month", yearly: "Every year" };

export default function RecurringPage() {
  const [rules, setRules] = useState<RecurringRule[] | null>(null);
  const [suggestions, setSuggestions] = useState<RecurringSuggestion[]>([]);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [editing, setEditing] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [prices, setPrices] = useState<PriceChange[]>([]);
  const [goals, setGoals] = useState<Goal[]>([]);

  const load = useCallback(async () => {
    const [r, s, w, c, p, g] = await Promise.all([
      api<RecurringRule[]>("/recurring"),
      api<RecurringSuggestion[]>("/recurring/suggestions"),
      api<Wallet[]>("/wallets"),
      api<Category[]>("/categories"),
      api<PriceChange[]>("/recurring/price-changes"),
      api<Goal[]>("/goals"),
    ]);
    setRules(r);
    setPrices(p);
    setGoals(g);
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
    `${r.kind === "income" ? "+" : r.kind === "expense" ? "−" : ""}${money(r.amount, wallets.find((w) => w.id === r.wallet_id)?.currency)}`;

  return (
    <Shell>
      <h1 className="mb-4 font-display text-3xl font-bold tracking-tight">Recurring</h1>
      {error && (
        <p role="alert" className="mb-4 text-sm text-critical">
          {error}
        </p>
      )}
      <div className="space-y-4">
        {prices.length > 0 && (
          <Panel title="Price changes" note="Latest charge differs from the saved amount">
            <ul className="divide-y divide-line">
              {prices.map((p) => {
                const rule = rules?.find((r) => r.id === p.rule_id);
                const currency = wallets.find((w) => w.id === p.wallet_id)?.currency;
                return (
                  <li key={p.rule_id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3 text-sm">
                    <span className="mr-auto">
                      <span className="font-medium">{p.merchant}</span>
                      <span className="block text-ink-2">
                        Charged {money(p.new, currency)} on {shortDate(p.date)}; this item says {money(p.old, currency)}.
                      </span>
                    </span>
                    <span className="flex gap-2">
                      <button
                        className="btn btn-primary"
                        disabled={!rule}
                        onClick={() => rule && run(() => api(`/recurring/${p.rule_id}`, { method: "PUT", json: { ...rule, amount: p.new } }))}
                      >
                        Update to {money(p.new, currency)}
                      </button>
                      <button
                        className="btn"
                        onClick={() => run(() => api(`/recurring/${p.rule_id}/keep-price`, { method: "POST", json: { amount: p.new } }))}
                      >
                        Keep {money(p.old, currency)}
                      </button>
                    </span>
                  </li>
                );
              })}
            </ul>
          </Panel>
        )}
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
                editing === r.id ? (
                  <li key={r.id} className="py-4">
                    <RecurringForm
                      wallets={wallets}
                      categories={categories}
                      initial={r}
                      onCancel={() => setEditing(null)}
                      onSubmit={(rule) => run(() => api(`/recurring/${r.id}`, { method: "PUT", json: { ...r, ...rule } }))}
                    />
                  </li>
                ) : (
                  <li key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-3 text-sm">
                    <span className="mr-auto">
                      <span className="font-medium">{r.merchant || "Untitled"}</span>
                      <span className="block text-ink-2">
                        {FREQUENCIES[r.frequency]}, {where(r)}
                      </span>
                      {r.goal_id && (
                        <span className="block text-ink-2">Goal: {goals.find((g) => g.id === r.goal_id)?.name}</span>
                      )}
                    </span>
                    <span className="text-right">
                      <span className={`block font-medium tnum ${r.kind === "income" ? "text-up" : ""}`}>{signed(r)}</span>
                      <span className="block text-ink-2">Next {shortDate(r.next_date)}</span>
                    </span>
                    <span className="flex gap-3">
                      <button
                        className="text-accent"
                        onClick={() => setEditing(r.id)}
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
