"use client";

import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { BudgetBars, BudgetStatus, Panel } from "@/components/charts";
import { api, ApiError, Budget, Category, Kind } from "@/lib/api";
import { slotColor } from "@/lib/format";

export default function BudgetsPage() {
  const [status, setStatus] = useState<BudgetStatus[]>([]);
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [limits, setLimits] = useState<Record<number, string>>({});
  const [newBudget, setNewBudget] = useState({ category_id: "", monthly_limit: "" });
  const [newCategory, setNewCategory] = useState({ name: "", kind: "expense" as Kind, color_slot: 1 });
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [s, b, c] = await Promise.all([
      api<BudgetStatus[]>("/analytics/budgets"),
      api<Budget[]>("/budgets"),
      api<Category[]>("/categories"),
    ]);
    setStatus(s);
    setBudgets(b);
    setCategories(c);
    setLimits(Object.fromEntries(b.map((x) => [x.id, String(x.monthly_limit)])));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function run(action: () => Promise<unknown>) {
    setError("");
    try {
      await action();
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The change was not saved. Check that TracepAI is running.");
    }
  }

  const byId = new Map(categories.map((c) => [c.id, c]));
  const unbudgeted = categories.filter((c) => c.kind === "expense" && !budgets.some((b) => b.category_id === c.id));

  return (
    <Shell>
      <h1 className="mb-4 font-display text-3xl font-bold tracking-tight">Budgets</h1>
      {error && (
        <p role="alert" className="mb-4 text-sm text-critical">
          {error}
        </p>
      )}
      <div className="space-y-4">
        <Panel title="This month">
          <BudgetBars rows={status} />
        </Panel>

        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Monthly limits">
            <ul className="divide-y divide-line">
              {budgets.map((b) => {
                const category = byId.get(b.category_id);
                const changed = limits[b.id] !== String(b.monthly_limit);
                return (
                  <li key={b.id} className="flex items-center gap-3 py-2.5 text-sm">
                    <span className="h-2.5 w-2.5 rounded-sm" style={{ background: slotColor(category?.color_slot) }} />
                    <span className="mr-auto">{category?.name ?? "Uncategorized"}</span>
                    <label className="flex items-center gap-1">
                      <span className="text-ink-2">$</span>
                      <input
                        className="field w-24 py-1 tnum"
                        aria-label={`${category?.name} monthly limit`}
                        type="number"
                        min="1"
                        step="1"
                        value={limits[b.id] ?? ""}
                        onChange={(e) => setLimits({ ...limits, [b.id]: e.target.value })}
                      />
                    </label>
                    {changed && (
                      <button
                        className="font-medium text-accent"
                        onClick={() =>
                          run(() =>
                            api(`/budgets/${b.id}`, {
                              method: "PUT",
                              json: { category_id: b.category_id, monthly_limit: Number(limits[b.id]) },
                            }),
                          )
                        }
                      >
                        Save
                      </button>
                    )}
                    <button
                      className="text-ink-2 hover:text-critical"
                      onClick={() => run(() => api(`/budgets/${b.id}`, { method: "DELETE" }))}
                    >
                      Remove
                    </button>
                  </li>
                );
              })}
            </ul>
            {unbudgeted.length > 0 && (
              <form
                className="mt-4 flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  run(async () => {
                    await api("/budgets", {
                      method: "POST",
                      json: { category_id: Number(newBudget.category_id), monthly_limit: Number(newBudget.monthly_limit) },
                    });
                    setNewBudget({ category_id: "", monthly_limit: "" });
                  });
                }}
              >
                <select
                  className="field"
                  aria-label="Category"
                  required
                  value={newBudget.category_id}
                  onChange={(e) => setNewBudget({ ...newBudget, category_id: e.target.value })}
                >
                  <option value="">Choose a category</option>
                  {unbudgeted.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
                <input
                  className="field w-28 tnum"
                  aria-label="Monthly limit"
                  placeholder="Limit"
                  type="number"
                  min="1"
                  required
                  value={newBudget.monthly_limit}
                  onChange={(e) => setNewBudget({ ...newBudget, monthly_limit: e.target.value })}
                />
                <button className="btn btn-primary shrink-0">Add budget</button>
              </form>
            )}
          </Panel>

          <Panel title="Categories">
            <ul className="mb-4 flex flex-wrap gap-2 text-sm">
              {categories.map((c) => (
                <li key={c.id} className="flex items-center gap-1.5 rounded-full bg-panel-sunk py-1 pr-1 pl-3">
                  <span className="h-2.5 w-2.5 rounded-sm" style={{ background: slotColor(c.color_slot) }} />
                  {c.name}
                  <span className="text-xs text-ink-2">{c.kind === "income" ? "income" : ""}</span>
                  <button
                    aria-label={`Delete ${c.name}`}
                    className="rounded-full px-2 text-ink-2 hover:text-critical"
                    onClick={() => run(() => api(`/categories/${c.id}`, { method: "DELETE" }))}
                  >
                    &times;
                  </button>
                </li>
              ))}
            </ul>
            <form
              className="flex flex-wrap items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                run(async () => {
                  await api("/categories", { method: "POST", json: newCategory });
                  setNewCategory({ ...newCategory, name: "" });
                });
              }}
            >
              <input
                className="field min-w-0 flex-1"
                aria-label="Category name"
                placeholder="New category"
                required
                value={newCategory.name}
                onChange={(e) => setNewCategory({ ...newCategory, name: e.target.value })}
              />
              <select
                className="field w-auto"
                aria-label="Type"
                value={newCategory.kind}
                onChange={(e) => setNewCategory({ ...newCategory, kind: e.target.value as Kind })}
              >
                <option value="expense">Expense</option>
                <option value="income">Income</option>
              </select>
              <fieldset className="flex gap-1" aria-label="Color">
                {[1, 2, 3, 4, 5, 6, 7, 8].map((slot) => (
                  <button
                    key={slot}
                    type="button"
                    aria-label={`Color ${slot}`}
                    aria-pressed={newCategory.color_slot === slot}
                    onClick={() => setNewCategory({ ...newCategory, color_slot: slot })}
                    className={`h-6 w-6 rounded-full ${newCategory.color_slot === slot ? "ring-2 ring-ink ring-offset-2 ring-offset-panel" : ""}`}
                    style={{ background: slotColor(slot) }}
                  />
                ))}
              </fieldset>
              <button className="btn btn-primary">Add category</button>
            </form>
          </Panel>
        </div>
      </div>
    </Shell>
  );
}
