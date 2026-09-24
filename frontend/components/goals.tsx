import { Goal } from "@/lib/api";
import { iso, money, parseIso, slotColor } from "@/lib/format";

const monthYear = (d: string) => parseIso(d).toLocaleDateString("en-US", { month: "short", year: "numeric" });

export function goalStatus(g: Goal) {
  if (g.remaining <= 0) return g.saved > g.target_amount ? `Reached, ${money(g.saved - g.target_amount)} over the target.` : "Reached.";
  if (g.target_date && g.target_date < iso(new Date())) return `The date has passed. ${money(g.remaining)} to go.`;
  if (g.monthly_needed && g.target_date) return `Save ${money(g.monthly_needed)} a month to reach it by ${monthYear(g.target_date)}.`;
  return `${money(g.remaining)} to go.`;
}

export function GoalBar({ goal }: { goal: Goal }) {
  return (
    <div
      className="h-3 overflow-hidden rounded-full bg-panel-sunk"
      role="progressbar"
      aria-label={`${goal.name} progress`}
      aria-valuenow={Math.round(goal.percent)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className="h-full rounded-full" style={{ width: `${Math.min(goal.percent, 100)}%`, background: slotColor(goal.color_slot) }} />
    </div>
  );
}

export function GoalsPanel({ goals }: { goals: Goal[] }) {
  if (!goals.length) {
    return (
      <p className="py-6 text-center text-sm text-ink-2">
        No goals yet. <a className="text-accent underline" href="/goals/">Add a savings goal</a>.
      </p>
    );
  }
  return (
    <ul className="space-y-4 text-sm">
      {goals.map((g) => (
        <li key={g.id}>
          <div className="mb-1.5 flex items-baseline gap-2">
            <span className="font-medium">{g.name}</span>
            <span className="ml-auto tnum text-ink-2">
              {money(g.saved)} of {money(g.target_amount)}
            </span>
          </div>
          <GoalBar goal={g} />
          <p className="mt-1 text-xs text-ink-2">{goalStatus(g)}</p>
        </li>
      ))}
    </ul>
  );
}
