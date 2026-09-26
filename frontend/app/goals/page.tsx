"use client";

import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { GoalBar, goalStatus } from "@/components/goals";
import ReceivedField from "@/components/ReceivedField";
import { api, ApiError, Contribution, Goal, GoalInput, Wallet } from "@/lib/api";
import { iso, money, shortDate, slotColor } from "@/lib/format";

type Draft = { name: string; target_amount: string; target_date: string; color_slot: number; wallet_id: string };

function GoalForm({ initial, wallets, walletLocked, submitLabel, onSubmit, onCancel }: {
  initial: Draft;
  wallets: Wallet[];
  walletLocked?: boolean;
  submitLabel: string;
  onSubmit: (goal: GoalInput) => Promise<void>;
  onCancel?: () => void;
}) {
  const [draft, setDraft] = useState(initial);
  return (
    <form
      className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_9rem_11rem_12rem]"
      onSubmit={async (e) => {
        e.preventDefault();
        await onSubmit({
          name: draft.name,
          target_amount: Number(draft.target_amount),
          target_date: draft.target_date || null,
          color_slot: draft.color_slot,
          wallet_id: Number(draft.wallet_id),
        });
      }}
    >
      <label className="text-sm font-medium">
        Name
        <input className="field mt-1" required placeholder="Lisbon trip" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
      </label>
      <label className="text-sm font-medium">
        Target
        <input
          className="field mt-1 tnum"
          type="number"
          inputMode="decimal"
          min="0.01"
          step="0.01"
          required
          value={draft.target_amount}
          onChange={(e) => setDraft({ ...draft, target_amount: e.target.value })}
        />
      </label>
      <label className="text-sm font-medium">
        By (optional)
        <input className="field mt-1" type="date" value={draft.target_date} onChange={(e) => setDraft({ ...draft, target_date: e.target.value })} />
      </label>
      <label className="text-sm font-medium">
        Kept in
        <select
          className="field mt-1"
          required
          disabled={walletLocked}
          aria-describedby={walletLocked ? "wallet-locked" : undefined}
          value={draft.wallet_id}
          onChange={(e) => setDraft({ ...draft, wallet_id: e.target.value })}
        >
          <option value="">Choose a wallet</option>
          {wallets.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
        {walletLocked && (
          <span id="wallet-locked" className="mt-1 block text-xs font-normal text-ink-2">
            Money has moved here, so the goal stays in this wallet.
          </span>
        )}
      </label>
      <div className="flex flex-wrap items-center gap-3 sm:col-span-2 lg:col-span-4">
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

function GoalCard({ goal, wallets, run }: { goal: Goal; wallets: Wallet[]; run: (action: () => Promise<unknown>) => Promise<boolean> }) {
  const others = wallets.filter((w) => w.id !== goal.wallet_id);
  const defaultOther = String((others.find((w) => w.kind === "bank") ?? others[0])?.id ?? "");
  const walletName = (id: number | null) => wallets.find((w) => w.id === id)?.name ?? "";
  const [mode, setMode] = useState<"add" | "take" | null>(null);
  const [amount, setAmount] = useState("");
  const [otherWallet, setOtherWallet] = useState("");
  const [repeat, setRepeat] = useState(false);
  const open = (m: "add" | "take", preset?: { amount: number; repeat: boolean }) => {
    setOtherWallet(defaultOther);
    setReceived("");
    setAmount(preset ? String(preset.amount) : "");
    setRepeat(preset?.repeat ?? false);
    setMode(m);
  };
  const [note, setNote] = useState("");
  const [received, setReceived] = useState("");
  const otherCurrency = wallets.find((w) => String(w.id) === otherWallet)?.currency ?? goal.currency;
  // Adding moves money from the other wallet into the goal's; taking out goes the other way.
  const [fromCurrency, toCurrency] = mode === "take" ? [goal.currency, otherCurrency] : [otherCurrency, goal.currency];
  const [history, setHistory] = useState<Contribution[] | null>(null);
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const loadHistory = () => api<Contribution[]>(`/goals/${goal.id}/contributions`).then(setHistory);

  if (editing) {
    return (
      <li className="rounded-2xl bg-panel p-5">
        <GoalForm
          initial={{
            ...goal,
            target_amount: String(goal.target_amount),
            target_date: goal.target_date ?? "",
            wallet_id: goal.wallet_id ? String(goal.wallet_id) : "",
          }}
          wallets={wallets}
          walletLocked={goal.transfer_count > 0}
          submitLabel="Save changes"
          onCancel={() => setEditing(false)}
          onSubmit={async (g) => {
            if (await run(() => api(`/goals/${goal.id}`, { method: "PUT", json: g }))) setEditing(false);
          }}
        />
      </li>
    );
  }

  return (
    <li className="rounded-2xl bg-panel p-5">
      <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="mr-auto flex items-center gap-2 font-display text-xl font-semibold">
          <span className="h-3 w-3 rounded-full" style={{ background: slotColor(goal.color_slot) }} />
          {goal.name}
        </h2>
        <p className="tnum">
          <span className="font-display text-2xl font-semibold">{money(goal.saved, goal.currency)}</span>
          <span className="text-ink-2"> of {money(goal.target_amount, goal.currency)}</span>
        </p>
      </div>
      <GoalBar goal={goal} />
      <p className="mt-2 text-sm text-ink-2">
        {Math.round(goal.percent)}% saved. {goalStatus(goal)}
        {goal.wallet_id && ` Kept in ${walletName(goal.wallet_id)}.`}
        {!mode && goal.wallet_id && goal.monthly_needed && !goal.repeating.length && others.length > 0 && (
          <>
            {" "}
            <button className="text-accent" onClick={() => open("add", { amount: goal.monthly_needed!, repeat: true })}>
              Set up {money(goal.monthly_needed, goal.currency)} monthly
            </button>
          </>
        )}
      </p>
      {goal.repeating.map((r) => (
        <p key={r.rule_id} className="mt-1 flex flex-wrap items-baseline gap-x-3 text-sm text-ink-2">
          <span>
            Adds {money(r.amount, wallets.find((w) => w.id === r.wallet_id)?.currency)} monthly from {walletName(r.wallet_id)}, next on{" "}
            {shortDate(r.next_date)}.
          </span>
          <button
            className="hover:text-critical"
            title="Stops future transfers. Money already added stays."
            onClick={() => run(() => api(`/recurring/${r.rule_id}`, { method: "DELETE" }))}
          >
            Stop
          </button>
        </p>
      ))}

      {mode ? (
        <form
          className="mt-4 flex flex-wrap items-end gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            const ok = await run(() =>
              api(`/goals/${goal.id}/contributions`, {
                method: "POST",
                json: {
                  date: iso(new Date()),
                  amount: Number(amount),
                  direction: mode === "add" ? "in" : "out",
                  wallet_id: Number(otherWallet),
                  note,
                  received: fromCurrency !== toCurrency ? Number(received) : null,
                  repeat: mode === "add" && repeat ? "monthly" : null,
                },
              }),
            );
            if (ok) {
              setMode(null);
              setAmount("");
              setNote("");
              setReceived("");
              if (history) loadHistory();
            }
          }}
        >
          <label className="text-sm font-medium">
            {mode === "add" ? "Add" : "Take out"}
            {fromCurrency !== "USD" && ` (${fromCurrency})`}
            <input
              className="field mt-1 block w-32 tnum"
              type="number"
              inputMode="decimal"
              min="0.01"
              step="0.01"
              required
              autoFocus
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </label>
          <label className="text-sm font-medium">
            {mode === "add" ? "From" : "To"}
            <select className="field mt-1" required value={otherWallet} onChange={(e) => {
                setOtherWallet(e.target.value);
                setReceived("");
              }}
            >
              {others.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </label>
          <ReceivedField
            key={`${mode}-${otherWallet}`}
            className="field mt-1 block w-32"
            amount={amount}
            from={fromCurrency}
            to={toCurrency}
            date={iso(new Date())}
            value={received}
            onChange={setReceived}
          />
          <label className="min-w-40 flex-1 text-sm font-medium">
            Note (optional)
            <input className="field mt-1" value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          {mode === "add" && (
            <label className="flex items-center gap-2 self-center text-sm">
              <input type="checkbox" checked={repeat} onChange={(e) => setRepeat(e.target.checked)} />
              Repeat monthly
            </label>
          )}
          <button type="button" className="btn" onClick={() => setMode(null)}>
            Cancel
          </button>
          <button className="btn btn-primary">{mode === "add" ? "Add money" : "Take out"}</button>
        </form>
      ) : (
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          {goal.wallet_id ? (
            <>
              <button className="btn btn-primary" onClick={() => open("add")} disabled={!others.length}>
                Add money
              </button>
              <button className="btn" onClick={() => open("take")} disabled={goal.saved <= 0 || !others.length}>
                Take out
              </button>
            </>
          ) : (
            <button className="btn btn-primary" onClick={() => setEditing(true)}>
              Choose where this goal&apos;s money is kept
            </button>
          )}
          <button className="text-accent" aria-expanded={!!history} onClick={() => (history ? setHistory(null) : loadHistory())}>
            {history ? "Hide history" : "History"}
          </button>
          <button className="text-accent" onClick={() => setEditing(true)}>
            Edit
          </button>
          {confirmDelete ? (
            <span className="flex gap-3">
              <button className="font-medium text-critical" onClick={() => run(() => api(`/goals/${goal.id}`, { method: "DELETE" }))}>
                Delete goal (its transfers stay in Transactions)
              </button>
              <button className="text-ink-2" onClick={() => setConfirmDelete(false)}>
                Keep
              </button>
            </span>
          ) : (
            <button className="text-ink-2 hover:text-critical" onClick={() => setConfirmDelete(true)}>
              Delete
            </button>
          )}
        </div>
      )}

      {history && (
        <ul className="mt-4 divide-y divide-line border-t border-line text-sm">
          {history.length === 0 && <li className="py-3 text-ink-2">No money added yet.</li>}
          {history.map((c) => (
            <li key={c.id} className="flex items-center gap-3 py-2">
              <span className="w-14 shrink-0 text-ink-2 tnum">{shortDate(c.date)}</span>
              <span className="mr-auto truncate">
                {c.note || (c.amount > 0 ? "Added" : "Taken out")}
                <span className="text-ink-2">
                  {" "}
                  {c.amount > 0 ? "from" : "to"} {walletName(c.wallet_id)}
                </span>
              </span>
              <span className={`tnum ${c.amount > 0 ? "text-up" : ""}`}>
                {c.amount > 0 ? "+" : "−"}
                {money(Math.abs(c.amount), goal.currency)}
              </span>
              <button
                className="text-ink-2 hover:text-critical"
                aria-label={`Remove ${money(Math.abs(c.amount), goal.currency)} from ${shortDate(c.date)} and its transfer`}
                title="Remove, and undo the transfer"
                onClick={async () => {
                  if (await run(() => api(`/goals/contributions/${c.id}`, { method: "DELETE" }))) loadHistory();
                }}
              >
                &times;
              </button>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export default function GoalsPage() {
  const [goals, setGoals] = useState<Goal[] | null>(null);
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [gs, ws] = await Promise.all([api<Goal[]>("/goals"), api<Wallet[]>("/wallets")]);
    setWallets(ws);
    setGoals(gs);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function run(action: () => Promise<unknown>) {
    setError("");
    try {
      await action();
      await load();
      return true;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The change was not saved. Check that TracepAI is running.");
      return false;
    }
  }

  return (
    <Shell>
      <h1 className="mb-4 font-display text-3xl font-bold tracking-tight">Goals</h1>
      {error && (
        <p role="alert" className="mb-4 text-sm text-critical">
          {error}
        </p>
      )}
      {goals && (
        <ul className="mb-4 space-y-4">
          {goals.length === 0 && (
            <li className="rounded-2xl bg-panel p-8 text-center text-ink-2">
              No goals yet. Add one below, like a trip or an emergency fund.
            </li>
          )}
          {goals.map((g) => (
            <GoalCard key={g.id} goal={g} wallets={wallets} run={run} />
          ))}
        </ul>
      )}
      {goals && (
        <section className="rounded-2xl bg-panel p-5">
          <h2 className="mb-4 font-display text-lg font-semibold">Add a goal</h2>
          <GoalForm
            key={goals.length}
            wallets={wallets}
            initial={{
              name: "",
              target_amount: "",
              target_date: "",
              color_slot: 3,
              wallet_id: String(wallets.find((w) => w.kind === "savings")?.id ?? ""),
            }}
            submitLabel="Add goal"
            onSubmit={async (g) => {
              await run(() => api("/goals", { method: "POST", json: g }));
            }}
          />
        </section>
      )}
    </Shell>
  );
}
