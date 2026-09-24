"use client";

import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { GoalBar, goalStatus } from "@/components/goals";
import { api, ApiError, Contribution, Goal, GoalInput } from "@/lib/api";
import { iso, money, shortDate, slotColor } from "@/lib/format";

type Draft = { name: string; target_amount: string; target_date: string; color_slot: number };

function GoalForm({ initial, submitLabel, onSubmit, onCancel }: {
  initial: Draft;
  submitLabel: string;
  onSubmit: (goal: GoalInput) => Promise<void>;
  onCancel?: () => void;
}) {
  const [draft, setDraft] = useState(initial);
  return (
    <form
      className="grid gap-3 sm:grid-cols-[1fr_9rem_11rem]"
      onSubmit={async (e) => {
        e.preventDefault();
        await onSubmit({
          name: draft.name,
          target_amount: Number(draft.target_amount),
          target_date: draft.target_date || null,
          color_slot: draft.color_slot,
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

function GoalCard({ goal, run }: { goal: Goal; run: (action: () => Promise<unknown>) => Promise<boolean> }) {
  const [mode, setMode] = useState<"add" | "take" | null>(null);
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [history, setHistory] = useState<Contribution[] | null>(null);
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const loadHistory = () => api<Contribution[]>(`/goals/${goal.id}/contributions`).then(setHistory);

  if (editing) {
    return (
      <li className="rounded-2xl bg-panel p-5">
        <GoalForm
          initial={{ ...goal, target_amount: String(goal.target_amount), target_date: goal.target_date ?? "" }}
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
          <span className="font-display text-2xl font-semibold">{money(goal.saved)}</span>
          <span className="text-ink-2"> of {money(goal.target_amount)}</span>
        </p>
      </div>
      <GoalBar goal={goal} />
      <p className="mt-2 text-sm text-ink-2">
        {Math.round(goal.percent)}% saved. {goalStatus(goal)}
      </p>

      {mode ? (
        <form
          className="mt-4 flex flex-wrap items-end gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            const value = Number(amount) * (mode === "take" ? -1 : 1);
            const ok = await run(() =>
              api(`/goals/${goal.id}/contributions`, { method: "POST", json: { date: iso(new Date()), amount: value, note } }),
            );
            if (ok) {
              setMode(null);
              setAmount("");
              setNote("");
              if (history) loadHistory();
            }
          }}
        >
          <label className="text-sm font-medium">
            {mode === "add" ? "Add" : "Take out"}
            <input
              className="field mt-1 w-32 tnum"
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
          <label className="min-w-40 flex-1 text-sm font-medium">
            Note (optional)
            <input className="field mt-1" value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <button type="button" className="btn" onClick={() => setMode(null)}>
            Cancel
          </button>
          <button className="btn btn-primary">{mode === "add" ? "Add money" : "Take out"}</button>
        </form>
      ) : (
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <button className="btn btn-primary" onClick={() => setMode("add")}>
            Add money
          </button>
          <button className="btn" onClick={() => setMode("take")} disabled={goal.saved <= 0}>
            Take out
          </button>
          <button className="text-accent" aria-expanded={!!history} onClick={() => (history ? setHistory(null) : loadHistory())}>
            {history ? "Hide history" : "History"}
          </button>
          <button className="text-accent" onClick={() => setEditing(true)}>
            Edit
          </button>
          {confirmDelete ? (
            <span className="flex gap-3">
              <button className="font-medium text-critical" onClick={() => run(() => api(`/goals/${goal.id}`, { method: "DELETE" }))}>
                Delete goal and its history
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
              <span className="mr-auto truncate">{c.note || (c.amount > 0 ? "Added" : "Taken out")}</span>
              <span className={`tnum ${c.amount > 0 ? "text-up" : ""}`}>
                {c.amount > 0 ? "+" : "−"}
                {money(Math.abs(c.amount))}
              </span>
              <button
                className="text-ink-2 hover:text-critical"
                aria-label={`Remove ${money(Math.abs(c.amount))} from ${shortDate(c.date)}`}
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
  const [error, setError] = useState("");

  const load = useCallback(async () => setGoals(await api<Goal[]>("/goals")), []);

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
            <GoalCard key={g.id} goal={g} run={run} />
          ))}
        </ul>
      )}
      <section className="rounded-2xl bg-panel p-5">
        <h2 className="mb-4 font-display text-lg font-semibold">Add a goal</h2>
        <GoalForm
          key={goals?.length}
          initial={{ name: "", target_amount: "", target_date: "", color_slot: 3 }}
          submitLabel="Add goal"
          onSubmit={async (g) => {
            await run(() => api("/goals", { method: "POST", json: g }));
          }}
        />
      </section>
    </Shell>
  );
}
